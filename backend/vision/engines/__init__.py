"""
backend/vision/engines/__init__.py — Vision Engine Package Exports
"""
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
from backend.vision.engines.gemini_engine import GeminiEngine
from backend.vision.engines.claude_engine import ClaudeEngine
from backend.vision.engines.manager import EngineManager

__all__ = [
    "VisionEngine",
    "EngineHealth",
    "PageImage",
    "ReadContext",
    "PageReadResult",
    "HeaderResult",
    "DateSlotResult",
    "RowReadResult",
    "CellReadResult",
    "GeminiEngine",
    "ClaudeEngine",
    "EngineManager",
]
