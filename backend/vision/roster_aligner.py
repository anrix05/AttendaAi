"""
backend/vision/roster_aligner.py — Fuzzy Student Roster Alignment
"""
import re
from dataclasses import dataclass
from typing import List, Optional, Dict, Any
from rapidfuzz import fuzz, distance
from backend.config import settings


@dataclass
class ScannedStudentRow:
    sr_no: Optional[int]
    raw_roll_no: str
    raw_name: str
    batch: int = 1


@dataclass
class RosterStudent:
    sr_no: int
    roll_no: str
    name: str
    batch: int = 1


@dataclass
class AlignedStudentRow:
    matched_student: RosterStudent
    original_scan: ScannedStudentRow
    confidence: float
    match_strategy: str  # 'exact_roll', 'fuzzy_name_and_sr', 'roll_edit_distance', 'fuzzy_name'
    needs_review: bool = False


class RosterAligner:
    """
    Aligns imperfect OCR rows from a scanned attendance register to the verified subject roster.
    Uses multi-stage cascade: exact roll -> roll typo repair -> fuzzy name + sr_no -> fallback.
    """

    def __init__(self, confidence_threshold: float = 0.65):
        self.confidence_threshold = confidence_threshold
        self.roll_regex = re.compile(settings.ROLL_NO_REGEX)

    def normalize_roll(self, roll: str) -> str:
        """Fix common OCR digit/letter confusions in VIT roll format."""
        clean = roll.strip().upper().replace(" ", "")
        # Common OCR fixes in prefix (e.g. 24108B or 25108B)
        # If length is 10
        if len(clean) == 10:
            chars = list(clean)
            # Position 0..4 are digits (24108)
            for i in range(5):
                if chars[i] == 'O': chars[i] = '0'
                elif chars[i] == 'I' or chars[i] == 'L': chars[i] = '1'
                elif chars[i] == 'B': chars[i] = '8'
            # Position 5 is letter 'B'
            if chars[5] == '8': chars[5] = 'B'
            # Position 6..9 are digits
            for i in range(6, 10):
                if chars[i] == 'O': chars[i] = '0'
                elif chars[i] == 'I' or chars[i] == 'L': chars[i] = '1'
                elif chars[i] == 'B': chars[i] = '8'
            clean = "".join(chars)
        return clean

    def align(
        self,
        scanned_rows: List[ScannedStudentRow],
        roster: List[RosterStudent],
    ) -> List[AlignedStudentRow]:
        """Align all scanned rows to the master roster."""
        unmatched_roster = {r.roll_no: r for r in roster}
        aligned_results: List[AlignedStudentRow] = []

        # 1. Exact Roll Match
        for s in scanned_rows:
            norm_roll = self.normalize_roll(s.raw_roll_no)
            if norm_roll in unmatched_roster:
                target = unmatched_roster.pop(norm_roll)
                aligned_results.append(AlignedStudentRow(
                    matched_student=target,
                    original_scan=s,
                    confidence=1.0,
                    match_strategy="exact_roll",
                    needs_review=False,
                ))
            else:
                # Store for fuzzy passes
                aligned_results.append(AlignedStudentRow(
                    matched_student=None,  # to fill
                    original_scan=s,
                    confidence=0.0,
                    match_strategy="pending",
                    needs_review=True,
                ))

        # 2. Match Remaining by Roll Edit Distance + Name Similarity
        for idx, item in enumerate(aligned_results):
            if item.matched_student is not None or not unmatched_roster:
                continue

            s = item.original_scan
            norm_roll = self.normalize_roll(s.raw_roll_no)
            best_match = None
            best_score = 0.0
            best_strategy = "fallback"

            for candidate_roll, candidate in unmatched_roster.items():
                # Edit distance on roll
                lev = distance.Levenshtein.distance(norm_roll, candidate_roll)
                name_sim = fuzz.token_sort_ratio(s.raw_name.upper(), candidate.name.upper()) / 100.0

                if lev <= 2:
                    # Roll typo with high probability
                    score = 0.85 + (name_sim * 0.15)
                    if score > best_score:
                        best_score = score
                        best_match = candidate
                        best_strategy = "roll_edit_distance"
                elif s.sr_no == candidate.sr_no and name_sim >= 0.70:
                    # Same row order and very similar name
                    score = 0.80 + (name_sim * 0.15)
                    if score > best_score:
                        best_score = score
                        best_match = candidate
                        best_strategy = "fuzzy_name_and_sr"
                elif name_sim >= 0.85:
                    # Very strong name match
                    score = name_sim
                    if score > best_score:
                        best_score = score
                        best_match = candidate
                        best_strategy = "fuzzy_name"

            if best_match and best_score >= self.confidence_threshold:
                unmatched_roster.pop(best_match.roll_no)
                aligned_results[idx] = AlignedStudentRow(
                    matched_student=best_match,
                    original_scan=s,
                    confidence=round(best_score, 2),
                    match_strategy=best_strategy,
                    needs_review=best_score < 0.80,
                )
            else:
                # If still unmatched and sr_no exists in roster
                fallback_candidate = next((r for r in unmatched_roster.values() if r.sr_no == s.sr_no), None)
                if fallback_candidate:
                    unmatched_roster.pop(fallback_candidate.roll_no)
                    aligned_results[idx] = AlignedStudentRow(
                        matched_student=fallback_candidate,
                        original_scan=s,
                        confidence=0.50,
                        match_strategy="sr_no_fallback",
                        needs_review=True,
                    )

        # Sort aligned rows by student sr_no
        aligned_results.sort(key=lambda x: x.matched_student.sr_no if x.matched_student else 999)
        return aligned_results
