"""
backend/vision/engines/manager.py — AttendAI Vision Engine Fallback Manager & Cache
"""
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

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
from backend.vision.engines.gemini_engine import GeminiEngine
from backend.vision.engines.claude_engine import ClaudeEngine

logger = logging.getLogger("attendai.vision.manager")


# Recent page diagnostics (engine, slots, rows, token counts per slot)
RECENT_PAGE_STATS: List[Dict[str, Any]] = []


class EngineManager:
    """
    Orchestrates AttendAI Vision engines with automatic failover, health monitoring,
    disk-based SHA256 caching, and customer-facing branded status reporting.
    """

    def __init__(self, engine_order: Optional[str] = None):
        self.order_str = engine_order or settings.ENGINE_ORDER
        self.engine_names = [e.strip().lower() for e in self.order_str.split(",") if e.strip()]

        # Initialize cloud instances
        self.engines: Dict[str, VisionEngine] = {
            "gemini": GeminiEngine(),
            "claude": ClaudeEngine(),
        }

        # Cache directory
        self.cache_dir = settings.CACHE_DIR / "vision"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    @classmethod
    def get_recent_stats(cls) -> List[Dict[str, Any]]:
        return list(RECENT_PAGE_STATS)

    def check_health(self) -> Tuple[str, str, Dict[str, EngineHealth]]:
        """
        Check health of all configured cloud engines.
        Returns:
            (status_chip_text, tooltip_text, health_details_dict)
            Chip states: 'AttendAI Vision: Online' | 'Manual mode' (no provider names)
        """
        details: Dict[str, EngineHealth] = {}
        first_healthy_cloud = None

        for name in self.engine_names:
            engine = self.engines.get(name)
            if not engine:
                continue
            h = engine.health()
            details[name] = h
            if h.ok and first_healthy_cloud is None:
                first_healthy_cloud = name

        if first_healthy_cloud:
            chip = "AttendAI Vision: Online"
            tooltip = "AttendAI Vision cloud is online and ready."
        else:
            chip = "Manual mode"
            tooltip = "AttendAI Vision is offline right now. You can still mark attendance manually."

        return chip, tooltip, details

    def _validate_result(self, result: Optional[PageReadResult]) -> bool:
        """
        Validate result before caching or returning from cache:
        - Must have rows
        - Must not be marked as manual_mode
        - Must have at least one non-BLANK mark
        """
        if not result or not result.rows or result.engine_used == "manual_mode":
            return False
        total_non_blank = sum(
            1 for r in result.rows for c in r.cells if c.token not in (TokenEnum.BLANK, TokenEnum.EMPTY_OVAL)
        )
        return total_non_blank > 0

    def _record_and_log_page_stats(self, result: PageReadResult, image_label: str):
        """Log token counts per slot without student names and record for diagnostics."""
        slots = sorted(list({c.slot for r in result.rows for c in r.cells}))
        token_counts_by_slot: Dict[int, Dict[str, int]] = {}
        for s in slots:
            token_counts_by_slot[s] = {"SIGN": 0, "AB": 0, "ARROW": 0, "BLANK": 0, "UNSURE": 0}

        for r in result.rows:
            for c in r.cells:
                slot_dict = token_counts_by_slot.setdefault(c.slot, {"SIGN": 0, "AB": 0, "ARROW": 0, "BLANK": 0, "UNSURE": 0})
                t_str = c.token.value if hasattr(c.token, "value") else str(c.token)
                if "ARROW" in t_str:
                    slot_dict["ARROW"] += 1
                elif t_str in slot_dict:
                    slot_dict[t_str] += 1
                else:
                    slot_dict["UNSURE"] += 1

        stat_entry = {
            "page": image_label,
            "engine": result.engine_used,
            "cached": getattr(result, "cached", False),
            "num_slots": len(slots),
            "num_rows": len(result.rows),
            "token_counts_by_slot": token_counts_by_slot,
        }
        RECENT_PAGE_STATS.append(stat_entry)
        if len(RECENT_PAGE_STATS) > 20:
            RECENT_PAGE_STATS.pop(0)

        logger.info(
            "PAGE_STATS [Engine: %s | Cached: %s | Slots: %d | Rows: %d | Token Counts: %s]",
            result.engine_used,
            getattr(result, "cached", False),
            len(slots),
            len(result.rows),
            token_counts_by_slot,
        )

    def clear_cache(self, image_hash: Optional[str] = None):
        """Invalidate cache for a specific image hash or all vision caches."""
        if image_hash:
            cache_file = self.cache_dir / f"{image_hash}.json"
            if cache_file.exists():
                try:
                    cache_file.unlink()
                    logger.info("Purged vision cache for %s", image_hash[:8])
                except Exception as e:
                    logger.warning("Could not delete cache file: %s", e)
        else:
            for f in self.cache_dir.glob("*.json"):
                try:
                    f.unlink()
                except Exception:
                    pass
            logger.info("Purged all vision caches.")

    def read_page_with_fallback(self, page: PageImage, ctx: ReadContext) -> PageReadResult:
        """
        Read an attendance page with disk caching and automatic multi-engine fallback.
        """
        page_label = Path(page.path).name if page.path else page.image_hash[:8]

        # 1. Check cache first
        cache_file = self.cache_dir / f"{page.image_hash}.json"
        if cache_file.exists():
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    cached_data = json.load(f)
                result = PageReadResult.model_validate(cached_data)
                if self._validate_result(result):
                    result.cached = True
                    logger.info("Retrieved validated cached AttendAI Vision result for %s", page_label)
                    self._record_and_log_page_stats(result, page_label)
                    return result
                else:
                    logger.warning("Purging empty/failed cached result for %s", page_label)
                    cache_file.unlink(missing_ok=True)
            except Exception as e:
                logger.warning("Cache read failed: %s. Removing corrupt file.", e)
                cache_file.unlink(missing_ok=True)

        # 2. Try engines in configured order
        last_error = None
        for name in self.engine_names:
            engine = self.engines.get(name)
            if not engine:
                continue

            try:
                logger.info("Attempting extraction with %s...", name)
                result = engine.read_page(page, ctx)
                if result and self._validate_result(result):
                    # Save to cache only when valid
                    try:
                        with open(cache_file, "w", encoding="utf-8") as f:
                            json.dump(result.model_dump(), f, indent=2)
                    except Exception as cache_err:
                        logger.warning("Failed to save vision cache: %s", cache_err)

                    self._record_and_log_page_stats(result, page_label)
                    return result
                elif result and result.rows:
                    logger.warning("Engine '%s' returned rows with only blank cells. Trying next engine...", name)
            except Exception as exc:
                last_error = exc
                logger.warning("Engine '%s' failed on page %s: %s. Falling back to next engine...", name, page_label, exc)

        # 3. Final fallback: Return manual mode grid with clear error message (NEVER cached)
        err_msg = f"AttendAI Vision could not read page ({last_error or 'No engines available'}). Please retry or switch to Manual mode."
        logger.warning("All engines failed or exhausted. Returning manual mode grid with error: %s", err_msg)
        return self._generate_manual_mode_grid(ctx, err_msg)

    def _generate_manual_mode_grid(self, ctx: ReadContext, err_msg: str) -> PageReadResult:
        roster = ctx.roster_hints or []
        num_rows = len(roster) if roster else 30
        rows = []

        for idx in range(num_rows):
            if idx < len(roster):
                roll = roster[idx].get("roll_no", f"24108B{idx+1:04d}")
                name = roster[idx].get("name", f"STUDENT {idx+1}")
                r_batch = roster[idx].get("batch")
                if r_batch is not None:
                    batch = int(r_batch)
                elif idx < 19:
                    batch = 1
                elif idx < 30:
                    batch = 2
                elif idx < 50:
                    batch = 3
                else:
                    batch = 4
            else:
                roll = f"24108B{idx+1:04d}"
                name = f"STUDENT {idx+1}"
                if idx < 19:
                    batch = 1
                elif idx < 30:
                    batch = 2
                elif idx < 50:
                    batch = 3
                else:
                    batch = 4

            cells = [
                CellReadResult(slot=i + 1, token=TokenEnum.BLANK, confidence=0.0)
                for i in range(4)
            ]
            rows.append(RowReadResult(roll_no=roll, name=name, batch=batch, sr_no=idx + 1, cells=cells))

        return PageReadResult(
            header=HeaderResult(
                class_name=ctx.class_name or "T.Y.B.TECH",
                subject="SS",
                faculty="SHP",
                division=ctx.division or "B",
                type="Theory",
                academic_year=ctx.academic_year or "2026-27 (Odd)",
            ),
            date_slots=[DateSlotResult(slot=i + 1, raw=f"Slot {i+1}", confidence=0.0) for i in range(4)],
            rows=rows,
            engine_used="manual_mode",
            error=f"AttendAI Vision is offline right now. You can still mark attendance manually. ({err_msg})",
        )


