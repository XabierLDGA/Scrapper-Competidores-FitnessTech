from src.detector import ChangeDetector


def test_detect_new_product_when_no_snapshot():
    detector = ChangeDetector()
    assert detector.detect_new_product(None) is True
    assert detector.detect_new_product({"price": 10.0}) is False


def test_detect_price_change_ignores_small_change():
    detector = ChangeDetector(price_change_threshold=5.0)
    old_snapshot = {"price": 100.0}
    new_snapshot = {"price": 104.0}  # +4%, por debajo del umbral

    assert detector.detect_price_change(old_snapshot, new_snapshot) is None


def test_detect_price_change_detects_increase_at_threshold():
    detector = ChangeDetector(price_change_threshold=5.0)
    old_snapshot = {"price": 100.0}
    new_snapshot = {"price": 105.0}  # exactamente +5%

    result = detector.detect_price_change(old_snapshot, new_snapshot)

    assert result is not None
    assert result["direction"] == "increase"
    assert result["percent_change"] == 5.0


def test_detect_price_change_detects_decrease():
    detector = ChangeDetector(price_change_threshold=5.0)
    old_snapshot = {"price": 100.0}
    new_snapshot = {"price": 80.0}  # -20%

    result = detector.detect_price_change(old_snapshot, new_snapshot)

    assert result is not None
    assert result["direction"] == "decrease"
    assert result["old_price"] == 100.0
    assert result["new_price"] == 80.0
    assert result["percent_change"] == -20.0


def test_detect_price_change_without_previous_snapshot():
    detector = ChangeDetector()
    assert detector.detect_price_change(None, {"price": 50.0}) is None


def test_detect_price_change_handles_decimal_from_mysql():
    """La BD (mysql-connector) devuelve Decimal para columnas DECIMAL; db.py
    lo convierte a float antes de llegar aqui, asi que el detector solo debe
    ver floats. Este test fija ese contrato."""
    detector = ChangeDetector(price_change_threshold=5.0)
    old_snapshot = {"price": 100.0}
    new_snapshot = {"price": 120.0}

    result = detector.detect_price_change(old_snapshot, new_snapshot)

    assert isinstance(result["percent_change"], float)
    assert result["percent_change"] == 20.0


def test_detect_availability_change():
    detector = ChangeDetector()
    old_snapshot = {"available": True}
    new_snapshot = {"available": False}

    result = detector.detect_availability_change(old_snapshot, new_snapshot)

    assert result == {
        "type": "availability_change",
        "was_available": True,
        "now_available": False,
    }


def test_detect_availability_change_no_change():
    detector = ChangeDetector()
    old_snapshot = {"available": True}
    new_snapshot = {"available": True}

    assert detector.detect_availability_change(old_snapshot, new_snapshot) is None
