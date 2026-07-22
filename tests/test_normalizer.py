from src.normalizer import Normalizer


def test_normalize_product_fills_defaults():
    normalizer = Normalizer(currency="EUR", country="ES")
    raw = {"id": 42, "url": " /p/42 ", "title": " Reloj GPS ", "price": "199"}

    product = normalizer.normalize_product(raw, source="shopify")

    assert product["external_id"] == "42"
    assert product["title"] == "Reloj GPS"
    assert product["price"] == 199.0
    assert product["price_original"] == 199.0
    assert product["currency"] == "EUR"
    assert product["country"] == "ES"
    assert product["available"] is True
    assert product["source"] == "shopify"


def test_validate_product_rejects_missing_external_id():
    normalizer = Normalizer()
    product = normalizer.normalize_product({"title": "X", "price": 10})
    product["external_id"] = ""

    assert normalizer.validate_product(product) is False


def test_validate_product_rejects_missing_title():
    normalizer = Normalizer()
    product = normalizer.normalize_product({"id": "1", "price": 10})
    product["title"] = ""

    assert normalizer.validate_product(product) is False


def test_validate_product_rejects_negative_price():
    normalizer = Normalizer()
    product = normalizer.normalize_product({"id": "1", "title": "X", "price": -5})

    assert normalizer.validate_product(product) is False


def test_validate_product_accepts_valid_product():
    normalizer = Normalizer()
    product = normalizer.normalize_product({"id": "1", "title": "X", "price": 0})

    assert normalizer.validate_product(product) is True


def test_batch_normalize_filters_invalid_products():
    normalizer = Normalizer()
    raw_products = [
        {"id": "1", "title": "Valido", "price": 10},
        {"id": "", "title": "Sin id", "price": 10},
        {"id": "2", "title": "", "price": 10},
        {"id": "3", "title": "Precio negativo", "price": -1},
    ]

    normalized = normalizer.batch_normalize(raw_products)

    assert len(normalized) == 1
    assert normalized[0]["external_id"] == "1"
