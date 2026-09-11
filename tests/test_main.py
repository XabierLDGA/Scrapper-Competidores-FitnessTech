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

    def __init__(self, competitors, candidatos=None):
        self._competitors = competitors
        self._candidatos = candidatos or []
        self.errores_registrados = []
        self.reemplazos_pedidos = []
        self.candidatos_pedidos = []
        self.retirados = []

    def get_competitors(self):
        return self._competitors

    def log_crawl_error(self, competitor_name, error_message):
        self.errores_registrados.append((competitor_name, error_message))

    def mark_superseded_variants(self, competitor_id):
        self.reemplazos_pedidos.append(competitor_id)
        return 0

    def get_removal_candidates(self, competitor_id):
        self.candidatos_pedidos.append(competitor_id)
        return self._candidatos

    def mark_products_removed(self, product_ids):
        self.retirados.extend(product_ids)

    def insert_or_update_product(self, **kwargs):
        return 1

    def get_last_snapshot(self, product_id):
        return None

    def insert_snapshot(self, **kwargs):
        pass

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

    assert db.reemplazos_pedidos == []
    assert db.candidatos_pedidos == []
    assert db.retirados == []


class CrawlerConFichas:
    """Crawler de mentira que devuelve un catalogo fijo y contesta lo que se
    le diga sobre si cada ficha sigue viva."""

    def __init__(self, fichas):
        self._fichas = fichas
        self.comprobadas = []

    async def crawl_magento_categories(self, base_url):
        return [{"id": "SKU-1", "sku": "SKU-1", "title": "Producto", "url": "https://x/1",
                 "price": 10.0, "original_price": 10.0, "available": True}]

    async def url_is_gone(self, url):
        self.comprobadas.append(url)
        return self._fichas[url]

    async def close(self):
        pass


def _db_con_candidato(fichas_url):
    return FakeDatabase(
        [{"id": 7, "name": "Titanium Strength", "platform": "magento",
          "website_url": "https://www.titaniumstrength.es", "product_api_url": None}],
        candidatos=[{"id": 33, "url": fichas_url, "title": "Extension de Triceps"}],
    )


def _monta(monkeypatch, db, crawler):
    monkeypatch.setattr(main_module, "Database", lambda **kwargs: db)
    monkeypatch.setattr(main_module, "Crawler", lambda: crawler)


@pytest.mark.asyncio
async def test_no_da_de_baja_un_producto_cuya_ficha_sigue_publicada(monkeypatch):
    """El caso EL-PL72: se cayo del listado de categorias pero su ficha
    responde 200. Desaparecer del listado no es estar de baja."""
    url = "https://www.titaniumstrength.es/extension-de-triceps-y-fondos-de-pie.html"
    db = _db_con_candidato(url)
    crawler = CrawlerConFichas({url: False})
    _monta(monkeypatch, db, crawler)

    await main_module.main()

    assert crawler.comprobadas == [url]
    assert db.retirados == []


@pytest.mark.asyncio
async def test_da_de_baja_cuando_la_ficha_ya_no_existe(monkeypatch):
    """La baja legitima sigue marcandose: BS-S48 y F-MR-CROSS dan 404."""
    url = "https://www.titaniumstrength.es/selectorizada-dual.html"
    db = _db_con_candidato(url)
    crawler = CrawlerConFichas({url: True})
    _monta(monkeypatch, db, crawler)

    await main_module.main()

    assert db.retirados == [33]


@pytest.mark.asyncio
async def test_no_da_de_baja_si_la_comprobacion_no_concluye(monkeypatch):
    """Ante un 5xx o un timeout se deja el producto activo y se reintenta
    en la vuelta siguiente, en vez de apuntarse una baja que quiza no lo es."""
    url = "https://www.titaniumstrength.es/quien-sabe.html"
    db = _db_con_candidato(url)
    crawler = CrawlerConFichas({url: None})
    _monta(monkeypatch, db, crawler)

    await main_module.main()

    assert db.retirados == []


@pytest.mark.asyncio
async def test_las_variantes_reemplazadas_se_reclasifican_antes_de_buscar_bajas(monkeypatch):
    """La variante que Shopify recreo con id nuevo no esta de baja, pero
    tampoco sigue en el catalogo: hay que sacarla de 'active', o se queda de
    fantasma inflando el recuento para siempre. Y tiene que pasar ANTES de
    listar candidatos, para que ni llegue a gastarse una comprobacion de
    ficha en ella."""
    url = "https://www.fitnesstech.es/products/set-mancuernas-60kg"
    db = _db_con_candidato(url)
    crawler = CrawlerConFichas({url: False})
    _monta(monkeypatch, db, crawler)

    await main_module.main()

    assert db.reemplazos_pedidos == [7]
    assert db.candidatos_pedidos == [7]
