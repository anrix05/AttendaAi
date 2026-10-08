"""
backend/vision/dates.py — Robust Academic Date Parsing and Normalization
Handles messy handwritten formats, academic year inference, and error warnings.
"""
import re
from datetime import datetime
from typing import Optional, Tuple
from pydantic import BaseModel


class DateParseResult(BaseModel):
    raw: str
    iso: str
    is_valid: bool
    warning: Optional[str] = None


class AcademicDateParser:
    """
    Parses dates from VIT registers with context of the academic year.
    Supported inputs:
      - '9/9/26', '09/09/2026', '9-9-26', '9.9.26', '9/9'
      - '23/9/26', '30/09/26', '7/10/26'
    """

    def __init__(self, academic_year: str = "2026-27 (Odd)"):
        self.academic_year = academic_year
        self.base_year, self.end_year, self.term = self._parse_academic_year(academic_year)

    def _parse_academic_year(self, ac_year: str) -> Tuple[int, int, str]:
        """Extract base year (e.g. 2026), end year (e.g. 2027), and term ('Odd'/'Even')."""
        m = re.search(r"(\d{4})[^\d]*(\d{2,4})?", ac_year)
        if m:
            base = int(m.group(1))
            end_raw = m.group(2)
            if end_raw:
                end = int(end_raw) if len(end_raw) == 4 else (base // 100) * 100 + int(end_raw)
            else:
                end = base + 1
        else:
            base, end = 2026, 2027

        term = "Odd" if "odd" in ac_year.lower() else ("Even" if "even" in ac_year.lower() else "Odd")
        return base, end, term

    def parse(self, raw_date: Optional[str], fallback_iso: Optional[str] = None) -> DateParseResult:
        """Parse raw date string into standardized ISO 8601 YYYY-MM-DD."""
        if not raw_date or not str(raw_date).strip():
            iso_fallback = fallback_iso or f"{self.base_year}-09-09"
            return DateParseResult(
                raw=raw_date or "",
                iso=iso_fallback,
                is_valid=False,
                warning="Missing date, used fallback.",
            )

        clean = str(raw_date).strip()

        # Check if already ISO format YYYY-MM-DD
        if re.match(r"^\d{4}-\d{2}-\d{2}$", clean):
            return self._validate_iso(clean, clean)

        # Remove day of week words (e.g. 'Wed 9/9/26')
        clean = re.sub(r"^(mon|tue|wed|thu|fri|sat|sun)[a-z]*\s*", "", clean, flags=re.IGNORECASE).strip()

        # Split on slashes, hyphens, dots
        parts = re.split(r"[/\-.\s]+", clean)
        parts = [p for p in parts if p]

        if len(parts) >= 2:
            try:
                day = int(parts[0])
                month = int(parts[1])
            except ValueError:
                iso_fallback = fallback_iso or f"{self.base_year}-09-09"
                return DateParseResult(raw=clean, iso=iso_fallback, is_valid=False, warning=f"Non-numeric date '{clean}'")

            # Validate day and month ranges
            if month > 12 and day <= 12:
                # Swapped day and month (MM/DD)
                day, month = month, day

            if not (1 <= month <= 12 and 1 <= day <= 31):
                iso_fallback = fallback_iso or f"{self.base_year}-09-09"
                return DateParseResult(raw=clean, iso=iso_fallback, is_valid=False, warning=f"Out of range date values: day={day}, month={month}")

            # Year determination
            warning = None
            if len(parts) >= 3:
                try:
                    raw_yr = int(parts[2])
                    if raw_yr < 100:
                        yr = 2000 + raw_yr
                    else:
                        yr = raw_yr
                except ValueError:
                    yr = self.infer_year_for_month(month)
                    warning = f"Could not parse year in '{clean}', inferred {yr}."
            else:
                # Year omitted, infer from academic year and month
                yr = self.infer_year_for_month(month)

            # Check if year is outside academic session range
            if yr < self.base_year or yr > self.end_year:
                warning = f"Year {yr} is outside expected academic year {self.academic_year}."

            iso_date = f"{yr:04d}-{month:02d}-{day:02d}"
            return DateParseResult(raw=clean, iso=iso_date, is_valid=True, warning=warning)

        iso_fallback = fallback_iso or f"{self.base_year}-09-09"
        return DateParseResult(
            raw=clean,
            iso=iso_fallback,
            is_valid=False,
            warning=f"Unrecognized date format '{clean}'",
        )

    def infer_year_for_month(self, month: int) -> int:
        """
        Infer calendar year from month in academic calendar.
        Odd term (July-Dec) -> base_year (e.g. 2026)
        Even term (Jan-June) -> end_year (e.g. 2027)
        """
        if self.term == "Odd":
            # In Odd semester, July-December is base_year. Early Jan may happen for spillover
            return self.base_year if month >= 6 else self.end_year
        else:
            # Even semester, Jan-May is end_year
            return self.end_year if month <= 6 else self.base_year

    def _validate_iso(self, iso_str: str, raw_str: str) -> DateParseResult:
        try:
            dt = datetime.strptime(iso_str, "%Y-%m-%d")
            warning = None
            if dt.year < self.base_year or dt.year > self.end_year:
                warning = f"Year {dt.year} is outside expected academic year {self.academic_year}."
            return DateParseResult(raw=raw_str, iso=iso_str, is_valid=True, warning=warning)
        except ValueError:
            return DateParseResult(raw=raw_str, iso=f"{self.base_year}-09-09", is_valid=False, warning="Invalid ISO date.")
