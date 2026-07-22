import logging

logger = logging.getLogger(__name__)


class Normalizer:
    def __init__(self, currency: str = "EUR", country: str = "ES"):
        self.currency = currency
        self.country = country

    def normalize_product(self, raw_product: dict, source: str = "html") -> dict:
        """Convierte un producto crawleado a formato estandar."""
        return {
            "external_id": str(raw_product.get("id", "")).strip(),
            "url": raw_product.get("url", "").strip(),
            "title": raw_product.get("title", "Unknown").strip(),
            "price": float(raw_product.get("price", 0)),
            "price_original": float(raw_product.get("original_price", raw_product.get("price", 0))),
            "currency": raw_product.get("currency", self.currency),
            "country": raw_product.get("country", self.country),
            "available": raw_product.get("available", True),
            "shipping_text": raw_product.get("shipping_text", ""),
            "source": source,
        }

    def validate_product(self, product: dict) -> bool:
        """Verifica que el producto tiene datos minimos."""
        if not product.get("external_id"):
            logger.warning(f"Producto sin external_id: {product}")
            return False
        if not product.get("title"):
            logger.warning(f"Producto sin title: {product}")
            return False
        if product.get("price", 0) < 0:
            logger.warning(f"Precio negativo: {product}")
            return False
        return True

    def batch_normalize(self, raw_products: list[dict], source: str = "html") -> list[dict]:
        """Normaliza un batch de productos y filtra los invalidos."""
        normalized = []
        for raw in raw_products:
            normalized_product = self.normalize_product(raw, source)
            if self.validate_product(normalized_product):
                normalized.append(normalized_product)
        logger.info(f"Normalizados {len(normalized)}/{len(raw_products)} productos")
        return normalized
