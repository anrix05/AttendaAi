"""
backend/roster.py — Master Roster Management, Roll Normalization & Union Logic
"""
import re
from typing import List, Dict, Optional, Tuple, Set, Any
from pydantic import BaseModel, Field

from backend.config import settings


class RosterStudentItem(BaseModel):
    roll_no: str
    name: str
    batch: int = 1
    sr_no: Optional[int] = None


class PageStudentBatch(BaseModel):
    page_index: int
    students: List[RosterStudentItem]
    first_roll: Optional[str] = None
    last_roll: Optional[str] = None


class PageOrderWarning(BaseModel):
    type: str  # 'gap' | 'overlap' | 'duplicate_in_session'
    message: str
    details: Optional[Dict[str, Any]] = None


def normalize_roll_number(raw_roll: str) -> str:
    """
    Normalizes a VIT roll number:
    - Strips whitespace
    - Normalizes lowercase 'b' to 'B'
    - Repairs common OCR digit/letter confusions (O/0, B/8, I/1)
    - Validates against VIT roll number pattern (^2[45]108[Bb]\\d{4}$)
    """
    clean = str(raw_roll or "").strip().upper()

    # Repair OCR confusions if length is 10
    if len(clean) == 10:
        chars = list(clean)
        # Position 0..4 are digits (e.g. '24108' or '25108')
        for i in range(5):
            if chars[i] == 'O':
                chars[i] = '0'
            elif chars[i] in ('I', 'L'):
                chars[i] = '1'
            elif chars[i] == 'B':
                chars[i] = '8'

        # Position 5 is letter 'B'
        if chars[5] == '8':
            chars[5] = 'B'

        # Position 6..9 are digits (e.g. '0001' or '2001')
        for i in range(6, 10):
            if chars[i] == 'O':
                chars[i] = '0'
            elif chars[i] in ('I', 'L'):
                chars[i] = '1'
            elif chars[i] == 'B':
                chars[i] = '8'

        clean = "".join(chars)

    return clean


def is_valid_vit_roll(roll_no: str) -> bool:
    """Check if roll number satisfies standard VIT pattern: 24108B0001 or 25108B2001."""
    norm = normalize_roll_number(roll_no)
    return bool(re.match(settings.ROLL_NO_REGEX, norm))


class RosterManager:
    """
    Manages union roster across multiple print sheets/pages.
    ROLL NUMBER is the only key (never match on Sr No).
    """

    @staticmethod
    def build_union_roster(
        existing_roster: List[RosterStudentItem],
        new_students: List[RosterStudentItem],
    ) -> Tuple[List[RosterStudentItem], List[RosterStudentItem]]:
        """
        Merge new student rows into master roster by normalized roll number.
        Returns:
            (updated_master_roster_sorted, newly_discovered_students)
        """
        master_dict: Dict[str, RosterStudentItem] = {
            normalize_roll_number(s.roll_no): s for s in existing_roster
        }
        newly_added: List[RosterStudentItem] = []

        for s in new_students:
            norm_roll = normalize_roll_number(s.roll_no)
            if not is_valid_vit_roll(norm_roll):
                continue

            if norm_roll not in master_dict:
                item = RosterStudentItem(
                    roll_no=norm_roll,
                    name=s.name.strip().upper(),
                    batch=s.batch,
                )
                master_dict[norm_roll] = item
                newly_added.append(item)
            else:
                # Update name if previously blank or generic
                existing = master_dict[norm_roll]
                if not existing.name or existing.name.startswith("STUDENT "):
                    if s.name and not s.name.startswith("STUDENT "):
                        existing.name = s.name.strip().upper()

        # Sort master roster deterministically: Batch 1 first, then Batch 2, then by roll number
        sorted_students = sorted(
            master_dict.values(),
            key=lambda x: (x.batch, x.roll_no)
        )

        # Regenerate Sr. No sequentially (1..N)
        for idx, student in enumerate(sorted_students, start=1):
            student.sr_no = idx

        return sorted_students, newly_added

    @staticmethod
    def check_page_order_and_duplicates(pages: List[PageStudentBatch]) -> List[PageOrderWarning]:
        """
        Analyze multi-page batches for:
        1. Duplicate roll numbers within the same session
        2. Gaps or overlapping roll ranges between consecutive pages
        """
        warnings = []
        seen_rolls: Dict[str, int] = {}  # roll -> page_index

        for p in pages:
            for s in p.students:
                norm_roll = normalize_roll_number(s.roll_no)
                if norm_roll in seen_rolls:
                    warnings.append(PageOrderWarning(
                        type="duplicate_in_session",
                        message=f"Duplicate student '{norm_roll}' detected on page {p.page_index} (already seen on page {seen_rolls[norm_roll]}).",
                    ))
                else:
                    seen_rolls[norm_roll] = p.page_index

        # Check ordering between consecutive pages if multiple pages exist
        for i in range(len(pages) - 1):
            curr_p = pages[i]
            next_p = pages[i + 1]
            if curr_p.last_roll and next_p.first_roll:
                if curr_p.last_roll > next_p.first_roll:
                    warnings.append(PageOrderWarning(
                        type="overlap",
                        message=f"Potential out-of-order pages: Page {curr_p.page_index} ends at '{curr_p.last_roll}', but Page {next_p.page_index} starts at '{next_p.first_roll}'.",
                    ))

        return warnings
