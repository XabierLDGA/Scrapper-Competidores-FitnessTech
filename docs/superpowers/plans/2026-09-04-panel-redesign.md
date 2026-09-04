# Rediseño del panel como bandeja de cambios — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Sustituir las nueve vistas del panel actual por las dos que define el artboard aprobado —bandeja única de cambios de 24 h y vista por tienda— con tema claro/oscuro y los colores de FitnessTech.es.

**Architecture:** No cambia el modelo de la aplicación: Flask renderiza la página entera y el JavaScript solo decide qué sección se ve, con navegación por `#hash`. Entra una función pura nueva en `src/metrics.py` que aplana los cuatro tipos de evento en un feed ordenado; la plantilla, el CSS y el JS se reescriben; el mapa de calor se retira del código y de los tests.

**Tech Stack:** Python 3 · Flask + Jinja2 · pytest · CSS y JavaScript a mano, sin build ni dependencias de front.

**Spec:** `docs/superpowers/specs/2026-09-04-panel-redesign-design.md`
**Referencia visual:** `docs/superpowers/specs/2026-09-04-panel-redesign-artboard.html` — artboard exportado de Claude Design. Es la fuente de verdad del aspecto: colores, medidas, espaciados y textos salen de ahí. Ábrelo en el navegador para verlo funcionando con datos de ejemplo.

**Rama:** `redisenio-panel` (ya creada, con el spec commiteado).

## Global Constraints

- Todo el texto de interfaz va en **español con acentos correctos**. El repo ya lo hace en la plantilla actual.
- **Sin dependencias nuevas.** Ni de Python ni de front: nada de npm, bundlers ni frameworks. El JavaScript se escribe en ES5 sin `const`/`let`/arrow functions, igual que `static/js/console.js`.
- **Formato español de números y fechas solo en los filtros Jinja** de `dashboard.py` (`miles`, `pct`, `eur`, `fecha`). No se duplica en Python ni en JavaScript. Excepción única: el recálculo de cifras en cliente al filtrar por tienda, que usa la función `numeroEs` que ya existe en el JS actual y hay que conservar.
- **Ningún dato inventado.** Toda cifra del panel sale del catálogo real o de los eventos de las últimas 24 h, como dice el docstring de `src/metrics.py`. Los datos de ejemplo del artboard son solo maqueta.
- **Tokens de color, exactos** (tema claro / tema oscuro):
  `--accent:#00a7af` / `#00c2cb` · `--bg:#f4f6f6` / `#0e1215` · `--surface:#ffffff` / `#151b1f` · `--surface-2:#fafbfb` / `#1b2226` · `--ink:#0c1112` / `#e4eaed` · `--ink-2:#59666b` / `#9aa6ac` · `--ink-3:#8e9a9e` / `#77848a` · `--line:#e6eaeb` / `#232b30` · `--line-2:#d7dddf` / `#2c353a` · `--accent-ink:#00666b` / `#7fe4e9` · `--accent-wash:rgba(0,167,175,.10)` / `rgba(0,167,175,.16)`.
  Estados: `--up-bg:#fdecec` / `rgba(226,90,80,.16)` con `--up-ink:#b3261e` / `#f19b93` · `--down-bg:#e7f6ee` / `rgba(63,190,114,.16)` con `--down-ink:#127a4a` / `#6fd39a` · `--new-bg:#eaf1fe` / `rgba(94,132,240,.16)` con `--new-ink:#2b4ec2` / `#9db2f5` · `--gone-bg:#f2f0ee` / `rgba(150,140,130,.16)` con `--gone-ink:#6b6259` / `#b6ada4` · `--stock-bg:#fdf4e3` / `rgba(214,158,46,.16)` con `--stock-ink:#8d6100` / `#e0bc74`.
  Sombra: `--shadow:0 1px 2px rgba(12,17,18,.05)` en claro, `none` en oscuro.
- **Ojo con los nombres `--up-*` y `--down-*`:** en el artboard `--up-*` es rojo y se usa para las **bajadas** de precio, y `--down-*` es verde para las **subidas**. Nombran la dirección del semáforo comercial (una bajada del rival es mala noticia), no la del precio. Cópialos tal cual para no romper la correspondencia con el artboard.
- **Tema claro por defecto.** Persistido en `localStorage` bajo la clave `vig-theme`.
- Cada tarea termina con **commit propio**. Mensajes en español, en imperativo, como el historial del repo (`Filtrar por objetivo en las vistas de registro`).

## File Structure

| Fichero | Responsabilidad | Estado |
| --- | --- | --- |
| `src/metrics.py` | Agregados puros sobre las filas de la BD. Gana `build_change_feed`; pierde el mapa de calor, `target_code` y `COMPETITOR_LOGOS` | Modificar |
| `tests/test_metrics.py` | Tests de los agregados. Gana los del feed; pierde los del mapa de calor y los códigos | Modificar |
| `dashboard.py` | App Flask, filtros de formato, ruta `/` y `/crawl`. Solo cambia qué pasa a la plantilla | Modificar (`index`) |
| `templates/dashboard.html` | Marcado de las dos pantallas | Reescribir |
| `static/css/panel.css` | Estilo completo del panel, con los dos temas | Crear (sustituye `console.css`) |
| `static/js/panel.js` | Routing, filtros, pestañas, búsqueda, tema y reloj | Crear (sustituye `console.js`) |
| `README.md` | Descripción del panel | Modificar (secciones del dashboard) |

**Orden y por qué:** primero el backend (Task 1), luego la vista completa (Tasks 2-4) y solo al final la poda (Task 5). Así el panel nunca queda en un estado que no arranca: el código muerto se borra cuando ya nadie lo usa. Invertir el orden dejaría la plantilla vieja pidiendo `t.histogram` y reventando la página.

---

### Task 1: `build_change_feed` en `src/metrics.py`

Función pura que aplana los cuatro tipos de evento de todas las tiendas en una lista única ordenada por fecha descendente. Es el corazón de la pantalla nueva y lo único de este trabajo que se puede probar automáticamente, así que va con TDD y a fondo.

**Files:**
- Modify: `src/metrics.py` (añadir al final, tras `global_metrics`)
- Test: `tests/test_metrics.py` (añadir al final)

**Interfaces:**
- Consumes: `build_targets(...)` (ya existe) y su `_as_datetime` interna.
- Produces: `build_change_feed(targets: list[dict]) -> list[dict]`. Cada entrada:
  `{"kind": str, "store": str, "is_own_store": bool, "sku": str|None, "title": str, "url": str|None, "when": datetime|None, "old_price": float|None, "new_price": float|None, "pct": float|None, "was_available": bool|None, "now_available": bool|None, "last_seen": date|None}`.
  `kind` ∈ `{"price_down", "price_up", "new", "stock", "removed"}`. Lo consumen Task 2 (`dashboard.py`) y Task 3 (plantilla).

- [ ] **Step 1: Escribir los tests que fallan**

Añade al final de `tests/test_metrics.py`. Fíjate en los helpers `_competitor` y `_product` que ya existen en el fichero y reutilízalos.

```python
# ---------- feed de cambios ----------

def _targets_con(**listas):
    """Monta un objetivo unico ('Acme') con las listas de eventos que se le
    pasen, para no repetir el andamiaje en cada test del feed."""
    return build_targets(
        competitors=[_competitor("Acme")],
        new_products=listas.get("new_products", []),
        price_events=listas.get("price_events", []),
        availability_events=listas.get("availability_events", []),
        removed_products=listas.get("removed_products", []),
        catalog=[],
    )


def _evento_precio(tipo="decrease", old=1499.0, new=1279.0, pct=-14.7,
                   cuando="2026-09-04T03:12:00", competitor="Acme"):
    return {
        "competitor": competitor, "title": "Half Rack HD", "sku": "TS-HR-HD",
        "event_type": tipo, "old_price": old, "new_price": new,
        "percent_change": pct, "detected_at": cuando,
    }


def test_change_feed_parte_los_eventos_de_precio_por_direccion():
    feed = build_change_feed(_targets_con(price_events=[
        _evento_precio(tipo="decrease"),
        _evento_precio(tipo="increase", old=2790.0, new=2990.0, pct=7.2),
    ]))

    assert {c["kind"] for c in feed} == {"price_down", "price_up"}


def test_change_feed_lleva_los_precios_y_el_porcentaje():
    feed = build_change_feed(_targets_con(price_events=[_evento_precio()]))

    cambio = feed[0]
    assert cambio["old_price"] == 1499.0
    assert cambio["new_price"] == 1279.0
    assert cambio["pct"] == -14.7
    assert cambio["was_available"] is None
    assert cambio["last_seen"] is None


def test_change_feed_las_altas_traen_precio_sin_precio_anterior():
    # La plantilla pinta "antes -> ahora" solo si hay old_price: un alta
    # tiene que dejarlo a None para que salga el precio suelto.
    feed = build_change_feed(_targets_con(new_products=[{
        "competitor": "Acme", "title": "Rack FT Pro", "sku": "FT-RK-20",
        "url": "https://example.com/rack", "price": 1190.0,
        "first_seen": "2026-09-04T03:07:00",
    }]))

    assert feed[0]["kind"] == "new"
    assert feed[0]["new_price"] == 1190.0
    assert feed[0]["old_price"] is None


def test_change_feed_lleva_el_antes_y_el_despues_de_disponibilidad():
    feed = build_change_feed(_targets_con(availability_events=[{
        "competitor": "Acme", "title": "Mancuernas hex", "sku": "TS-MH-30",
        "url": "https://example.com/mh", "was_available": 1,
        "now_available": False, "detected_at": "2026-09-04T03:12:00",
    }]))

    assert feed[0]["kind"] == "stock"
    # La BD devuelve 1/0 en unas filas y True/False en otras: el feed
    # normaliza a bool para que la plantilla no tenga que adivinar.
    assert feed[0]["was_available"] is True
    assert feed[0]["now_available"] is False


def test_change_feed_las_bajas_traen_la_ultima_vez_que_se_vio():
    feed = build_change_feed(_targets_con(removed_products=[{
        "competitor": "Acme", "title": "Banco plano", "sku": "TS-BP",
        "url": "https://example.com/bp", "last_seen": date(2026, 8, 31),
        "removed_at": "2026-09-04T03:12:00",
    }]))

    assert feed[0]["kind"] == "removed"
    assert feed[0]["last_seen"] == date(2026, 8, 31)


def test_change_feed_ordena_por_fecha_descendente_mezclando_tipos():
    feed = build_change_feed(_targets_con(
        price_events=[_evento_precio(cuando="2026-09-04T01:00:00")],
        new_products=[{"competitor": "Acme", "title": "Nuevo", "sku": None,
                       "url": None, "price": 10.0,
                       "first_seen": "2026-09-04T05:00:00"}],
        availability_events=[{"competitor": "Acme", "title": "Stock",
                              "sku": None, "url": None, "was_available": 0,
                              "now_available": 1,
                              "detected_at": "2026-09-04T03:00:00"}],
    ))

    assert [c["title"] for c in feed] == ["Nuevo", "Stock", "Half Rack HD"]


def test_change_feed_ordena_fechas_de_tipos_mezclados():
    # MySQL devuelve date en unas columnas y datetime en otras; compararlas
    # entre si revienta la pagina entera.
    feed = build_change_feed(_targets_con(
        removed_products=[{"competitor": "Acme", "title": "Baja",
                           "sku": None, "url": None, "last_seen": None,
                           "removed_at": date(2026, 9, 4)}],
        price_events=[_evento_precio(cuando=datetime(2026, 9, 3, 3, 12))],
    ))

    assert [c["title"] for c in feed] == ["Baja", "Half Rack HD"]


def test_change_feed_manda_al_final_lo_que_no_tiene_fecha_legible():
    feed = build_change_feed(_targets_con(
        price_events=[_evento_precio(cuando="ayer por la tarde")],
        new_products=[{"competitor": "Acme", "title": "Con fecha",
                       "sku": None, "url": None, "price": 10.0,
                       "first_seen": "2026-09-01T03:00:00"}],
    ))

    assert [c["title"] for c in feed] == ["Con fecha", "Half Rack HD"]
    assert feed[-1]["when"] is None


def test_change_feed_mezcla_las_tiendas_y_marca_las_propias():
    targets = build_targets(
        competitors=[_competitor("Titanium Strength"),
                     _competitor("Fitness Tech")],
        new_products=[],
        price_events=[_evento_precio(competitor="Titanium Strength",
                                     cuando="2026-09-04T03:12:00"),
                      _evento_precio(competitor="Fitness Tech",
                                     cuando="2026-09-04T03:07:00")],
        availability_events=[], removed_products=[], catalog=[],
    )

    feed = build_change_feed(targets)
    por_tienda = {c["store"]: c for c in feed}
    assert por_tienda["Titanium Strength"]["is_own_store"] is False
    assert por_tienda["Fitness Tech"]["is_own_store"] is True


def test_change_feed_sin_eventos_devuelve_una_lista_vacia():
    assert build_change_feed(_targets_con()) == []


def test_change_feed_sin_objetivos_devuelve_una_lista_vacia():
    assert build_change_feed([]) == []
```

Añade `build_change_feed` al `from src.metrics import (...)` de la cabecera del fichero de tests, y `date`/`datetime` al import de `datetime` si no están ya.

- [ ] **Step 2: Ejecutar los tests para verlos fallar**

Run: `python -m pytest tests/test_metrics.py -k change_feed -v`
Expected: FAIL — `ImportError: cannot import name 'build_change_feed'`

- [ ] **Step 3: Implementar `build_change_feed`**

Añade al final de `src/metrics.py`:

```python
def _bool_o_none(value) -> bool | None:
    """MySQL devuelve 1/0 en unas filas y True/False en otras. La plantilla
    no deberia tener que distinguirlas, asi que el feed normaliza aqui."""
    return None if value is None else bool(value)


def build_change_feed(targets: list[dict]) -> list[dict]:
    """Aplana los cuatro tipos de evento de todos los objetivos en una sola
    lista, ordenada de mas reciente a mas antiguo.

    Es lo que alimenta la bandeja de la pantalla principal: la pregunta que
    se le hace al panel cada manana es "que se movio anoche", y esa
    respuesta no deberia estar repartida en cuatro tablas.

    No compone texto: guarda los valores y deja que la plantilla los pinte
    con los filtros de formato, para que el formato espanol viva en un solo
    sitio.
    """
    feed = []

    for target in targets:
        comun = {"store": target["name"],
                 "is_own_store": target["is_own_store"]}

        for event in target["price_events"]:
            feed.append({
                **comun,
                "kind": "price_down" if event.get("event_type") == "decrease" else "price_up",
                "sku": event.get("sku"),
                "title": event.get("title"),
                "url": event.get("url"),
                "when": _as_datetime(event.get("detected_at")),
                "old_price": event.get("old_price"),
                "new_price": event.get("new_price"),
                "pct": event.get("percent_change"),
                "was_available": None,
                "now_available": None,
                "last_seen": None,
            })

        for product in target["new_products"]:
            feed.append({
                **comun,
                "kind": "new",
                "sku": product.get("sku"),
                "title": product.get("title"),
                "url": product.get("url"),
                "when": _as_datetime(product.get("first_seen")),
                # Sin precio anterior: la plantilla pinta el precio suelto.
                "old_price": None,
                "new_price": product.get("price"),
                "pct": None,
                "was_available": None,
                "now_available": None,
                "last_seen": None,
            })

        for event in target["availability_events"]:
            feed.append({
                **comun,
                "kind": "stock",
                "sku": event.get("sku"),
                "title": event.get("title"),
                "url": event.get("url"),
                "when": _as_datetime(event.get("detected_at")),
                "old_price": None,
                "new_price": None,
                "pct": None,
                "was_available": _bool_o_none(event.get("was_available")),
                "now_available": _bool_o_none(event.get("now_available")),
                "last_seen": None,
            })

        for product in target["removed_products"]:
            feed.append({
                **comun,
                "kind": "removed",
                "sku": product.get("sku"),
                "title": product.get("title"),
                "url": product.get("url"),
                "when": _as_datetime(product.get("removed_at")),
                "old_price": None,
                "new_price": None,
                "pct": None,
                "was_available": None,
                "now_available": None,
                "last_seen": product.get("last_seen"),
            })

    # datetime.min para las fechas ilegibles: ordenar con None dentro de la
    # lista lanza TypeError y se lleva por delante la pagina entera. Van al
    # final, que es donde molestan menos.
    feed.sort(key=lambda c: c["when"] or datetime.min, reverse=True)
    return feed
```

- [ ] **Step 4: Ejecutar los tests para verlos pasar**

Run: `python -m pytest tests/test_metrics.py -k change_feed -v`
Expected: PASS — 11 tests

Luego la suite entera, que no debe haberse movido:
Run: `python -m pytest -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/metrics.py tests/test_metrics.py
git commit -m "Aplanar los cambios de las cuatro tiendas en un feed unico"
```

---

### Task 2: La cáscara — tema, barra lateral y cabecera

Reescribe la plantilla, el CSS y el JS con la estructura del artboard, pero **solo la cáscara**: barra lateral, cabecera y el armazón de las dos vistas, todavía vacías por dentro. Al terminar esta tarea el panel arranca, se ve la navegación con datos reales y el tema cambia; el contenido llega en las Tasks 3 y 4.

**Files:**
- Modify: `dashboard.py` (solo la función `index`, líneas ~104-121)
- Rewrite: `templates/dashboard.html`
- Create: `static/css/panel.css`
- Create: `static/js/panel.js`
- Delete: `static/css/console.css`, `static/js/console.js`

**Interfaces:**
- Consumes: `build_change_feed` de Task 1.
- Produces: el contexto de plantilla `{targets, totals, changes}`; las clases CSS `.panel`, `.rail`, `.stage`, `.topbar`, `.view`; y en `panel.js` las funciones `mostrar(clave)`, `numeroEs(valor, decimales)`, `aplicarTema(tema)`, `coincide(fila)` —¿pasa la fila la búsqueda actual?— y el array `refiltradores`, donde cada vista registra su función de refiltrado. Las Tasks 3 y 4 se enganchan a `refiltradores`; no vuelven a tocar el buscador.

- [ ] **Step 1: Pasar el feed a la plantilla**

En `dashboard.py`, cambia el import y la función `index`:

```python
from src.metrics import build_change_feed, build_targets, global_metrics
```

```python
@app.route("/")
def index():
    db = get_db()
    targets = build_targets(
        competitors=db.get_competitor_stats(),
        new_products=db.get_recently_added_products(hours=24),
        price_events=db.get_recent_price_events(hours=24),
        availability_events=db.get_recent_availability_events(hours=24),
        removed_products=db.get_recently_removed_products(hours=24),
        catalog=db.get_latest_snapshots(),
    )
    return render_template(
        "dashboard.html",
        targets=targets,
        totals=global_metrics(targets),
        changes=build_change_feed(targets),
    )
```

`PRICE_BANDS` sale del import y `price_bands` deja de pasarse a la plantilla.

- [ ] **Step 2: Escribir `static/css/panel.css` con los tokens y el armazón**

Empieza el fichero con los tokens **exactos** de la sección Global Constraints, en `:root` y `:root[data-theme="dark"]`, copiados del bloque `<style>` del artboard (`docs/superpowers/specs/2026-09-04-panel-redesign-artboard.html`, líneas 15-45).

```css
:root{
  --bg:#f4f6f6; --surface:#ffffff; --surface-2:#fafbfb;
  --ink:#0c1112; --ink-2:#59666b; --ink-3:#8e9a9e;
  --line:#e6eaeb; --line-2:#d7dddf;
  --accent:#00a7af; --accent-ink:#00666b; --accent-wash:rgba(0,167,175,.10);
  --up-bg:#fdecec; --up-ink:#b3261e;
  --down-bg:#e7f6ee; --down-ink:#127a4a;
  --new-bg:#eaf1fe; --new-ink:#2b4ec2;
  --gone-bg:#f2f0ee; --gone-ink:#6b6259;
  --stock-bg:#fdf4e3; --stock-ink:#8d6100;
  --shadow:0 1px 2px rgba(12,17,18,.05);
}
:root[data-theme="dark"]{
  --bg:#0e1215; --surface:#151b1f; --surface-2:#1b2226;
  --ink:#e4eaed; --ink-2:#9aa6ac; --ink-3:#77848a;
  --line:#232b30; --line-2:#2c353a;
  --accent:#00c2cb; --accent-ink:#7fe4e9; --accent-wash:rgba(0,167,175,.16);
  --up-bg:rgba(226,90,80,.16); --up-ink:#f19b93;
  --down-bg:rgba(63,190,114,.16); --down-ink:#6fd39a;
  --new-bg:rgba(94,132,240,.16); --new-ink:#9db2f5;
  --gone-bg:rgba(150,140,130,.16); --gone-ink:#b6ada4;
  --stock-bg:rgba(214,158,46,.16); --stock-ink:#e0bc74;
  --shadow:none;
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
     font-family:'IBM Plex Sans',system-ui,sans-serif;-webkit-font-smoothing:antialiased}
a{color:var(--accent-ink);text-decoration:none}
a:hover{color:var(--accent)}
input,button{font:inherit}
::placeholder{color:var(--ink-3)}
```

Después, el armazón. El artboard usa estilos inline; tradúcelos a clases con estos nombres, leyendo las medidas del propio artboard:

- `.panel` — rejilla de dos columnas `246px 1fr`, `min-height:100vh`.
- `.rail` — barra lateral: fondo `#000` (negro fijo, **no** un token: es negro en los dos temas), `position:sticky`, `top:0`, `height:100vh`, `padding:20px 14px`, columna flex con `gap:22px`.
- `.rail__logo` — `height:26px;width:auto`.
- `.rail__search` — caja de búsqueda: fondo `rgba(255,255,255,.07)`, borde `rgba(255,255,255,.10)`, `border-radius:10px`, `height:36px`; el `input` transparente, sin borde, texto blanco de 13px.
- `.rail__section` — rótulo de grupo: Archivo itálica 700, 10px, `letter-spacing:.12em`, mayúsculas, `rgba(255,255,255,.38)`.
- `.navitem` — enlace de tienda: fila flex, `gap:10px`, `padding:8px 10px`, `border-radius:9px`, 13.5px. Con `.is-active` el texto va a `#fff`. Modificadores `.navitem--own` (fondo `rgba(0,167,175,.22)`, y `.46` si activo) y `.navitem--rival` (fondo `rgba(212,63,53,.20)`, y `.42` si activo).
- `.navitem__dot` — 6px, redondo. `#5fe0e6` en tienda propia en línea, `#f19b93` en rival en línea, `rgba(255,255,255,.28)` si no está en línea.
- `.navitem__count` — IBM Plex Mono 11px, `rgba(255,255,255,.55)`.
- `.navitem--pronto` — el letrero de «Comparativa Titanium»: `rgba(255,255,255,.32)`, sin `href`, con `.pill-pronto` dentro (9.5px, mayúsculas, borde `rgba(255,255,255,.18)`, `border-radius:999px`, `padding:2px 6px`).
- `.rail__foot` — `margin-top:auto`, reloj en Mono 11px `rgba(255,255,255,.42)` y botón de tema de 28px con borde `rgba(255,255,255,.14)`.
- `.stage` — columna flex, `min-width:0`.
- `.topbar` — `padding:18px 28px`, borde inferior `var(--line)`, fondo `var(--surface)`. Título en Archivo itálica 800, 19px, mayúsculas; subtítulo 13px `var(--ink-3)`; botón `.btn-sync` a la derecha con `margin-left:auto`, fondo `var(--accent)`, texto blanco, `height:34px`, `border-radius:10px`.
- `.viewport` — `padding:22px 28px 40px`, columna flex con `gap:22px`.
- `.view` — `display:none`; `.view.is-on` — `display:flex;flex-direction:column;gap:22px`.
- `.origin` — la línea de pie, 11.5px `var(--ink-3)`.

Responsive: por debajo de 900px la rejilla pasa a una columna y `.rail` deja de ser `sticky` (repasa cómo lo resuelve `console.css` antes de borrarlo, que ya tenía un menú plegable para móvil).

- [ ] **Step 3: Escribir la cáscara de `templates/dashboard.html`**

Reescribe el fichero entero. Cabecera y armazón:

```jinja
<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>Vigilancia de mercado — FitnessTech</title>
<link rel="icon" href="data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 32 32%22><rect width=%2232%22 height=%2232%22 fill=%22%23000000%22/><path d=%22M6 6h5v3H9v14h2v3H6zM26 6h-5v3h2v14h-2v3h5z%22 fill=%22%2300a7af%22/><rect x=%2214%22 y=%2211%22 width=%224%22 height=%2210%22 fill=%22%2300a7af%22/></svg>">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Archivo:ital,wght@1,700;1,800&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
<link rel="stylesheet" href="{{ asset('css/panel.css') }}">
<script>
  // Antes de pintar nada: si se aplicara al final, quien tenga el tema
  // oscuro veria un fogonazo blanco en cada carga.
  (function () {
    try {
      var t = localStorage.getItem("vig-theme");
      document.documentElement.dataset.theme = (t === "dark" || t === "light") ? t : "light";
    } catch (e) { document.documentElement.dataset.theme = "light"; }
  })();
</script>
</head>
<body>
```

Barra lateral (`propias` y `rivales` se derivan de `targets` con `is_own_store`, igual que en la plantilla actual):

```jinja
{% set propias = targets | selectattr('is_own_store') | list %}
{% set rivales = targets | rejectattr('is_own_store') | list %}

<div class="panel">
<aside class="rail">
  <img class="rail__logo" src="{{ asset('logos/fitnesstech-brand.png') }}" alt="Fitness Tech">

  <div class="rail__search">
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="rgba(255,255,255,.5)"
         stroke-width="1.5" stroke-linecap="round" aria-hidden="true">
      <circle cx="7" cy="7" r="4.5"></circle><path d="M10.5 10.5 14 14"></path>
    </svg>
    <input type="search" id="buscador" autocomplete="off" spellcheck="false"
           placeholder="Buscar producto o SKU" aria-label="Buscar producto o SKU">
  </div>

  <nav class="rail__nav" aria-label="Secciones">
    <p class="rail__section">Panel principal</p>
    <a class="navitem" href="#cambios" data-view="cambios">
      <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor"
           stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <path d="M2 4h12M2 8h12M2 12h8"></path>
      </svg>
      <span class="navitem__text">Cambios</span>
      <span class="navitem__count">{{ changes | length }}</span>
    </a>

    {% for grupo, titulo, clase in [(propias, 'Mis tiendas', 'navitem--own'), (rivales, 'Competencia', 'navitem--rival')] %}
    <p class="rail__section">{{ titulo }}</p>
    {% for t in grupo %}
    <a class="navitem {{ clase }}" href="#tienda/{{ t.slug }}" data-view="tienda/{{ t.slug }}">
      <span class="navitem__dot{{ ' is-live' if t.is_live }}"
            title="{{ 'Leída en las últimas 48 h' if t.is_live else 'Sin lectura reciente' }}"></span>
      <span class="navitem__text">{{ t.name }}</span>
      <span class="navitem__count">{{ t.metrics.total | miles }}</span>
    </a>
    {% endfor %}
    {% endfor %}

    <p class="rail__section">Análisis</p>
    <span class="navitem navitem--pronto">
      <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor"
           stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <path d="M3 13V7M8 13V3M13 13v-4"></path>
      </svg>
      <span class="navitem__text">Comparativa Titanium</span>
      <span class="pill-pronto">Pronto</span>
    </span>
  </nav>

  <div class="rail__foot">
    <span class="rail__clock">Madrid <b id="reloj">--:--</b></span>
    <button type="button" id="tema" class="rail__theme" aria-label="Cambiar tema">
      <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor"
           stroke-width="1.4" stroke-linecap="round" aria-hidden="true">
        <path d="M13 9.5A5.5 5.5 0 0 1 6.5 3a5.5 5.5 0 1 0 6.5 6.5z"></path>
      </svg>
    </button>
  </div>
</aside>
```

Cabecera y armazón de vistas. **Los avisos `flash` van aquí**: en la plantilla vieja vivían en un bloque `.notices` que desaparece con ella, y si no se recolocan a mano el resultado de Sincronizar se pierde sin que nadie lo note.

```jinja
<div class="stage">
  <header class="topbar">
    <h1 class="topbar__title" id="titulo">Cambios</h1>
    <span class="topbar__sub" id="subtitulo">Últimas 24 horas · {{ targets | length }} escaparates</span>
    <form method="POST" action="{{ url_for('trigger_crawl') }}">
      <button type="submit" class="btn-sync">
        <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor"
             stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <path d="M14 8a6 6 0 1 1-1.8-4.3"></path><path d="M14 2v4h-4"></path>
        </svg>
        <span>Sincronizar</span>
      </button>
    </form>
  </header>

  <div class="viewport">
    {% with mensajes = get_flashed_messages(with_categories=true) %}
      {% if mensajes %}
      <div class="avisos">
        {% for categoria, texto in mensajes %}
        <p class="aviso aviso--{{ categoria }}">{{ texto }}</p>
        {% endfor %}
      </div>
      {% endif %}
    {% endwith %}

    <section class="view is-on" data-view="cambios" tabindex="-1">
      {# Task 3 #}
    </section>

    {% for t in targets %}
    <section class="view" data-view="tienda/{{ t.slug }}" tabindex="-1">
      {# Task 4 #}
    </section>
    {% endfor %}

    <p class="origin">Lectura de MySQL al cargar. Sincronización automática cada día a las 03:00 (Madrid).</p>
  </div>
</div>
</div>

<script src="{{ asset('js/panel.js') }}" defer></script>
</body>
</html>
```

- [ ] **Step 4: Escribir `static/js/panel.js` con tema, reloj y routing**

ES5, sin dependencias, envuelto en IIFE, igual que el JS actual. `numeroEs` se copia tal cual de `static/js/console.js` (líneas 29-41) porque la Task 3 la necesita para repintar cifras al filtrar.

```javascript
(function () {
  "use strict";

  // ---------- tema ----------
  var raiz = document.documentElement;

  function aplicarTema(tema) {
    raiz.dataset.theme = tema;
    try { localStorage.setItem("vig-theme", tema); } catch (e) {}
  }

  var botonTema = document.getElementById("tema");
  if (botonTema) {
    botonTema.addEventListener("click", function () {
      aplicarTema(raiz.dataset.theme === "dark" ? "light" : "dark");
    });
  }

  // ---------- reloj ----------
  var reloj = document.getElementById("reloj");
  function pintarHora() {
    if (!reloj) return;
    reloj.textContent = new Date().toLocaleTimeString("es-ES", {
      timeZone: "Europe/Madrid", hour: "2-digit", minute: "2-digit"
    });
  }
  pintarHora();
  setInterval(pintarHora, 20000);

  // ---------- numeros en formato espanol ----------
  // Punto para los miles, coma para los decimales. Se usa al repintar las
  // cifras de cabecera cuando se filtra por tienda, que es lo unico que el
  // servidor no puede formatear.
  function numeroEs(valor, decimales) {
    var texto = valor.toFixed(decimales || 0);
    var partes = texto.split(".");
    partes[0] = partes[0].replace(/\B(?=(\d{3})+(?!\d))/g, ".");
    return partes.length > 1 ? partes.join(",") : partes[0];
  }

  // ---------- busqueda ----------
  // Vive aqui, en el IIFE, porque la usan tanto la bandeja como cada vista
  // de tienda: el buscador de la barra lateral filtra la vista que este
  // abierta, sea cual sea.
  var textoBusqueda = "";
  function busquedaActual() { return textoBusqueda; }

  function coincide(fila) {
    return !textoBusqueda
      || fila.getAttribute("data-busca").indexOf(textoBusqueda) !== -1;
  }

  // Cada vista registra aqui su funcion de refiltrado al construirse, para
  // que el buscador no tenga que saber como funciona ninguna por dentro.
  var refiltradores = [];

  var buscador = document.getElementById("buscador");
  if (buscador) {
    buscador.addEventListener("input", function () {
      textoBusqueda = buscador.value.trim().toLowerCase();
      refiltradores.forEach(function (fn) { fn(); });
    });
  }

  // ---------- navegacion ----------
  var vistas = [].slice.call(document.querySelectorAll(".view"));
  var items = [].slice.call(document.querySelectorAll(".navitem[data-view]"));
  var titulo = document.getElementById("titulo");
  var subtitulo = document.getElementById("subtitulo");

  function mostrar(clave) {
    var vista = document.querySelector('.view[data-view="' + clave + '"]');
    if (!vista) { vista = vistas[0]; clave = vista.getAttribute("data-view"); }

    vistas.forEach(function (v) { v.classList.toggle("is-on", v === vista); });
    items.forEach(function (n) {
      n.classList.toggle("is-active", n.getAttribute("data-view") === clave);
    });

    if (titulo) titulo.textContent = vista.getAttribute("data-titulo") || "Cambios";
    if (subtitulo) subtitulo.textContent = vista.getAttribute("data-sub") || "";
  }

  function desdeHash() {
    mostrar((location.hash || "#cambios").slice(1));
  }
  window.addEventListener("hashchange", desdeHash);
  desdeHash();
})();
```

En la plantilla, cada `.view` lleva `data-titulo` y `data-sub` para que la cabecera se actualice al navegar: `data-titulo="Cambios"` con `data-sub="Últimas 24 horas · N escaparates"` en la bandeja, y `data-titulo="{{ t.name }}"` con `data-sub="Última lectura {{ t.last_crawled_at | fecha(true) }}"` en cada tienda. Añádelos ahora a los dos `<section class="view">` del Step 3.

- [ ] **Step 5: Borrar el CSS y el JS viejos**

```bash
git rm static/css/console.css static/js/console.js
```

- [ ] **Step 6: Comprobar que arranca**

Run: `python dashboard.py` y abre `http://localhost:5000`.
Expected: se ve la barra lateral negra con el logo, las cuatro tiendas repartidas en *Mis tiendas* y *Competencia* con sus totales reales, el letrero *Pronto*, el reloj en hora de Madrid y la cabecera con el botón Sincronizar. El cuerpo está vacío: es lo esperado en esta tarea. El botón de tema alterna claro/oscuro y **la elección sobrevive a recargar la página sin ningún parpadeo blanco**. Pulsar una tienda en la barra lateral cambia el título de la cabecera.

Run: `python -m pytest -q`
Expected: PASS (aquí todavía no se ha tocado nada que los tests cubran, salvo `dashboard.py`).

- [ ] **Step 7: Commit**

```bash
git add -A dashboard.py templates/dashboard.html static/css static/js
git commit -m "Rehacer la cascara del panel con el tema claro y oscuro"
```

---

### Task 3: Pantalla «Cambios»

Rellena la vista de la bandeja: filtro de tienda, cinco cifras, tabla unificada y tarjetas por tienda.

**Files:**
- Modify: `templates/dashboard.html` (la `<section class="view" data-view="cambios">`)
- Modify: `static/css/panel.css` (añadir)
- Modify: `static/js/panel.js` (añadir)

**Interfaces:**
- Consumes: `changes` (Task 1), `totals`, `targets`; de `panel.js`, `numeroEs`.
- Produces: el macro Jinja `detalle(c)` y las clases `.cifras`, `.pastilla`, `.tabla`, `.tarjetas`, que reutiliza la Task 4.

- [ ] **Step 1: Escribir el macro del detalle y el de la píldora de tipo**

Al principio de `templates/dashboard.html`, tras el `{% set %}` de propias/rivales:

```jinja
{#  Etiqueta y color de cada tipo de cambio. Ojo: 'price_down' usa la rampa
    --up-* (roja) y 'price_up' la --down-* (verde). Nombran la direccion
    del semaforo comercial, no la del precio: que un rival baje es mala
    noticia. Viene asi del artboard; no lo "arregles". #}
{% set TIPOS = {
  'price_down': ('Bajada', 'up'),
  'price_up':   ('Subida', 'down'),
  'new':        ('Alta',   'new'),
  'removed':    ('Baja',   'gone'),
  'stock':      ('Stock',  'stock'),
} %}

{% macro pildora(kind) %}
  {%- set etiqueta, tono = TIPOS[kind] -%}
  <span class="pildora pildora--{{ tono }}">{{ etiqueta }}</span>
{% endmacro %}

{#  Columna Detalle. Una sola regla para los precios: si hay precio
    anterior se pinta "antes -> ahora" con su porcentaje; si no, el precio
    suelto (que es el caso de las altas). #}
{% macro detalle(c) %}
  {%- if c.kind in ('price_down', 'price_up', 'new') -%}
    {%- if c.old_price is not none -%}
      {{ c.old_price | eur }} <span class="flecha" aria-hidden="true">→</span> {{ c.new_price | eur }}
      {%- if c.pct is not none %} <b class="delta">{{ '%+.1f' | format(c.pct) | replace('.', ',') }} %</b>{% endif -%}
    {%- else -%}
      {{ c.new_price | eur }}
    {%- endif -%}
  {%- elif c.kind == 'stock' -%}
    {{ 'Disponible' if c.was_available else 'Agotado' }}
    <span class="flecha" aria-hidden="true">→</span>
    {{ 'Disponible' if c.now_available else 'Agotado' }}
  {%- else -%}
    Visto {{ c.last_seen | fecha }}
  {%- endif -%}
{% endmacro %}

{% macro producto(c) %}
  {%- if c.url -%}<a href="{{ c.url }}" target="_blank" rel="noopener">{{ c.title }}</a>
  {%- else -%}{{ c.title }}{%- endif -%}
{% endmacro %}
```

- [ ] **Step 2: Escribir el contenido de la vista**

Dentro de `<section class="view is-on" data-view="cambios" ...>`:

```jinja
<div class="filtros-tienda" role="group" aria-label="Filtrar por tienda">
  <span class="filtros__rotulo">Tienda</span>
  <button type="button" class="pastilla is-active" data-tienda="">
    <span class="pastilla__dot"></span>Todas
  </button>
  {% for t in targets %}
  <button type="button" class="pastilla" data-tienda="{{ t.name }}"
          data-total="{{ t.metrics.total }}"
          data-disp="{{ t.metrics.availability_pct }}"
          data-promo="{{ t.metrics.promo_pct }}"
          data-live="{{ 1 if t.is_live else 0 }}">
    <span class="pastilla__dot{{ ' is-live' if t.is_live }}"></span>{{ t.name }}
  </button>
  {% endfor %}
</div>

<div class="cifras">
  {# Cada cifra que el JS repinta al filtrar va en su propio <span> con id.
     Si el numero fuese texto suelto dentro del <p>, el JS tendria que
     manosear firstChild.nodeValue y se romperia en cuanto alguien toque
     el marcado. #}
  <div class="cifra"><p class="cifra__rotulo">Productos vigilados</p>
    <p class="cifra__valor"><span id="c-productos">{{ totals.products | miles }}</span></p></div>
  <div class="cifra"><p class="cifra__rotulo">Tiendas en línea</p>
    <p class="cifra__valor"><span id="c-live">{{ totals.live_targets }}</span><span class="cifra__unidad" id="c-live-total">/ {{ totals.targets }}</span></p></div>
  <div class="cifra"><p class="cifra__rotulo">Disponibilidad</p>
    <p class="cifra__valor"><span id="c-disp">{{ totals.availability_pct | pct }}</span><span class="cifra__unidad">%</span></p></div>
  <div class="cifra"><p class="cifra__rotulo">Con precio rebajado</p>
    <p class="cifra__valor"><span id="c-promo">{{ totals.promo_pct | pct }}</span><span class="cifra__unidad">%</span></p></div>
  <div class="cifra"><p class="cifra__rotulo">Cambios 24 h</p>
    <p class="cifra__valor"><span id="c-cambios">{{ changes | length }}</span></p></div>
</div>

<section class="bloque">
  <div class="bloque__filtros" role="group" aria-label="Filtrar por tipo">
    {% for clave, etiqueta in [('', 'Todos'), ('price', 'Precios'), ('new', 'Altas'), ('stock', 'Stock'), ('removed', 'Bajas')] %}
    <button type="button" class="pastilla{{ ' is-active' if not clave }}" data-tipo="{{ clave }}">
      {{ etiqueta }} <small data-cuenta-tipo="{{ clave }}"></small>
    </button>
    {% endfor %}
  </div>
  <div class="tablawrap">
    <table class="tabla">
      <thead><tr>
        <th>Tienda</th><th>Cambio</th><th>Producto</th>
        <th class="t-num">Detalle</th><th class="t-num">Detectado</th>
      </tr></thead>
      <tbody>
        {% for c in changes %}
        <tr data-tienda="{{ c.store }}" data-tipo="{{ c.kind }}"
            data-busca="{{ (c.title ~ ' ' ~ (c.sku or '')) | lower }}">
          <td><span class="chip">{{ c.store }}</span></td>
          <td>{{ pildora(c.kind) }}</td>
          <td class="t-nombre">{{ producto(c) }}</td>
          <td class="t-num t-detalle t-detalle--{{ TIPOS[c.kind][1] }}">{{ detalle(c) }}</td>
          <td class="t-num t-cuando">{{ c.when | fecha(true) }}</td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
    <p class="vacio" data-vacio>Nada que revisar con este filtro.</p>
  </div>
</section>

<div class="tarjetas">
  {% for t in targets %}
  <a class="tarjeta" href="#tienda/{{ t.slug }}" data-tienda="{{ t.name }}">
    <span class="tarjeta__cab">
      <span class="tarjeta__dot{{ ' is-live' if t.is_live }}"></span>
      <span class="tarjeta__nombre">{{ t.name }}</span>
      <span class="tarjeta__rol">{{ 'Tienda propia' if t.is_own_store else 'Competencia' }}</span>
    </span>
    <span class="tarjeta__cifras">
      <span><small>Catálogo</small><b>{{ t.metrics.total | miles }}</b></span>
      <span><small>Disponible</small><b>{{ t.metrics.availability_pct | pct }} %</b></span>
      <span><small>Mediana</small><b>{{ t.metrics.median_price | eur }}</b></span>
    </span>
    <span class="tarjeta__pie">
      {% if t.is_live %}Leída {{ t.last_crawled_at | fecha(true) }}
      {% else %}Sin lectura reciente · {{ t.last_crawled_at | fecha(true) }}{% endif %}
    </span>
  </a>
  {% endfor %}
</div>
```

- [ ] **Step 3: Estilar la bandeja en `panel.css`**

Siguiendo el artboard:

- `.pastilla` — `height:30px`, `padding:0 12px`, `border-radius:999px`, borde `var(--line-2)`, fondo transparente, texto `var(--ink-2)`, 12.5px. Con `.is-active`: fondo `var(--accent)`, texto `#fff`, borde `var(--accent)`. El `<small>` del contador en Mono 11px con `opacity:.6`.
- `.cifras` — `grid-template-columns:repeat(auto-fit,minmax(175px,1fr))`, `gap:12px`.
- `.cifra` — fondo `var(--surface)`, borde `var(--line)`, `border-radius:14px`, `padding:14px 16px`, `box-shadow:var(--shadow)`. `.cifra__rotulo` 11.5px `var(--ink-3)`; `.cifra__valor` Mono 23px peso 500 con `letter-spacing:-.02em`; `.cifra__unidad` 13px `var(--ink-3)`.
- `.bloque` — la caja de la tabla: mismo fondo, borde y radio que `.cifra`, con `overflow:hidden`. `.bloque__filtros` con `padding:12px 14px` y borde inferior `var(--line)`.
- `.tabla` — `width:100%`, `border-collapse:collapse`, 13px. `th` 11.5px peso 500 `var(--ink-3)` con borde inferior; `td` `padding:11px 14px` y borde inferior `var(--line)`; `tr:hover` fondo `var(--surface-2)`.
- `.t-num` alinea a la derecha; `.t-detalle` y `.t-cuando` en Mono (12.5px y 12px). `.t-cuando` en `var(--ink-3)`.
- `.t-detalle--up` en `var(--up-ink)`, `.t-detalle--down` en `var(--down-ink)`; los demás en `var(--ink-2)`.
- `.chip` — la tienda: `padding:3px 9px`, `border-radius:999px`, fondo `var(--accent-wash)`, texto `var(--accent-ink)`, 12px.
- `.pildora--up|down|new|gone|stock` — mismo formato que `.chip` pero con el par de tokens de su estado.
- `.t-nombre` — `max-width:420px` con `overflow:hidden;text-overflow:ellipsis;white-space:nowrap`; el enlace hereda el color del texto (`color:var(--ink)`) y solo al `:hover` pasa a `var(--accent)`, para que la tabla no se vea llena de enlaces.
- `.vacio` — `padding:34px 14px`, centrado, 13px `var(--ink-3)`; oculto por defecto con `display:none` y visible con `.is-on`.
- `.tablawrap` — `overflow-x:auto`, para que la tabla haga scroll dentro de su caja y la página nunca se desplace en horizontal.
- `.tarjetas` — `grid-template-columns:repeat(auto-fit,minmax(250px,1fr))`, `gap:12px`. `.tarjeta` como `.cifra` más `display:flex;flex-direction:column;gap:12px`, con `.tarjeta__cifras` en tres columnas y los valores en Mono 15px.
- `.avisos` / `.aviso` — los mensajes flash: `border-radius:10px`, `padding:10px 14px`, 13px. `.aviso--success` con los tokens `--down-*`, `.aviso--error` con los `--up-*`.

- [ ] **Step 4: Filtros, búsqueda y recálculo en `panel.js`**

Añade dentro del IIFE, después de la navegación:

```javascript
  // ---------- filtros de la bandeja ----------
  var bandeja = document.querySelector('.view[data-view="cambios"]');

  if (bandeja) {
    var filaTienda = "";
    var filaTipo = "";

    var filas = [].slice.call(bandeja.querySelectorAll("tbody tr"));
    var pastillasTienda = [].slice.call(
      bandeja.querySelectorAll(".filtros-tienda [data-tienda]"));
    var pastillasTipo = [].slice.call(bandeja.querySelectorAll("[data-tipo]"));

    // 'price' agrupa subidas y bajadas en un solo filtro.
    function encaja(fila, tipo) {
      var t = fila.getAttribute("data-tipo");
      return !tipo || t === tipo || (tipo === "price" && t.indexOf("price") === 0);
    }

    function pasaTienda(fila) {
      return !filaTienda || fila.getAttribute("data-tienda") === filaTienda;
    }

    function filtrarBandeja() {
      var visibles = 0;

      filas.forEach(function (fila) {
        var ok = pasaTienda(fila) && encaja(fila, filaTipo) && coincide(fila);
        fila.style.display = ok ? "" : "none";
        if (ok) visibles++;
      });

      var vacio = bandeja.querySelector("[data-vacio]");
      if (vacio) vacio.classList.toggle("is-on", visibles === 0);

      // Contadores de las pastillas de tipo, sobre lo que deja pasar el
      // filtro de tienda y la busqueda: si contasen sobre el total,
      // dirian una cosa y la tabla mostraria otra.
      ["", "price", "new", "stock", "removed"].forEach(function (tipo) {
        var n = filas.filter(function (fila) {
          return pasaTienda(fila) && encaja(fila, tipo) && coincide(fila);
        }).length;
        var salida = bandeja.querySelector('[data-cuenta-tipo="' + tipo + '"]');
        if (salida) salida.textContent = n;
      });

      recalcularCifras(visibles);
      pintarTarjetas();
    }

    // Al filtrar por una tienda, las cifras de cabecera pasan a ser las
    // suyas. Los porcentajes se ponderan por tamano de catalogo: cuatro
    // tiendas de 865 a 1.428 productos dan un numero falso con una media
    // simple.
    function recalcularCifras(visibles) {
      var elegidas = pastillasTienda.filter(function (p) {
        var nombre = p.getAttribute("data-tienda");
        return nombre && (!filaTienda || nombre === filaTienda);
      });
      if (!elegidas.length) return;

      var productos = 0, disp = 0, promo = 0, live = 0;
      elegidas.forEach(function (p) {
        var total = parseFloat(p.getAttribute("data-total")) || 0;
        productos += total;
        disp += parseFloat(p.getAttribute("data-disp")) * total;
        promo += parseFloat(p.getAttribute("data-promo")) * total;
        live += parseInt(p.getAttribute("data-live"), 10);
      });

      document.getElementById("c-productos").textContent = numeroEs(productos, 0);
      document.getElementById("c-live").textContent = live;
      document.getElementById("c-live-total").textContent = "/ " + elegidas.length;
      document.getElementById("c-disp").textContent =
        productos ? numeroEs(disp / productos, 1) : "0";
      document.getElementById("c-promo").textContent =
        productos ? numeroEs(promo / productos, 1) : "0";
      document.getElementById("c-cambios").textContent = visibles;
    }

    function pintarTarjetas() {
      bandeja.querySelectorAll(".tarjeta").forEach(function (tarjeta) {
        var nombre = tarjeta.getAttribute("data-tienda");
        tarjeta.style.display = (!filaTienda || nombre === filaTienda) ? "" : "none";
      });
    }

    bandeja.addEventListener("click", function (e) {
      var pastilla = e.target.closest(".pastilla");
      if (!pastilla) return;

      if (pastilla.hasAttribute("data-tienda")) {
        filaTienda = pastilla.getAttribute("data-tienda");
        pastillasTienda.forEach(function (p) {
          p.classList.toggle("is-active", p === pastilla);
        });
      } else if (pastilla.hasAttribute("data-tipo")) {
        filaTipo = pastilla.getAttribute("data-tipo");
        pastillasTipo.forEach(function (p) {
          p.classList.toggle("is-active", p === pastilla);
        });
      }
      filtrarBandeja();
    });

    refiltradores.push(filtrarBandeja);
    filtrarBandeja();
  }
```

Fíjate en que `pastillasTienda` se construye con `.filtros-tienda [data-tienda]` y no con `[data-tienda]` a secas: las tarjetas de tienda del final de la vista llevan ese mismo atributo, y con el selector ancho entrarían en el cálculo de las cifras y lo falsearían.

- [ ] **Step 5: Comprobar en el navegador**

Run: `python dashboard.py`
Expected, en `http://localhost:5000`:
- La bandeja lista los cambios reales de las últimas 24 h, el más reciente arriba, mezclando las cuatro tiendas.
- Las bajadas salen en rojo y las subidas en verde, con su porcentaje.
- Filtrar por tienda cambia las cinco cifras y esconde las tarjetas del resto.
- Filtrar por tipo actualiza los contadores de las píldoras.
- Buscar un SKU deja solo sus filas; si no hay ninguna, sale «Nada que revisar con este filtro.»
- El título de un producto abre su ficha en una pestaña nueva.
- Todo legible en los dos temas.

- [ ] **Step 6: Commit**

```bash
git add templates/dashboard.html static/css/panel.css static/js/panel.js
git commit -m "Reunir los cambios de las cuatro tiendas en una sola bandeja"
```

---

### Task 4: Pantalla «Tienda»

Cuatro cifras, dos pestañas (Catálogo y Cambios 24 h) y sus subfiltros.

**Files:**
- Modify: `templates/dashboard.html` (el bucle `{% for t in targets %}` de las vistas de tienda)
- Modify: `static/css/panel.css` (añadir)
- Modify: `static/js/panel.js` (añadir)

**Interfaces:**
- Consumes: `targets` con su `metrics` y `catalog`; `changes` (Task 1) para los cambios de cada tienda; los macros `pildora`, `detalle`, `producto` y las clases de la Task 3.
- Produces: nada que consuman tareas posteriores.

- [ ] **Step 1: Escribir el contenido de la vista de tienda**

Dentro de `<section class="view" data-view="tienda/{{ t.slug }}" ...>`:

```jinja
{% set cambios_tienda = changes | selectattr('store', 'equalto', t.name) | list %}

<div class="cifras">
  <div class="cifra"><p class="cifra__rotulo">En catálogo</p>
    <p class="cifra__valor">{{ t.metrics.total | miles }}</p></div>
  <div class="cifra"><p class="cifra__rotulo">Disponible</p>
    <p class="cifra__valor">{{ t.metrics.availability_pct | pct }}<span class="cifra__unidad">%</span></p></div>
  <div class="cifra"><p class="cifra__rotulo">Precio mediano</p>
    <p class="cifra__valor">{{ t.metrics.median_price | eur }}</p></div>
  <div class="cifra"><p class="cifra__rotulo">Precio más alto</p>
    <p class="cifra__valor">{{ t.metrics.max_price | eur }}</p></div>
</div>

<section class="bloque">
  <div class="bloque__filtros" role="tablist" aria-label="Datos de {{ t.name }}">
    <button type="button" class="pastilla is-active" role="tab" data-pestana="catalogo">
      Catálogo <small>{{ t.catalog | length }}</small>
    </button>
    <button type="button" class="pastilla" role="tab" data-pestana="cambios">
      Cambios 24 h <small>{{ cambios_tienda | length }}</small>
    </button>
  </div>

  <div class="subfiltros" data-para="catalogo">
    <span class="filtros__rotulo">Estado</span>
    {% for clave, etiqueta, n in [
        ('', 'Todos', t.catalog | length),
        ('si', 'Disponible', t.catalog | selectattr('available') | list | length),
        ('no', 'Agotado', t.catalog | rejectattr('available') | list | length)] %}
    <button type="button" class="pastilla pastilla--sm{{ ' is-active' if not clave }}" data-sub="{{ clave }}">
      {{ etiqueta }} <small>{{ n }}</small>
    </button>
    {% endfor %}
  </div>

  <div class="subfiltros u-oculto" data-para="cambios">
    <span class="filtros__rotulo">Tipo</span>
    {% for clave, etiqueta in [('', 'Todos'), ('new', 'Alta'), ('price', 'Precio'), ('stock', 'Stock'), ('removed', 'Baja')] %}
    <button type="button" class="pastilla pastilla--sm{{ ' is-active' if not clave }}" data-sub="{{ clave }}">
      {{ etiqueta }} <small data-cuenta-sub="{{ clave }}"></small>
    </button>
    {% endfor %}
  </div>

  <div class="tablawrap" data-panel="catalogo">
    <table class="tabla">
      <thead><tr>
        <th>SKU</th><th>Producto</th><th>Estado</th>
        <th class="t-num">Precio</th><th class="t-num">Última lectura</th>
      </tr></thead>
      <tbody>
        {% for p in t.catalog %}
        <tr data-sub="{{ 'si' if p.available else 'no' }}"
            data-busca="{{ (p.title ~ ' ' ~ (p.sku or '')) | lower }}">
          <td class="t-sku">{{ p.sku or "—" }}</td>
          <td class="t-nombre">{{ producto(p) }}</td>
          <td>{% if p.available %}<span class="pildora pildora--down">Disponible</span>
              {% else %}<span class="pildora pildora--up">Agotado</span>{% endif %}</td>
          <td class="t-num t-detalle">{{ p.price | eur }}</td>
          <td class="t-num t-cuando">{{ p.captured_at | fecha }}</td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
    <p class="vacio" data-vacio>Sin resultados.</p>
  </div>

  <div class="tablawrap u-oculto" data-panel="cambios">
    <table class="tabla">
      <thead><tr>
        <th>SKU</th><th>Producto</th><th>Cambio</th>
        <th class="t-num">Detalle</th><th class="t-num">Detectado</th>
      </tr></thead>
      <tbody>
        {% for c in cambios_tienda %}
        <tr data-sub="{{ c.kind }}"
            data-busca="{{ (c.title ~ ' ' ~ (c.sku or '')) | lower }}">
          <td class="t-sku">{{ c.sku or "—" }}</td>
          <td class="t-nombre">{{ producto(c) }}</td>
          <td>{{ pildora(c.kind) }}</td>
          <td class="t-num t-detalle t-detalle--{{ TIPOS[c.kind][1] }}">{{ detalle(c) }}</td>
          <td class="t-num t-cuando">{{ c.when | fecha(true) }}</td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
    <p class="vacio" data-vacio>Sin resultados.</p>
  </div>
</section>
```

El macro `producto(p)` sirve igual para el catálogo: usa `.url` y `.title`, que las filas del catálogo también traen.

- [ ] **Step 2: Estilar los subfiltros**

En `panel.css`:

- `.subfiltros` — fila con `gap:6px`, `flex-wrap:wrap`, `padding:11px 14px`, borde inferior `var(--line)`, fondo `var(--surface-2)`.
- `.pastilla--sm` — `height:26px`, `padding:0 10px`, 12px; su `<small>` a 10.5px.
- `.filtros__rotulo` — 11.5px `var(--ink-3)`, `margin-right:4px`.
- `.u-oculto` — `display:none`.
- `.t-sku` — Mono 12px `var(--ink-3)`, sin ajuste de línea.

- [ ] **Step 3: Pestañas y subfiltros en `panel.js`**

Añade dentro del IIFE:

```javascript
  // ---------- vistas de tienda ----------
  [].slice.call(document.querySelectorAll('.view[data-view^="tienda/"]'))
    .forEach(function (vista) {
      var pestanaActiva = "catalogo";
      var sub = "";

      function encajaSub(fila) {
        var s = fila.getAttribute("data-sub");
        return !sub || s === sub || (sub === "price" && s.indexOf("price") === 0);
      }

      function filtrar() {
        var panel = vista.querySelector('[data-panel="' + pestanaActiva + '"]');
        var visibles = 0;

        [].slice.call(panel.querySelectorAll("tbody tr")).forEach(function (fila) {
          var ok = encajaSub(fila) && coincide(fila);
          fila.style.display = ok ? "" : "none";
          if (ok) visibles++;
        });

        var vacio = panel.querySelector("[data-vacio]");
        if (vacio) vacio.classList.toggle("is-on", visibles === 0);

        // Contadores del subfiltro de tipo, solo en la pestana de cambios:
        // los del catalogo son fijos y ya los imprime la plantilla.
        if (pestanaActiva === "cambios") {
          var filasCambios = [].slice.call(panel.querySelectorAll("tbody tr"));
          ["", "new", "price", "stock", "removed"].forEach(function (clave) {
            var n = filasCambios.filter(function (fila) {
              var s = fila.getAttribute("data-sub");
              return !clave || s === clave || (clave === "price" && s.indexOf("price") === 0);
            }).length;
            var salida = vista.querySelector('[data-cuenta-sub="' + clave + '"]');
            if (salida) salida.textContent = n;
          });
        }
      }

      function cambiarPestana(clave) {
        pestanaActiva = clave;
        sub = "";

        vista.querySelectorAll("[data-pestana]").forEach(function (b) {
          b.classList.toggle("is-active", b.getAttribute("data-pestana") === clave);
        });
        vista.querySelectorAll("[data-panel]").forEach(function (p) {
          p.classList.toggle("u-oculto", p.getAttribute("data-panel") !== clave);
        });
        vista.querySelectorAll("[data-para]").forEach(function (f) {
          f.classList.toggle("u-oculto", f.getAttribute("data-para") !== clave);
          f.querySelectorAll("[data-sub]").forEach(function (b, i) {
            b.classList.toggle("is-active", i === 0);
          });
        });
        filtrar();
      }

      vista.addEventListener("click", function (e) {
        var boton = e.target.closest(".pastilla");
        if (!boton) return;

        if (boton.hasAttribute("data-pestana")) {
          cambiarPestana(boton.getAttribute("data-pestana"));
        } else if (boton.hasAttribute("data-sub")) {
          sub = boton.getAttribute("data-sub");
          boton.parentNode.querySelectorAll("[data-sub]").forEach(function (b) {
            b.classList.toggle("is-active", b === boton);
          });
          filtrar();
        }
      });

      // El buscador de la barra lateral filtra la vista abierta sin saber
      // como funciona por dentro: cada vista solo se apunta aqui.
      refiltradores.push(filtrar);
      filtrar();
    });
```

No hay que tocar nada del buscador ni del código de la Task 3: `coincide` y `refiltradores` los creó la Task 2 precisamente para esto.

- [ ] **Step 4: Comprobar en el navegador**

Run: `python dashboard.py`
Expected: al entrar en una tienda desde la barra lateral o desde su tarjeta, se ven sus cuatro cifras y el catálogo completo. Cambiar a *Cambios 24 h* muestra solo los suyos y cambia la fila de subfiltros de Estado a Tipo. Los subfiltros filtran, la búsqueda funciona dentro de la pestaña activa, y una combinación sin resultados muestra «Sin resultados.» Volver a *Cambios* en la barra lateral devuelve a la bandeja. Recargar con `#tienda/<slug>` en la URL abre directamente esa tienda.

- [ ] **Step 5: Commit**

```bash
git add templates/dashboard.html static/css/panel.css static/js/panel.js
git commit -m "Reducir la vista de tienda a catalogo y cambios"
```

---

### Task 5: Retirar el mapa de calor, los códigos y los logos por tienda

Ya no los usa nadie: ahora se borran. Es la tarea que cumple la decisión de corte limpio del spec.

**Files:**
- Modify: `src/metrics.py`
- Modify: `tests/test_metrics.py`

**Interfaces:**
- Consumes: nada nuevo.
- Produces: `src/metrics.py` sin `PRICE_BANDS`, `price_histogram`, `target_code` ni `COMPETITOR_LOGOS`; `global_metrics` sin la clave `top_share`; los objetivos sin las claves `histogram`, `code` ni `logo`.

- [ ] **Step 1: Borrar los tests del mapa de calor y de los códigos**

En `tests/test_metrics.py`, elimina:
- Los cuatro `test_target_code_*`.
- Los seis `test_price_histogram_*`.
- Los cinco `test_heat_levels_*`.
- En `test_build_targets_adjunta_metricas_e_histograma`: quita las aserciones sobre `histogram` y renombra el test a `test_build_targets_adjunta_las_metricas`.
- En los `test_global_metrics_*`: quita las aserciones sobre `top_share`.
- De la cabecera del fichero, los imports `HEAT_LEVELS`, `PRICE_BANDS`, `price_histogram` y `target_code`.

- [ ] **Step 2: Verificar que la suite falla solo por lo esperado**

Run: `python -m pytest tests/test_metrics.py -q`
Expected: PASS. Solo se han borrado tests, así que no debería romperse nada. Si falla, es que algún test que se queda dependía de lo borrado: arréglalo antes de seguir.

- [ ] **Step 3: Borrar el código de `src/metrics.py`**

Elimina:
- `COMPETITOR_LOGOS` (y la clave `"logo"` que `build_targets` pone en cada objetivo).
- `PRICE_BANDS`, `_BAND_EDGES`, `HEAT_LEVELS`, `HEAT_GAMMA`.
- Las funciones `price_histogram`, `_apply_heat_levels` y `target_code`.
- En `build_targets`: las claves `"code"` y `"logo"` del diccionario del objetivo, la línea `target["histogram"] = price_histogram(...)` y la llamada final a `_apply_heat_levels(ordered)`.
- En `global_metrics`: la clave `"top_share"` y su comentario.
- Los imports que quedan sin uso: `math`, `bisect_right`. **`median` de `statistics` se queda** — la usa `target_metrics`.

Actualiza el docstring del módulo si menciona el mapa de calor.

- [ ] **Step 4: Verificar**

Run: `python -m pytest -q`
Expected: PASS, la suite entera.

Run: `python -c "import ast,sys; ast.parse(open('src/metrics.py',encoding='utf-8').read())"` y luego `python dashboard.py`
Expected: el panel sigue funcionando exactamente igual que al final de la Task 4. Si sale un `UndefinedError` de Jinja, es que quedó una referencia a `t.code`, `t.logo` o `t.histogram` en la plantilla: búscala con `grep -n "\.code\|\.logo\|histogram\|price_bands" templates/dashboard.html`.

- [ ] **Step 5: Commit**

```bash
git add src/metrics.py tests/test_metrics.py
git commit -m "Retirar el mapa de calor de posicionamiento por precio"
```

---

### Task 6: Actualizar el README y verificación final

El README describe un panel que ya no existe: habla de vista general con mapa de posicionamiento, cinco pestañas por objetivo y registros.

**Files:**
- Modify: `README.md` (líneas ~95-110 y ~205-225)

**Interfaces:**
- Consumes: nada.
- Produces: nada.

- [ ] **Step 1: Reescribir la descripción del panel**

En la sección que hoy empieza en la línea 98 («la **vista general**…»), sustituye la descripción de las tres clases de vista por las dos actuales: la **bandeja de cambios** (todo lo que se ha movido en las últimas 24 h en las cuatro tiendas, con filtros por tienda y por tipo) y la **vista por tienda** (catálogo y cambios, en dos pestañas). Mantén la frase de que la vista viaja en el hash de la URL y la de que todo se renderiza en el servidor.

Quita «tramos del mapa de calor» de la lista de cifras derivadas de la línea 107 y de la 219, y menciona el tema claro/oscuro.

- [ ] **Step 2: Actualizar los nombres de fichero**

En la línea ~208, `static/css/console.css` y `static/js/console.js` pasan a `static/css/panel.css` y `static/js/panel.js`. En la 219, la lista de cifras que calcula `src/metrics.py` pierde los tramos del mapa y los códigos de objetivo, y gana el feed de cambios.

- [ ] **Step 3: Verificación completa**

Run: `python -m pytest -q`
Expected: PASS.

Run: `python dashboard.py` y recorre el panel entero:
- Bandeja: orden por fecha, filtros de tienda y tipo, búsqueda, enlaces, «Nada que revisar con este filtro.»
- Una tienda de cada grupo (propia y rival): cifras, las dos pestañas, subfiltros, «Sin resultados.»
- Los dos temas, y que el elegido sobrevive a recargar sin parpadeo.
- Anchura de móvil (unos 400px): nada se desborda en horizontal; las tablas hacen scroll dentro de su caja.
- Pulsar Sincronizar y comprobar que el aviso `flash` sale bajo la cabecera. Tarda lo que tarde el crawl: eso es conocido y está fuera de alcance.

Run: `grep -rn "console\.css\|console\.js\|price_bands\|histogram\|target_code" --include=*.py --include=*.html --include=*.md .`
Expected: sin resultados fuera de `docs/superpowers/` (los planes y specs viejos hablan del panel anterior y se quedan como están: son el registro histórico).

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "Poner al dia el README con el panel redisenado"
```

---

## Al terminar

El trabajo queda en la rama `redisenio-panel`, sin fusionar. Antes de desplegar en el VPS conviene que el usuario vea el panel en local con los datos reales.

El despliegue tiene un cabo suelto conocido: el `docker-compose.yml` de `/home/deploy/scraper-competidores` está modificado sin commitear desde el 2026-09-02 y diverge del repo. Hay que resolver esa divergencia **antes** de hacer `git pull` en el VPS, o el pull fallará o se llevará por delante cambios de producción.
