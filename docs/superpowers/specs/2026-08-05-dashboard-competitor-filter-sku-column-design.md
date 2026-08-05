# Filtro por competidor y columna SKU en el dashboard

Fecha: 2026-08-05

## Contexto

El dashboard (`dashboard.py` + `templates/dashboard.html`) muestra 6
secciones (Competidores, Productos anadidos, Cambios de precio, Cambios de
disponibilidad, Productos eliminados, Catalogo actual) mezclando todos los
competidores sin forma de aislar uno. Ademas, `db.py` ya trae `p.sku` en
casi todas las consultas de listado de producto (de un trabajo anterior),
pero no se pinta en ninguna tabla, y una consulta
(`get_recent_price_events`) todavia no lo selecciona.

## Alcance

- Filtro por competidor, en cliente (JavaScript), sin recargar la pagina.
- Columna SKU en las 5 tablas que listan productos individuales.
- `get_recent_price_events` gana `p.sku` en el `SELECT`.

Fuera de alcance: filtro en servidor, persistir la seleccion del filtro
entre recargas, SKU en la tabla de Competidores (es un resumen agregado,
no tiene sentido).

## Diseno

### Filtro por competidor

- Desplegable `<select id="competitor-filter">` en el `<header>`, con una
  opcion "Todos los competidores" (valor vacio) y una opcion por cada
  competidor de `competitors` (ya disponible en la plantilla, sin tocar
  `dashboard.py`).
- Cada `<tr>` de las 6 tablas (incluida Competidores) lleva
  `data-competitor="{{ x.name o x.competitor }}"`.
- JS vanilla (`<script>` al final del `<body>`): al cambiar el filtro,
  recorre todas las filas del documento y aplica `style.display = "" | "none"`
  segun coincida `data-competitor` con el valor elegido (o se muestran todas
  si el valor es vacio).
- Tras filtrar, recalcula el contador de cada `<h2>` que tenga un patron
  `(N ...)` contando las filas visibles de su tabla, para que el titulo de
  seccion no quede desincronizado con lo que se ve.
- Sin backend: no se toca `dashboard.py` ni `db.py` para esto.

### Columna SKU

- `src/db.py::get_recent_price_events`: anadir `p.sku` al `SELECT` (ya hace
  `JOIN products p`, no requiere cambiar el `JOIN`).
- `templates/dashboard.html`: anadir `<th>SKU</th>` y
  `<td>{{ x.sku or "-" }}</td>` en las tablas de: Productos anadidos
  recientemente, Cambios de precio, Cambios de disponibilidad, Productos
  eliminados, Catalogo actual.

## Testing

Sin tests automaticos nuevos: es una consulta SQL de una linea sin logica
condicional (coherente con que `db.py` no tiene tests de sus metodos de
consulta, solo del helper `_to_float`) y cambios de plantilla/JS que se
verifican a mano arrancando `dashboard.py` y probando el filtro en el
navegador.
