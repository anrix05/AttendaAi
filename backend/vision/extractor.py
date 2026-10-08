"""
backend/vision/extractor.py — Multimodal Attendance Sheet Token Extractor
"""
import base64
import json
import logging
import re
import time
from pathlib import Path
from typing import Dict, List, Optional, Any, Union

import cv2
import numpy as np
from pydantic import BaseModel

from backend.config import settings
from backend.schemas import (
    TokenEnum,
    AttendanceStatus,
    HeaderInfo,
    DateColumn,
    CellToken,
    CellResolved,
    RowExtraction,
    ScanPreviewResponse,
)
from backend.vision.arrow_resolver import ArrowResolver, InputCell
from backend.vision.roster_aligner import RosterAligner, ScannedStudentRow, RosterStudent

logger = logging.getLogger("attendai.extractor")


# ─────────────────────────────────────────────────────────────
# EXTRACTION PROMPT & SCHEMA
# ─────────────────────────────────────────────────────────────

TOKEN_EXTRACTION_PROMPT = """You are an expert AI assistant specialized in digitizing handwritten college attendance registers (VIT Vidyalankar Institute of Technology).

Read this standardized academic attendance register image completely and extract all information into a strict JSON object.

═══════════════════════════════════════════════════════
1. HEADER METADATA (top of sheet, handwritten & printed)
═══════════════════════════════════════════════════════
- Class: e.g. "T.Y.B.TECH"
- Subject: handwritten course code, e.g. "SS"
- Faculty: handwritten initials, e.g. "SHP"
- Division: e.g. "B"
- Type: "Theory" (often written outside upper border) or "Practical"
- Academic Year: e.g. "2026-27 (Odd)"
- Week No: handwritten week number if visible, or null

═══════════════════════════════════════════════════════
2. DATE COLUMNS
═══════════════════════════════════════════════════════
Identify each active date column from left to right.
- Format written on paper is d/m/yy (e.g. "9/9/26", "23/9/26", "30/9/26", "7/10/26").
- Convert to standard ISO date: YYYY-MM-DD (e.g. "2026-09-09").
- IMPORTANT: The 5th date column is typically printed but BLANK/UNWRITTEN. Completely IGNORE any unwritten date column!

═══════════════════════════════════════════════════════
3. STUDENT ROWS & BATCHES
═══════════════════════════════════════════════════════
- Skip divider rows labeled "Batch 1", "Batch 2", "Batch 3", or "Batch 4". They are NOT students.
- Extract student rows with:
  * sr_no: integer sequence number
  * roll_no: printed string, e.g. "24108B0001", "25108B2001"
  * name: student name in CAPS
  * batch: integer batch number (1, 2, 3, or 4)

═══════════════════════════════════════════════════════
4. CELL TOKEN EXTRACTION (CRITICAL RULE)
═══════════════════════════════════════════════════════
For each active date column, inspect the cell box. DO NOT decide P/A directly.
Emit ONLY ONE raw token from this exact vocabulary:
- "SIGN": Handwritten pen signature (cursive ink signature, blue or black ink).
- "AB": Handwritten "AB" or "A" marking (in pink, red, black, or blue ink).
- "ARROW_UP": Upward pointing arrow ("↑") in the cell.
- "ARROW_DOWN": Downward pointing arrow ("↓") in the cell.
- "ARROW_SPAN": Long vertical line/bracket stroke running through the cell.
- "BLANK": Clean empty cell with no marks (session not yet marked).
- "UNSURE": Ambiguous, crossed-out mark (e.g. AB crossed out with a line), flourishing stroke bleeding across cells, or low clarity.

Return ONLY raw JSON with this exact structure:
{
  "header": {
    "class_name": "T.Y.B.TECH",
    "subject": "SS",
    "faculty": "SHP",
    "division": "B",
    "type": "Theory",
    "academic_year": "2026-27 (Odd)",
    "week_no": "08"
  },
  "date_columns": [
    {"col_idx": 0, "raw_date": "9/9/26", "iso_date": "2026-09-09", "confidence": 0.98},
    {"col_idx": 1, "raw_date": "23/9/26", "iso_date": "2026-09-23", "confidence": 0.98},
    {"col_idx": 2, "raw_date": "30/9/26", "iso_date": "2026-09-30", "confidence": 0.98},
    {"col_idx": 3, "raw_date": "7/10/26", "iso_date": "2026-10-07", "confidence": 0.98}
  ],
  "rows": [
    {
      "sr_no": 1,
      "roll_no": "24108B0001",
      "name": "VEDANT PATOLE",
      "batch": 1,
      "cells": [
        {"col_idx": 0, "token": "SIGN", "confidence": 0.95, "ink_color": "blue"},
        {"col_idx": 1, "token": "SIGN", "confidence": 0.95, "ink_color": "blue"},
        {"col_idx": 2, "token": "SIGN", "confidence": 0.95, "ink_color": "blue"},
        {"col_idx": 3, "token": "SIGN", "confidence": 0.95, "ink_color": "blue"}
      ]
    }
  ]
}
"""


# ─────────────────────────────────────────────────────────────
# MOCK EXTRACTOR (FOR REPRODUCIBLE TESTS & OFFLINE WORK)
# ─────────────────────────────────────────────────────────────

class MockExtractor:
    """
    Simulates AI extraction by reading directly from ground-truth JSON fixture.
    Allows complete offline execution, CI pipeline runs, and benchmark testing.
    """

    def __init__(self, fixture_path: Optional[Path] = None):
        self.fixture_path = fixture_path or (
            Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "ground_truth_ss_divb.json"
        )
        self.arrow_resolver = ArrowResolver()
        self.roster_aligner = RosterAligner()

    def extract(
        self,
        image_path: Union[str, Path],
        roster: Optional[List[RosterStudent]] = None,
        subject_id: str = "tybtech_b_ss_theory",
    ) -> ScanPreviewResponse:
        with open(self.fixture_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        header_data = data.get("subject_info", {})
        header = HeaderInfo(
            class_name=header_data.get("class_name", "T.Y.B.TECH"),
            subject=header_data.get("subject", "SS"),
            faculty=header_data.get("faculty", "SHP"),
            division=header_data.get("division", "B"),
            type=header_data.get("type", "Theory"),
            academic_year=header_data.get("academic_year", "2026-27 (Odd)"),
            week_no=header_data.get("week_no"),
        )

        dates = [
            DateColumn(
                col_idx=d["col_idx"],
                raw_date=d["raw"],
                iso_date=d["iso"],
                confidence=1.0,
            )
            for d in data.get("dates", [])
        ]

        # Build raw cells per column to run through arrow resolver
        col_cells: Dict[int, List[InputCell]] = {d.col_idx: [] for d in dates}
        student_rows_raw = data.get("students", [])

        for s_idx, s in enumerate(student_rows_raw, start=1):
            records = s.get("records", {})
            for d in dates:
                rec = records.get(d.iso_date, {"token": "BLANK"})
                token_str = rec.get("token", "BLANK")
                try:
                    tok = TokenEnum(token_str)
                except Exception:
                    tok = TokenEnum.UNSURE

                col_cells[d.col_idx].append(InputCell(
                    row_idx=s["sr_no"],
                    batch_id=s["batch"],
                    token=tok,
                    confidence=0.95 if not rec.get("ambiguous") else 0.70,
                ))

        # Resolve each column with pure-logic ArrowResolver
        resolved_by_col: Dict[int, List[CellResolved]] = {}
        for d in dates:
            resolved_cells = self.arrow_resolver.resolve_column(col_cells[d.col_idx])
            resolved_by_col[d.col_idx] = [
                CellResolved(
                    col_idx=d.col_idx,
                    token=rc.token,
                    status=rc.status,
                    confidence=rc.confidence,
                    reason=rc.reason,
                    ambiguous=rc.ambiguous,
                )
                for rc in resolved_cells
            ]

        # Assemble row extraction items
        has_uncertain = False
        final_rows = []
        for row_i, s in enumerate(student_rows_raw):
            row_cells = []
            for d in dates:
                c_res = resolved_by_col[d.col_idx][row_i]
                if c_res.status == AttendanceStatus.UNCERTAIN:
                    has_uncertain = True
                row_cells.append(c_res)

            final_rows.append(RowExtraction(
                sr_no=s["sr_no"],
                roll_no=s["roll_no"],
                name=s["name"],
                batch=s["batch"],
                cells=row_cells,
            ))

        return ScanPreviewResponse(
            subject_id=subject_id,
            header=header,
            date_columns=dates,
            rows=final_rows,
            image_url=str(image_path),
            has_uncertain=has_uncertain,
        )


# ─────────────────────────────────────────────────────────────
# GEMINI LIVE VISION TOKEN EXTRACTOR
# ─────────────────────────────────────────────────────────────

class GeminiTokenExtractor:
    """
    Live multimodal extractor utilizing Google GenAI SDK (client.models.generate_content).
    Extracts raw cell tokens and validates with Pydantic.
    """

    def __init__(self, api_key: Optional[str] = None, model_name: Optional[str] = None):
        self.api_key = api_key or settings.effective_api_key
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY is not configured.")
        self.model_name = model_name or settings.GEMINI_MODEL
        self.arrow_resolver = ArrowResolver()
        self.roster_aligner = RosterAligner()

        from google import genai
        self.client = genai.Client(api_key=self.api_key)

    @staticmethod
    def _normalize_iso_date(raw_date: str, fallback_iso: Optional[str] = None) -> str:
        if fallback_iso:
            clean_iso = str(fallback_iso).strip()
            if re.match(r"^\d{4}-\d{2}-\d{2}$", clean_iso):
                return clean_iso
        clean_raw = str(raw_date or "").strip()
        parts = re.split(r"[/\-.]", clean_raw)
        if len(parts) == 3:
            try:
                day, month, year = int(parts[0]), int(parts[1]), int(parts[2])
                if year < 100:
                    year += 2000
                return f"{year:04d}-{month:02d}-{day:02d}"
            except Exception:
                pass
        return str(fallback_iso or "2026-09-09").strip()

    @staticmethod
    def _iso_to_raw(iso_date: str) -> str:
        parts = str(iso_date).strip().split("-")
        if len(parts) == 3:
            try:
                return f"{int(parts[2])}/{int(parts[1])}/{int(parts[0]) % 100}"
            except Exception:
                pass
        return str(iso_date).strip()

    def extract(
        self,
        image_path: Union[str, Path],
        roster: Optional[List[RosterStudent]] = None,
        subject_id: str = "tybtech_b_ss_theory",
    ) -> ScanPreviewResponse:
        from google.genai import types

        img_path = Path(image_path)
        if not img_path.exists():
            raise FileNotFoundError(f"Image not found at {img_path}")

        mime_type = "image/jpeg"
        if img_path.suffix.lower() == ".png":
            mime_type = "image/png"

        with open(img_path, "rb") as f:
            image_bytes = f.read()

        logger.info("Sending %s to Google GenAI (%s)...", img_path.name, self.model_name)

        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.1,
        )

        candidate_models = [self.model_name]
        for alt_m in ["gemini-3.5-flash-lite", "gemini-flash-latest", "gemini-3.5-flash"]:
            if alt_m not in candidate_models:
                candidate_models.append(alt_m)

        response = None
        last_error = None

        for m_name in candidate_models:
            for attempt in range(2):
                try:
                    logger.info("Attempting extraction with model: %s (attempt %d)", m_name, attempt + 1)
                    response = self.client.models.generate_content(
                        model=m_name,
                        contents=[
                            types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                            TOKEN_EXTRACTION_PROMPT,
                        ],
                        config=config,
                    )
                    break
                except Exception as exc:
                    last_error = exc
                    err_str = str(exc).lower()
                    if "503" in err_str or "unavailable" in err_str or "high demand" in err_str or "429" in err_str:
                        logger.warning("Model '%s' unavailable (spike in demand: %s). Retrying/falling back...", m_name, exc)
                        time.sleep(1.5)
                        continue
                    else:
                        break  # Non-transient error, break attempt loop

            if response is not None:
                break

        if response is None:
            raise RuntimeError(
                f"Google Gemini Vision API is temporarily experiencing high traffic demand (503). "
                f"Details: {last_error}. Tip: Switch to '⚡ Offline Mock Extractor' in the UI for instant testing."
            )

        raw_json_str = response.text or "{}"
        try:
            parsed = json.loads(raw_json_str)
        except Exception:
            clean_str = re.sub(r"^```json\s*", "", raw_json_str.strip(), flags=re.IGNORECASE)
            clean_str = re.sub(r"^```\s*", "", clean_str)
            clean_str = re.sub(r"\s*```$", "", clean_str)
            try:
                parsed = json.loads(clean_str)
            except Exception as exc:
                logger.error("Failed to parse Gemini JSON output: %s", exc)
                raise ValueError(f"Gemini returned invalid JSON: {exc}")

        # Construct Header
        h_dict = parsed.get("header", {}) or {}
        header = HeaderInfo(
            class_name=h_dict.get("class_name", "T.Y.B.TECH"),
            subject=h_dict.get("subject", "SS"),
            faculty=h_dict.get("faculty", "SHP"),
            division=h_dict.get("division", "B"),
            type=h_dict.get("type", "Theory"),
            academic_year=h_dict.get("academic_year", "2026-27 (Odd)"),
            week_no=h_dict.get("week_no"),
        )

        # Construct Date Columns with defensive filtering of empty/unwritten columns
        valid_dates_meta = []
        raw_date_cols = parsed.get("date_columns", []) or []
        for orig_idx, d in enumerate(raw_date_cols):
            if not isinstance(d, dict):
                continue
            raw_v = d.get("raw_date")
            iso_v = d.get("iso_date")
            raw_s = str(raw_v).strip() if raw_v is not None else ""
            iso_s = str(iso_v).strip() if iso_v is not None else ""

            # Check if this column is empty/blank/unwritten
            invalid_sentinels = {"", "none", "null", "n/a", "na", "-", "date", "blank", "unwritten"}
            if raw_s.lower() in invalid_sentinels and iso_s.lower() in invalid_sentinels:
                logger.info("Ignoring unwritten/blank date column at index %s", orig_idx)
                continue
            if not any(ch.isdigit() for ch in raw_s) and not any(ch.isdigit() for ch in iso_s):
                logger.info("Ignoring date column without digits at index %s: %s", orig_idx, d)
                continue

            orig_col_idx = d.get("col_idx", orig_idx)
            try:
                orig_col_idx = int(orig_col_idx)
            except Exception:
                orig_col_idx = orig_idx

            clean_iso = self._normalize_iso_date(raw_s, iso_s)
            clean_raw = raw_s if (raw_s and any(c.isdigit() for c in raw_s)) else self._iso_to_raw(clean_iso)

            conf = 0.95
            try:
                conf = float(d.get("confidence", 0.95))
            except Exception:
                pass

            valid_dates_meta.append({
                "orig_col_idx": orig_col_idx,
                "raw_date": clean_raw,
                "iso_date": clean_iso,
                "confidence": conf,
            })

        # Ensure at least one date column fallback if none survived
        if not valid_dates_meta:
            valid_dates_meta.append({
                "orig_col_idx": 0,
                "raw_date": "Session 1",
                "iso_date": "2026-09-09",
                "confidence": 0.50,
            })

        # Remap to sequential col_idx: 0, 1, 2, ...
        dates: List[DateColumn] = []
        orig_to_new_col: Dict[int, int] = {}
        for new_idx, meta in enumerate(valid_dates_meta):
            orig_to_new_col[meta["orig_col_idx"]] = new_idx
            dates.append(DateColumn(
                col_idx=new_idx,
                raw_date=meta["raw_date"],
                iso_date=meta["iso_date"],
                confidence=meta["confidence"],
            ))

        # Build raw cells per column for pure-logic arrow resolution
        col_cells: Dict[int, List[InputCell]] = {d.col_idx: [] for d in dates}
        parsed_rows = parsed.get("rows", []) or []

        for s in parsed_rows:
            batch_val = int(s.get("batch", 1) or 1)
            sr_val = int(s.get("sr_no", 1) or 1)
            cell_tokens: Dict[int, str] = {}
            for c in (s.get("cells", []) or []):
                if isinstance(c, dict):
                    c_idx = c.get("col_idx")
                    if c_idx is not None:
                        try:
                            c_idx = int(c_idx)
                        except Exception:
                            pass
                    cell_tokens[c_idx] = c.get("token", "BLANK")

            for meta in valid_dates_meta:
                orig_c = meta["orig_col_idx"]
                new_c = orig_to_new_col[orig_c]
                tok_str = cell_tokens.get(orig_c, "BLANK")
                try:
                    tok = TokenEnum(tok_str)
                except Exception:
                    tok = TokenEnum.UNSURE

                col_cells[new_c].append(InputCell(
                    row_idx=sr_val,
                    batch_id=batch_val,
                    token=tok,
                    confidence=0.90,
                ))

        # Resolve each column with ArrowResolver
        resolved_by_col: Dict[int, List[CellResolved]] = {}
        for d in dates:
            resolved_cells = self.arrow_resolver.resolve_column(col_cells[d.col_idx])
            resolved_by_col[d.col_idx] = [
                CellResolved(
                    col_idx=d.col_idx,
                    token=rc.token,
                    status=rc.status,
                    confidence=rc.confidence,
                    reason=rc.reason,
                    ambiguous=rc.ambiguous,
                )
                for rc in resolved_cells
            ]

        # Reconcile student rows
        has_uncertain = False
        final_rows = []
        for row_i, s in enumerate(parsed_rows):
            row_cells = []
            for d in dates:
                if row_i < len(resolved_by_col[d.col_idx]):
                    c_res = resolved_by_col[d.col_idx][row_i]
                else:
                    c_res = CellResolved(
                        col_idx=d.col_idx,
                        token=TokenEnum.BLANK,
                        status=AttendanceStatus.NM,
                    )
                if c_res.status == AttendanceStatus.UNCERTAIN:
                    has_uncertain = True
                row_cells.append(c_res)

            final_rows.append(RowExtraction(
                sr_no=int(s.get("sr_no", row_i + 1) or (row_i + 1)),
                roll_no=str(s.get("roll_no", "") or "").strip().upper(),
                name=str(s.get("name", "") or "").strip().upper(),
                batch=int(s.get("batch", 1) or 1),
                cells=row_cells,
            ))

        return ScanPreviewResponse(
            subject_id=subject_id,
            header=header,
            date_columns=dates,
            rows=final_rows,
            image_url=str(image_path),
            has_uncertain=has_uncertain,
        )


class MultiEngineExtractor:
    """
    Unified AttendAI Vision extractor combining EngineManager (failover + caching)
    with pure-logic deterministic ArrowResolver and RosterAligner.
    """

    def __init__(self, use_mock: bool = False, engine_order: Optional[str] = None):
        self.use_mock = use_mock
        self.mock_extractor = MockExtractor() if use_mock else None
        from backend.vision.engines import EngineManager
        self.manager = EngineManager(engine_order=engine_order)
        self.arrow_resolver = ArrowResolver()
        self.roster_aligner = RosterAligner()

    def extract(
        self,
        image_path: Union[str, Path],
        roster: Optional[List[RosterStudent]] = None,
        subject_id: str = "tybtech_b_ss_theory",
    ) -> ScanPreviewResponse:
        if self.use_mock:
            return self.mock_extractor.extract(image_path=image_path, roster=roster, subject_id=subject_id)

        from backend.vision.engines import PageImage, ReadContext
        page = PageImage(path=Path(image_path))
        ctx = ReadContext(subject_id=subject_id)
        page_res = self.manager.read_page_with_fallback(page, ctx)

        # 1. Header
        header = HeaderInfo(
            class_name=page_res.header.class_name,
            subject=page_res.header.subject,
            faculty=page_res.header.faculty,
            division=page_res.header.division,
            type=page_res.header.type,
            academic_year=page_res.header.academic_year,
            week_no=page_res.header.week_no,
        )

        # 2. Determine all candidate slots across date_slots and student rows
        from datetime import datetime, timedelta
        from backend.vision.dates import AcademicDateParser
        date_parser = AcademicDateParser(academic_year=page_res.header.academic_year or "2026-27 (Odd)")

        slots_in_dates = [d.slot for d in page_res.date_slots]
        slots_in_cells = [c.slot for r in page_res.rows for c in r.cells]
        candidate_slots = sorted(list(set(slots_in_dates + slots_in_cells)))
        if not candidate_slots:
            candidate_slots = [1, 2, 3, 4]

        date_slots_map = {d.slot: d for d in page_res.date_slots}
        total_students = len(page_res.rows)

        # Rule 1: A date slot is ACTIVE if it has a date written OR at least 20% of its cells contain ink/marks
        active_slots: List[int] = []
        for s_num in candidate_slots:
            slot_info = date_slots_map.get(s_num)
            raw_text = str(slot_info.raw or "").strip() if slot_info else ""
            has_date_written = bool(raw_text and any(ch.isdigit() for ch in raw_text))

            # Count cells with ink/marks (SIGN, AB, arrows, etc.)
            marked_count = sum(
                1 for r in page_res.rows
                for c in r.cells
                if c.slot == s_num and c.token not in (TokenEnum.BLANK, TokenEnum.EMPTY_OVAL)
            )
            mark_ratio = (marked_count / total_students) if total_students > 0 else 0.0

            if has_date_written or mark_ratio >= 0.20:
                active_slots.append(s_num)
            else:
                logger.info("Slot %d ignored: has_date=%s, mark_ratio=%.2f (<20%%)", s_num, has_date_written, mark_ratio)

        # Fallback to slot 1 if zero slots active
        if not active_slots:
            active_slots = [1]

        logger.info("Page %s: detected %d active slots out of %s candidate slots", image_path, len(active_slots), candidate_slots)

        # Build DateColumn list for each active slot
        dates: List[DateColumn] = []
        latest_date_dt: Optional[datetime] = None

        for col_idx, s_num in enumerate(active_slots):
            slot_info = date_slots_map.get(s_num)
            raw_text = str(slot_info.raw or "").strip() if slot_info else ""
            has_date_written = bool(raw_text and any(ch.isdigit() for ch in raw_text))

            if has_date_written:
                parsed_dt = date_parser.parse(raw_text)
                iso_d = slot_info.iso or parsed_dt.iso
                try:
                    latest_date_dt = datetime.strptime(iso_d, "%Y-%m-%d")
                except Exception:
                    pass
                dates.append(DateColumn(
                    col_idx=col_idx,
                    raw_date=raw_text,
                    iso_date=iso_d,
                    confidence=slot_info.confidence if slot_info else 1.0,
                    needs_confirmation=False,
                ))
            else:
                # Active slot without a date
                if latest_date_dt:
                    suggested_dt = latest_date_dt + timedelta(days=7)
                else:
                    suggested_dt = datetime(2026, 9, 9) + timedelta(days=col_idx * 7)
                latest_date_dt = suggested_dt
                sugg_iso = suggested_dt.strftime("%Y-%m-%d")

                dates.append(DateColumn(
                    col_idx=col_idx,
                    raw_date=f"Date missing (column {s_num})",
                    iso_date=sugg_iso,
                    confidence=0.5,
                    needs_confirmation=True,
                    suggested_date=sugg_iso,
                ))

        # 3. Build raw cells per active column for arrow resolution
        col_cells: Dict[int, List[InputCell]] = {d.col_idx: [] for d in dates}
        for s in page_res.rows:
            batch_val = s.batch
            sr_val = s.sr_no or 1
            cell_tokens = {c.slot: c.token for c in s.cells}

            for col_idx, s_num in enumerate(active_slots):
                tok = cell_tokens.get(s_num, TokenEnum.BLANK)
                col_cells[col_idx].append(InputCell(
                    row_idx=sr_val,
                    batch_id=batch_val,
                    token=tok,
                    confidence=0.90,
                ))

        # 4. Resolve columns with pure-logic ArrowResolver
        resolved_by_col: Dict[int, List[CellResolved]] = {}
        for d in dates:
            resolved_cells = self.arrow_resolver.resolve_column(col_cells[d.col_idx])
            resolved_by_col[d.col_idx] = [
                CellResolved(
                    col_idx=d.col_idx,
                    token=rc.token,
                    status=rc.status,
                    confidence=rc.confidence,
                    reason=rc.reason,
                    ambiguous=rc.ambiguous,
                )
                for rc in resolved_cells
            ]


        # 5. Assemble reconciled rows
        has_uncertain = False
        final_rows = []
        for row_i, s in enumerate(page_res.rows):
            row_cells = []
            for d in dates:
                if row_i < len(resolved_by_col[d.col_idx]):
                    c_res = resolved_by_col[d.col_idx][row_i]
                else:
                    c_res = CellResolved(
                        col_idx=d.col_idx,
                        token=TokenEnum.BLANK,
                        status=AttendanceStatus.NM,
                    )
                if c_res.status == AttendanceStatus.UNCERTAIN:
                    has_uncertain = True
                row_cells.append(c_res)

            final_rows.append(RowExtraction(
                sr_no=s.sr_no or (row_i + 1),
                roll_no=s.roll_no,
                name=s.name,
                batch=s.batch,
                cells=row_cells,
            ))

        return ScanPreviewResponse(
            subject_id=subject_id,
            header=header,
            date_columns=dates,
            rows=final_rows,
            image_url=str(image_path),
            has_uncertain=has_uncertain,
        )


def get_extractor(use_mock: bool = False):
    """Factory function: Returns MockExtractor if requested, otherwise MultiEngineExtractor."""
    if use_mock:
        return MockExtractor()
    return MultiEngineExtractor(use_mock=False)

