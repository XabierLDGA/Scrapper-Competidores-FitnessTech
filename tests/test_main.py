import pytest

import main as main_module
from main import crawl_competitor_products


class FakeCrawler:
    def __init__(self):
        self.magento_calls = []
        self.shopify_calls = []

    async def crawl_magento_categories(self, base_url):
        self.magento_calls.append(base_url)
        return [{"id": "SKU-1", "sku": "SKU-1", "title": "Producto", "url": "https://x/1",
                 "price": 10.0, "original_price": 10.0, "available": True}]

    async def crawl_shopify_products(self, products_api_url):
        self.shopify_calls.append(products_api_url)
        return [{"id": 1, "title": "Producto Shopify", "url": "https://x/2",
                 "price": 5.0, "original_price": 5.0, "available": True, "sku": "SH-1"}]

    async def crawl_html_products(self, website_url):
        raise AssertionError("no deberia llamarse en este test")


@pytest.mark.asyncio
async def test_routes_to_magento_when_platform_is_magento():
    crawler = FakeCrawler()
    competitor = {"platform": "magento", "website_url": "https://www.titaniumstrength.es",
                  "product_api_url": None}

    products, source = await crawl_competitor_products(crawler, competitor)

    assert source == "magento"
    assert crawler.magento_calls == ["https://www.titaniumstrength.es"]
    assert products[0]["sku"] == "SKU-1"


@pytest.mark.asyncio
async def test_existing_shopify_routing_is_unaffected_by_platform_column():
    """Regresion: un competidor sin platform (NULL en BD -> None en dict)
    debe seguir yendo por Shopify si tiene product_api_url, exactamente
    igual que antes de anadir la columna platform."""
    crawler = FakeCrawler()
    competitor = {"platform": None, "website_url": "https://example.com",
                  "product_api_url": "https://example.com/products.json"}

    products, source = await crawl_competitor_products(crawler, competitor)

    assert source == "shopify"
    assert crawler.shopify_calls == ["https://example.com/products.json"]


class FakeDatabase:
    """Lo justo de Database para que main() llegue al final, apuntando lo
    que se le pide registrar."""

    def __init__(self, competitors):
        self._competitors = competitors
        self.errores_registrados = []
        self.retirados = []

    def get_competitors(self):
        return self._competitors

    def log_crawl_error(self, competitor_name, error_message):
        self.errores_registrados.append((competitor_name, error_message))

    def mark_missing_products_removed(self, competitor_id):
        self.retirados.append(competitor_id)

    def get_new_products(self, days):
        return []

    def get_unnotified_events(self):
        return []

    def mark_events_notified(self, ids):
        pass


class CrawlerSinProductos:
    async def crawl_magento_categories(self, base_url):
        return []

    async def close(self):
        pass


@pytest.mark.asyncio
async def test_catalogo_vacio_se_registra_como_error(monkeypatch):
    """Una tienda que devuelve cero productos no lanza excepcion, pero es un
    fallo: bloqueo, HTML cambiado o tienda caida. Tiene que llegar a
    crawl_errors, que es lo que lee el aviso de salud del crawl."""
    db = FakeDatabase([{"id": 7, "name": "Titanium Strength", "platform": "magento",
                        "website_url": "https://www.titaniumstrength.es",
                        "product_api_url": None}])
    monkeypatch.setattr(main_module, "Database", lambda **kwargs: db)
    monkeypatch.setattr(main_module, "Crawler", CrawlerSinProductos)

    resultado = await main_module.main()

    assert db.errores_registrados == [
        ("Titanium Strength", "El catalogo se descargo vacio: 0 productos")]
    assert resultado["errors"] == ["Titanium Strength"]


@pytest.mark.asyncio
async def test_catalogo_vacio_no_da_por_retirado_el_catalogo(monkeypatch):
    """El `continue` importa tanto como el registro: sin el,
    mark_missing_products_removed marcaria como retirada toda la tienda."""
    db = FakeDatabase([{"id": 7, "name": "Titanium Strength", "platform": "magento",
                        "website_url": "https://www.titaniumstrength.es",
                        "product_api_url": None}])
    monkeypatch.setattr(main_module, "Database", lambda **kwargs: db)
    monkeypatch.setattr(main_module, "Crawler", CrawlerSinProductos)

    await main_module.main()

    assert db.retirados == []
