"""
backend/tests/test_arrow_resolver.py — Pytest Suite for Pure-Logic Arrow Resolver
"""
import pytest
from backend.schemas import TokenEnum, AttendanceStatus
from backend.vision.arrow_resolver import ArrowResolver, InputCell


@pytest.fixture
def resolver():
    return ArrowResolver(allow_cross_batch=False)


def test_direct_token_mapping(resolver):
    cells = [
        InputCell(row_idx=1, batch_id=1, token=TokenEnum.SIGN),
        InputCell(row_idx=2, batch_id=1, token=TokenEnum.AB),
        InputCell(row_idx=3, batch_id=1, token=TokenEnum.BLANK),
        InputCell(row_idx=4, batch_id=1, token=TokenEnum.UNSURE),
    ]
    res = resolver.resolve_column(cells)
    assert [r.status for r in res] == [
        AttendanceStatus.P,
        AttendanceStatus.A,
        AttendanceStatus.NM,
        AttendanceStatus.UNCERTAIN,
    ]


def test_real_case_sample_9_sept_batch_1(resolver):
    """
    Real VIT register case:
    Sr 9: ↑ (ARROW_UP)
    Sr 10: AB
    Sr 11: ↓ (ARROW_DOWN)
    Sr 12: ↓ (ARROW_DOWN)
    Sr 13: SIGN
    All rows 9-12 must resolve to ABSENT ('A').
    """
    cells = [
        InputCell(row_idx=9, batch_id=1, token=TokenEnum.ARROW_UP),
        InputCell(row_idx=10, batch_id=1, token=TokenEnum.AB),
        InputCell(row_idx=11, batch_id=1, token=TokenEnum.ARROW_DOWN),
        InputCell(row_idx=12, batch_id=1, token=TokenEnum.ARROW_DOWN),
        InputCell(row_idx=13, batch_id=1, token=TokenEnum.SIGN),
    ]
    res = resolver.resolve_column(cells)
    statuses = [r.status for r in res]
    assert statuses == [
        AttendanceStatus.A,
        AttendanceStatus.A,
        AttendanceStatus.A,
        AttendanceStatus.A,
        AttendanceStatus.P,
    ]
    assert "anchored to row 10" in res[0].reason
    assert "anchored to row 10" in res[2].reason
    assert "anchored to row 10" in res[3].reason


def test_real_case_sample_9_sept_batch_2(resolver):
    """
    Real VIT register case:
    Sr 24: SIGN
    Sr 25: ↑
    Sr 26: AB
    Sr 27: ↓
    Sr 28: SIGN
    Sr 29: SIGN
    Sr 30: AB
    """
    cells = [
        InputCell(row_idx=24, batch_id=2, token=TokenEnum.SIGN),
        InputCell(row_idx=25, batch_id=2, token=TokenEnum.ARROW_UP),
        InputCell(row_idx=26, batch_id=2, token=TokenEnum.AB),
        InputCell(row_idx=27, batch_id=2, token=TokenEnum.ARROW_DOWN),
        InputCell(row_idx=28, batch_id=2, token=TokenEnum.SIGN),
        InputCell(row_idx=29, batch_id=2, token=TokenEnum.SIGN),
        InputCell(row_idx=30, batch_id=2, token=TokenEnum.AB),
    ]
    res = resolver.resolve_column(cells)
    statuses = [r.status for r in res]
    assert statuses == [
        AttendanceStatus.P,
        AttendanceStatus.A,
        AttendanceStatus.A,
        AttendanceStatus.A,
        AttendanceStatus.P,
        AttendanceStatus.P,
        AttendanceStatus.A,
    ]


def test_arrow_span_resolution(resolver):
    """
    Vertical bracket spanning line anchored to row 27 AB.
    """
    cells = [
        InputCell(row_idx=25, batch_id=2, token=TokenEnum.ARROW_SPAN),
        InputCell(row_idx=26, batch_id=2, token=TokenEnum.ARROW_SPAN),
        InputCell(row_idx=27, batch_id=2, token=TokenEnum.AB),
        InputCell(row_idx=28, batch_id=2, token=TokenEnum.ARROW_SPAN),
        InputCell(row_idx=29, batch_id=2, token=TokenEnum.ARROW_SPAN),
    ]
    res = resolver.resolve_column(cells)
    assert all(r.status == AttendanceStatus.A for r in res)


def test_unanchored_arrow_is_uncertain(resolver):
    """
    Arrow with no AB anchor in reach must resolve to UNCERTAIN.
    """
    cells = [
        InputCell(row_idx=1, batch_id=1, token=TokenEnum.ARROW_UP),
        InputCell(row_idx=2, batch_id=1, token=TokenEnum.SIGN),
    ]
    res = resolver.resolve_column(cells)
    assert res[0].status == AttendanceStatus.UNCERTAIN
    assert res[0].ambiguous is True


def test_chain_broken_by_sign_or_blank(resolver):
    """
    Arrow chain stops at SIGN or BLANK cell.
    """
    cells = [
        InputCell(row_idx=1, batch_id=1, token=TokenEnum.AB),
        InputCell(row_idx=2, batch_id=1, token=TokenEnum.ARROW_DOWN),
        InputCell(row_idx=3, batch_id=1, token=TokenEnum.SIGN),
        InputCell(row_idx=4, batch_id=1, token=TokenEnum.ARROW_DOWN),
    ]
    res = resolver.resolve_column(cells)
    assert res[0].status == AttendanceStatus.A
    assert res[1].status == AttendanceStatus.A
    assert res[2].status == AttendanceStatus.P
    assert res[3].status == AttendanceStatus.UNCERTAIN  # broken by SIGN


def test_batch_boundary_protection(resolver):
    """
    Arrows must NOT propagate across Batch boundaries unless explicitly allowed.
    """
    cells = [
        InputCell(row_idx=19, batch_id=1, token=TokenEnum.ARROW_UP),  # in Batch 1
        InputCell(row_idx=20, batch_id=2, token=TokenEnum.AB),        # in Batch 2
    ]
    res = resolver.resolve_column(cells)
    assert res[0].status == AttendanceStatus.UNCERTAIN  # Cannot jump across batch 1 -> 2
