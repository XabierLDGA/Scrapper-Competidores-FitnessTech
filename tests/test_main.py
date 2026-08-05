import pytest

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
