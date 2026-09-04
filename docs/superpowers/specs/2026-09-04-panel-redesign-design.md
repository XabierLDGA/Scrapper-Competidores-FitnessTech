# Rediseñar el panel como bandeja de cambios

Fecha: 2026-09-04

## Contexto

El panel de vigilancia (`templates/dashboard.html`, `static/css/console.css`,
`static/js/console.js`) se diseñó en agosto como una "consola de vigilancia
de mercado": nueve vistas, mapa de calor de posicionamiento por precio y un
registro separado por cada tipo de cambio. En uso diario eso obliga a
recorrer cuatro pantallas para saber qué se movió anoche, que es la única
pregunta que se le hace al panel cada mañana.

El usuario ha rediseñado el panel en Claude Design y ha exportado el
resultado (`Vigilancia.dc.html`, artboard con marcado y lógica, más
`github.md` con el mapa de pantallas). El diseño reduce el panel a dos
pantallas y añade tema claro/oscuro con los colores de marca de
FitnessTech.es. Este documento traduce ese artboard a un cambio concreto
sobre el repo.

El artboard es la referencia visual y está aprobado: aquí no se rediscute
el aspecto, solo cómo se implementa y qué se hace con lo que el diseño
deja fuera.

Decisiones tomadas con el usuario:

- **Corte limpio.** Lo que el diseño no incluye se borra, no se esconde:
  el mapa de calor sale también de `src/metrics.py` y de sus tests. Si
  algún día hace falta, está en el historial de git.
- **«Comparativa Titanium» queda como letrero.** Se pinta inerte con la
  píldora *Pronto*, igual que en el artboard. Marca la intención sin gastar
  trabajo ahora; la pantalla se diseña en su propia sesión.
- **Se recuperan dos cosas que el artboard simplificó:** el título de cada
  fila vuelve a enlazar a la ficha del producto (pestaña nueva) y el
  porcentaje de variación se pinta pegado al precio en la columna Detalle.
  Son lo que hace útil la bandeja: ver la caída de un vistazo y poder abrir
  el producto.
- **El botón Sincronizar se repinta pero no se toca por dentro.** Hoy
  ejecuta el crawl completo dentro de la petición HTTP (el crawl del
  2026-09-04 tardó doce minutos, de 03:00 a 03:12), lo que deja la pestaña
  colgada y, si el proxy corta antes, el crawl sigue por dentro sin que el
  usuario lo sepa. No es una regresión de este trabajo y el crawl que de
  verdad se usa es el automático de las 03:00, así que se aborda aparte.

## Alcance

Repo `Scrapper-Competidores-FitnessTech` (local:
`C:\Users\xlope\Desktop\Proyectos\scrapper-Competidores`):

- `src/metrics.py`: añadir `build_change_feed`; retirar el mapa de calor y
  `target_code`.
- `dashboard.py`: dejar de pasar `price_bands` a la plantilla y pasar el
  feed de cambios.
- `templates/dashboard.html`: reescrito.
- `static/css/console.css` → `static/css/panel.css`: reescrito.
- `static/js/console.js` → `static/js/panel.js`: reescrito.
- `tests/test_metrics.py`: tests nuevos del feed; fuera los del mapa de
  calor.
- `README.md`: describe un panel de tres clases de vista con mapa de
  posicionamiento y cinco pestañas por objetivo. Se pone al día, o queda
  mintiendo sobre lo único que documenta del panel.

No se toca `src/crawler.py`, `src/db.py`, `src/detector.py`,
`src/normalizer.py`, `src/notifier.py`, `main.py`, `scheduler.py` ni las
migraciones. El backend ya expone todo lo que el diseño necesita.

## Diseño

### Arquitectura

Se mantiene el patrón actual: Flask renderiza la página entera en la
petición y el JavaScript solo decide qué sección se muestra, con
navegación por `#hash`. No se introduce API ni `fetch`. El artboard es un
componente con estado, pero ese estado —vista, filtro de tienda, filtro de
tipo, pestaña, búsqueda y tema— es todo de cliente, así que traduce
directamente sin cambiar el modelo de la aplicación.

Las vistas pasan de nueve a dos:

| Vista | Hash | Qué muestra |
| --- | --- | --- |
| Cambios | `#cambios` | Bandeja única de las últimas 24 h de las cuatro tiendas |
| Tienda | `#tienda/<slug>` | Catálogo y cambios de una tienda |

Desaparecen las cuatro vistas de registro por tipo (`#registro/<clave>`):
sus filas son ahora los filtros de tipo de la bandeja.

### `build_change_feed(targets)`

Función pura en `src/metrics.py`, del mismo estilo que el resto del módulo:
opera sobre lo que `build_targets` ya ha agrupado, no toca la base de datos
ni Flask. Aplana los cuatro tipos de evento de todas las tiendas en una
lista única ordenada por fecha descendente.

Cada entrada del feed:

```python
{
    "kind": str,           # price_down | price_up | new | stock | removed
    "store": str,          # nombre del competidor
    "is_own_store": bool,  # para el punto de color y el agrupado de la sidebar
    "sku": str | None,
    "title": str,
    "url": str | None,
    "when": datetime | None,   # fecha por la que se ordena el feed
    # Campos del detalle, a None en los tipos que no los usan:
    "old_price": float | None,
    "new_price": float | None,
    "pct": float | None,
    "was_available": bool | None,
    "now_available": bool | None,
    "last_seen": date | None,
}
```

El feed **no compone texto**: guarda valores y la plantilla los pinta con
los filtros Jinja que ya existen en `dashboard.py` (`eur`, `pct`, `fecha`),
que no se tocan. Así los tests comparan números y no cadenas con comas y
símbolos de euro, y el formato español sigue en un solo sitio.

Mapeo desde las listas que ya trae cada objetivo:

| Origen | `kind` | Campos del detalle | `when` |
| --- | --- | --- | --- |
| `price_events` con `event_type == "decrease"` | `price_down` | `old_price`, `new_price`, `pct` | `detected_at` |
| `price_events` con `event_type == "increase"` | `price_up` | ídem | `detected_at` |
| `new_products` | `new` | `new_price` (precio de alta) | `first_seen` |
| `availability_events` | `stock` | `was_available`, `now_available` | `detected_at` |
| `removed_products` | `removed` | `last_seen` | `removed_at` |

Las altas usan `new_price` y dejan `old_price` a `None` a propósito: así la
plantilla tiene una sola regla —si hay `old_price` pinta `antes → ahora`, y
si no, solo el precio— en vez de un caso por tipo.

La ordenación reutiliza `_as_datetime`, que ya existe en el módulo para
esto mismo. MySQL devuelve `date` en unas columnas y `datetime` en otras, y
mezclarlas en una comparación revienta la página entera; el comentario que
ya hay en `build_targets` documenta ese disgusto. Las entradas cuya fecha
no se pueda normalizar van al final del feed en vez de romper el orden.

### Lo que se retira de `src/metrics.py`

`PRICE_BANDS`, `_BAND_EDGES`, `HEAT_LEVELS`, `HEAT_GAMMA`,
`price_histogram`, `_apply_heat_levels`, la clave `histogram` de cada
objetivo y `top_share` de `global_metrics`. También `target_code`: el
código corto (`TS·ES`) solo aparecía en el mapa de calor y en cabeceras que
el diseño elimina.

`COMPETITOR_LOGOS` sale igualmente, porque el diseño identifica cada tienda
con un punto de color y no con su logo. Los cuatro PNG
(`static/logos/titanium-strength.png`, `fitnesstech-es|fr|pt.png`) se dejan
en disco: no estorban y evitan volver a buscarlos si los logos regresan a
las tarjetas de tienda.

Se mantienen `slugify`, `target_metrics`, `build_targets`, `global_metrics`
(menos `top_share`), `OWN_STORES` y `LIVE_WINDOW`.

### Pantalla «Cambios»

Es la home. De arriba abajo, siguiendo el artboard:

1. **Filtro de tienda** en píldoras: *Todas* más una por tienda, con punto
   de color según esté en línea.
2. **Cinco cifras**: productos vigilados, tiendas en línea (`n / total`),
   disponibilidad, con precio rebajado y cambios 24 h. De entrada salen de
   `global_metrics`; al filtrar por una tienda pasan a ser las suyas. Como
   no hay servidor de por medio, la plantilla imprime las cifras de cada
   tienda en atributos `data-*` y el JavaScript las lee para repintar. Los
   porcentajes de disponibilidad y promoción se ponderan por tamaño de
   catálogo, no se promedian a pelo: cuatro tiendas de 865 a 1.428
   productos darían un número falso con una media simple.
3. **Bandeja**: filtros de tipo (*Todos, Precios, Altas, Stock, Bajas*) con
   su contador, y tabla de cinco columnas — Tienda, Cambio, Producto,
   Detalle, Detectado. El producto enlaza a su ficha; el detalle lleva el
   porcentaje cuando es un cambio de precio, en el color del tipo.
4. **Tarjetas por tienda**: catálogo, disponibilidad y precio mediano, con
   la fecha de la última lectura al pie. Llevan a la vista de esa tienda.

Vacío: «Nada que revisar con este filtro.»

### Pantalla «Tienda»

Cuatro cifras de `target_metrics` (en catálogo, disponible, precio mediano,
precio más alto), dos pestañas —*Catálogo* y *Cambios 24 h*— y una fila de
subfiltros que cambia según la pestaña: estado (*Todos, Disponible,
Agotado*) en catálogo, tipo (*Todos, Alta, Precio, Stock, Baja*) en
cambios. La tabla comparte estructura con la bandeja.

Vacío: «Sin resultados.»

### Barra lateral

Fondo negro, logo `fitnesstech-brand.png`, buscador de producto o SKU, y la
navegación en cuatro bloques: *Panel principal* (Cambios, con el total de
cambios), *Mis tiendas*, *Competencia* y *Análisis* (solo «Comparativa
Titanium», inerte, con la píldora *Pronto*). Al pie, el reloj de Madrid y
el botón de tema.

Las tiendas se reparten entre *Mis tiendas* y *Competencia* con
`is_own_store`, que ya calcula `build_targets` a partir de `OWN_STORES`. En
la base de datos la tienda española se llama `Fitness Tech`, no
«Fitness Tech ES» como en los datos de ejemplo del artboard: se usa el
nombre real.

### Estilo

Los tokens salen del artboard, en `:root` y `:root[data-theme="dark"]`:

- Acento `#00a7af` (turquesa de FitnessTech.es), `#00c2cb` en oscuro.
- Rampa de estados: bajada roja, subida verde, alta azul, baja parda,
  stock ámbar, cada una con fondo y tinta propios en ambos temas.
- Tipografía: Archivo itálica 700/800 para títulos y rótulos de sección,
  IBM Plex Sans para el cuerpo, IBM Plex Mono para cifras, precios y
  fechas. Hay que añadir Archivo al `<link>` de Google Fonts, que hoy solo
  carga IBM Plex.

**Tema claro por defecto.** El tema elegido se guarda en `localStorage` y
se aplica poniendo `data-theme` en `<html>`. La aplicación va en un script
inline en el `<head>`, antes de que se pinte nada: si se hiciera al final,
quien tenga el tema oscuro vería un fogonazo blanco en cada carga.

El CSS y el JS se reescriben y se renombran a `panel.css` y `panel.js`.
"Consola" era el nombre del diseño que se está retirando. El versionado por
`mtime` del helper `asset()` en `dashboard.py` sigue igual y se encarga de
que el navegador no sirva la versión vieja tras desplegar.

### JavaScript

`static/js/panel.js` mantiene el estilo del actual (ES5, sin dependencias,
sin build) y cubre: routing por hash, filtro de tienda, filtro de tipo,
pestañas con sus subfiltros, búsqueda por producto o SKU sobre la vista
activa, recuento de las píldoras al filtrar, reloj de Madrid y alternancia
de tema.

Se van el barrido de la vista, el caret animado de la navegación, los
contadores que suben al entrar y todo el manejo del mapa de calor
(`iluminar`, `leerCelda`, `soltarCelda`).

### Errores y casos límite

- Filtro o búsqueda sin resultados: aviso en la tabla, no una tabla vacía.
- Producto sin `url`: el título se pinta como texto plano, no como enlace
  con `href` vacío.
- Producto sin `sku`: guion, como hoy.
- Sin ningún cambio en 24 h: la bandeja muestra su aviso y las cifras van a
  cero; la página no se rompe.
- Los avisos `flash` del resultado de Sincronizar se reubican bajo la
  cabecera nueva. Hoy viven en un bloque `.notices` que desaparece con la
  plantilla vieja, así que hay que colocarlos explícitamente o se pierden
  sin que nadie lo note.

## Pruebas

`tests/test_metrics.py`, sobre `build_change_feed`:

- Ordena por fecha descendente mezclando tipos distintos.
- Cada tipo de origen produce su `kind` (los eventos de precio se parten en
  `price_down` y `price_up` según `event_type`).
- Cada tipo rellena sus campos de detalle y deja el resto a `None`.
- Las altas traen `new_price` con `old_price` a `None`.
- Mezcla las cuatro tiendas en una sola lista y marca `is_own_store`.
- Listas vacías dan un feed vacío, sin reventar.
- Fechas de tipos mezclados (`date` y `datetime`) se ordenan juntas.
- Una entrada con fecha ilegible va al final en vez de romper el orden.

Se borran los tests del mapa de calor:
`test_price_histogram_*` (seis), `test_heat_levels_*` (cinco),
`test_target_code_*` (cuatro) y la parte de histograma de
`test_build_targets_adjunta_metricas_e_histograma`. En
`test_global_metrics_*` desaparecen las aserciones sobre `top_share`.

El resto de la suite (`test_crawler`, `test_detector`, `test_db`,
`test_main`, `test_normalizer`, `test_notifier`, `test_scheduler`) no se
toca.

Verificación manual antes de dar por bueno el trabajo: `python dashboard.py`
contra la base de datos real, recorrer las dos pantallas en tema claro y
oscuro, comprobar los filtros y la búsqueda, y que el enlace de un producto
abre su ficha.

## Fuera de alcance

- **El botón Sincronizar**, por la decisión de arriba. Sigue siendo un
  `POST /crawl` bloqueante.
- **«Comparativa Titanium»**: letrero, no pantalla.
- **El 404 del webhook de n8n.** El crawl del 2026-09-04 registró
  `404 Not Found` en
  `https://fitnesstech.duckdns.org/webhook/competencia-resumen-diario`, y
  los eventos se marcan como notificados igualmente: el resumen diario no
  llega a nadie. Es un fallo real, pero de notificaciones, no del panel.
- **El `docker-compose.yml` divergente en el VPS**, modificado el
  2026-09-02 sin volver al repo (queda además un
  `docker-compose.yml.bak.20260902-102721` sin trackear).
- **El despliegue.** Se hace al terminar, cuando el usuario haya visto el
  panel en local.

## Riesgos

- **Reescritura grande de plantilla, CSS y JS a la vez.** El panel no tiene
  pruebas de interfaz, así que la red de seguridad es la verificación
  manual descrita arriba. Se mitiga trabajando por partes y dejando el
  backend (donde sí hay tests) cerrado antes de tocar la vista.
- **Pérdida silenciosa de los avisos `flash`** al retirar la plantilla
  vieja. Anotado explícitamente arriba para que no se escape.
