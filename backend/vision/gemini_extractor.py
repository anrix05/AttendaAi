"""
gemini_extractor.py
────────────────────
Uses Gemini Vision API (gemini-3.8-flash) to extract the COMPLETE
attendance sheet — student names, roll numbers, dates, and every
attendance mark — from a single image.

This is the primary extraction engine of the system.
YOLO + OpenCV act as a verification / backup layer.
"""

import base64
import json
import os
import re
from pathlib import Path

from google import genai


# ─────────────────────────────────────────────────────────────
# PROMPT
# ─────────────────────────────────────────────────────────────

EXTRACTION_PROMPT = """You are an expert attendance sheet digitization assistant for an Indian engineering college.

Your job is to read this attendance sheet image completely and accurately, and return ALL information as a JSON object.

═══════════════════════════════════════════
WHAT TO EXTRACT
═══════════════════════════════════════════

1. SHEET INFO (from the header area of the sheet):
   - Subject name
   - Class / Division / Branch
   - Academic year (e.g. "2024-25")
   - All date column headers (exactly as written, e.g. "01/09", "02-Sep-24", "1", "2")

2. STUDENT DATA (every row in the table):
   - Sr No (serial number)
   - Roll Number (e.g. "24108B0001")
   - Student Name (FULL NAME IN CAPS)
   - Batch (e.g. "B1", "B2", "1", "2" — if present)
   - Attendance for EACH date column

═══════════════════════════════════════════
ATTENDANCE MARK RULES
═══════════════════════════════════════════

Use EXACTLY these codes:
  "P"  → Student is PRESENT:
         - Any signature, handwritten name, or scribble
         - Letter "P" written in the cell
         - Tick mark (✓) or any positive mark
  "A"  → Student is ABSENT:
         - Letter "A" or "AB" written (usually in red ink)
         - The word "Absent"
  "NM" → NOT MARKED (the cell is completely empty)
  "?"  → UNCERTAIN (something visible but unreadable)

IMPORTANT: A signature = PRESENT. Do not confuse printed table lines with attendance marks.

═══════════════════════════════════════════
OUTPUT FORMAT (return ONLY this JSON, no explanation)
═══════════════════════════════════════════

{
  "sheet_info": {
    "subject":       "Machine Learning",
    "class":         "B.E. Computers",
    "academic_year": "2024-25",
    "dates":         ["01/09", "02/09", "03/09"]
  },
  "students": [
    {
      "sr_no":   1,
      "roll_no": "24108B0001",
      "name":    "VEDANT PATOLE",
      "batch":   "B1",
      "attendance": {
        "1": "P",
        "2": "A",
        "3": "NM"
      }
    }
  ]
}

Notes:
- The "attendance" keys are 1-based string indices matching the "dates" array.
- If sheet_info fields are not visible, set them to null.
- Include EVERY student row — do not skip any.
- If batches are separated by a divider row, still list all students sequentially.
- Count every date column carefully before assigning attendance.

Return ONLY the raw JSON. No markdown. No code fences. No explanation.
"""


# ─────────────────────────────────────────────────────────────
# GEMINI EXTRACTOR CLASS
# ─────────────────────────────────────────────────────────────

class GeminiExtractor:
    """
    Extracts complete attendance information from a sheet image
    using Gemini Vision.
    """

    MODEL = "gemini-3.8-flash"

    def __init__(self, api_key: str | None = None):
        key = api_key or os.environ.get("GEMINI_API_KEY", "")
        if not key:
            raise ValueError(
                "GEMINI_API_KEY not set.\n"
                "Set it as an environment variable:\n"
                "  set GEMINI_API_KEY=your_key_here\n"
                "Or pass it as api_key argument."
            )
        self.client = genai.Client(api_key=key)

    # ─────────────────────────────────────────
    # EXTRACT FROM IMAGE FILE
    # ─────────────────────────────────────────

    def extract(self, image_path: str) -> dict:
        """
        Send the attendance sheet image to Gemini and get back
        a structured JSON with all student data and attendance marks.

        Returns a dict matching the schema above.
        Raises on API failure.
        """
        image_path = Path(image_path)

        mime_map = {
            ".jpg":  "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png":  "image/png",
            ".bmp":  "image/bmp",
            ".webp": "image/webp",
        }
        mime = mime_map.get(image_path.suffix.lower(), "image/jpeg")

        with open(image_path, "rb") as f:
            image_bytes = f.read()

        image_b64 = base64.b64encode(image_bytes).decode("utf-8")

        import time
        print()
        print("🤖 Sending image to OCR Vision Engine for full extraction...")
        print(f"   Model : {self.MODEL}")
        print(f"   Image : {image_path.name}")

        max_retries = 4
        interaction = None
        
        for attempt in range(max_retries):
            try:
                interaction = self.client.interactions.create(
                    model=self.MODEL,
                    input=[
                        {"type": "text",  "text": EXTRACTION_PROMPT},
                        {"type": "image", "data": image_b64, "mime_type": mime},
                    ],
                    store=False,   # don't persist; this is transient OCR data
                )
                break  # Success, exit retry loop
                
            except Exception as e:
                err_str = str(e).lower()
                if "429" in err_str or "rate limit" in err_str or "too_many_requests" in err_str:
                    if attempt < max_retries - 1:
                        sleep_time = 4 + (attempt * 2)  # Wait 4s, 6s, 8s
                        print(f"   [!] Rate limit hit (429). Waiting {sleep_time}s before retrying... (Attempt {attempt+1}/{max_retries})")
                        time.sleep(sleep_time)
                    else:
                        raise RuntimeError(f"OCR Vision Engine API rate limit exceeded after {max_retries} attempts. The Free Tier allows 20 requests per day. Please try again tomorrow or upgrade your API key tier.") from e
                else:
                    raise  # Not a rate limit error, raise immediately

        raw_text = interaction.output_text or ""
        return self._parse_response(raw_text)

    # ─────────────────────────────────────────
    # PARSE GEMINI RESPONSE
    # ─────────────────────────────────────────

    def _parse_response(self, text: str) -> dict:
        """
        Clean and parse the JSON returned by Gemini.
        Handles markdown code fences gracefully.
        """
        text = text.strip()

        # Strip markdown code fences if present
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$",          "", text)
        text = text.strip()

        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            # Try to find the first { ... } block
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if match:
                try:
                    data = json.loads(match.group())
                except json.JSONDecodeError:
                    raise ValueError(
                        f"OCR Vision Engine returned non-JSON response:\n{text[:500]}"
                    ) from exc
            else:
                raise ValueError(
                    f"OCR Vision Engine returned non-JSON response:\n{text[:500]}"
                ) from exc

        return self._validate_and_normalise(data)

    # ─────────────────────────────────────────
    # VALIDATE & NORMALISE
    # ─────────────────────────────────────────

    def _validate_and_normalise(self, data: dict) -> dict:
        """
        Ensure the response follows the expected schema.
        Fill in defaults for missing fields.
        """
        sheet_info = data.get("sheet_info") or {}
        students   = data.get("students")   or []

        # Normalise sheet_info
        dates = sheet_info.get("dates") or []
        if not isinstance(dates, list):
            dates = []

        normalised_sheet = {
            "subject":       sheet_info.get("subject"),
            "class":         sheet_info.get("class"),
            "academic_year": sheet_info.get("academic_year"),
            "dates":         [str(d).strip() for d in dates if d],
        }

        # Normalise students
        valid_statuses = {"P", "A", "NM", "?"}
        normalised_students = []

        for student in students:
            if not isinstance(student, dict):
                continue

            attendance_raw = student.get("attendance") or {}
            attendance = {}

            for key, val in attendance_raw.items():
                val_str = str(val).strip().upper()
                if val_str not in valid_statuses:
                    val_str = "?"
                attendance[str(key)] = val_str

            normalised_students.append({
                "sr_no":      student.get("sr_no") or len(normalised_students) + 1,
                "roll_no":    str(student.get("roll_no") or "").strip(),
                "name":       str(student.get("name") or "").strip().upper(),
                "batch":      student.get("batch"),
                "attendance": attendance,
            })

        result = {
            "sheet_info": normalised_sheet,
            "students":   normalised_students,
        }

        print()
        print("✅ OCR Vision Engine extraction complete:")
        print(f"   Subject  : {normalised_sheet.get('subject')}")
        print(f"   Dates    : {len(normalised_sheet['dates'])} columns")
        print(f"   Students : {len(normalised_students)}")

        return result
