# Soporte de scraping para Titanium Strength (titaniumstrength.es)

Fecha: 2026-08-05

## Contexto

`titaniumstrength.es` es un competidor (fitness/musculación) que el usuario
quiere añadir al sistema de monitorización. El pipeline actual (`main.py` →
`Crawler` → `Normalizer` → `Database` → `ChangeDetector` → `Notifier`) asume
dos rutas de descarga de catálogo: Shopify `/products.json` o scraping HTML
genérico con un único selector `.product` fijo, ambas sobre `httpx`.

Investigación previa al diseño (contra el sitio real):

- **Plataforma**: Magento (confirmado por `robots.txt`, cabecera
  `x-magento-cache-debug`, y markup `product-item-info` estándar de Luma).
  No expone `/products.json` — ese endpoint devuelve un reto de Cloudflare.
- **Sin sitemap útil**: `sitemap.xml` da 404; no hay feed de productos
  público.
- **Descubrimiento del catálogo**: el menú principal (`nav.navigation` en el
  HTML de la home) lista las ~58 categorías/subcategorías y cubre todo el
  árbol de catálogo. No hace falta mantener una lista de URLs a mano.
- **Datos de producto en la rejilla de categoría** (no hace falta entrar a
  cada ficha de producto): cada `li.product-item > .product-item-info`
  contiene:
  - `a.product-item-photo[href]` → URL del producto
  - `data-id` / `data-simple-id` → SKU
  - `data-name` → título
  - `.price-box` → `[data-price-type="finalPrice"][data-price-amount]`
    (precio actual, siempre presente, con o sin descuento) y
    `[data-price-type="oldPrice"][data-price-amount]` (precio original,
    solo presente si hay descuento; si no hay descuento, original = final).
    Usar el atributo `data-price-type` en vez del wrapper (`.special-price`
    / `.normal-price`) es más robusto: verificado en vivo que el id
    `#product-price-<id>` con `data-price-type="finalPrice"` aparece en
    ambos casos, con y sin descuento.
  - `p.availability` con clase `in-stock` o `out-of-stock` → disponibilidad.
  - Paginación estándar de Magento: `?p=2`, `?p=3`... (48 productos/página
    por defecto), se corta cuando una página no devuelve productos.
- **Bloqueo de Cloudflare**: el sitio filtra por huella TLS/JA3, no solo por
  User-Agent. Verificado en vivo: `curl` (con cualquier UA) pasa con 200;
  `httpx` (usado hoy por `Crawler.fetch`) recibe 403 en *todas* las páginas,
  incluso con HTTP/2 activado. `curl_cffi` (impersonar TLS de Chrome) sería
  la alternativa más ligera, pero en la máquina Windows del usuario una
  política de Control de Aplicaciones bloquea su DLL nativa. Playwright
  (Chromium headless real) sí se ha probado en vivo con éxito: 200 OK y HTML
  con los datos de producto.

Decisión del usuario: usar **Playwright** para este competidor (más pesado
en dependencias, pero sin el bloqueo de Control de Aplicaciones que sí afecta
a `curl_cffi`, y resistente a futuros retos JS de Cloudflare). También pidió
que se dé de alta el competidor en la base de datos como parte de este
trabajo, no solo el código del crawler.

## Alcance

Incluye:
- Descarga vía Playwright con reutilización de navegador entre llamadas.
- Descubrimiento automático de categorías desde el menú principal.
- Parseo de la rejilla de producto por categoría (con paginación) a la
  misma forma de `dict` que ya producen `crawl_shopify_products` /
  `crawl_html_products`.
- Deduplicación por SKU entre categorías solapadas (padre/hijo).
- Columna `platform` en `competitors` y ruteo en `main.py` para no afectar a
  los competidores existentes.
- Alta del competidor Titanium Strength en la BD.
- Tests unitarios del parseo (sin navegador real).
- Añadir `playwright` a `requirements.txt` y nota de setup en el README.

Fuera de alcance (no pedido, no lo añade este diseño):
- Scraping de plazos de envío (`crawl_shipping_time` ya existe pero no está
  conectado al pipeline principal para ningún competidor; no se conecta
  aquí tampoco).
- Activar `daily_crawl.yml` en producción — el roadmap del README ya dice
  explícitamente que esto está pendiente de que la BD sea alcanzable desde
  internet, y Playwright en un runner de GitHub Actions es un tema aparte
  (requiere `playwright install --with-deps chromium` en el workflow) que no
  se toca en este trabajo.
- Un mecanismo genérico de "selector configurable por competidor" para el
  fallback HTML existente. Esto es una integración específica para un sitio
  Magento, no una generalización del scraper genérico.

## Diseño

### 1. `Crawler.fetch_rendered(url) -> str | None`

Reemplaza `httpx` por Playwright para las páginas de este competidor.
Lanza el navegador de forma perezosa (`self._browser`, `self._playwright`)
en la primera llamada y lo reutiliza en las siguientes — arrancar Chromium
por cada una de las ~58 páginas sería inaceptablemente lento. Mismo patrón
de reintentos que `fetch()` (3 intentos, backoff exponencial), mismo
`rate_limit` entre llamadas para no machacar el sitio.

`Crawler.close()`: cierra `self._browser`/`self._playwright` si se
llegaron a abrir. Se llama una vez desde `main.py`, al final del `main()`,
en un `finally`, para no dejar procesos de Chromium huérfanos aunque el
crawl falle a mitad.

### 2. `Crawler.crawl_magento_categories(base_url: str) -> list[dict]`

Orquestador, sigue el mismo patrón que `crawl_shopify_products`:

1. `html = await self.fetch_rendered(base_url)` → si falla, devuelve `[]`.
2. `category_urls = self._discover_magento_categories(html, base_url)`
   (función pura, parsea `nav.navigation a[href]`, filtra al mismo dominio,
   deduplica).
3. Por cada URL de categoría, pagina con un límite de seguridad (`max_pages
   = 20`, igual de espíritu que el `max_pages=50` de Shopify): construye
   `?p=N` a partir de la página 2, llama `fetch_rendered`, parsea con
   `self._parse_magento_category(html)` (función pura). Si una página
   devuelve 0 productos, corta la paginación de esa categoría y pasa a la
   siguiente.
4. Acumula todos los productos en un `dict` por SKU (deduplicación:
   categorías padre e hijas listan los mismos productos).
5. Devuelve `list(productos.values())`.

`_discover_magento_categories` y `_parse_magento_category` son funciones
puras sobre HTML (usan `selectolax`, igual que el resto del crawler), así
que se testean con HTML de fixture sin necesitar Playwright real — mismo
patrón que los tests actuales, que mockean `crawler.fetch`.

Forma del `dict` de producto devuelto (igual que los otros métodos de
`Crawler`, para que `Normalizer.normalize_product` no necesite cambios):

```python
{
    "id": sku,            # data-id; estable, ya es el identificador natural de Magento
    "sku": sku,
    "title": data_name,
    "url": href,
    "price": final_price,       # float, desde data-price-amount
    "original_price": old_price_or_final,  # = final_price si no hay descuento
    "available": True | False,  # clase in-stock / out-of-stock
}
```

### 3. Esquema: `migrations/004_add_competitor_platform.sql`

```sql
ALTER TABLE competitors
  ADD COLUMN platform VARCHAR(20) NULL AFTER product_api_url;
```

`NULL` en competidores existentes preserva el comportamiento actual
(Shopify si hay `product_api_url`, si no HTML genérico). `db.add_competitor`
gana un parámetro opcional `platform: str = None`, incluido en el INSERT.

### 4. Ruteo en `main.py`

```python
async def crawl_competitor_products(crawler, competitor):
    if competitor.get("platform") == "magento":
        products = await crawler.crawl_magento_categories(competitor["website_url"])
        return products, "magento"

    if competitor.get("product_api_url"):
        products = await crawler.crawl_shopify_products(competitor["product_api_url"])
        if products:
            return products, "shopify"

    products = await crawler.crawl_html_products(competitor["website_url"])
    return products, "html"
```

Y en `main()`, envolver el bucle de competidores en `try/finally` para
llamar a `await crawler.close()` al terminar.

### 5. Alta del competidor

Como parte de este trabajo (no un script aparte), se inserta:

```python
db.add_competitor(
    name="Titanium Strength",
    website_url="https://www.titaniumstrength.es",
    platform="magento",
    country="ES",
)
```

### 6. Dependencias

- `requirements.txt`: añadir `playwright==1.62.0` (versión probada en vivo
  contra el sitio durante la investigación de este diseño).
- README: nota de setup — tras `pip install -r requirements.txt`, correr
  `playwright install chromium` una vez (descarga ~115MB de binario del
  navegador).

## Manejo de errores

- `fetch_rendered` sigue el mismo contrato que `fetch`: `None` en fallo
  tras 3 intentos, nunca excepción — el resto del pipeline ya sabe tratar
  catálogos vacíos (`if not raw_products: continue` en `main.py`).
- Si `_discover_magento_categories` no encuentra ningún enlace de categoría
  (p. ej. cambia el markup del menú), `crawl_magento_categories` devuelve
  `[]` igual que un fallo de red — no rompe el resto del crawl de otros
  competidores.
- Categorías individuales que fallen al renderizar (`fetch_rendered`
  devuelve `None`) se saltan sin abortar el resto de categorías.

## Testing

- `_parse_magento_category`: fixture HTML con 2-3 productos (con y sin
  descuento, uno out-of-stock) → verifica sku/título/precio/disponibilidad.
- `_discover_magento_categories`: fixture HTML de nav con enlaces internos
  y externos mezclados → verifica filtro de dominio y deduplicación.
- `crawl_magento_categories`: monkeypatch de `fetch_rendered` (no
  Playwright real) para verificar orquestación (paginación hasta página
  vacía, deduplicación por SKU entre categorías solapadas).
- No se añaden tests de integración contra el sitio real ni contra
  Playwright real — coherente con el resto de la suite (`tests/` no toca
  red ni MySQL reales).
