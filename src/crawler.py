import asyncio
import hashlib
import json
import logging
import re
from typing import Optional

import httpx
from selectolax.parser import HTMLParser

logger = logging.getLogger(__name__)


class Crawler:
    def __init__(self, timeout: int = 10, rate_limit: float = 0.5):
        self.timeout = timeout
        self.rate_limit = rate_limit
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Competitor Monitor v1.0) +https://yourcompany.com/bot"
        }

    async def fetch(self, url: str) -> Optional[str]:
        """Descarga una URL con reintentos."""
        async with httpx.AsyncClient(timeout=self.timeout, headers=self.headers) as client:
            for attempt in range(3):
                try:
                    resp = await client.get(url)
                    resp.raise_for_status()
                    await asyncio.sleep(self.rate_limit)
                    return resp.text
                except httpx.HTTPError as e:
                    logger.warning(f"Intento {attempt + 1} fallido para {url}: {e}")
                    if attempt == 2:
                        logger.error(f"No se pudo descargar {url}")
                        return None
                    await asyncio.sleep(2 ** attempt)
        return None

    async def crawl_sitemap(self, sitemap_url: str) -> list[dict]:
        """Extrae URLs de un sitemap.xml."""
        content = await self.fetch(sitemap_url)
        if not content:
            return []

        parser = HTMLParser(content)
        urls = []
        for loc in parser.css("loc"):
            url = loc.text()
            lastmod = None
            parent = loc.parent
            if parent:
                mod_elem = parent.css_first("lastmod")
                if mod_elem:
                    lastmod = mod_elem.text()
            urls.append({"url": url, "lastmod": lastmod})
        return urls

    async def crawl_shopify_products(self, products_json_url: str, max_pages: int = 50) -> list[dict]:
        """Descarga el catalogo completo desde /products.json de Shopify.

        Shopify pagina esta ruta (30 productos por defecto si no se pide
        limit, 250 como maximo por pagina), asi que hay que iterar paginas
        hasta que una devuelva 0 productos. Pedir la URL tal cual, sin
        parametros, solo trae la primera pagina y sub-reporta el catalogo.
        """
        base_url = products_json_url.split("?")[0].replace("/products.json", "")
        all_products = []

        for page in range(1, max_pages + 1):
            paged_url = f"{base_url}/products.json?limit=250&page={page}"
            content = await self.fetch(paged_url)
            if not content:
                break

            try:
                data = json.loads(content)
            except json.JSONDecodeError:
                logger.error(f"No se pudo parsear JSON de Shopify en {paged_url}")
                break

            page_products = data.get("products", [])
            if not page_products:
                break

            for product in page_products:
                for variant in product.get("variants", []):
                    all_products.append({
                        "id": variant.get("id"),
                        "title": product.get("title"),
                        "url": f"{base_url}/products/{product.get('handle')}",
                        "price": float(variant.get("price", 0)),
                        "original_price": float(variant.get("compare_at_price") or variant.get("price", 0)),
                        "available": variant.get("available", False),
                        "sku": variant.get("sku"),
                    })

        return all_products

    async def crawl_html_products(self, url: str, css_selector: str = ".product") -> list[dict]:
        """Scraping HTML generico (fallback para tiendas no-Shopify)."""
        content = await self.fetch(url)
        if not content:
            return []

        parser = HTMLParser(content)
        products = []
        for product in parser.css(css_selector):
            title_elem = product.css_first(".product-title, [data-name], h2")
            price_elem = product.css_first(".price, [data-price], .product-price")
            url_elem = product.css_first("a")

            title = title_elem.text() if title_elem else "Unknown"
            price_text = price_elem.text() if price_elem else "0"
            product_url = url_elem.attributes.get("href", "") if url_elem else ""

            if not product_url:
                continue

            price = self._parse_price(price_text)
            products.append({
                # hash() esta salteado por proceso en Python 3 (PYTHONHASHSEED
                # aleatorio) y cambiaria en cada ejecucion, rompiendo el
                # seguimiento de "producto ya visto". sha1 es estable.
                "id": hashlib.sha1(product_url.encode("utf-8")).hexdigest()[:16],
                "title": title.strip(),
                "url": product_url,
                "price": price,
                "original_price": price,
            })

        return products

    def _parse_price(self, text: str) -> float:
        """Extrae un numero de precio de un string, aceptando tanto formato
        europeo (1.299,00) como americano (1,299.00 / 29.95).

        El separador decimal es el que aparece mas a la derecha; el resto se
        trata como separador de miles y se descarta.
        """
        match = re.search(r"[\d.,]+", text)
        if not match:
            return 0.0

        number = match.group()
        has_comma = "," in number
        has_dot = "." in number

        if has_comma and has_dot:
            if number.rfind(",") > number.rfind("."):
                number = number.replace(".", "").replace(",", ".")
            else:
                number = number.replace(",", "")
        elif has_comma:
            # Coma unica: decimal si deja exactamente 2 digitos tras ella
            # (19,99), miles en caso contrario (1,299)
            if len(number.split(",")[-1]) == 2:
                number = number.replace(",", ".")
            else:
                number = number.replace(",", "")

        return float(number)

    async def crawl_shipping_time(self, product_url: str) -> Optional[str]:
        """Extrae el texto de plazo de entrega de una pagina de producto."""
        content = await self.fetch(product_url)
        if not content:
            return None

        parser = HTMLParser(content)

        selectors = [
            ".shipping-info", "[data-shipping]", ".delivery-time",
            ".product-shipping", ".shipping-text",
        ]

        for selector in selectors:
            elem = parser.css_first(selector)
            if elem:
                return elem.text(strip=True)

        text = parser.text()
        match = re.search(
            r"(envio|entrega|shipping|delivery).*?(\d+[-–]\d+\s*(horas|dias|days|hours)|24h|48h)",
            text,
            re.IGNORECASE,
        )
        return match.group() if match else None
