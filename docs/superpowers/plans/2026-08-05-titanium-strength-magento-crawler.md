# Titanium Strength (Magento + Playwright) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Añadir Titanium Strength (`titaniumstrength.es`, Magento, detrás de
Cloudflare) como competidor monitorizado, sin tocar el comportamiento de los
competidores existentes (Fitness Tech, Fitness Tech FR).

**Architecture:** `Crawler` gana un segundo modo de descarga basado en
Playwright (Chromium headless) además del existente basado en `httpx`,
porque Cloudflare bloquea `httpx` por huella TLS. El parseo del catálogo
sigue el mismo patrón que el resto del crawler: funciones puras sobre HTML
con `selectolax`, separadas de la descarga, así se testean sin navegador
real. `main.py` rutea por una nueva columna `platform` en `competitors`
(`'magento'` → Playwright; cualquier otro valor → comportamiento actual sin
cambios).

**Tech Stack:** Python 3.11, `playwright` (nuevo), `selectolax`, `httpx`,
`mysql-connector-python`, `pytest` + `pytest-asyncio` (`asyncio_mode = auto`).

## Global Constraints

- No modificar el comportamiento de competidores existentes: cualquier
  competidor con `platform` NULL debe seguir el camino Shopify/HTML actual
  exactamente igual que hoy.
- `playwright==1.62.0` en `requirements.txt` (versión verificada en vivo
  contra el sitio durante el diseño).
- El SKU (`data-id` en el HTML de Magento) es el identificador natural del
  producto (`id` y `sku` en el dict devuelto por el crawler); no usar hash
  de URL para este competidor.
- Extracción de precios: usar siempre `[data-price-type="finalPrice"]` para
  el precio actual y `[data-price-type="oldPrice"]` para el original
  (presente solo si hay descuento); reutilizar `Crawler._parse_price` para
  convertir `data-price-amount` a `float`, no reimplementar el parseo.
- Disponibilidad: `"out-of-stock" not in class` del elemento `p.availability`
  (por defecto `True` si el elemento no aparece).
- Ningún test de este plan debe requerir MySQL real ni un navegador
  Playwright real corriendo — todo se testea con HTML de fixture y
  `monkeypatch`, igual que los tests actuales de `crawl_shopify_products`.

---

## File Structure

- **Modify `src/crawler.py`** — nuevos métodos: `fetch_rendered`, `close`,
  `_discover_magento_categories`, `_parse_magento_category`,
  `crawl_magento_categories`. Nuevos imports (`urllib.parse`,
  `playwright.async_api`).
- **Modify `src/db.py`** — `add_competitor` gana el parámetro opcional
  `platform`.
- **Create `migrations/004_add_competitor_platform.sql`** — columna
  `platform` en `competitors`.
- **Modify `main.py`** — `crawl_competitor_products` rutea a
  `crawl_magento_categories` cuando `competitor["platform"] == "magento"`;
  `main()` cierra el navegador Playwright en un `finally`.
- **Modify `requirements.txt`** y **`README.md`** — nueva dependencia y
  paso de setup (`playwright install chromium`).
- **Modify `tests/test_crawler.py`** — tests de las funciones puras nuevas.
- **Create `tests/test_main.py`** — test del ruteo por `platform` en
  `crawl_competitor_products`.
- Alta del competidor en MySQL — ejecución directa (no un fichero nuevo en
  el repo), siguiendo el patrón ya documentado en el README para añadir
  competidores.

---

### Task 1: Columna `platform` en `competitors`

**Files:**
- Create: `migrations/004_add_competitor_platform.sql`
- Modify: `src/db.py:263-282` (método `add_competitor`)

**Interfaces:**
- Produces: `Database.add_competitor(name, website_url, product_api_url=None, country="ES", platform=None) -> int`. Filas existentes de `competitors` quedan con `platform = NULL`.

- [ ] **Step 1: Crear la migración**

Crea `migrations/004_add_competitor_platform.sql`:

```sql
USE competitor_monitor;

ALTER TABLE competitors
  ADD COLUMN platform VARCHAR(20) NULL AFTER product_api_url;
```

- [ ] **Step 2: Aplicar la migración contra MySQL local**

Run: `mysql -h localhost -u root -p competitor_monitor < migrations/004_add_competitor_platform.sql`

Expected: sin errores. Verifica con:
`mysql -h localhost -u root -p -e "DESCRIBE competitor_monitor.competitors;"`
La salida debe incluir una fila `platform | varchar(20) | YES | ... | NULL`.

- [ ] **Step 3: Añadir el parámetro `platform` a `add_competitor`**

En `src/db.py`, sustituye el método completo (líneas 263-282):

```python
    def add_competitor(self, name: str, website_url: str,
                        product_api_url: str = None, country: str = "ES",
                        platform: str = None) -> int:
        """Anade un competidor a la BD."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("""
                    INSERT INTO competitors (name, website_url, product_api_url, country, platform)
                    VALUES (%s, %s, %s, %s, %s)
                """, (name, website_url, product_api_url, country, platform))
                conn.commit()
                return cursor.lastrowid
            except mysql.connector.Error as err:
                if err.errno == MYSQL_ERR_DUPLICATE_ENTRY:
                    logger.warning(f"Competidor {name} ya existe")
                    cursor.execute("SELECT id FROM competitors WHERE name = %s", (name,))
                    return cursor.fetchone()[0]
                raise
            finally:
                cursor.close()
```

- [ ] **Step 4: Commit**

```bash
git add migrations/004_add_competitor_platform.sql src/db.py
git commit -m "Anadir columna platform a competitors para rutear crawlers no-Shopify"
```

---

### Task 2: `Crawler.fetch_rendered` y `Crawler.close` (descarga vía Playwright)

**Files:**
- Modify: `src/crawler.py:1-20` (imports y `__init__`)
- Modify: `src/crawler.py` (nuevos métodos, al final de la clase, tras `crawl_shipping_time`)

**Interfaces:**
- Consumes: nada de tareas anteriores.
- Produces: `Crawler.fetch_rendered(url: str) -> str | None` (mismo
  contrato que `fetch`: `None` tras 3 intentos fallidos, nunca excepción).
  `Crawler.close() -> None` (cierra el navegador si se llegó a abrir; segura
  de llamar aunque nunca se haya usado `fetch_rendered`).

- [ ] **Step 1: Añadir los imports necesarios**

En `src/crawler.py`, sustituye las líneas 1-11:

```python
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
```

- [ ] **Step 2: Añadir estado de Playwright al constructor**

Sustituye las líneas 14-20 (el método `__init__`):

```python
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
```

- [ ] **Step 3: Añadir `fetch_rendered` y `close` al final de la clase**

Añade al final de `src/crawler.py` (tras el `return match.group() if match else None` de `crawl_shipping_time`):

```python

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
```

- [ ] **Step 4: Verificación manual contra el sitio real**

No se añade un test automático para `fetch_rendered` (igual que `fetch`,
que tampoco tiene test automático — ambos dependen de red real). Verifica a
mano:

Run:
```bash
python -c "
import asyncio
from src.crawler import Crawler

async def main():
    c = Crawler()
    html = await c.fetch_rendered('https://www.titaniumstrength.es/cardio-funcional-hiit/cintas-de-correr')
    print('OK' if html and 'product-item-info' in html else 'FAIL', len(html) if html else 0)
    await c.close()

asyncio.run(main())
"
```

Expected: `OK` y una longitud > 0.

- [ ] **Step 5: Commit**

```bash
git add src/crawler.py
git commit -m "Anadir Crawler.fetch_rendered (Playwright) para sitios que bloquean httpx por TLS"
```

---

### Task 3: Descubrimiento de categorías (`_discover_magento_categories`)

**Files:**
- Modify: `src/crawler.py` (nuevo método)
- Test: `tests/test_crawler.py`

**Interfaces:**
- Consumes: nada (función pura sobre HTML).
- Produces: `Crawler._discover_magento_categories(html: str, base_url: str) -> list[str]` — URLs absolutas, mismo dominio que `base_url`, sin duplicados, en el orden en que aparecen en el menú.

- [ ] **Step 1: Escribir el test que falla**

Añade al final de `tests/test_crawler.py`:

```python
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
```

Este test importa `Crawler` que ya está importado en la cabecera del
fichero (`from src.crawler import Crawler`); no hace falta tocar los
imports.

- [ ] **Step 2: Ejecutar y comprobar que falla**

Run: `pytest tests/test_crawler.py -k discover_magento -v`
Expected: FAIL — `AttributeError: 'Crawler' object has no attribute '_discover_magento_categories'`

- [ ] **Step 3: Implementar el método**

Añade a `src/crawler.py`, dentro de la clase `Crawler` (después de `close`):

```python

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
```

- [ ] **Step 4: Ejecutar y comprobar que pasa**

Run: `pytest tests/test_crawler.py -k discover_magento -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add src/crawler.py tests/test_crawler.py
git commit -m "Anadir descubrimiento de categorias Magento desde el menu principal"
```

---

### Task 4: Parseo de la rejilla de producto (`_parse_magento_category`)

**Files:**
- Modify: `src/crawler.py` (nuevo método)
- Test: `tests/test_crawler.py`

**Interfaces:**
- Consumes: `Crawler._parse_price` (ya existe, línea ~136 de `src/crawler.py`).
- Produces: `Crawler._parse_magento_category(html: str) -> list[dict]`, cada dict con claves `id`, `sku`, `title`, `url`, `price` (float), `original_price` (float), `available` (bool). Usado por `crawl_magento_categories` (Task 5).

- [ ] **Step 1: Escribir el test que falla**

Añade al final de `tests/test_crawler.py`:

```python
MAGENTO_CATEGORY_HTML = """
<ol class="products list items product-items">
    <li class="item product product-item">
        <div class="product-item-info" data-container="product-grid">
            <a href="https://www.titaniumstrength.es/cinta-a.html"
               class="product photo product-item-photo"
               data-id="SKU-A" data-name="Cinta A"></a>
            <div class="price-box price-final_price" data-product-id="1">
                <span class="old-price">
                    <span id="old-price-1" data-price-amount="1495"
                          data-price-type="oldPrice" class="price-wrapper">
                        <span class="price">1.495,00&#8364;</span>
                    </span>
                </span>
                <span class="special-price">
                    <span id="product-price-1" data-price-amount="995"
                          data-price-type="finalPrice" class="price-wrapper">
                        <span class="price">995,00&#8364;</span>
                    </span>
                </span>
            </div>
            <p class="availability in-stock NO_entrega24h">En Stock</p>
        </div>
    </li>
    <li class="item product product-item">
        <div class="product-item-info" data-container="product-grid">
            <a href="https://www.titaniumstrength.es/cinta-b.html"
               class="product photo product-item-photo"
               data-id="SKU-B" data-name="Cinta B"></a>
            <div class="price-box price-final_price" data-product-id="2">
                <span class="normal-price">
                    <span id="product-price-2" data-price-amount="1195"
                          data-price-type="finalPrice" class="price-wrapper">
                        <span class="price">1.195,00&#8364;</span>
                    </span>
                </span>
            </div>
            <p class="availability in-stock NO_entrega24h">En Stock</p>
        </div>
    </li>
    <li class="item product product-item">
        <div class="product-item-info" data-container="product-grid">
            <a href="https://www.titaniumstrength.es/cinta-c.html"
               class="product photo product-item-photo"
               data-id="SKU-C" data-name="Cinta C"></a>
            <div class="price-box price-final_price" data-product-id="3">
                <span class="normal-price">
                    <span id="product-price-3" data-price-amount="750"
                          data-price-type="finalPrice" class="price-wrapper">
                        <span class="price">750,00&#8364;</span>
                    </span>
                </span>
            </div>
            <p class="availability out-of-stock">Proximamente Disponible</p>
        </div>
    </li>
</ol>
"""


def test_parse_magento_category_extracts_discount_and_stock():
    crawler = Crawler()

    products = crawler._parse_magento_category(MAGENTO_CATEGORY_HTML)

    assert len(products) == 3

    by_sku = {p["sku"]: p for p in products}

    discounted = by_sku["SKU-A"]
    assert discounted["id"] == "SKU-A"
    assert discounted["title"] == "Cinta A"
    assert discounted["url"] == "https://www.titaniumstrength.es/cinta-a.html"
    assert discounted["price"] == 995.0
    assert discounted["original_price"] == 1495.0
    assert discounted["available"] is True

    no_discount = by_sku["SKU-B"]
    assert no_discount["price"] == 1195.0
    assert no_discount["original_price"] == 1195.0

    out_of_stock = by_sku["SKU-C"]
    assert out_of_stock["available"] is False


def test_parse_magento_category_empty_html_returns_empty_list():
    crawler = Crawler()
    assert crawler._parse_magento_category("<html><body>sin productos</body></html>") == []
```

- [ ] **Step 2: Ejecutar y comprobar que falla**

Run: `pytest tests/test_crawler.py -k parse_magento_category -v`
Expected: FAIL — `AttributeError: 'Crawler' object has no attribute '_parse_magento_category'`

- [ ] **Step 3: Implementar el método**

Añade a `src/crawler.py`, dentro de la clase `Crawler` (después de `_discover_magento_categories`):

```python

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
```

- [ ] **Step 4: Ejecutar y comprobar que pasa**

Run: `pytest tests/test_crawler.py -k parse_magento_category -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add src/crawler.py tests/test_crawler.py
git commit -m "Anadir parseo de la rejilla de producto Magento (precio, descuento, stock)"
```

---

### Task 5: Orquestador `crawl_magento_categories`

**Files:**
- Modify: `src/crawler.py` (nuevo método)
- Test: `tests/test_crawler.py`

**Interfaces:**
- Consumes: `Crawler.fetch_rendered` (Task 2), `Crawler._discover_magento_categories` (Task 3), `Crawler._parse_magento_category` (Task 4).
- Produces: `Crawler.crawl_magento_categories(base_url: str, max_pages_per_category: int = 20) -> list[dict]`. Usado por `main.py` (Task 6).

- [ ] **Step 1: Escribir el test que falla**

Añade al final de `tests/test_crawler.py`:

```python
@pytest.mark.asyncio
async def test_crawl_magento_categories_paginates_and_dedupes(monkeypatch):
    """Dos categorias que comparten un producto (tipico padre/hija): el
    resultado no debe repetirlo. La categoria A tiene 2 paginas (la 2a
    llega vacia y corta la paginacion); la B tiene solo 1."""
    crawler = Crawler()

    nav_html = """
    <nav class="navigation">
        <a href="/cat-a">Cat A</a>
        <a href="/cat-b">Cat B</a>
    </nav>
    """

    def product_li(sku, price):
        return f"""
        <li class="item product product-item">
            <div class="product-item-info">
                <a href="https://example.com/{sku}.html"
                   class="product photo product-item-photo"
                   data-id="{sku}" data-name="Producto {sku}"></a>
                <div class="price-box price-final_price">
                    <span id="product-price-{sku}" data-price-amount="{price}"
                          data-price-type="finalPrice" class="price-wrapper"></span>
                </div>
                <p class="availability in-stock">En Stock</p>
            </div>
        </li>
        """

    responses = {
        "https://example.com": nav_html,
        "https://example.com/cat-a": f"<ol>{product_li('SKU-1', 100)}</ol>",
        "https://example.com/cat-a?p=2": "<ol></ol>",
        "https://example.com/cat-b": f"<ol>{product_li('SKU-1', 100)}{product_li('SKU-2', 200)}</ol>",
        "https://example.com/cat-b?p=2": "<ol></ol>",
    }

    async def mock_fetch_rendered(url):
        return responses.get(url)

    monkeypatch.setattr(crawler, "fetch_rendered", mock_fetch_rendered)

    products = await crawler.crawl_magento_categories("https://example.com")

    assert {p["sku"] for p in products} == {"SKU-1", "SKU-2"}
    assert len(products) == 2


@pytest.mark.asyncio
async def test_crawl_magento_categories_home_fetch_fails_returns_empty(monkeypatch):
    crawler = Crawler()

    async def mock_fetch_rendered(url):
        return None

    monkeypatch.setattr(crawler, "fetch_rendered", mock_fetch_rendered)

    products = await crawler.crawl_magento_categories("https://example.com")

    assert products == []
```

- [ ] **Step 2: Ejecutar y comprobar que falla**

Run: `pytest tests/test_crawler.py -k crawl_magento_categories -v`
Expected: FAIL — `AttributeError: 'Crawler' object has no attribute 'crawl_magento_categories'`

- [ ] **Step 3: Implementar el método**

Añade a `src/crawler.py`, dentro de la clase `Crawler` (después de `_parse_magento_category`):

```python

    async def crawl_magento_categories(self, base_url: str, max_pages_per_category: int = 20) -> list[dict]:
        """Descarga el catalogo completo de una tienda Magento detras de
        Cloudflare, via Playwright.

        Descubre las categorias desde el menu principal y pagina cada una
        hasta que una pagina no devuelve productos. Los productos se
        deduplican por sku porque las categorias padre/hija listan los
        mismos productos.
        """
        home_html = await self.fetch_rendered(base_url)
        if not home_html:
            return []

        category_urls = self._discover_magento_categories(home_html, base_url)
        products_by_sku: dict[str, dict] = {}

        for category_url in category_urls:
            for page_num in range(1, max_pages_per_category + 1):
                page_url = category_url if page_num == 1 else f"{category_url}?p={page_num}"
                html = await self.fetch_rendered(page_url)
                if not html:
                    break

                items = self._parse_magento_category(html)
                if not items:
                    break

                for item in items:
                    products_by_sku[item["sku"]] = item

        return list(products_by_sku.values())
```

- [ ] **Step 4: Ejecutar y comprobar que pasa**

Run: `pytest tests/test_crawler.py -k crawl_magento_categories -v`
Expected: 2 passed

Run también la suite completa para confirmar que no se ha roto nada:
Run: `pytest tests/test_crawler.py -v`
Expected: todos los tests pasan (los previos + los 6 nuevos de este plan).

- [ ] **Step 5: Commit**

```bash
git add src/crawler.py tests/test_crawler.py
git commit -m "Anadir Crawler.crawl_magento_categories (orquestador con paginacion y dedupe)"
```

---

### Task 6: Ruteo en `main.py` por `platform`

**Files:**
- Modify: `main.py:21-31` (`crawl_competitor_products`)
- Modify: `main.py:92-163` (`main`, para cerrar el navegador)
- Create: `tests/test_main.py`

**Interfaces:**
- Consumes: `Crawler.crawl_magento_categories` (Task 5), `Crawler.close` (Task 2).
- Produces: sin cambios de firma pública; `crawl_competitor_products` sigue devolviendo `tuple[list[dict], str]`.

- [ ] **Step 1: Escribir el test que falla**

Crea `tests/test_main.py`:

```python
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
```

- [ ] **Step 2: Ejecutar y comprobar que falla**

Run: `pytest tests/test_main.py -v`
Expected: FAIL en `test_routes_to_magento_when_platform_is_magento` — la
función actual no comprueba `platform` y acaba llamando a
`crawler.crawl_html_products`, que en `FakeCrawler` lanza `AssertionError`
(o, si no llega ahí, el `assert source == "magento"` falla porque devuelve
`"html"`).

- [ ] **Step 3: Actualizar `crawl_competitor_products`**

En `main.py`, sustituye las líneas 21-31:

```python
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
```

- [ ] **Step 4: Ejecutar y comprobar que pasa**

Run: `pytest tests/test_main.py -v`
Expected: 2 passed

- [ ] **Step 5: Cerrar el navegador Playwright al final de `main()`**

En `main.py`, el bucle `for competitor in competitors:` (líneas 116-141)
debe quedar envuelto para garantizar el cierre del navegador aunque falle
algo a mitad. Sustituye desde `errors = []` (línea 115) hasta la línea 141
(el `errors.append(competitor["name"])` con el que termina hoy ese bloque)
por el código de abajo. Todo lo que viene después en `main()` — el bloque
que empieza en `new_products = db.get_new_products(days=1)` — no cambia:

```python
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
        # hacer nada si ningun competidor lo necesito (close() es segura de
        # llamar sin haberse usado fetch_rendered nunca).
        await crawler.close()
```

Esto sustituye el bloque `for competitor in competitors: ... except Exception: ... errors.append(...)` existente por la misma lógica envuelta en
`try/finally`; el resto de `main()` (cálculo de `new_products`,
`pending_events`, el digest y el `return` final) no cambia.

- [ ] **Step 6: Ejecutar toda la suite**

Run: `pytest -v`
Expected: todos los tests pasan (los de `test_crawler.py`, `test_main.py` y el resto sin tocar).

- [ ] **Step 7: Commit**

```bash
git add main.py tests/test_main.py
git commit -m "Rutear competidores Magento a Playwright y cerrar el navegador al terminar el crawl"
```

---

### Task 7: Dependencia `playwright` y setup

**Files:**
- Modify: `requirements.txt`
- Modify: `README.md` (sección "Instalacion local")

**Interfaces:**
- Consumes: nada.
- Produces: entorno con `playwright` instalado y el binario de Chromium descargado, requisito para que Task 2-5 funcionen en una máquina nueva.

- [ ] **Step 1: Añadir la dependencia**

En `requirements.txt`, añade una línea al final:

```
playwright==1.62.0
```

- [ ] **Step 2: Documentar el paso de setup en el README**

En `README.md`, dentro de la sección `### 1. Python y dependencias`, después
del bloque de `pip install -r requirements.txt`, añade:

```markdown
Titanium Strength (`titaniumstrength.es`) está detrás de Cloudflare y
bloquea las peticiones HTTP normales por huella TLS, así que ese competidor
se descarga con un navegador Chromium real (Playwright) en vez de `httpx`.
Tras instalar las dependencias, descarga el binario del navegador una vez:

```bash
playwright install chromium
```

Este paso descarga ~115MB y solo hace falta ejecutarlo una vez por máquina.
```

- [ ] **Step 3: Verificar instalación limpia**

Run: `pip install -r requirements.txt && playwright install chromium`
Expected: sin errores; el comando final confirma que Chromium ya está
descargado (o lo descarga si falta).

- [ ] **Step 4: Commit**

```bash
git add requirements.txt README.md
git commit -m "Anadir playwright como dependencia para el competidor Magento"
```

---

### Task 8: Alta de Titanium Strength en la base de datos

**Files:** ninguno del repo — ejecución directa contra MySQL local, igual
que el flujo ya documentado en el README para dar de alta competidores.

**Interfaces:**
- Consumes: `Database.add_competitor(name, website_url, product_api_url=None, country="ES", platform=None)` (Task 1).

- [ ] **Step 1: Insertar el competidor**

Run:
```bash
python -c "
from dotenv import load_dotenv
load_dotenv()
import os
from src.db import Database

db = Database(
    host=os.getenv('DB_HOST', 'localhost'),
    user=os.getenv('DB_USER', 'root'),
    password=os.getenv('DB_PASSWORD', ''),
    database=os.getenv('DB_NAME', 'competitor_monitor'),
    port=int(os.getenv('DB_PORT', '3306')),
)
competitor_id = db.add_competitor(
    name='Titanium Strength',
    website_url='https://www.titaniumstrength.es',
    platform='magento',
    country='ES',
)
print(f'Competidor anadido: ID {competitor_id}')
"
```

Expected: `Competidor anadido: ID <n>` (o, si ya existía de una ejecución
anterior de este mismo paso, el aviso `Competidor Titanium Strength ya
existe` y el mismo id de siempre — `add_competitor` ya maneja ese caso).

- [ ] **Step 2: Verificar el alta**

Run:
```bash
python -c "
from dotenv import load_dotenv
load_dotenv()
import os
from src.db import Database

db = Database(
    host=os.getenv('DB_HOST', 'localhost'), user=os.getenv('DB_USER', 'root'),
    password=os.getenv('DB_PASSWORD', ''), database=os.getenv('DB_NAME', 'competitor_monitor'),
    port=int(os.getenv('DB_PORT', '3306')),
)
for c in db.get_competitors():
    print(c['name'], '|', c['website_url'], '|', c['platform'])
"
```

Expected: entre las filas aparece `Titanium Strength | https://www.titaniumstrength.es | magento`.

No hay commit en este paso (no se toca ningún fichero del repo).

---

### Task 9: Verificación end-to-end

**Files:** ninguno — solo ejecución y observación.

- [ ] **Step 1: Ejecutar el crawl completo**

Run: `python main.py`

Expected en el log: una sección `Crawleando: Titanium Strength` seguida de
`N productos descargados (magento)` con `N` > 0, sin excepciones, y al
final el resumen `Crawl completado`.

- [ ] **Step 2: Confirmar en el dashboard**

Run: `python dashboard.py` y abre `http://localhost:5000`.

Expected: la tabla "Competidores" ahora lista 3 filas, incluyendo
`Titanium Strength` con un número de productos > 0 y `Ultimo crawl` con la
fecha de hoy.

- [ ] **Step 3: Segunda pasada de verificación de idempotencia**

Run: `python main.py` una segunda vez.

Expected: no debe haber errores; el número de "productos nuevos" para
Titanium Strength en esta segunda pasada debe ser 0 (ya se vieron en la
primera), confirmando que `insert_or_update_product` y la deduplicación por
sku funcionan correctamente sobre datos reales.

Este paso cierra el plan: no hay commit (es solo verificación manual sobre
el sistema ya implementado en las tareas anteriores).
