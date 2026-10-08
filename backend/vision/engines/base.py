"""
backend/vision/engines/base.py — Common Vision Engine Protocol & Data Contracts
"""
from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path
from typing import List, Optional, Protocol, Union, Dict, Any
from pydantic import BaseModel, Field

from backend.schemas import TokenEnum, AttendanceStatus


@dataclass
class EngineHealth:
    ok: bool
    name: str                           # 'gemini', 'claude', 'local'
    reason: str
    provider_model: Optional[str] = None  # internal only, hidden from client UI


@dataclass
class PageImage:
    path: Path
    bytes: Optional[bytes] = None
    image_hash: str = ""

    def __post_init__(self):
        if not self.image_hash:
            if self.bytes:
                self.image_hash = sha256(self.bytes).hexdigest()
            elif self.path and Path(self.path).exists():
                with open(self.path, "rb") as f:
                    content = f.read()
                    self.bytes = content
                    self.image_hash = sha256(content).hexdigest()


@dataclass
class ReadContext:
    subject_id: Optional[str] = None
    academic_year: Optional[str] = "2026-27 (Odd)"
    class_name: Optional[str] = "T.Y.B.TECH"
    division: Optional[str] = "B"
    page_number: int = 1
    total_pages: int = 1
    privacy_mode: str = "columns_only"  # 'columns_only' | 'full_page'
    roster_hints: Optional[List[Dict[str, Any]]] = None


class CellReadResult(BaseModel):
    slot: int                          # 1-based or 0-based column index
    token: TokenEnum = TokenEnum.BLANK
    confidence: float = 0.95
    ink: Optional[str] = "blue"
    circled: bool = False
    text: str = ""


class RowReadResult(BaseModel):
    roll_no: str = ""
    name: str = ""
    batch: int = 1
    sr_no: Optional[int] = None
    cells: List[CellReadResult] = Field(default_factory=list)


class DateSlotResult(BaseModel):
    slot: int
    raw: str = "Date"
    iso: Optional[str] = "2026-09-09"
    confidence: float = 0.95


class HeaderResult(BaseModel):
    class_name: str = "T.Y.B.TECH"
    subject: str = "SS"
    faculty: str = "SHP"
    division: str = "B"
    type: str = "Theory"
    academic_year: str = "2026-27 (Odd)"
    week_no: Optional[str] = None


class PageReadResult(BaseModel):
    header: HeaderResult = Field(default_factory=HeaderResult)
    date_slots: List[DateSlotResult] = Field(default_factory=list)
    rows: List[RowReadResult] = Field(default_factory=list)
    engine_used: str = "attendai_vision"  # Branded engine identifier
    cached: bool = False
    error: Optional[str] = None


class VisionEngine(Protocol):
    name: str

    def health(self) -> EngineHealth:
        """Run tiny real test call. Returns ok/error + reason."""
        ...

    def read_page(self, page: PageImage, ctx: ReadContext) -> PageReadResult:
        """Read a single attendance sheet page image and return structured result."""
        ...
