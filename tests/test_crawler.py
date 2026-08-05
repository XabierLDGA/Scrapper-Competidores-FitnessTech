import json

import pytest

from src.crawler import Crawler


@pytest.mark.asyncio
async def test_parse_price():
    crawler = Crawler()
    assert crawler._parse_price("19,99") == 19.99
    assert crawler._parse_price("$29.95") == 29.95
    assert crawler._parse_price("149") == 149.0
    assert crawler._parse_price("1.299,00") == 1299.0
    assert crawler._parse_price("1,299.00") == 1299.0


@pytest.mark.asyncio
async def test_sitemap_parsing(monkeypatch):
    crawler = Crawler()

    sitemap_content = """<?xml version="1.0" encoding="UTF-8"?>
    <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
        <url><loc>https://example.com/product1</loc><lastmod>2024-01-15</lastmod></url>
        <url><loc>https://example.com/product2</loc></url>
    </urlset>"""

    async def mock_fetch(url):
        return sitemap_content

    monkeypatch.setattr(crawler, "fetch", mock_fetch)
    urls = await crawler.crawl_sitemap("https://example.com/sitemap.xml")

    assert len(urls) == 2
    assert urls[0]["url"] == "https://example.com/product1"
    assert urls[0]["lastmod"] == "2024-01-15"


@pytest.mark.asyncio
async def test_shopify_products_parsing(monkeypatch):
    crawler = Crawler()

    page_1_json = """
    {
        "products": [
            {
                "title": "Reloj GPS",
                "handle": "reloj-gps",
                "variants": [
                    {"id": 111, "price": "199.00", "compare_at_price": "249.00",
                     "available": true, "sku": "GPS-1"}
                ]
            }
        ]
    }
    """
    empty_page_json = '{"products": []}'

    async def mock_fetch(url):
        return page_1_json if "page=1" in url else empty_page_json

    monkeypatch.setattr(crawler, "fetch", mock_fetch)
    products = await crawler.crawl_shopify_products("https://example.com/products.json")

    assert len(products) == 1
    assert products[0]["id"] == 111
    assert products[0]["price"] == 199.0
    assert products[0]["original_price"] == 249.0
    assert products[0]["url"] == "https://example.com/products/reloj-gps"


@pytest.mark.asyncio
async def test_shopify_products_pagination(monkeypatch):
    """Shopify pagina /products.json (30 por defecto, 250 max); el crawler
    debe seguir pidiendo paginas hasta recibir una vacia, no quedarse con
    la primera."""
    crawler = Crawler()

    def make_page(product_id):
        return json.dumps({
            "products": [{
                "title": f"Producto {product_id}",
                "handle": f"producto-{product_id}",
                "variants": [{"id": product_id, "price": "10.00", "available": True}],
            }]
        })

    async def mock_fetch(url):
        if "page=1" in url:
            return make_page(1)
        if "page=2" in url:
            return make_page(2)
        return '{"products": []}'

    monkeypatch.setattr(crawler, "fetch", mock_fetch)
    products = await crawler.crawl_shopify_products("https://example.com/products.json")

    assert len(products) == 2
    assert {p["id"] for p in products} == {1, 2}


@pytest.mark.asyncio
async def test_html_products_have_stable_id(monkeypatch):
    """El id de un producto scrapeado por HTML debe ser estable entre
    ejecuciones (no basado en hash() de Python, que varia por proceso)."""
    crawler = Crawler()

    html = """
    <div class="product">
        <h2 class="product-title">Cinta de correr</h2>
        <span class="price">1.299,00</span>
        <a href="/productos/cinta-de-correr">ver</a>
    </div>
    """

    async def mock_fetch(url):
        return html

    monkeypatch.setattr(crawler, "fetch", mock_fetch)

    products_run_1 = await crawler.crawl_html_products("https://example.com/catalogo")
    products_run_2 = await crawler.crawl_html_products("https://example.com/catalogo")

    assert len(products_run_1) == 1
    assert products_run_1[0]["id"] == products_run_2[0]["id"]
    assert products_run_1[0]["price"] == 1299.0


def test_discover_magento_categories_filters_and_dedupes():
    crawler = Crawler()

    html = """
    <html><body>
    <nav class="navigation">
        <a href="/cardio-funcional-hiit/cintas-de-correr">Cintas</a>
        <a href="/cardio-funcional-hiit/cintas-de-correr">Cintas (repetido)</a>
        <a href="https://www.titaniumstrength.es/musculacion-titanium/bancos">Bancos</a>
        <a href="https://otra-web-externa.com/tracking">Externo</a>
    </nav>
    <footer>
        <a href="/no-deberia-aparecer">Fuera del menu</a>
    </footer>
    </body></html>
    """

    urls = crawler._discover_magento_categories(html, "https://www.titaniumstrength.es")

    assert urls == [
        "https://www.titaniumstrength.es/cardio-funcional-hiit/cintas-de-correr",
        "https://www.titaniumstrength.es/musculacion-titanium/bancos",
    ]


def test_discover_magento_categories_no_nav_returns_empty():
    crawler = Crawler()
    urls = crawler._discover_magento_categories("<html><body>sin menu</body></html>", "https://example.com")
    assert urls == []
