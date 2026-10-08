"""
backend/vision/arrow_resolver.py — Pure-Logic Arrow & Range Propagation Engine
"""
from dataclasses import dataclass
from typing import List, Optional
from backend.schemas import TokenEnum, AttendanceStatus


@dataclass
class InputCell:
    row_idx: int
    batch_id: int
    token: TokenEnum
    confidence: float = 1.0
    extra: Optional[str] = None


@dataclass
class ResolvedCell:
    row_idx: int
    batch_id: int
    token: TokenEnum
    status: AttendanceStatus
    confidence: float
    reason: str
    ambiguous: bool = False


class ArrowResolver:
    """
    Pure-logic arrow and range resolver for a single column of attendance marks.
    No ML involved. Follows deterministic propagation rules with safety bounds.
    """

    def __init__(self, allow_cross_batch: bool = False):
        self.allow_cross_batch = allow_cross_batch

    def resolve_column(self, cells: List[InputCell]) -> List[ResolvedCell]:
        """
        Resolve an ordered list of cells (one per student row) for a single session column.
        """
        n = len(cells)
        if n == 0:
            return []

        # Start with base direct mapping
        resolved = []
        for c in cells:
            if c.token == TokenEnum.SIGN:
                resolved.append(ResolvedCell(
                    row_idx=c.row_idx,
                    batch_id=c.batch_id,
                    token=c.token,
                    status=AttendanceStatus.P,
                    confidence=c.confidence,
                    reason="Direct signature",
                    ambiguous=False,
                ))
            elif c.token == TokenEnum.AB:
                resolved.append(ResolvedCell(
                    row_idx=c.row_idx,
                    batch_id=c.batch_id,
                    token=c.token,
                    status=AttendanceStatus.A,
                    confidence=c.confidence,
                    reason="Direct absent mark",
                    ambiguous=False,
                ))
            elif c.token == TokenEnum.BLANK:
                resolved.append(ResolvedCell(
                    row_idx=c.row_idx,
                    batch_id=c.batch_id,
                    token=c.token,
                    status=AttendanceStatus.NM,
                    confidence=c.confidence,
                    reason="Empty cell",
                    ambiguous=False,
                ))
            elif c.token == TokenEnum.UNSURE:
                resolved.append(ResolvedCell(
                    row_idx=c.row_idx,
                    batch_id=c.batch_id,
                    token=c.token,
                    status=AttendanceStatus.UNCERTAIN,
                    confidence=c.confidence,
                    reason="Unclear or conflicting handwriting",
                    ambiguous=True,
                ))
            elif c.token == TokenEnum.EMPTY_OVAL:
                resolved.append(ResolvedCell(
                    row_idx=c.row_idx,
                    batch_id=c.batch_id,
                    token=c.token,
                    status=AttendanceStatus.UNCERTAIN,
                    confidence=0.5,
                    reason="Empty oval contour (ambiguous marking)",
                    ambiguous=True,
                ))
            elif c.token == TokenEnum.TEXT_NOTE:
                reason_txt = f"Cell contains text annotation: '{c.extra}'" if c.extra else "Cell contains text annotation"
                is_present_text = bool(c.extra and "present" in c.extra.lower())
                resolved.append(ResolvedCell(
                    row_idx=c.row_idx,
                    batch_id=c.batch_id,
                    token=c.token,
                    status=AttendanceStatus.UNCERTAIN,
                    confidence=0.6 if is_present_text else 0.4,
                    reason=reason_txt + (" (Suggested: Present)" if is_present_text else ""),
                    ambiguous=True,
                ))
            else:
                # Arrow token, to be resolved below
                resolved.append(ResolvedCell(
                    row_idx=c.row_idx,
                    batch_id=c.batch_id,
                    token=c.token,
                    status=AttendanceStatus.UNCERTAIN,
                    confidence=c.confidence,
                    reason="Pending arrow resolution",
                    ambiguous=False,
                ))

        # Pass 1: Resolve ARROW_UP
        # An ARROW_UP at index i looks downward for an anchor AB at index j > i
        for i in range(n):
            if cells[i].token == TokenEnum.ARROW_UP:
                anchor_idx = None
                blocked = False

                for j in range(i + 1, n):
                    # Check batch boundary
                    if not self.allow_cross_batch and cells[j].batch_id != cells[i].batch_id:
                        blocked = True
                        break
                    # If we encounter a SIGN or BLANK before finding AB, chain is broken
                    if cells[j].token in (TokenEnum.SIGN, TokenEnum.BLANK):
                        blocked = True
                        break
                    # If we encounter AB, we found our anchor
                    if cells[j].token == TokenEnum.AB:
                        anchor_idx = j
                        break
                    # Another arrow token continues the chain
                    if cells[j].token in (TokenEnum.ARROW_UP, TokenEnum.ARROW_SPAN):
                        continue
                    if cells[j].token == TokenEnum.ARROW_DOWN:
                        # Arrow pointing opposite direction before AB is ambiguous
                        blocked = True
                        break

                if anchor_idx is not None and not blocked:
                    resolved[i].status = AttendanceStatus.A
                    resolved[i].reason = f"Propagated absent via upward arrow anchored to row {cells[anchor_idx].row_idx}"
                    resolved[i].confidence = min(cells[i].confidence, cells[anchor_idx].confidence)
                    resolved[i].ambiguous = False
                else:
                    resolved[i].status = AttendanceStatus.UNCERTAIN
                    resolved[i].reason = "Unanchored or blocked upward arrow"
                    resolved[i].ambiguous = True

        # Pass 2: Resolve ARROW_DOWN
        # An ARROW_DOWN at index i looks upward for an anchor AB at index j < i
        for i in range(n):
            if cells[i].token == TokenEnum.ARROW_DOWN:
                anchor_idx = None
                blocked = False

                for j in range(i - 1, -1, -1):
                    # Check batch boundary
                    if not self.allow_cross_batch and cells[j].batch_id != cells[i].batch_id:
                        blocked = True
                        break
                    # If we hit SIGN or BLANK, chain is broken
                    if cells[j].token in (TokenEnum.SIGN, TokenEnum.BLANK):
                        blocked = True
                        break
                    # Found AB anchor
                    if cells[j].token == TokenEnum.AB:
                        anchor_idx = j
                        break
                    # Continuing arrow
                    if cells[j].token in (TokenEnum.ARROW_DOWN, TokenEnum.ARROW_SPAN):
                        continue
                    if cells[j].token == TokenEnum.ARROW_UP:
                        blocked = True
                        break

                if anchor_idx is not None and not blocked:
                    resolved[i].status = AttendanceStatus.A
                    resolved[i].reason = f"Propagated absent via downward arrow anchored to row {cells[anchor_idx].row_idx}"
                    resolved[i].confidence = min(cells[i].confidence, cells[anchor_idx].confidence)
                    resolved[i].ambiguous = False
                else:
                    resolved[i].status = AttendanceStatus.UNCERTAIN
                    resolved[i].reason = "Unanchored or blocked downward arrow"
                    resolved[i].ambiguous = True

        # Pass 3: Resolve ARROW_SPAN (long vertical bracket line through cells)
        for i in range(n):
            if cells[i].token == TokenEnum.ARROW_SPAN:
                # Look both upward and downward within the contiguous span for an AB anchor
                anchor_up = None
                for j in range(i - 1, -1, -1):
                    if not self.allow_cross_batch and cells[j].batch_id != cells[i].batch_id:
                        break
                    if cells[j].token == TokenEnum.AB:
                        anchor_up = j
                        break
                    if cells[j].token not in (TokenEnum.ARROW_SPAN, TokenEnum.ARROW_UP, TokenEnum.ARROW_DOWN):
                        break

                anchor_down = None
                for j in range(i + 1, n):
                    if not self.allow_cross_batch and cells[j].batch_id != cells[i].batch_id:
                        break
                    if cells[j].token == TokenEnum.AB:
                        anchor_down = j
                        break
                    if cells[j].token not in (TokenEnum.ARROW_SPAN, TokenEnum.ARROW_UP, TokenEnum.ARROW_DOWN):
                        break

                if anchor_up is not None or anchor_down is not None:
                    chosen_anchor = anchor_up if anchor_up is not None else anchor_down
                    resolved[i].status = AttendanceStatus.A
                    resolved[i].reason = f"Propagated absent inside spanning line anchored to row {cells[chosen_anchor].row_idx}"
                    resolved[i].confidence = cells[i].confidence
                    resolved[i].ambiguous = False
                else:
                    resolved[i].status = AttendanceStatus.UNCERTAIN
                    resolved[i].reason = "Spanning vertical line without valid AB anchor"
                    resolved[i].ambiguous = True

        return resolved
