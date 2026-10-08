"""
backend/vision/engines/claude_engine.py — AttendAI Vision Engine (Claude Cloud Backend)
"""
import base64
import json
import logging
import re
import time
from typing import Optional, List, Dict, Any

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

logger = logging.getLogger("attendai.vision.claude")

CLAUDE_STRUCTURED_PROMPT = """You are AttendAI Vision, an expert system for digitizing Indian college attendance registers (VIT Vidyalankar Institute of Technology).

Read this standardized academic attendance register page image completely and extract all information into a strict JSON object.

Extract:
1. Header: class, subject, faculty, division, type, academic_year, week_no
2. Active Date Slots (1-5): only include slots that have a handwritten date header (e.g. "9/9/26"). Ignore unused blank date columns.
3. Student Rows: roll_no (e.g. "24108B0001", "25108B2001"), name in UPPERCASE, batch (1..4). Skip Batch divider rows.
4. Cell Tokens for active date slots:
   - "SIGN": Handwritten signature
   - "AB": Handwritten "AB" or "A"
   - "ARROW_UP": Upward arrow ("↑")
   - "ARROW_DOWN": Downward arrow ("↓")
   - "ARROW_SPAN": Vertical line through cell
   - "EMPTY_OVAL": Empty oval/circle contour
   - "TEXT_NOTE": Word in cell (e.g. "proxy", "Present")
   - "BLANK": Empty cell
   - "UNSURE": Ambiguous mark

Output ONLY raw JSON matching:
{
  "header": {"class": "T.Y.B.TECH", "subject": "SS", "faculty": "SHP", "division": "B", "type": "Theory", "academic_year": "2026-27 (Odd)", "week_no": "08"},
  "date_slots": [{"slot": 1, "raw": "9/9/26", "confidence": 0.98}],
  "rows": [
    {
      "roll_no": "24108B0001", "name": "VEDANT PATOLE", "batch": 1,
      "cells": [{"slot": 1, "token": "SIGN", "confidence": 0.95, "ink": "blue", "circled": false, "text": ""}]
    }
  ]
}
"""


class ClaudeEngine:
    name: str = "claude"

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or settings.ANTHROPIC_API_KEY
        self.model = model or settings.ANTHROPIC_MODEL
        self._client = None
        if self.api_key:
            try:
                import anthropic
                self._client = anthropic.Anthropic(api_key=self.api_key)
            except Exception as e:
                logger.error("Failed to initialize Anthropic client: %s", e)

    def health(self) -> EngineHealth:
        if not self.api_key:
            return EngineHealth(
                ok=False,
                name=self.name,
                reason="Cloud API key not configured.",
                provider_model=self.model,
            )
        if not self._client:
            return EngineHealth(
                ok=False,
                name=self.name,
                reason="Client initialization failed.",
                provider_model=self.model,
            )

        try:
            # Tiny test call
            msg = self._client.messages.create(
                model=self.model,
                max_tokens=10,
                messages=[{"role": "user", "content": "Respond with ok"}],
            )
            if msg and msg.content:
                return EngineHealth(
                    ok=True,
                    name=self.name,
                    reason="Cloud vision service responsive and ready.",
                    provider_model=self.model,
                )
            return EngineHealth(
                ok=False,
                name=self.name,
                reason="Cloud service returned empty response.",
                provider_model=self.model,
            )
        except Exception as exc:
            err_msg = str(exc)
            logger.warning("Claude health check failed: %s", err_msg)
            return EngineHealth(
                ok=False,
                name=self.name,
                reason=f"Service unavailable: {err_msg[:80]}",
                provider_model=self.model,
            )

    def read_page(self, page: PageImage, ctx: ReadContext) -> PageReadResult:
        if not self._client:
            raise RuntimeError("Vision cloud client is not configured.")

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

        b64_data = base64.b64encode(image_bytes).decode("utf-8")

        response = self._client.messages.create(
            model=self.model,
            max_tokens=4096,
            system="You are AttendAI Vision. You must return ONLY raw valid JSON without markdown wrapping or commentary.",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": mime_type,
                                "data": b64_data,
                            },
                        },
                        {"type": "text", "text": CLAUDE_STRUCTURED_PROMPT},
                    ],
                }
            ],
        )

        content_text = ""
        for block in response.content:
            if getattr(block, "type", "") == "text":
                content_text += block.text

        parsed = self._parse_json_with_retry(content_text)
        return self._build_result(parsed)

    def _parse_json_with_retry(self, raw_json_str: str) -> dict:
        try:
            return json.loads(raw_json_str)
        except Exception:
            clean = re.sub(r"^```json\s*", "", raw_json_str.strip(), flags=re.IGNORECASE)
            clean = re.sub(r"^```\s*", "", clean)
            clean = re.sub(r"\s*```$", "", clean)
            try:
                return json.loads(clean)
            except Exception as exc:
                logger.error("JSON parse failed: %s. Raw preview: %s", exc, raw_json_str[:200])
                raise ValueError(f"Invalid structured JSON response from vision model: {exc}")

    def _build_result(self, parsed: dict) -> PageReadResult:
        # Same structured mapping as Gemini
        h_data = parsed.get("header", {}) or {}
        header = HeaderResult(
            class_name=h_data.get("class") or "T.Y.B.TECH",
            subject=h_data.get("subject") or "SS",
            faculty=h_data.get("faculty") or "SHP",
            division=h_data.get("division") or "B",
            type=h_data.get("type") or "Theory",
            academic_year=h_data.get("academic_year") or "2026-27 (Odd)",
            week_no=h_data.get("week_no"),
        )

        date_slots = []
        for idx, d in enumerate(parsed.get("date_slots", [])):
            if not isinstance(d, dict):
                continue
            raw_str = str(d.get("raw", "")).strip()
            date_slots.append(DateSlotResult(
                slot=int(d.get("slot", idx + 1)),
                raw=raw_str,
                iso=d.get("iso"),
                confidence=float(d.get("confidence", 0.95)),
            ))

        rows = []
        for r_idx, r in enumerate(parsed.get("rows", [])):
            if not isinstance(r, dict):
                continue
            roll = str(r.get("roll_no") or "").strip().upper()
            name = str(r.get("name") or "").strip().upper()
            batch = int(r.get("batch", 1) or 1)
            cells = []
            for c in r.get("cells", []):
                tok_str = str(c.get("token") or "BLANK").strip().upper()
                try:
                    tok = TokenEnum(tok_str)
                except Exception:
                    tok = TokenEnum.UNSURE
                cells.append(CellReadResult(
                    slot=int(c.get("slot", 1)),
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
                sr_no=r.get("sr_no", r_idx + 1),
                cells=cells,
            ))

        return PageReadResult(
            header=header,
            date_slots=date_slots,
            rows=rows,
            engine_used="attendai_vision",
        )
