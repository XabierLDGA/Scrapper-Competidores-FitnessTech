from decimal import Decimal

from src.db import _to_float


def test_to_float_converts_decimal():
    assert _to_float(Decimal("19.99")) == 19.99
    assert isinstance(_to_float(Decimal("19.99")), float)


def test_to_float_passes_through_none():
    assert _to_float(None) is None


def test_to_float_passes_through_float():
    assert _to_float(3.5) == 3.5
