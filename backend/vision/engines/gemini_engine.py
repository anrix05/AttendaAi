"""
backend/vision/engines/gemini_engine.py — AttendAI Vision Engine (Gemini Cloud Backend)
"""
import json
import logging
import re
import time
from io import BytesIO
from typing import Optional, List, Dict, Any
from pathlib import Path

from backend.config import settings
from backend.schemas import TokenEnum
from backend.vision.engines.base import (
    VisionEngine,
    EngineHealth,
    PageImage,
    ReadContext,
    PageReadResult,
    HeaderResult,
    DateSlotResult,
    RowReadResult,
    CellReadResult,
)

logger = logging.getLogger("attendai.vision.gemini")


def _prepare_image(raw: bytes) -> bytes:
    """Downscale large photos and re-encode as JPEG. Returns the original on any failure."""
    try:
        from PIL import Image
        img = Image.open(BytesIO(raw)).convert("RGB")
        img.thumbnail((2200, 2200))  # keeps enough resolution for handwriting
        buf = BytesIO()
        img.save(buf, "JPEG", quality=88)
        return buf.getvalue()
    except Exception:
        return raw

GEMINI_STRUCTURED_PROMPT = """You are AttendAI Vision, an expert system for digitizing Indian college attendance registers (VIT Vidyalankar Institute of Technology).

Read this standardized academic attendance register page image completely and extract all information into a strict JSON object.

═══════════════════════════════════════════════════════
1. HEADER METADATA (top of sheet)
═══════════════════════════════════════════════════════
Extract:
- class: e.g. "T.Y.B.TECH" or "TE"
- subject: handwritten course code, e.g. "SS", "AIML"
- faculty: handwritten initials, e.g. "SHP", "FR"
- division: e.g. "B"
- type: "Theory" or "Practical"
- academic_year: e.g. "2026-27 (Odd)"
- week_no: handwritten week number if visible, or null

═══════════════════════════════════════════════════════
2. DATE SLOTS
═══════════════════════════════════════════════════════
The register has up to 5 date columns from left to right.
- slot: 1, 2, 3, 4, 5
- raw: handwritten date as written, e.g. "9/9/26", "23/9/26", "30/9/26", "7/10/26". If a column header is blank, set raw to "".
- confidence: float 0.0 to 1.0
Always report all date column slots 1 to 5 that exist in the table grid.


═══════════════════════════════════════════════════════
3. STUDENT ROWS & BATCHES
═══════════════════════════════════════════════════════
- Skip divider rows labeled "Batch 1", "Batch 2", "Batch 3", "Batch 4". They are NOT students. Note the active batch for subsequent student rows.
- For every student row, extract:
  * roll_no: printed string, e.g. "24108B0001", "25108B2001" (normalise lowercase 'b' to 'B')
  * name: student name in UPPERCASE
  * batch: integer batch number (1, 2, 3, or 4)
  * cells: array of cell marks for each ACTIVE date slot

═══════════════════════════════════════════════════════
4. CELL TOKEN EXTRACTION (DO NOT DECIDE FINAL P/A)
═══════════════════════════════════════════════════════
For each active date slot, report ONLY ONE raw token from this exact vocabulary:
- "SIGN": Handwritten cursive signature (blue or black ink).
- "AB": Handwritten "AB" or "A" marking (in pink, red, blue, or black ink, often circled).
- "ARROW_UP": Upward pointing arrow ("↑") in the cell.
- "ARROW_DOWN": Downward pointing arrow ("↓") in the cell.
- "ARROW_SPAN": Long vertical stroke / line passing through this cell.
- "EMPTY_OVAL": Drawn oval or circle with nothing written inside.
- "TEXT_NOTE": Word written in cell (e.g. "proxy", "Present"). Store text in the "text" field.
- "BLANK": Clean empty cell with no markings (session not marked yet).
- "UNSURE": Ambiguous mark, crossed-out marking, or flourishing stroke bleeding across borders.

Return ONLY valid JSON matching this exact structure:
{
  "header": {
    "class": "T.Y.B.TECH",
    "subject": "SS",
    "faculty": "SHP",
    "division": "B",
    "type": "Theory",
    "academic_year": "2026-27 (Odd)",
    "week_no": "08"
  },
  "date_slots": [
    {"slot": 1, "raw": "9/9/26", "confidence": 0.98},
    {"slot": 2, "raw": "23/9/26", "confidence": 0.98},
    {"slot": 3, "raw": "30/9/26", "confidence": 0.98},
    {"slot": 4, "raw": "7/10/26", "confidence": 0.98}
  ],
  "rows": [
    {
      "roll_no": "24108B0001",
      "name": "VEDANT PATOLE",
      "batch": 1,
      "cells": [
        {"slot": 1, "token": "SIGN", "confidence": 0.95, "ink": "blue", "circled": false, "text": ""},
        {"slot": 2, "token": "SIGN", "confidence": 0.95, "ink": "blue", "circled": false, "text": ""},
        {"slot": 3, "token": "SIGN", "confidence": 0.95, "ink": "blue", "circled": false, "text": ""},
        {"slot": 4, "token": "SIGN", "confidence": 0.95, "ink": "blue", "circled": false, "text": ""}
      ]
    }
  ]
}
"""


class GeminiEngine:
    name: str = "gemini"

    _last_check_time: float = 0.0
    _cached_health: Optional[EngineHealth] = None

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or settings.effective_api_key
        self.model = model or settings.GEMINI_MODEL
        self._client = None
        if self.api_key:
            try:
                from google import genai
                from google.genai import types as _types
                try:
                    self._client = genai.Client(
                        api_key=self.api_key,
                        http_options=_types.HttpOptions(timeout=60_000),  # milliseconds
                    )
                except Exception:
                    # Older SDK without HttpOptions timeout support: fall back to default client
                    self._client = genai.Client(api_key=self.api_key)
            except Exception as e:
                logger.error("Failed to initialize Google GenAI client: %s", e)

    def _set_health(self, ok: bool, reason: str):
        GeminiEngine._cached_health = EngineHealth(
            ok=ok, name=self.name, reason=reason, provider_model=self.model
        )
        GeminiEngine._last_check_time = time.time()

    def health(self) -> EngineHealth:
        if not self.api_key:
            return EngineHealth(ok=False, name=self.name,
                                reason="Cloud API key not configured.", provider_model=self.model)
        if not self._client:
            return EngineHealth(ok=False, name=self.name,
                                reason="Client initialization failed.", provider_model=self.model)

        # Passive health: reflects the last real scan. Never spends generation quota.
        cached = GeminiEngine._cached_health
        if cached is not None:
            # A failure expires after 60s so the status chip does not stay red forever
            if cached.ok or (time.time() - GeminiEngine._last_check_time < 60.0):
                return cached
        return EngineHealth(ok=True, name=self.name,
                            reason="Configured and ready.", provider_model=self.model)

    def read_page(self, page: PageImage, ctx: ReadContext) -> PageReadResult:
        if not self._client:
            raise RuntimeError("Vision cloud client is not configured.")

        from google.genai import types

        # Ensure image bytes
        image_bytes = page.bytes
        if not image_bytes and page.path and page.path.exists():
            with open(page.path, "rb") as f:
                image_bytes = f.read()

        if not image_bytes:
            raise FileNotFoundError(f"Image data not found for {page.path}")

        mime_type = "image/jpeg"
        if str(page.path).lower().endswith(".png"):
            mime_type = "image/png"

        prepared = _prepare_image(image_bytes)
        if prepared is not image_bytes:
            image_bytes = prepared
            mime_type = "image/jpeg"

        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.1,
        )

        # Max 2 models. Quota errors switch model immediately. Hard overall deadline.
        models_to_try = list(dict.fromkeys([m for m in [self.model, "gemini-3.1-flash-lite"] if m]))
        deadline = time.time() + 75
        response = None
        last_error = None

        for m_name in models_to_try:
            backoff_sec = 2.0  # reset per model
            for attempt in range(2):
                if time.time() > deadline:
                    break
                try:
                    logger.info("Vision call: %s (attempt %d)", m_name, attempt + 1)
                    response = self._client.models.generate_content(
                        model=m_name,
                        contents=[
                            types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                            GEMINI_STRUCTURED_PROMPT,
                        ],
                        config=config,
                    )
                    if response and response.text:
                        self._set_health(True, "Cloud vision service responsive and ready.")
                        break
                except Exception as exc:
                    last_error = exc
                    err = str(exc).lower()
                    if "429" in err or "resource_exhausted" in err or "quota" in err:
                        logger.warning("Quota hit on %s. Switching model, no retry.", m_name)
                        self._set_health(False, "Rate limit reached. Cached results active.")
                        break  # never retry the same model on a quota error
                    if "503" in err or "unavailable" in err or "high demand" in err:
                        time.sleep(backoff_sec)
                        backoff_sec *= 2.0
                        continue
                    logger.warning("Vision error on %s: %s", m_name, exc)
                    break
            if response and response.text:
                break

        if not response or not response.text:
            raise RuntimeError(f"Cloud vision request failed: {last_error}")

        raw_json = response.text or "{}"
        parsed = self._parse_json_with_retry(raw_json)

        return self._build_result(parsed)

    def _parse_json_with_retry(self, raw_json_str: str) -> dict:
        try:
            return json.loads(raw_json_str)
        except Exception:
            # Strip markdown ```json ... ``` wrapper
            clean = re.sub(r"^```json\s*", "", raw_json_str.strip(), flags=re.IGNORECASE)
            clean = re.sub(r"^```\s*", "", clean)
            clean = re.sub(r"\s*```$", "", clean)
            try:
                return json.loads(clean)
            except Exception as exc:
                logger.error("JSON parse failed: %s. Raw preview: %s", exc, raw_json_str[:200])
                raise ValueError(f"Invalid structured JSON response from vision model: {exc}")

    def _build_result(self, parsed: dict) -> PageReadResult:
        h_data = parsed.get("header", {}) or {}
        header = HeaderResult(
            class_name=h_data.get("class") or h_data.get("class_name") or "T.Y.B.TECH",
            subject=h_data.get("subject") or "SS",
            faculty=h_data.get("faculty") or "SHP",
            division=h_data.get("division") or "B",
            type=h_data.get("type") or "Theory",
            academic_year=h_data.get("academic_year") or "2026-27 (Odd)",
            week_no=h_data.get("week_no"),
        )

        # Parse date slots for all table columns
        date_slots = []
        raw_slots = parsed.get("date_slots") or parsed.get("date_columns") or []
        for idx, d in enumerate(raw_slots):
            if not isinstance(d, dict):
                continue
            raw_str = str(d.get("raw") or d.get("raw_date") or "").strip()
            slot_num = d.get("slot") or d.get("col_idx") or (idx + 1)
            try:
                slot_num = int(slot_num)
            except Exception:
                slot_num = idx + 1

            date_slots.append(DateSlotResult(
                slot=slot_num,
                raw=raw_str,
                iso=d.get("iso") or d.get("iso_date"),
                confidence=float(d.get("confidence", 0.95)),
            ))


        # Parse rows
        rows = []
        parsed_rows = parsed.get("rows") or []
        for r_idx, r in enumerate(parsed_rows):
            if not isinstance(r, dict):
                continue
            roll = str(r.get("roll_no") or "").strip().upper()
            name = str(r.get("name") or "").strip().upper()
            batch = int(r.get("batch", 1) or 1)
            sr = r.get("sr_no")
            if sr is not None:
                try:
                    sr = int(sr)
                except Exception:
                    sr = r_idx + 1
            else:
                sr = r_idx + 1

            cells = []
            for c in (r.get("cells") or []):
                if not isinstance(c, dict):
                    continue
                c_slot = c.get("slot") or c.get("col_idx") or 1
                try:
                    c_slot = int(c_slot)
                except Exception:
                    c_slot = 1
                tok_str = str(c.get("token") or "BLANK").strip().upper()
                try:
                    tok = TokenEnum(tok_str)
                except Exception:
                    tok = TokenEnum.UNSURE

                cells.append(CellReadResult(
                    slot=c_slot,
                    token=tok,
                    confidence=float(c.get("confidence", 0.90)),
                    ink=c.get("ink", "blue"),
                    circled=bool(c.get("circled", False)),
                    text=str(c.get("text") or ""),
                ))

            rows.append(RowReadResult(
                roll_no=roll,
                name=name,
                batch=batch,
                sr_no=sr,
                cells=cells,
            ))

        return PageReadResult(
            header=header,
            date_slots=date_slots,
            rows=rows,
            engine_used="attendai_vision",
        )
