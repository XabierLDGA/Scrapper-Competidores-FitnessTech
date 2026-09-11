import asyncio
import hashlib
import json
import logging
import re
from typing import Optional
from urllib.parse import urljoin, urlparse

import httpx
from playwright.async_api import Browser, Playwright, async_playwright
from selectolax.parser import HTMLParser

logger = logging.getLogger(__name__)


class Crawler:
    def __init__(self, timeout: int = 10, rate_limit: float = 0.5):
        self.timeout = timeout
        self.rate_limit = rate_limit
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Competitor Monitor v1.0) +https://yourcompany.com/bot"
        }
        # Sitios detras de Cloudflare bloquean httpx por huella TLS (JA3)
        # aunque se le ponga un User-Agent de navegador; hace falta un
        # navegador real. Este UA es el que se ha verificado que pasa.
        self.browser_user_agent = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None

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
                        "_shopify_product_id": product.get("id"),
                    })

        series_by_product_id = await self._crawl_shopify_series_map(base_url, max_pages)
        for entry in all_products:
            entry["series"] = series_by_product_id.get(entry.pop("_shopify_product_id"))

        return all_products

    async def _crawl_shopify_series_map(self, base_url: str, max_pages: int = 50) -> dict:
        """Cruza las colecciones de Shopify cuyo titulo sugiere que son una
        linea de producto (contiene 'series' o 'select', ej. 'Elite Series',
        'Compact Select') -no una categoria generica como 'Cardio'- con los
        productos que contienen, para poder etiquetar cada producto con su
        serie. Devuelve {shopify_product_id: nombre_de_la_serie}.
        """
        collections = []
        for page in range(1, max_pages + 1):
            content = await self.fetch(f"{base_url}/collections.json?limit=250&page={page}")
            if not content:
                break
            try:
                data = json.loads(content)
            except json.JSONDecodeError:
                logger.error(f"No se pudo parsear JSON de colecciones Shopify en {base_url}")
                break
            page_collections = data.get("collections", [])
            if not page_collections:
                break
            collections.extend(page_collections)

        series_map = {}
        for collection in collections:
            title = collection.get("title", "")
            handle = collection.get("handle")
            lowered = title.lower()
            if not handle or ("series" not in lowered and "select" not in lowered):
                continue

            for page in range(1, max_pages + 1):
                content = await self.fetch(
                    f"{base_url}/collections/{handle}/products.json?limit=250&page={page}"
                )
                if not content:
                    break
                try:
                    data = json.loads(content)
                except json.JSONDecodeError:
                    logger.error(f"No se pudo parsear JSON de la coleccion {handle}")
                    break
                page_products = data.get("products", [])
                if not page_products:
                    break
                for product in page_products:
                    series_map[product.get("id")] = title

        return series_map

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
            sku_elem = product.css_first("[data-sku], .sku, .product-sku")

            title = title_elem.text() if title_elem else "Unknown"
            price_text = price_elem.text() if price_elem else "0"
            product_url = url_elem.attributes.get("href", "") if url_elem else ""
            sku = sku_elem.text(strip=True) if sku_elem else None

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
                "sku": sku,
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

    async def _ensure_browser(self) -> Browser:
        if self._browser is None:
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(headless=True)
        return self._browser

    async def fetch_rendered(self, url: str) -> Optional[str]:
        """Descarga una URL con un navegador Chromium real (Playwright).

        Necesario para sitios detras de Cloudflare que bloquean por huella
        TLS: Cloudflare distingue el cliente por como negocia TLS, no solo
        por las cabeceras HTTP, asi que httpx recibe 403 aunque se le ponga
        un User-Agent de navegador (verificado en vivo contra el sitio).
        El navegador se lanza una vez (bajo demanda) y se reutiliza entre
        llamadas: arrancar Chromium en cada pagina seria demasiado lento.
        """
        browser = await self._ensure_browser()
        for attempt in range(3):
            page = None
            try:
                page = await browser.new_page(user_agent=self.browser_user_agent)
                response = await page.goto(
                    url, wait_until="domcontentloaded", timeout=self.timeout * 1000
                )
                if response is None or response.status >= 400:
                    status = response.status if response else "sin respuesta"
                    raise RuntimeError(f"HTTP {status}")
                content = await page.content()
                await asyncio.sleep(self.rate_limit)
                return content
            except Exception as e:
                logger.warning(f"Intento {attempt + 1} fallido (Playwright) para {url}: {e}")
                if attempt == 2:
                    logger.error(f"No se pudo renderizar {url}")
                    return None
                await asyncio.sleep(2 ** attempt)
            finally:
                if page is not None:
                    await page.close()
        return None

    async def close(self):
        """Cierra el navegador Playwright si se llego a abrir.

        Debe llamarse una vez al terminar todo el crawl (no por competidor),
        para no dejar procesos de Chromium huerfanos.
        """
        if self._browser is not None:
            await self._browser.close()
            self._browser = None
        if self._playwright is not None:
            await self._playwright.stop()
            self._playwright = None

    async def _probe_plain_http(self, url: str) -> Optional[str]:
        """Una sola peticion httpx, sin reintentos, para decidir si una tienda
        necesita navegador.

        Reintentar no aporta nada: si Cloudflare bloquea por huella TLS lo
        hace las tres veces, y solo llenaria el log de avisos en cada crawl.
        """
        async with httpx.AsyncClient(timeout=self.timeout, headers=self.headers) as client:
            try:
                resp = await client.get(url)
                resp.raise_for_status()
                return resp.text
            except httpx.HTTPError:
                return None

    async def _status_plain(self, url: str) -> Optional[int]:
        """Codigo HTTP de una URL por httpx, sin seguir redirecciones y sin
        descargar el cuerpo. None si no se llego a hablar con el servidor."""
        async with httpx.AsyncClient(timeout=self.timeout, headers=self.headers,
                                      follow_redirects=False) as client:
            try:
                resp = await client.head(url)
                # Algunas tiendas no implementan HEAD y contestan 405; ahi
                # hay que preguntar con GET para saber si la ficha existe.
                if resp.status_code == 405:
                    resp = await client.get(url)
                await asyncio.sleep(self.rate_limit)
                return resp.status_code
            except httpx.HTTPError as e:
                logger.warning(f"No se pudo comprobar {url} por HTTP normal: {e}")
                return None

    async def _status_rendered(self, url: str) -> Optional[int]:
        """Codigo HTTP de una URL abriendola con Chromium, para tiendas que
        rechazan httpx por huella TLS."""
        try:
            browser = await self._ensure_browser()
        except Exception as e:
            logger.warning(f"No se pudo abrir el navegador para comprobar {url}: {e}")
            return None

        page = None
        try:
            page = await browser.new_page(user_agent=self.browser_user_agent)
            response = await page.goto(
                url, wait_until="domcontentloaded", timeout=self.timeout * 1000
            )
            await asyncio.sleep(self.rate_limit)
            return response.status if response is not None else None
        except Exception as e:
            logger.warning(f"No se pudo comprobar {url} con navegador: {e}")
            return None
        finally:
            if page is not None:
                await page.close()

    async def url_is_gone(self, url: str) -> Optional[bool]:
        """Dice si la ficha de un producto ha dejado de existir.

        True = 404/410, la ficha ya no esta. False = responde 2xx, sigue
        publicada. None = no se ha podido averiguar.

        Existe porque desaparecer del listado NO es lo mismo que estar de
        baja, y confundirlos llenaba el panel de bajas falsas: variantes de
        Shopify que se recrean con id nuevo al editar sus opciones (la
        ficha ni se entera), y productos de Magento que se quedan sin
        categoria navegable pero siguen publicados (EL-PL72 de Titanium,
        agotado, ficha viva y visible en el buscador de la tienda).

        Solo el 404/410 marca la baja: ante un 5xx, un timeout o una
        redireccion se prefiere no concluir y reintentar en la vuelta
        siguiente. Una baja tardia es barata; una falsa se cuela en el
        panel y en el correo semanal.
        """
        status = await self._status_plain(url)
        # 403 y 'ni contesta' son justo lo que devuelve una tienda detras de
        # Cloudflare a httpx, no una pista sobre el producto: ahi si merece
        # la pena pagar el navegador. El resto de codigos ya son respuesta
        # de la tienda y no hace falta repetir la pregunta.
        if status is None or status == 403:
            status = await self._status_rendered(url)

        if status is None:
            return None
        if status in (404, 410):
            return True
        if 200 <= status < 300:
            return False
        logger.info(f"Comprobacion no concluyente ({status}) para {url}")
        return None

    def _best_page_size(self, html: str) -> Optional[str]:
        """El mayor tamano de pagina que ofrece el selector de la propia tienda.

        Magento solo acepta los valores de ese selector: pedir cualquier otro
        (`product_list_limit=200`) lo ignora y devuelve la pagina por defecto,
        asi que el valor se lee de la pagina en vez de fijarlo a mano. Binom
        ofrece 'all' -su catalogo entero en una peticion- y Titanium llega a
        48, la mitad de peticiones que con las 24 de por defecto.
        """
        parser = HTMLParser(html)
        values = {
            option.attributes.get("value")
            for select in parser.css("select.limiter-options")
            for option in select.css("option")
        }
        if "all" in values:
            return "all"
        numeric = [int(v) for v in values if v and v.isdigit()]
        return str(max(numeric)) if numeric else None

    def _magento_page_url(self, category_url: str, page_num: int,
                          page_size: Optional[str]) -> str:
        """URL de una pagina de categoria, respetando la query que ya traiga.

        Algunas categorias salen del menu con parametros propios
        (`?view_landing=true`), asi que el separador no puede ser siempre '?'.
        """
        params = []
        if page_num > 1:
            params.append(f"p={page_num}")
        if page_size:
            params.append(f"product_list_limit={page_size}")
        if not params:
            return category_url
        separator = "&" if "?" in category_url else "?"
        return category_url + separator + "&".join(params)

    def _discover_magento_categories(self, html: str, base_url: str) -> list[str]:
        """Extrae las URLs de categoria del menu principal de Magento.

        El menu (nav.navigation) ya lista todo el arbol de categorias, asi
        que no hace falta mantener una lista de URLs a mano por competidor.
        """
        parser = HTMLParser(html)
        nav = parser.css_first("nav.navigation")
        if not nav:
            return []

        domain = urlparse(base_url).netloc
        seen = set()
        urls = []
        for a in nav.css("a"):
            href = a.attributes.get("href")
            if not href:
                continue
            absolute = urljoin(base_url, href).split("#")[0]
            if urlparse(absolute).netloc != domain:
                continue
            if absolute not in seen:
                seen.add(absolute)
                urls.append(absolute)
        return urls

    def _parse_magento_category(self, html: str) -> list[dict]:
        """Extrae productos de una pagina de categoria de Magento (grid Luma).

        No hace falta entrar a la ficha de cada producto: el grid ya trae
        sku, titulo, precio (actual y original si hay descuento) y
        disponibilidad en atributos data-* y en el price-box de cada
        '.product-item-info'.
        """
        parser = HTMLParser(html)
        products = []

        for item in parser.css(".product-item-info"):
            link = item.css_first("a.product-item-photo")
            if not link:
                continue

            sku = link.attributes.get("data-id")
            title = link.attributes.get("data-name")
            url = link.attributes.get("href")
            if not sku or not url:
                continue

            final_elem = item.css_first('[data-price-type="finalPrice"]')
            old_elem = item.css_first('[data-price-type="oldPrice"]')

            final_price = (
                self._parse_price(final_elem.attributes.get("data-price-amount", "0"))
                if final_elem else 0.0
            )
            original_price = (
                self._parse_price(old_elem.attributes.get("data-price-amount", "0"))
                if old_elem else final_price
            )

            availability_elem = item.css_first("p.availability")
            available = True
            if availability_elem:
                classes = availability_elem.attributes.get("class") or ""
                available = "out-of-stock" not in classes

            products.append({
                "id": sku,
                "sku": sku,
                "title": title,
                "url": url,
                "price": final_price,
                "original_price": original_price,
                "available": available,
            })

        return products

    async def crawl_magento_categories(self, base_url: str, max_pages_per_category: int = 20) -> list[dict]:
        """Descarga el catalogo completo de una tienda Magento.

        Descubre las categorias desde el menu principal y pagina cada una
        hasta que deja de aparecer producto nuevo. Los productos se
        deduplican por sku porque las categorias padre/hija listan los
        mismos.

        La descarga va por httpx y solo sube a navegador real si la tienda
        no acepta peticiones normales: Titanium esta detras de Cloudflare y
        lo necesita, Binom no. Lanzar Chromium donde no hace falta cuesta
        cientos de MB y varios segundos por pagina, asi que se prueba
        primero la via barata.
        """
        home_html = await self._probe_plain_http(base_url)
        fetch = self.fetch
        if not home_html or not self._discover_magento_categories(home_html, base_url):
            logger.info(f"{base_url} no se deja leer por HTTP normal, se usa navegador")
            fetch = self.fetch_rendered
            home_html = await fetch(base_url)
        if not home_html:
            return []

        category_urls = self._discover_magento_categories(home_html, base_url)
        products_by_sku: dict[str, dict] = {}
        # El tamano de pagina se descubre leyendo la primera categoria y se
        # aplica a partir de la siguiente: cambiarlo a mitad de una categoria
        # se saltaria productos, porque con limite 48 la pagina 2 empieza en
        # el articulo 49 y no en el 25.
        discovered_page_size: Optional[str] = None

        for category_url in category_urls:
            page_size = discovered_page_size
            seen_in_category: set[str] = set()

            for page_num in range(1, max_pages_per_category + 1):
                html = await fetch(self._magento_page_url(category_url, page_num, page_size))
                if not html:
                    break

                if discovered_page_size is None:
                    discovered_page_size = self._best_page_size(html)

                items = self._parse_magento_category(html)
                # Se corta por sku repetido y no por pagina vacia: pedir una
                # pagina que no existe no siempre da vacio, Binom devuelve
                # otra vez la ultima y la paginacion no terminaria nunca.
                new_items = [item for item in items if item["sku"] not in seen_in_category]
                if not new_items:
                    break

                for item in new_items:
                    seen_in_category.add(item["sku"])
                    products_by_sku[item["sku"]] = item

                if page_size == "all":
                    break

        return list(products_by_sku.values())
