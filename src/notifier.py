import logging
import os
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


class Notifier:
    def __init__(self, webhook_url: Optional[str] = None):
        self.webhook_url = webhook_url or os.getenv("N8N_WEBHOOK_URL")

    def send_daily_digest(self, new_products: list, price_events: list):
        """Envia el resumen diario completo (productos nuevos y cambios de
        precio, con todo el detalle) a un webhook de n8n. n8n decide a
        quien y como avisar (email, hoy) - este metodo no sabe nada de
        destinatarios ni formato de email, solo manda los datos.

        Best-effort: un unico intento con timeout corto. Si falla, se
        loguea y no se relanza - un fallo aqui no debe tumbar el crawl
        (mismo comportamiento que tenia el notifier de Slack)."""
        if not self.webhook_url:
            logger.warning("N8N_WEBHOOK_URL no configurado, saltando notificacion")
            return

        if not new_products and not price_events:
            return

        payload = {
            "new_products": [
                {
                    "competitor": p["competitor"],
                    "title": p["title"],
                    "sku": p.get("sku"),
                    "url": p["url"],
                }
                for p in new_products
            ],
            "price_events": [
                {
                    "competitor": e["competitor"],
                    "title": e["title"],
                    "sku": e.get("sku"),
                    "old_price": e["old_price"],
                    "new_price": e["new_price"],
                    "percent_change": e["percent_change"],
                }
                for e in price_events
            ],
        }

        try:
            response = httpx.post(self.webhook_url, json=payload, timeout=10.0)
            response.raise_for_status()
            logger.info(
                f"Resumen diario enviado a n8n: {len(new_products)} nuevos, "
                f"{len(price_events)} cambios de precio"
            )
        except Exception as exc:
            logger.error(f"Error enviando resumen diario a n8n: {exc}")
