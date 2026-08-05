import asyncio
import logging
import os

from dotenv import load_dotenv

from src.crawler import Crawler
from src.db import Database
from src.detector import ChangeDetector
from src.normalizer import Normalizer
from src.notifier import Notifier

load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def crawl_competitor_products(crawler: Crawler, competitor: dict) -> tuple[list[dict], str]:
    """Elige la estrategia de descarga segun el competidor: Magento detras
    de Cloudflare (Playwright), Shopify (/products.json), o HTML generico
    como ultimo recurso."""
    if competitor.get("platform") == "magento":
        products = await crawler.crawl_magento_categories(competitor["website_url"])
        return products, "magento"

    if competitor.get("product_api_url"):
        products = await crawler.crawl_shopify_products(competitor["product_api_url"])
        if products:
            return products, "shopify"

    logger.info(f"  -> Sin datos de Shopify, probando scraping HTML de {competitor['website_url']}")
    products = await crawler.crawl_html_products(competitor["website_url"])
    return products, "html"


async def process_product(db: Database, detector: ChangeDetector, notifier: Notifier,
                           product: dict, competitor_id: int, competitor_name: str) -> None:
    product_id = db.insert_or_update_product(
        competitor_id=competitor_id,
        external_id=product["external_id"],
        url=product["url"],
        title=product["title"],
        sku=product.get("sku"),
    )

    old_snapshot = db.get_last_snapshot(product_id)

    db.insert_snapshot(
        product_id=product_id,
        price=product["price"],
        price_original=product["price_original"],
        currency=product["currency"],
        country=product["country"],
        available=product["available"],
        shipping_text=product["shipping_text"],
    )

    if detector.detect_new_product(old_snapshot):
        logger.info(f"    [nuevo] {product['title'][:60]}")
        notifier.send_slack_new_product(product, competitor_name)
        return

    price_change = detector.detect_price_change(old_snapshot, product)
    if price_change:
        logger.info(
            f"    [precio] EUR {price_change['old_price']:.2f} -> EUR {price_change['new_price']:.2f} "
            f"({price_change['percent_change']:+.1f}%)"
        )
        db.create_price_event(
            product_id=product_id,
            event_type=price_change["direction"],
            old_price=price_change["old_price"],
            new_price=price_change["new_price"],
            percent_change=price_change["percent_change"],
        )
        notifier.send_slack_price_change(
            product,
            price_change["old_price"],
            price_change["new_price"],
            price_change["percent_change"],
            competitor_name,
        )

    availability_change = detector.detect_availability_change(old_snapshot, product)
    if availability_change:
        logger.info(f"    [disponibilidad] {availability_change}")
        db.create_availability_event(
            product_id=product_id,
            was_available=availability_change["was_available"],
            now_available=availability_change["now_available"],
        )


async def main() -> dict:
    db = Database(
        host=os.getenv("DB_HOST", "localhost"),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", ""),
        database=os.getenv("DB_NAME", "competitor_monitor"),
        port=int(os.getenv("DB_PORT", "3306")),
    )
    crawler = Crawler()
    normalizer = Normalizer(currency="EUR", country="ES")
    detector = ChangeDetector(price_change_threshold=5.0)
    notifier = Notifier(slack_token=os.getenv("SLACK_BOT_TOKEN"))

    logger.info("=" * 60)
    logger.info("Iniciando crawl de competidores")
    logger.info("=" * 60)

    competitors = db.get_competitors()
    if not competitors:
        logger.warning("No hay competidores configurados en la BD")
        logger.info("Anade competidores con db.add_competitor(...)")
        return {"new_products": 0, "pending_events": 0, "errors": []}

    errors = []
    try:
        for competitor in competitors:
            logger.info(f"\nCrawleando: {competitor['name']}")
            try:
                raw_products, source = await crawl_competitor_products(crawler, competitor)
                if not raw_products:
                    logger.warning("  No se pudieron obtener productos")
                    continue

                logger.info(f"  {len(raw_products)} productos descargados ({source})")
                normalized = normalizer.batch_normalize(raw_products, source=source)

                for product in normalized:
                    try:
                        await process_product(db, detector, notifier, product,
                                               competitor["id"], competitor["name"])
                    except Exception:
                        logger.exception(f"    Error procesando producto {product.get('title', 'Unknown')}")

                # Solo se marcan eliminados si el catalogo se descargo con exito
                # (raw_products no vacio, arriba); asi un fallo parcial del
                # crawler no borra productos que en realidad siguen a la venta.
                db.mark_missing_products_removed(competitor["id"])

            except Exception:
                logger.exception(f"  Error crawleando {competitor['name']}")
                errors.append(competitor["name"])
    finally:
        # Cierra Chromium si crawl_magento_categories llego a abrirlo; no
        # hace nada si ningun competidor lo necesito (close() es segura de
        # llamar sin haberse usado fetch_rendered nunca).
        await crawler.close()

    # El digest se construye leyendo el estado real de la BD (no listas en
    # memoria), asi que sigue siendo correcto aunque el crawl haya fallado
    # a mitad para algun competidor.
    new_products = db.get_new_products(days=1)
    pending_events = db.get_unnotified_events()

    logger.info("\n" + "=" * 60)
    logger.info("Crawl completado")
    logger.info(f"  - {len(new_products)} productos nuevos")
    logger.info(f"  - {len(pending_events)} eventos de precio pendientes de notificar")
    logger.info("=" * 60)

    if new_products or pending_events:
        notifier.send_daily_digest(new_products, pending_events)
        db.mark_events_notified([event["id"] for event in pending_events])

    return {
        "new_products": len(new_products),
        "pending_events": len(pending_events),
        "errors": errors,
    }


if __name__ == "__main__":
    asyncio.run(main())
