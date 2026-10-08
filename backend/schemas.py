"""
backend/schemas.py — Pydantic Validation & Transfer Schemas
"""
from datetime import datetime
from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, ConfigDict, field_validator
import re
from backend.config import settings


# ─────────────────────────────────────────────────────────────
# ENUMS
# ─────────────────────────────────────────────────────────────

class TokenEnum(str, Enum):
    SIGN = "SIGN"
    AB = "AB"
    ARROW_UP = "ARROW_UP"
    ARROW_DOWN = "ARROW_DOWN"
    ARROW_SPAN = "ARROW_SPAN"
    EMPTY_OVAL = "EMPTY_OVAL"
    TEXT_NOTE = "TEXT_NOTE"
    BLANK = "BLANK"
    UNSURE = "UNSURE"


class AttendanceStatus(str, Enum):
    P = "P"
    A = "A"
    NM = "NM"
    NA = "NA"
    UNCERTAIN = "UNCERTAIN"


# ─────────────────────────────────────────────────────────────
# STUDENT SCHEMAS
# ─────────────────────────────────────────────────────────────

class StudentBase(BaseModel):
    sr_no: int
    roll_no: str
    name: str
    batch: int = 1

    @field_validator("roll_no")
    @classmethod
    def validate_roll_no(cls, v: str) -> str:
        clean = v.strip().upper()
        if not re.match(settings.ROLL_NO_REGEX, clean):
            raise ValueError(f"Invalid VIT Roll Number '{clean}'. Expected format like '24108B0001' or '25108B2001'.")
        return clean

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        return v.strip().upper()


class StudentCreate(StudentBase):
    pass


class StudentResponse(StudentBase):
    id: int
    subject_id: str
    model_config = ConfigDict(from_attributes=True)


class StudentUpdate(BaseModel):
    name: Optional[str] = None
    batch: Optional[int] = None
    sr_no: Optional[int] = None
    roll_no: Optional[str] = None


class StudentCommitInfo(BaseModel):
    roll_no: str
    name: str = ""
    batch: int = 1
    sr_no: Optional[int] = None


# ─────────────────────────────────────────────────────────────
# SUBJECT SCHEMAS
# ─────────────────────────────────────────────────────────────

class SubjectBase(BaseModel):
    name: str = Field(..., json_schema_extra={"example": "System Software"})
    code: str = Field(..., json_schema_extra={"example": "SS"})
    class_name: str = Field(default="Semester 5", json_schema_extra={"example": "Semester 5"})
    branch: Optional[str] = Field(default="Electronics & Computer Science", json_schema_extra={"example": "Electronics & Computer Science"})
    division: str = Field(default="B", json_schema_extra={"example": "B"})
    type: str = Field(default="Theory", json_schema_extra={"example": "Theory"})
    faculty: str = Field(..., json_schema_extra={"example": "SHP"})
    academic_year: str = Field(default="2026-27 (Odd)", json_schema_extra={"example": "2026-27 (Odd)"})


class SubjectCreate(SubjectBase):
    id: Optional[str] = None
    roster: Optional[List[StudentCreate]] = None


class SubjectStats(BaseModel):
    total_sessions: int = 0
    enrolled_students: int = 0
    average_attendance_pct: float = 0.0
    students_below_75: int = 0


class SubjectResponse(SubjectBase):
    id: str
    created_at: datetime
    stats: SubjectStats = Field(default_factory=SubjectStats)
    model_config = ConfigDict(from_attributes=True)


class SubjectDetailResponse(SubjectResponse):
    students: List[StudentResponse] = []
    scans_count: int = 0
    sessions: List[str] = []


# ─────────────────────────────────────────────────────────────
# EXTRACTOR TOKEN & GRID SCHEMAS
# ─────────────────────────────────────────────────────────────

class HeaderInfo(BaseModel):
    class_name: Optional[str] = "Semester 5"
    branch: Optional[str] = "Electronics & Computer Science"
    subject: Optional[str] = "SS"
    faculty: Optional[str] = "SHP"
    division: Optional[str] = "B"
    type: Optional[str] = "Theory"
    academic_year: Optional[str] = "2026-27 (Odd)"
    week_no: Optional[str] = None


class DateColumn(BaseModel):
    col_idx: int
    raw_date: str = "Date"          # e.g., "9/9/26" or "Date missing (column 1)"
    iso_date: str = "2026-09-09"    # e.g., "2026-09-09"
    confidence: float = 1.0
    needs_confirmation: bool = False
    suggested_date: Optional[str] = None

    @field_validator("raw_date", mode="before")
    @classmethod
    def sanitize_raw_date(cls, v: Any) -> str:
        if v is None:
            return "Date"
        s = str(v).strip()
        return s if s else "Date"

    @field_validator("iso_date", mode="before")
    @classmethod
    def sanitize_iso_date(cls, v: Any) -> str:
        if v is None:
            return "2026-09-09"
        s = str(v).strip()
        return s if s else "2026-09-09"



class CellToken(BaseModel):
    col_idx: int
    token: TokenEnum
    confidence: float = 1.0
    ink_color: Optional[str] = "blue"


class CellResolved(BaseModel):
    col_idx: int
    token: TokenEnum
    status: AttendanceStatus
    confidence: float = 1.0
    reason: str = "Direct extraction"
    ambiguous: bool = False


class RowExtraction(BaseModel):
    sr_no: int = 1
    roll_no: str = ""
    name: str = ""
    batch: int = 1
    cells: List[CellResolved] = []

    @field_validator("roll_no", mode="before")
    @classmethod
    def sanitize_roll_no(cls, v: Any) -> str:
        if v is None:
            return ""
        return str(v).strip().upper()

    @field_validator("name", mode="before")
    @classmethod
    def sanitize_name(cls, v: Any) -> str:
        if v is None:
            return ""
        return str(v).strip().upper()


class ScanPreviewResponse(BaseModel):
    scan_id: Optional[int] = None
    subject_id: str
    header: HeaderInfo
    date_columns: List[DateColumn]
    rows: List[RowExtraction]
    image_url: Optional[str] = None
    has_uncertain: bool = False
    warnings: List[str] = []
    quality_notes: Optional[str] = None



# ─────────────────────────────────────────────────────────────
# COMMIT & MERGE SCHEMAS
# ─────────────────────────────────────────────────────────────

class CellCommitItem(BaseModel):
    roll_no: str
    date: str
    status: AttendanceStatus


class CommitRequest(BaseModel):
    scan_id: Optional[int] = None
    date_columns: List[str]
    records: List[CellCommitItem]
    students: Optional[List[StudentCommitInfo]] = None
    overwrite_conflicts: bool = False


class CommitResponse(BaseModel):
    subject_id: str
    added_dates: List[str]
    updated_students_count: int
    conflicts_detected: List[Dict[str, Any]] = []
    class_average_pct: float
    master_download_url: str
