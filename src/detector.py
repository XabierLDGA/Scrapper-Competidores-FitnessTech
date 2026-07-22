import logging
from typing import Optional

logger = logging.getLogger(__name__)


class ChangeDetector:
    def __init__(self, price_change_threshold: float = 5.0):
        """
        price_change_threshold: porcentaje minimo para generar alerta de precio.
        Esta es la UNICA fuente de verdad para el umbral: db.create_price_event
        solo persiste lo que aqui se decide, no lo recalcula.
        """
        self.price_threshold = price_change_threshold

    def detect_price_change(self, old_snapshot: Optional[dict],
                             new_snapshot: dict) -> Optional[dict]:
        """Compara precios y genera evento si cambio >= threshold."""
        if not old_snapshot or old_snapshot.get("price") is None:
            return None

        old_price = old_snapshot["price"]
        new_price = new_snapshot["price"]

        if old_price == new_price:
            return None

        percent_change = ((new_price - old_price) / old_price) * 100

        if abs(percent_change) < self.price_threshold:
            logger.debug(f"Cambio de precio ignorado ({percent_change:.1f}% < {self.price_threshold}%)")
            return None

        return {
            "type": "price_change",
            "old_price": old_price,
            "new_price": new_price,
            "percent_change": percent_change,
            "direction": "increase" if new_price > old_price else "decrease",
        }

    def detect_new_product(self, old_snapshot: Optional[dict]) -> bool:
        """Un producto es nuevo si no hay snapshot anterior."""
        return old_snapshot is None

    def detect_availability_change(self, old_snapshot: Optional[dict],
                                    new_snapshot: dict) -> Optional[dict]:
        """Detecta cambios en disponibilidad."""
        if not old_snapshot or old_snapshot.get("available") == new_snapshot.get("available"):
            return None

        return {
            "type": "availability_change",
            "was_available": old_snapshot.get("available"),
            "now_available": new_snapshot.get("available"),
        }
