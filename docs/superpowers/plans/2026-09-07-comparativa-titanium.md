# Comparativa Titanium — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Una pantalla del panel que enfrente cada máquina nuestra con su equivalente de Titanium Strength a precios vivos, y un correo diario que avise cuando Titanium mueve alguno de esos precios.

**Architecture:** El emparejamiento que ha preparado producto en un Excel entra en MySQL por una tabla nueva (`titanium_pairs`) que se puebla con SQL generado en local. La pantalla resuelve ese emparejamiento contra el catálogo vigente con dos funciones puras en `src/metrics.py`, sin consultas nuevas. El correo lo monta n8n por su cuenta con su propia consulta, igual que el aviso semanal que ya existe.

**Tech Stack:** Python 3.11, Flask + Jinja2, MySQL 8.4, `openpyxl` (solo en local), pytest, n8n. Sin build de frontend: CSS y JS a pelo.

**Spec:** `docs/superpowers/specs/2026-09-07-comparativa-titanium-design.md`

## Global Constraints

- **Idioma:** todo el texto de cara al usuario y todos los comentarios de código, en español. Los comentarios explican **por qué**, no qué.
- **El Excel solo aporta el emparejamiento.** Sus columnas de precio (`PVP FT`, `PVP Titanium`, `Dif. FT − Titanium`, `Variación vs Titanium`, `Enlace disponible`) se ignoran a propósito. Todos los precios salen del scrapper.
- **Δ = nuestro PVP − PVP Titanium.** Δ positivo se pinta con la rampa `--down-*` (**verde**) y Δ negativo con `--up-*` (**roja**), por el signo de la cifra. Va a propósito al revés que las píldoras de la bandeja, donde el color sigue el semáforo comercial. Consecuencia a tener presente: verde aquí significa que somos **más caros**. No lo "arregles".
- **El lado nuestro es `Fitness Tech`** (ES). `Fitness Tech FR` y `Fitness Tech PT` quedan fuera.
- **El competidor es `Titanium Strength`**, `competitor_id = 4` en producción. En el código se referencia **por nombre**, nunca por id.
- **`src/metrics.py` solo contiene funciones puras:** reciben filas, devuelven estructuras. Ni BD ni Flask, para que queden cubiertas por tests.
- **`openpyxl` no está en `requirements.txt` ni en la imagen Docker**, a propósito (`export_excel.py:3-4`). Nada del stack desplegado puede importarlo.
- **Formato español de números:** punto para los miles, coma para los decimales. Vive en los filtros Jinja de `dashboard.py`, en un solo sitio.
- **Nada de dependencias nuevas** en `requirements.txt`.

---

## File Structure

**Se crean:**

| Fichero | Responsabilidad |
| --- | --- |
| `migrations/007_titanium_pairs.sql` | La tabla `titanium_pairs` |
| `data/comparativa-titanium.xlsx` | El fichero de producto, versionado |
| `data/titanium_pairs.sql` | El emparejamiento como SQL, generado; versionado para poder diffear revisiones |
| `import_comparativa.py` | Lee el `.xlsx` y emite el SQL. Uso local, nunca dentro del contenedor |
| `tests/test_import_comparativa.py` | Cobertura de la lectura del Excel y del escapado |
| `n8n/comparativa-titanium-email.js` | El código del nodo *Code* del correo diario |
| `n8n/comparativa-titanium-diaria.workflow.json` | El workflow completo, tal como lo exporta n8n |

**Se modifican:**

| Fichero | Qué cambia |
| --- | --- |
| `src/db.py` | Nuevo `get_titanium_pairs()` |
| `src/metrics.py` | Nuevos `build_titanium_comparison()` y `titanium_metrics()` |
| `tests/test_metrics.py` | Cobertura de ambos |
| `dashboard.py` | Hoisting de `catalog`, dos filtros Jinja nuevos, dos variables más al contexto |
| `templates/dashboard.html` | El `navitem` deja de ser letrero; la vista `comparativa` |
| `static/css/panel.css` | Sección 10 nueva; se borran `.navitem--pronto` y `.pill-pronto`; renumerado de las secciones 10 y 11 |
| `static/js/panel.js` | Los filtros de la vista nueva |
| `README.md` | La pantalla y el importador |
| `n8n/README.md` | El workflow nuevo |

---

## Task 1: La tabla y el importador

Deja los 70 pares listos para entrar en MySQL, verificable sin tocar nada más del panel.

**Files:**
- Create: `migrations/007_titanium_pairs.sql`
- Create: `import_comparativa.py`
- Create: `data/comparativa-titanium.xlsx` (copia de `C:\Users\xlope\Downloads\Comparativa PVP Fitness Tech vs Titanium Strength.xlsx`)
- Create: `data/titanium_pairs.sql` (generado en el paso 8)
- Test: `tests/test_import_comparativa.py`
- Modify: `src/db.py` (al final de la clase `Database`, tras `log_crawl_error`)

**Interfaces:**
- Produces: `leer_pares(ruta: str | Path) -> list[dict]`, donde cada dict tiene las claves `gama`, `orden`, `ft_sku`, `ft_title`, `equivalencia`, `titanium_title`, `titanium_url`, `observaciones` (todas `str`, salvo `orden: int`; `titanium_title`, `titanium_url` y `observaciones` pueden ser `None`).
- Produces: `generar_sql(pares: list[dict]) -> str`.
- Produces: `Database.get_titanium_pairs() -> list[dict]`, con esas mismas claves más `id`, ordenado por `gama, orden`.

- [ ] **Step 1: Escribir la migración**

Crear `migrations/007_titanium_pairs.sql`:

```sql
USE competitor_monitor;

-- El emparejamiento entre nuestras maquinas y las de Titanium, tal como lo
-- decide el departamento de producto. No lleva precios: los precios salen
-- vivos del scrapper y esta tabla solo dice quien compite contra quien.
CREATE TABLE titanium_pairs (
  id INT AUTO_INCREMENT PRIMARY KEY,
  gama VARCHAR(100) NOT NULL,
  orden INT NOT NULL,
  ft_sku VARCHAR(255) NOT NULL,
  ft_title VARCHAR(500),
  equivalencia VARCHAR(30) NOT NULL,
  titanium_title VARCHAR(500),
  titanium_url VARCHAR(500),
  observaciones TEXT,
  -- Un SKU nuestro sale una sola vez en todo el Excel. Que sea unico hace
  -- que un duplicado reviente al aplicar el SQL en vez de duplicar filas en
  -- la pantalla sin que nadie se entere.
  UNIQUE KEY unique_ft_sku (ft_sku),
  INDEX idx_gama (gama),
  -- Deliberadamente NO unico: dos maquinas nuestras pueden competir contra
  -- la misma suya (SE-28972 y SE-28974 comparten el Remo Bajo Black RX).
  INDEX idx_titanium_url (titanium_url)
);
```

No hay clave foránea a `products` a propósito: el emparejamiento es un juicio de producto y debe sobrevivir a que Titanium retire una máquina de su catálogo — esa desaparición es precisamente uno de los avisos.

- [ ] **Step 2: Escribir los tests del importador (fallarán)**

Crear `tests/test_import_comparativa.py`:

```python
import pytest

openpyxl = pytest.importorskip(
    "openpyxl",
    reason="openpyxl no esta en requirements.txt a proposito: import_comparativa.py "
           "es un script de uso local y no viaja en la imagen Docker.",
)

from import_comparativa import generar_sql, leer_pares


CABECERA = [
    "SKU Fitness Tech", "Máquina Fitness Tech", "PVP FT", "Equivalencia",
    "Máquina Titanium", "PVP Titanium", "Dif. FT − Titanium",
    "Variación vs Titanium", "Enlace disponible", "URL Titanium", "Observaciones",
]


def _libro(tmp_path, hojas):
    """Un .xlsx minimo con la misma forma que el de producto."""
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for titulo, filas in hojas.items():
        ws = wb.create_sheet(titulo)
        ws.append(CABECERA)
        for fila in filas:
            ws.append(fila)
    ruta = tmp_path / "comparativa.xlsx"
    wb.save(ruta)
    return ruta


def _fila(sku="SE-1", nombre="Femoral Sentado", equivalencia="Directa",
          ti_nombre="Curl Femoral Elite", url="https://ti.es/a.html", obs="Misma funcion"):
    return [sku, nombre, 1599, equivalencia, ti_nombre, 1395, 204, 0.146, "Sí", url, obs]


def test_lee_una_fila_con_la_hoja_como_gama(tmp_path):
    ruta = _libro(tmp_path, {"Compact vs Elite": [_fila()]})

    pares = leer_pares(ruta)

    assert pares == [{
        "gama": "Compact vs Elite",
        "orden": 0,
        "ft_sku": "SE-1",
        "ft_title": "Femoral Sentado",
        "equivalencia": "Directa",
        "titanium_title": "Curl Femoral Elite",
        "titanium_url": "https://ti.es/a.html",
        "observaciones": "Misma funcion",
    }]


def test_ignora_las_columnas_de_precio_del_excel(tmp_path):
    # Son una foto del dia en que producto monto el fichero. Los precios
    # salen del scrapper, no de aqui.
    ruta = _libro(tmp_path, {"Compact vs Elite": [_fila()]})

    par = leer_pares(ruta)[0]

    assert "PVP FT" not in par
    assert 1599 not in par.values()
    assert 1395 not in par.values()


def test_numera_el_orden_dentro_de_cada_hoja(tmp_path):
    ruta = _libro(tmp_path, {
        "Compact vs Elite": [_fila(sku="SE-1"), _fila(sku="SE-2")],
        "Pro vs Black": [_fila(sku="SE-3")],
    })

    pares = leer_pares(ruta)

    assert [(p["gama"], p["orden"], p["ft_sku"]) for p in pares] == [
        ("Compact vs Elite", 0, "SE-1"),
        ("Compact vs Elite", 1, "SE-2"),
        ("Pro vs Black", 0, "SE-3"),
    ]


def test_localiza_las_columnas_por_rotulo_no_por_posicion(tmp_path):
    # Producto puede anadir una columna al Excel; eso no debe romper nada.
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    ws = wb.create_sheet("Compact vs Elite")
    ws.append(["Notas internas"] + CABECERA)
    ws.append(["lo que sea"] + _fila())
    ruta = tmp_path / "movida.xlsx"
    wb.save(ruta)

    assert leer_pares(ruta)[0]["ft_sku"] == "SE-1"


def test_salta_las_filas_en_blanco(tmp_path):
    ruta = _libro(tmp_path, {"Compact vs Elite": [
        _fila(sku="SE-1"),
        [None] * len(CABECERA),
        _fila(sku="SE-2"),
    ]})

    assert [p["ft_sku"] for p in leer_pares(ruta)] == ["SE-1", "SE-2"]


def test_una_fila_sin_equivalente_deja_vacio_el_lado_de_titanium(tmp_path):
    ruta = _libro(tmp_path, {"Pro vs Black": [
        [ "SE-9", "Elevaciones Laterales", 1699, "Sin equivalente",
          None, None, None, None, None, None, "Black Series no la tiene" ],
    ]})

    par = leer_pares(ruta)[0]

    assert par["equivalencia"] == "Sin equivalente"
    assert par["titanium_title"] is None
    assert par["titanium_url"] is None


def test_dos_filas_pueden_compartir_la_url_de_titanium(tmp_path):
    # SE-28972 y SE-28974 compiten los dos contra el Remo Bajo Black RX.
    ruta = _libro(tmp_path, {"Advanced vs Black RX": [
        _fila(sku="SE-1", url="https://ti.es/remo.html"),
        _fila(sku="SE-2", url="https://ti.es/remo.html"),
    ]})

    assert len(leer_pares(ruta)) == 2


def test_un_sku_duplicado_aborta_diciendo_donde_esta(tmp_path):
    ruta = _libro(tmp_path, {
        "Compact vs Elite": [_fila(sku="SE-1")],
        "Pro vs Black": [_fila(sku="SE-1")],
    })

    with pytest.raises(ValueError, match="SE-1"):
        leer_pares(ruta)


def test_una_columna_que_falta_aborta_diciendo_hoja_y_rotulo(tmp_path):
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    ws = wb.create_sheet("Compact vs Elite")
    ws.append([c for c in CABECERA if c != "URL Titanium"])
    ruta = tmp_path / "coja.xlsx"
    wb.save(ruta)

    with pytest.raises(ValueError, match="URL Titanium"):
        leer_pares(ruta)


def test_el_sql_envuelve_el_reemplazo_en_una_transaccion(tmp_path):
    sql = generar_sql(leer_pares(_libro(tmp_path, {"Compact vs Elite": [_fila()]})))

    assert "START TRANSACTION;" in sql
    assert "DELETE FROM titanium_pairs;" in sql
    assert sql.index("DELETE FROM titanium_pairs;") < sql.index("INSERT INTO titanium_pairs")
    assert "COMMIT;" in sql


def test_el_sql_escapa_las_comillas_del_texto(tmp_path):
    # Las observaciones de producto son prosa: llevan apostrofes.
    ruta = _libro(tmp_path, {"Compact vs Elite": [
        _fila(obs="Titanium lo llama 'Elite', nosotros no"),
    ]})

    sql = generar_sql(leer_pares(ruta))

    assert "\\'Elite\\'" in sql


def test_el_sql_escribe_null_y_no_la_palabra_none(tmp_path):
    ruta = _libro(tmp_path, {"Pro vs Black": [
        ["SE-9", "Elevaciones", 1699, "Sin equivalente",
         None, None, None, None, None, None, None],
    ]})

    sql = generar_sql(leer_pares(ruta))

    assert "NULL" in sql
    assert "'None'" not in sql
```

- [ ] **Step 3: Ejecutar los tests para verificar que fallan**

Run: `.venv\Scripts\python -m pytest tests/test_import_comparativa.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'import_comparativa'`

- [ ] **Step 4: Escribir `import_comparativa.py`**

```python
"""Convierte el Excel de emparejamiento de producto en el SQL que puebla
`titanium_pairs`.

Script de uso manual desde el equipo local, nada del stack lo llama. Necesita
openpyxl, que no esta en requirements.txt a proposito para no meter la
dependencia en la imagen (igual que export_excel.py).

Emite SQL en vez de escribir en la base por dos motivos que no se pueden
esquivar: openpyxl no existe dentro del contenedor, y el contenedor `mysql`
no publica el 3306 fuera de la red interna de Docker. De regalo, el
emparejamiento queda versionado como texto legible y el diff entre dos
revisiones de producto se lee.

    python import_comparativa.py
    scp data/titanium_pairs.sql deploy@168.119.241.200:/tmp/
    ssh deploy@168.119.241.200
    docker exec -i mysql mysql -u root -p"$MYSQL_ROOT_PASSWORD" \\
      competitor_monitor < /tmp/titanium_pairs.sql
"""

import argparse
import sys
from pathlib import Path

from openpyxl import load_workbook

XLSX = Path("data/comparativa-titanium.xlsx")
SALIDA = Path("data/titanium_pairs.sql")

# Rotulo de la cabecera -> columna de la tabla. Lo que no este aqui se
# ignora: las columnas de precio y diferencia del Excel son una foto del dia
# en que producto lo monto, y los precios buenos salen del scrapper.
COLUMNAS = {
    "SKU Fitness Tech": "ft_sku",
    "Máquina Fitness Tech": "ft_title",
    "Equivalencia": "equivalencia",
    "Máquina Titanium": "titanium_title",
    "URL Titanium": "titanium_url",
    "Observaciones": "observaciones",
}

CAMPOS = ["gama", "orden", "ft_sku", "ft_title", "equivalencia",
          "titanium_title", "titanium_url", "observaciones"]


def _texto(valor):
    """Celda -> str limpio, o None si esta vacia. Las celdas del Excel llegan
    con espacios de sobra y saltos de linea de cuando se pego el texto."""
    if valor is None:
        return None
    limpio = str(valor).strip()
    return limpio or None


def leer_pares(ruta) -> list[dict]:
    """Los pares del Excel, una hoja por gama, en el orden en que los dejo
    producto.

    Lanza ValueError si falta una columna o si un SKU sale dos veces: son
    errores del fichero de producto y hay que verlos, no resolverlos por el.
    """
    libro = load_workbook(ruta, data_only=True)
    pares = []
    vistos = {}

    for hoja in libro.worksheets:
        filas = hoja.iter_rows(values_only=True)
        cabecera = next(filas, None)
        if cabecera is None:
            continue

        # Por rotulo y no por posicion: anadir una columna al Excel no debe
        # romper el importador.
        indice = {}
        for i, celda in enumerate(cabecera):
            rotulo = _texto(celda)
            if rotulo in COLUMNAS:
                indice[COLUMNAS[rotulo]] = i

        faltan = [r for r, campo in COLUMNAS.items() if campo not in indice]
        if faltan:
            raise ValueError(
                f"En la hoja '{hoja.title}' faltan columnas: {', '.join(faltan)}"
            )

        orden = 0
        for fila in filas:
            sku = _texto(fila[indice["ft_sku"]]) if indice["ft_sku"] < len(fila) else None
            if not sku:
                continue  # fila en blanco del final de la hoja

            if sku in vistos:
                raise ValueError(
                    f"El SKU {sku} sale dos veces: en '{vistos[sku]}' y en "
                    f"'{hoja.title}'. Corrigelo en el Excel de producto."
                )
            vistos[sku] = hoja.title

            par = {"gama": hoja.title, "orden": orden, "ft_sku": sku}
            for campo, i in indice.items():
                if campo != "ft_sku":
                    par[campo] = _texto(fila[i]) if i < len(fila) else None
            pares.append(par)
            orden += 1

    return pares


def _valor(v) -> str:
    """Un campo listo para meter en el INSERT."""
    if v is None:
        return "NULL"
    if isinstance(v, int):
        return str(v)
    return "'" + str(v).replace("\\", "\\\\").replace("'", "\\'") + "'"


def generar_sql(pares: list[dict]) -> str:
    """El reemplazo completo, envuelto en una transaccion, mas el informe.

    Reemplazo y no upsert: el Excel es la verdad entera, asi que si producto
    quita una fila tiene que desaparecer tambien aqui. Y la transaccion
    garantiza que la tabla no se quede a medias si el fichero viene roto.
    """
    lineas = [
        "-- Generado por import_comparativa.py a partir de",
        "-- data/comparativa-titanium.xlsx. No editar a mano.",
        "",
        "USE competitor_monitor;",
        "",
        "START TRANSACTION;",
        "",
        "DELETE FROM titanium_pairs;",
        "",
    ]

    for par in pares:
        valores = ", ".join(_valor(par.get(c)) for c in CAMPOS)
        lineas.append(
            f"INSERT INTO titanium_pairs ({', '.join(CAMPOS)}) VALUES ({valores});"
        )

    lineas += ["", "COMMIT;", "", INFORME]
    return "\n".join(lineas) + "\n"


# El informe va dentro del propio .sql, detras del COMMIT: asi se calcula
# donde estan los datos y sale por pantalla al aplicarlo, sin herramienta
# aparte. Nada de esto corrige nada; son avisos para producto.
INFORME = """
-- ---------------------------------------------------------------------
-- Informe. Nada de lo que salga aqui es un fallo del sistema: son cosas
-- que producto tiene que mirar en su fichero.
-- ---------------------------------------------------------------------

SELECT '1) URLs de Titanium que no existen en el catalogo vigilado' AS informe;
SELECT tp.gama, tp.ft_sku, tp.titanium_url
FROM titanium_pairs tp
LEFT JOIN products p
       ON p.url = tp.titanium_url
      AND p.competitor_id = (SELECT id FROM competitors WHERE name = 'Titanium Strength')
WHERE tp.titanium_url IS NOT NULL AND p.id IS NULL;

SELECT '2) SKUs nuestros que no estan publicados en Fitness Tech ES' AS informe;
SELECT tp.gama, tp.ft_sku, tp.ft_title
FROM titanium_pairs tp
LEFT JOIN products p
       ON p.sku = tp.ft_sku
      AND p.status = 'active'
      AND p.competitor_id = (SELECT id FROM competitors WHERE name = 'Fitness Tech')
WHERE p.id IS NULL;

SELECT '3) De esos, cuales existen con otro prefijo (SE- / PSE-)' AS informe;
SELECT tp.ft_sku AS en_el_excel, p.sku AS en_la_tienda, p.title
FROM titanium_pairs tp
JOIN products p
  ON p.sku <> tp.ft_sku
 AND SUBSTRING_INDEX(p.sku, '-', -1) = SUBSTRING_INDEX(tp.ft_sku, '-', -1)
 AND p.status = 'active'
 AND p.competitor_id = (SELECT id FROM competitors WHERE name = 'Fitness Tech')
LEFT JOIN products exacto
       ON exacto.sku = tp.ft_sku
      AND exacto.status = 'active'
      AND exacto.competitor_id = (SELECT id FROM competitors WHERE name = 'Fitness Tech')
WHERE exacto.id IS NULL;
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("xlsx", nargs="?", default=XLSX, type=Path,
                        help=f"Excel de producto (por defecto {XLSX})")
    parser.add_argument("-o", "--salida", default=SALIDA, type=Path,
                        help=f"Fichero SQL a escribir (por defecto {SALIDA})")
    args = parser.parse_args()

    try:
        pares = leer_pares(args.xlsx)
    except ValueError as e:
        # Sin escribir el .sql: mas vale no tener fichero que tener uno malo.
        print(f"Error en el Excel: {e}", file=sys.stderr)
        return 1

    args.salida.parent.mkdir(parents=True, exist_ok=True)
    args.salida.write_text(generar_sql(pares), encoding="utf-8")

    gamas = {p["gama"] for p in pares}
    print(f"{len(pares)} pares en {len(gamas)} gamas -> {args.salida}")
    for gama in sorted(gamas):
        print(f"  {gama}: {sum(1 for p in pares if p['gama'] == gama)}")
    print("\nAplicalo con:")
    print(f"  scp {args.salida} deploy@168.119.241.200:/tmp/")
    print('  ssh deploy@168.119.241.200 \'docker exec -i mysql mysql -u root '
          '-p"$MYSQL_ROOT_PASSWORD" competitor_monitor < /tmp/titanium_pairs.sql\'')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Ejecutar los tests hasta que pasen**

Run: `.venv\Scripts\python -m pytest tests/test_import_comparativa.py -v`
Expected: PASS, 12 tests.

- [ ] **Step 6: Añadir `get_titanium_pairs()` a `src/db.py`**

Al final de la clase `Database`, después de `log_crawl_error`. Sin test: en este repo `src/db.py` no tiene tests de integración (no hay MySQL en CI), y esta consulta se verifica en el paso 9 contra la base real.

```python
    def get_titanium_pairs(self) -> list[dict]:
        """El emparejamiento contra Titanium que mantiene producto.

        Sin precios: los pone `build_titanium_comparison` cruzando esto con el
        catalogo vigente. Se puebla con `import_comparativa.py`.
        """
        with self.get_connection() as conn:
            cursor = conn.cursor(dictionary=True)
            try:
                cursor.execute("""
                    SELECT id, gama, orden, ft_sku, ft_title, equivalencia,
                           titanium_title, titanium_url, observaciones
                    FROM titanium_pairs
                    ORDER BY gama, orden
                """)
                return cursor.fetchall()
            finally:
                cursor.close()
```

- [ ] **Step 7: Copiar el Excel de producto al repo**

```bash
mkdir -p data
cp "/c/Users/xlope/Downloads/Comparativa PVP Fitness Tech vs Titanium Strength.xlsx" \
   data/comparativa-titanium.xlsx
```

Comprobar que `.gitignore` no excluye `data/` — si lo excluyese, añadir una excepción, porque este fichero **debe** viajar en el repo: es la única copia trazable del criterio de producto.

- [ ] **Step 8: Generar el SQL y revisarlo a ojo**

Run: `.venv\Scripts\python import_comparativa.py`
Expected:

```
70 pares en 4 gamas -> data\titanium_pairs.sql
  Advanced vs Black RX: 19
  Compact vs Elite: 17
  Pro Tech vs Genesis: 15
  Pro vs Black: 19
```

Si sale otro número de pares, **parar**: o el Excel ha cambiado o el importador se está comiendo filas. Comprobar además que `data/titanium_pairs.sql` tiene 70 `INSERT` (`grep -c "^INSERT" data/titanium_pairs.sql`) y que las dos filas *Sin equivalente* llevan `NULL` en `titanium_url`.

- [ ] **Step 9: Aplicar la migración y el SQL en el VPS**

```bash
scp migrations/007_titanium_pairs.sql data/titanium_pairs.sql deploy@168.119.241.200:/tmp/
ssh deploy@168.119.241.200
docker exec -i mysql sh -c 'mysql -u root -p"$MYSQL_ROOT_PASSWORD"' \
  < /tmp/007_titanium_pairs.sql
docker exec -i mysql sh -c 'mysql -u root -p"$MYSQL_ROOT_PASSWORD" \
  --default-character-set=utf8mb4 competitor_monitor' \
  < /tmp/titanium_pairs.sql
```

**`--default-character-set=utf8mb4` no es opcional.** El cliente `mysql` del
contenedor arranca en `latin1`, así que sin él lee el fichero (UTF-8) como
Latin-1 y guarda `Extensión` como `ExtensiÃ³n`. Comprobado en carne propia el
2026-09-07. Y para verificarlo después, `LIKE '%Ã%'` **no vale**: la colación
`utf8mb4_unicode_ci` es insensible a acentos y casa con cualquier `a`, así que
dice que las 70 filas están mal cuando no lo está ninguna. Hay que comparar en
binario con `CONVERT(... USING binary)`.

Con **root** y no con el `DB_USER` del `.env` (que es `scraper`, sin permiso
para crear tablas), y expandiendo la contraseña **dentro** del contenedor,
que es el único sitio donde existe.

Después, comprobar que el usuario de la aplicación ve la tabla nueva — si los
`GRANT` de `scraper` fuesen por tabla y no por base, el panel daría un error
de permisos en producción y no en local:

```bash
cd /home/deploy/scraper-competidores && docker compose exec -T crawler python -c "
import os
from src.db import Database
db = Database(host='mysql', user=os.getenv('DB_USER'), password=os.getenv('DB_PASSWORD'),
              database=os.getenv('DB_NAME'))
with db.get_connection() as conn:
    cur = conn.cursor(dictionary=True)
    cur.execute('SELECT COUNT(*) n FROM titanium_pairs')
    print(cur.fetchone())
"
```

Expected: el informe imprime **ninguna** URL de Titanium huérfana, **20** SKUs nuestros sin publicar, y la consulta 3 señala `SE-28780` → `PSE-28780`. Si el informe (1) devuelve filas, el crawl ha cambiado alguna URL y hay que avisar a producto antes de seguir.

- [ ] **Step 10: Commit**

```bash
git add migrations/007_titanium_pairs.sql import_comparativa.py \
        tests/test_import_comparativa.py data/ src/db.py
git commit -m "Traer al scrapper el emparejamiento Titanium de producto"
```

---

## Task 2: El cálculo

Las dos funciones puras que resuelven el emparejamiento contra el catálogo vigente. Todo lo demás de la pantalla depende de esto.

**Files:**
- Modify: `src/metrics.py` (al final del fichero, tras `changes_since`)
- Test: `tests/test_metrics.py` (al final)

**Interfaces:**
- Consumes: `Database.get_titanium_pairs()` de la Task 1, y `Database.get_latest_snapshots()`, que devuelve dicts con `competitor`, `title`, `sku`, `series`, `url`, `price`, `price_original`, `available`, `captured_at`.
- Produces: `build_titanium_comparison(pairs: list[dict], catalog: list[dict]) -> list[dict]` — una lista de gamas, cada una `{"gama": str, "slug": str, "pares": list[dict]}`. Cada par lleva `ft_sku`, `ft_title`, `ft_url`, `ft_price`, `titanium_title`, `titanium_url`, `titanium_price`, `titanium_available`, `equivalencia`, `observaciones`, `estado`, `delta`, `delta_pct`.
- Produces: `titanium_metrics(gamas: list[dict], changes_week: list[dict]) -> dict` con las claves `pares`, `mas_caros`, `mas_baratos`, `delta_pct_mediano`, `cambios_semana`.

- [ ] **Step 1: Escribir los tests (fallarán)**

Añadir al final de `tests/test_metrics.py`, y añadir `build_titanium_comparison` y `titanium_metrics` al `from src.metrics import (...)` de la cabecera:

```python
# ---------- comparativa Titanium ----------

def _par(ft_sku="SE-1", gama="Compact vs Elite", orden=0, equivalencia="Directa",
         titanium_url="https://ti.es/a.html"):
    return {
        "gama": gama,
        "orden": orden,
        "ft_sku": ft_sku,
        "ft_title": "Femoral Sentado",
        "equivalencia": equivalencia,
        "titanium_title": "Curl Femoral Elite",
        "titanium_url": titanium_url,
        "observaciones": "Misma funcion",
    }


def _nuestro(sku="SE-1", price=1599.0):
    return _product(price=price, competitor="Fitness Tech") | {
        "sku": sku, "url": "https://fitnesstech.es/" + sku,
    }


def _suyo(url="https://ti.es/a.html", price=1395.0, available=True):
    return _product(price=price, available=available,
                    competitor="Titanium Strength") | {"sku": "TS-1", "url": url}


def test_comparativa_agrupa_por_gama_respetando_el_orden_de_producto():
    pairs = [
        _par(ft_sku="SE-2", gama="Compact vs Elite", orden=1),
        _par(ft_sku="SE-1", gama="Compact vs Elite", orden=0),
        _par(ft_sku="SE-3", gama="Pro vs Black", orden=0),
    ]
    # Llegan ya ordenados de la BD (ORDER BY gama, orden); aqui se comprueba
    # que la funcion no los reordena por su cuenta.
    pairs.sort(key=lambda p: (p["gama"], p["orden"]))

    gamas = build_titanium_comparison(pairs, [])

    assert [g["gama"] for g in gamas] == ["Compact vs Elite", "Pro vs Black"]
    assert [p["ft_sku"] for p in gamas[0]["pares"]] == ["SE-1", "SE-2"]
    assert gamas[0]["slug"] == "compact-vs-elite"


def test_comparativa_resuelve_ambos_lados_y_calcula_la_diferencia():
    gamas = build_titanium_comparison([_par()], [_nuestro(), _suyo()])
    par = gamas[0]["pares"][0]

    assert par["estado"] == "ok"
    assert par["ft_price"] == 1599.0
    assert par["titanium_price"] == 1395.0
    assert par["delta"] == 204.0
    assert par["delta_pct"] == pytest.approx(204.0 / 1395.0 * 100)


def test_comparativa_da_delta_negativo_cuando_somos_mas_baratos():
    gamas = build_titanium_comparison(
        [_par()], [_nuestro(price=1599.0), _suyo(price=1895.0)])

    assert gamas[0]["pares"][0]["delta"] == -296.0


def test_comparativa_solo_mira_fitness_tech_es():
    # FR y PT tienen los mismos SKU y otros precios: si se colasen, el lado
    # nuestro seria el de otro pais.
    catalogo = [
        _product(price=1200.0, competitor="Fitness Tech FR") | {
            "sku": "SE-1", "url": "https://fr.example/x"},
        _suyo(),
    ]

    par = build_titanium_comparison([_par()], catalogo)[0]["pares"][0]

    assert par["estado"] == "sin_publicar"
    assert par["ft_price"] is None


def test_comparativa_marca_sin_equivalente_cuando_producto_no_le_encontro_rival():
    pair = _par(equivalencia="Sin equivalente", titanium_url=None)

    par = build_titanium_comparison([pair], [_nuestro()])[0]["pares"][0]

    assert par["estado"] == "sin_equivalente"
    assert par["delta"] is None


def test_comparativa_marca_sin_publicar_cuando_el_sku_no_esta_en_la_tienda():
    par = build_titanium_comparison([_par()], [_suyo()])[0]["pares"][0]

    assert par["estado"] == "sin_publicar"
    assert par["ft_price"] is None
    assert par["titanium_price"] == 1395.0
    assert par["delta"] is None


def test_comparativa_marca_fuera_catalogo_cuando_titanium_retiro_la_maquina():
    # get_latest_snapshots excluye los productos 'removed', asi que una URL
    # que no aparece es una maquina que Titanium ha dado de baja.
    par = build_titanium_comparison([_par()], [_nuestro()])[0]["pares"][0]

    assert par["estado"] == "fuera_catalogo"
    assert par["delta"] is None


def test_comparativa_admite_dos_pares_contra_la_misma_maquina_de_titanium():
    # SE-28972 y SE-28974 compiten los dos contra el Remo Bajo Black RX.
    pairs = [
        _par(ft_sku="SE-1", orden=0, titanium_url="https://ti.es/remo.html"),
        _par(ft_sku="SE-2", orden=1, titanium_url="https://ti.es/remo.html"),
    ]
    catalogo = [_nuestro("SE-1", 1599.0), _nuestro("SE-2", 1899.0),
                _suyo(url="https://ti.es/remo.html", price=2395.0)]

    pares = build_titanium_comparison(pairs, catalogo)[0]["pares"]

    assert [p["delta"] for p in pares] == [-796.0, -496.0]


def test_metricas_cuentan_donde_somos_mas_caros_y_mas_baratos():
    pairs = [_par(ft_sku="SE-1", orden=0), _par(ft_sku="SE-2", orden=1)]
    catalogo = [
        _nuestro("SE-1", 1599.0), _nuestro("SE-2", 1000.0),
        _suyo(price=1395.0),
    ]
    gamas = build_titanium_comparison(pairs, catalogo)

    m = titanium_metrics(gamas, [])

    assert m["pares"] == 2
    assert m["mas_caros"] == 1
    assert m["mas_baratos"] == 1


def test_metricas_con_la_tabla_vacia_no_dividen_por_cero():
    m = titanium_metrics([], [])

    assert m["pares"] == 0
    assert m["delta_pct_mediano"] is None
    assert m["cambios_semana"] == 0


def test_metricas_cuentan_solo_los_cambios_de_titanium_en_productos_emparejados():
    gamas = build_titanium_comparison([_par()], [_nuestro(), _suyo()])
    feed = [
        {"store": "Titanium Strength", "url": "https://ti.es/a.html"},   # cuenta
        {"store": "Titanium Strength", "url": "https://ti.es/otra.html"},  # no emparejado
        {"store": "Fitness Tech", "url": "https://ti.es/a.html"},        # otra tienda
    ]

    assert titanium_metrics(gamas, feed)["cambios_semana"] == 1
```

Añadir `import pytest` al principio de `tests/test_metrics.py` si no está (hace falta por `pytest.approx`).

- [ ] **Step 2: Ejecutar los tests para verificar que fallan**

Run: `.venv\Scripts\python -m pytest tests/test_metrics.py -k titanium -v`
Expected: FAIL con `ImportError: cannot import name 'build_titanium_comparison'`

- [ ] **Step 3: Implementar en `src/metrics.py`**

Al final del fichero:

```python
# ---------------------------------------------------------------------------
# Comparativa contra Titanium Strength
#
# El emparejamiento lo decide producto y vive en `titanium_pairs`; aqui solo
# se cruza con el catalogo vigente para ponerle precios de hoy. Se referencia
# a las tiendas por nombre y no por id: los ids son de la base de produccion
# y no significan nada en un test.
# ---------------------------------------------------------------------------

# `NOSOTROS` es la tienda espanola en concreto, no el conjunto `OWN_STORES`
# de mas arriba: la comparativa enfrenta precios de ES contra titaniumstrength.es,
# y colar aqui la de Francia o Portugal daria un lado nuestro de otro pais.
NOSOTROS = "Fitness Tech"
TITANIUM = "Titanium Strength"
SIN_EQUIVALENTE = "Sin equivalente"


def build_titanium_comparison(pairs: list[dict], catalog: list[dict]) -> list[dict]:
    """Los pares de producto resueltos contra el catalogo vigente, agrupados
    por gama y en el orden en que los dejo producto.

    `catalog` es lo que devuelve `get_latest_snapshots()`, que el panel ya
    consulta para las tiendas: esta pantalla no cuesta ni una consulta mas.
    """
    por_sku = {p["sku"]: p for p in catalog
               if p.get("competitor") == NOSOTROS and p.get("sku")}
    por_url = {p["url"]: p for p in catalog
               if p.get("competitor") == TITANIUM and p.get("url")}

    gamas: list[dict] = []
    for pair in pairs:
        nuestro = por_sku.get(pair["ft_sku"])
        suyo = por_url.get(pair["titanium_url"]) if pair.get("titanium_url") else None

        # El orden importa. `sin_equivalente` primero porque es un juicio de
        # producto y no un hueco en los datos. Y `fuera_catalogo` antes que
        # `sin_publicar` porque, si Titanium ha retirado la maquina, el par
        # esta muerto tengamos nosotros SKU publicado o no.
        if pair["equivalencia"] == SIN_EQUIVALENTE:
            estado = "sin_equivalente"
        elif suyo is None:
            estado = "fuera_catalogo"
        elif nuestro is None:
            estado = "sin_publicar"
        else:
            estado = "ok"

        delta = delta_pct = None
        if estado == "ok" and nuestro.get("price") is not None \
                and suyo.get("price") is not None:
            delta = nuestro["price"] - suyo["price"]
            if suyo["price"]:
                delta_pct = delta / suyo["price"] * 100

        if not gamas or gamas[-1]["gama"] != pair["gama"]:
            gamas.append({"gama": pair["gama"],
                          "slug": slugify(pair["gama"]),
                          "pares": []})

        gamas[-1]["pares"].append({
            # Los nombres son los del Excel y no los de las tiendas: producto
            # llama "Femoral Sentado" a lo que la web titula "Cuadriceps y
            # femoral | Maquina selectorizada dual - Compact Series", y en una
            # tabla de comparacion mandan los suyos.
            "ft_sku": pair["ft_sku"],
            "ft_title": pair["ft_title"],
            "ft_url": nuestro["url"] if nuestro else None,
            "ft_price": nuestro["price"] if nuestro else None,
            "titanium_title": pair["titanium_title"],
            "titanium_url": pair["titanium_url"],
            "titanium_price": suyo["price"] if suyo else None,
            "titanium_available": _bool_o_none(suyo["available"]) if suyo else None,
            "equivalencia": pair["equivalencia"],
            "observaciones": pair["observaciones"],
            "estado": estado,
            "delta": delta,
            "delta_pct": delta_pct,
        })

    return gamas


def titanium_metrics(gamas: list[dict], changes_week: list[dict]) -> dict:
    """Las cifras de cabecera de la comparativa."""
    pares = [p for g in gamas for p in g["pares"]]
    resueltos = [p for p in pares if p["delta"] is not None]
    pcts = [p["delta_pct"] for p in resueltos if p["delta_pct"] is not None]

    emparejadas = {p["titanium_url"] for p in pares if p["titanium_url"]}
    cambios = [c for c in changes_week
               if c.get("store") == TITANIUM and c.get("url") in emparejadas]

    return {
        "pares": len(resueltos),
        "mas_caros": sum(1 for p in resueltos if p["delta"] > 0),
        "mas_baratos": sum(1 for p in resueltos if p["delta"] < 0),
        # Mediana y no media, por lo mismo que en `target_metrics`: una prensa
        # de pierna 1.096 EUR por debajo desplazaria la media hasta hacerla
        # inutil.
        "delta_pct_mediano": median(pcts) if pcts else None,
        "cambios_semana": len(cambios),
    }
```

- [ ] **Step 4: Ejecutar toda la batería**

Run: `.venv\Scripts\python -m pytest -v`
Expected: PASS, incluidos los 11 tests nuevos y los que ya había.

- [ ] **Step 5: Commit**

```bash
git add src/metrics.py tests/test_metrics.py
git commit -m "Resolver el emparejamiento Titanium contra el catalogo vigente"
```

---

## Task 3: La pantalla

**Files:**
- Modify: `dashboard.py` (filtros Jinja tras `fmt_fecha`; `index()`)
- Modify: `templates/dashboard.html:147-155` (el navitem) y una `<section class="view">` nueva
- Modify: `static/css/panel.css` (borrar `:248-262`; sección 10 nueva antes de `:689`)
- Modify: `static/js/panel.js` (bloque nuevo antes de `desdeHash`)
- Modify: `README.md`

**Interfaces:**
- Consumes: `build_titanium_comparison`, `titanium_metrics` y `Database.get_titanium_pairs()` de las tasks 1 y 2.
- Produces: la vista `#comparativa`. Nada depende de ella.

- [ ] **Step 1: Añadir los dos filtros Jinja a `dashboard.py`**

Justo después de `fmt_fecha`:

```python
@app.template_filter("eur_signo")
def fmt_eur_signo(value) -> str:
    """Como `eur`, pero con el signo siempre delante. La diferencia contra
    Titanium no se entiende sin el: 204 y -204 se leerian igual."""
    if value is None:
        return "—"
    signo = "+" if value > 0 else "-" if value < 0 else ""
    return signo + _es_number(abs(value), 2) + " €"


@app.template_filter("pct_signo")
def fmt_pct_signo(value) -> str:
    if value is None:
        return "—"
    signo = "+" if value > 0 else "-" if value < 0 else ""
    return signo + _es_number(abs(value), 1) + " %"
```

- [ ] **Step 2: Conectar la comparativa en `index()`**

Sustituir el cuerpo de `index()` por:

```python
@app.route("/")
def index():
    db = get_db()
    # Se saca a variable porque ahora lo usan dos cosas: las tiendas y la
    # comparativa. Consultarlo dos veces serian 3.400 filas de mas por carga.
    catalog = db.get_latest_snapshots()
    targets = build_targets(
        competitors=db.get_competitor_stats(),
        new_products=db.get_recently_added_products(hours=WEEK_HOURS),
        price_events=db.get_recent_price_events(hours=WEEK_HOURS),
        availability_events=db.get_recent_availability_events(hours=WEEK_HOURS),
        removed_products=db.get_recently_removed_products(hours=WEEK_HOURS),
        catalog=catalog,
    )
    week = build_change_feed(targets)
    comparativa = build_titanium_comparison(db.get_titanium_pairs(), catalog)
    return render_template(
        "dashboard.html",
        targets=targets,
        totals=global_metrics(targets),
        changes=changes_since(week, datetime.now() - timedelta(hours=24)),
        changes_week=week,
        comparativa=comparativa,
        comparativa_totals=titanium_metrics(comparativa, week),
    )
```

Y añadir `build_titanium_comparison` y `titanium_metrics` al `from src.metrics import (...)`.

- [ ] **Step 3: Convertir el letrero del raíl en enlace**

En `templates/dashboard.html`, sustituir las líneas 148-155 (el `<span class="navitem navitem--pronto">`) por:

```html
    <a class="navitem" href="#comparativa" data-view="comparativa">
      <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor"
           stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <path d="M3 13V7M8 13V3M13 13v-4"></path>
      </svg>
      <span class="navitem__text">Comparativa Titanium</span>
    </a>
```

- [ ] **Step 4: Añadir la vista**

En `templates/dashboard.html`, justo antes del `{# ------------------------- VISTAS DE TIENDA ------------------------ #}`:

```html
    {# ------------------------ COMPARATIVA TITANIUM --------------------- #}
    <section class="view" data-view="comparativa" tabindex="-1"
             data-titulo="Comparativa Titanium"
             data-sub="{{ comparativa_totals.pares }} pares con precio en ambos lados">

      <div class="filtros-tienda" role="group" aria-label="Filtrar por gama">
        <span class="filtros__rotulo">Gama</span>
        <button type="button" class="pastilla is-active" data-gama="">Todas</button>
        {% for g in comparativa %}
        <button type="button" class="pastilla" data-gama="{{ g.gama }}">{{ g.gama }}</button>
        {% endfor %}
      </div>

      <div class="cifras">
        <div class="cifra"><p class="cifra__rotulo">Pares vigilados</p>
          <p class="cifra__valor">{{ comparativa_totals.pares | miles }}</p></div>
        <div class="cifra"><p class="cifra__rotulo">Somos más caros</p>
          <p class="cifra__valor">{{ comparativa_totals.mas_caros | miles }}</p></div>
        <div class="cifra"><p class="cifra__rotulo">Somos más baratos</p>
          <p class="cifra__valor">{{ comparativa_totals.mas_baratos | miles }}</p></div>
        <div class="cifra"><p class="cifra__rotulo">Diferencia mediana</p>
          <p class="cifra__valor">{{ comparativa_totals.delta_pct_mediano | pct_signo }}</p></div>
        <div class="cifra"><p class="cifra__rotulo">Cambios 7 días</p>
          <p class="cifra__valor">{{ comparativa_totals.cambios_semana | miles }}</p></div>
      </div>

      <div class="filtros-tienda" role="group" aria-label="Filtrar por equivalencia">
        <span class="filtros__rotulo">Equivalencia</span>
        {% for clave in ['', 'Directa', 'Aproximada', 'Sin equivalente'] %}
        <button type="button" class="pastilla pastilla--sm{{ ' is-active' if not clave }}"
                data-equiv="{{ clave }}">{{ clave or 'Todas' }}</button>
        {% endfor %}
      </div>

      <div class="vs-gamas">
        {% for g in comparativa %}
        <section class="bloque" data-gama="{{ g.gama }}">
          <div class="bloque__filtros">
            <b class="vs-gama">{{ g.gama }}</b>
            <span class="vs-cuenta"><span data-cuenta-pares>{{ g.pares | length }}</span> pares</span>
          </div>
          <div class="tablawrap">
            <table class="tabla tabla--vs">
              <thead><tr>
                <th>Fitness Tech</th>
                <th class="vs-th-delta">Δ</th>
                <th>Titanium Strength</th>
              </tr></thead>
              <tbody>
                {% for p in g.pares %}
                <tr data-equiv="{{ p.equivalencia }}"
                    data-busca="{{ (p.ft_title ~ ' ' ~ p.ft_sku ~ ' ' ~ (p.titanium_title or '')) | lower }}">

                  <td>
                    <span class="vs-lado">
                      <span class="vs-nombre">
                        {%- if p.ft_url -%}
                          <a href="{{ p.ft_url }}" target="_blank" rel="noopener">{{ p.ft_title }}</a>
                        {%- else -%}{{ p.ft_title }}{%- endif -%}
                      </span>
                      <span class="vs-sku">{{ p.ft_sku }}</span>
                      {% if p.ft_price is not none %}
                      <span class="vs-precio">{{ p.ft_price | eur }}</span>
                      {% else %}
                      <span class="vs-nota">Sin publicar en la tienda</span>
                      {% endif %}
                    </span>
                  </td>

                  <td class="vs-delta{{ ' vs-delta--up' if p.delta and p.delta > 0 }}{{ ' vs-delta--down' if p.delta and p.delta < 0 }}">
                    {% if p.delta is not none %}
                    <b>{{ p.delta | eur_signo }}</b>
                    <span>{{ p.delta_pct | pct_signo }}</span>
                    {% endif %}
                  </td>

                  <td>
                    {% if p.estado == 'sin_equivalente' %}
                    <span class="vs-lado">
                      <span class="vs-nota">Sin equivalente en Titanium</span>
                      {% if p.observaciones %}<span class="vs-obs">{{ p.observaciones }}</span>{% endif %}
                    </span>
                    {% else %}
                    <span class="vs-lado">
                      <span class="vs-nombre">
                        {%- if p.titanium_url -%}
                          <a href="{{ p.titanium_url }}" target="_blank" rel="noopener">{{ p.titanium_title }}</a>
                        {%- else -%}{{ p.titanium_title }}{%- endif -%}
                      </span>
                      <span class="vs-meta">
                        {% if p.estado == 'fuera_catalogo' %}
                        Fuera de catálogo
                        {% else %}
                        <span class="vs-dot{{ ' is-on' if p.titanium_available }}"></span>
                        {{ 'Disponible' if p.titanium_available else 'Agotado' }}
                        {% endif %}
                        ·
                        <span{% if p.observaciones %} title="{{ p.observaciones }}"{% endif %}>{{ p.equivalencia }}</span>
                      </span>
                      {% if p.titanium_price is not none %}
                      <span class="vs-precio">{{ p.titanium_price | eur }}</span>
                      {% endif %}
                    </span>
                    {% endif %}
                  </td>

                </tr>
                {% endfor %}
              </tbody>
            </table>
          </div>
        </section>
        {% endfor %}
      </div>

      <p class="vacio{{ ' is-on' if not comparativa }}" data-vacio>
        {% if comparativa %}Nada que revisar con este filtro.
        {% else %}Todavía no hay emparejamiento cargado. Se genera con
        <code>python import_comparativa.py</code> y se aplica sobre MySQL.{% endif %}
      </p>
    </section>
```

- [ ] **Step 5: Borrar el CSS del letrero y añadir la sección nueva**

Borrar de `static/css/panel.css` las líneas 248-262 completas (`.navitem--pronto`, su `:hover`, el comentario, `.navitem--pronto .navitem__text` y `.pill-pronto`). Ya no queda ningún letrero pendiente en el panel; si algún día hace falta otro, está en el historial.

Insertar **antes** de `/* ---------- 10  Pantalla estrecha ---` (línea 689) y renumerar esa sección a 11 y `Utilidades` a 12:

```css
/* ---------- 10  Comparativa Titanium ------------------------------------- */

.vs-gamas { display: grid; gap: 14px; }

.vs-gama { font-size: 0.875rem; }
.vs-cuenta { font-size: 0.75rem; color: var(--ink-3); }

/* Ancho fijo y no automatico: con `auto` la columna del medio se estira con
   el texto de las cifras y separa las dos maquinas que toda la pantalla
   existe para ver juntas. */
.tabla--vs { table-layout: fixed; }
.tabla--vs th:first-child,
.tabla--vs th:last-child { width: 41%; }
.tabla--vs td { vertical-align: top; }

.vs-th-delta { text-align: center; }

.vs-lado { display: flex; flex-direction: column; gap: 3px; }

.vs-nombre { color: var(--ink); font-weight: 500; }
.vs-nombre a { color: inherit; }
.vs-nombre a:hover { color: var(--accent); text-decoration: underline; }

.vs-sku {
  font-family: "IBM Plex Mono", monospace;
  font-size: 0.719rem;
  color: var(--ink-3);
}

.vs-precio {
  font-family: "IBM Plex Mono", monospace;
  font-size: 0.813rem;
  color: var(--ink);
}

.vs-meta { font-size: 0.719rem; color: var(--ink-2); }
.vs-nota { font-size: 0.75rem; color: var(--ink-3); font-style: italic; }
.vs-obs { font-size: 0.719rem; color: var(--ink-3); }

.vs-dot {
  display: inline-block;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--ink-3);
  margin-right: 3px;
}
.vs-dot.is-on { background: var(--accent); }

/* Rojo cuando somos mas caros y verde cuando somos mas baratos: la misma
   convencion que la bandeja, donde --up-* viste las malas noticias. */
.vs-delta {
  text-align: center;
  font-family: "IBM Plex Mono", monospace;
  white-space: nowrap;
  color: var(--ink-3);
}
.vs-delta b { display: block; font-weight: 500; font-size: 0.813rem; }
.vs-delta span { display: block; font-size: 0.719rem; padding-top: 2px; }
.vs-delta--up { color: var(--up-ink); }
.vs-delta--down { color: var(--down-ink); }
```

Y dentro del bloque `@media (max-width: 560px)` de la sección de pantalla estrecha, añadir:

```css
  /* Las tres columnas apiladas, con la diferencia entre ambas maquinas, que
     es donde se entiende. */
  .tabla--vs, .tabla--vs tbody, .tabla--vs tr, .tabla--vs td { display: block; width: auto; }
  .tabla--vs thead { display: none; }
  .tabla--vs td { border-bottom: 0; padding: 4px 12px; }
  .tabla--vs tr { border-bottom: 1px solid var(--line); padding: 8px 0; }
  .vs-delta { text-align: left; }
  .vs-delta b, .vs-delta span { display: inline; }
```

- [ ] **Step 6: Añadir los filtros a `static/js/panel.js`**

Justo antes de `function desdeHash()`:

```js
  // ---------- comparativa Titanium ----------
  var comparativa = document.querySelector('.view[data-view="comparativa"]');

  if (comparativa) {
    var filtroGama = "";
    var filtroEquiv = "";

    // `.bloque[data-gama]` y `.pastilla[data-gama]` por separado: las
    // pastillas del filtro llevan el mismo atributo que los bloques, y a
    // secas se mezclarian.
    var bloques = [].slice.call(comparativa.querySelectorAll(".bloque[data-gama]"));
    var pastillasGama = [].slice.call(comparativa.querySelectorAll(".pastilla[data-gama]"));
    var pastillasEquiv = [].slice.call(comparativa.querySelectorAll(".pastilla[data-equiv]"));

    function filtrarComparativa() {
      var total = 0;

      bloques.forEach(function (bloque) {
        var deLaGama = !filtroGama || bloque.getAttribute("data-gama") === filtroGama;
        var visibles = 0;

        [].slice.call(bloque.querySelectorAll("tbody tr")).forEach(function (fila) {
          var ok = deLaGama
            && (!filtroEquiv || fila.getAttribute("data-equiv") === filtroEquiv)
            && coincide(fila);
          fila.style.display = ok ? "" : "none";
          if (ok) visibles++;
        });

        // Un bloque sin filas visibles se esconde entero: la cabecera de una
        // gama vacia solo hace ruido.
        bloque.classList.toggle("u-oculto", visibles === 0);
        var cuenta = bloque.querySelector("[data-cuenta-pares]");
        if (cuenta) cuenta.textContent = numeroEs(visibles, 0);
        total += visibles;
      });

      var vacio = comparativa.querySelector("[data-vacio]");
      if (vacio && bloques.length) vacio.classList.toggle("is-on", total === 0);
    }

    comparativa.addEventListener("click", function (e) {
      var pastilla = e.target.closest(".pastilla");
      if (!pastilla) return;

      if (pastilla.hasAttribute("data-gama")) {
        filtroGama = pastilla.getAttribute("data-gama");
        pastillasGama.forEach(function (p) { p.classList.toggle("is-active", p === pastilla); });
      } else if (pastilla.hasAttribute("data-equiv")) {
        filtroEquiv = pastilla.getAttribute("data-equiv");
        pastillasEquiv.forEach(function (p) { p.classList.toggle("is-active", p === pastilla); });
      }
      filtrarComparativa();
    });

    registrar(comparativa, filtrarComparativa);
    filtrarComparativa();
  }
```

- [ ] **Step 7: Verificar en el navegador**

Con MySQL local poblado, o apuntando `.env` a una copia:

Run: `.venv\Scripts\python dashboard.py`

Abrir `http://localhost:5000/#comparativa` y comprobar, uno a uno:

1. La entrada del raíl ya no dice *Pronto* y navega.
2. Cuatro bloques con 17, 19, 19 y 15 pares.
3. Una fila con Δ positivo se ve **roja** y una con Δ negativo, **verde**.
4. Las 19 filas de *Advanced* muestran *Sin publicar en la tienda* y la columna Δ vacía.
5. `PSE-28568` y `SE-28981` muestran *Sin equivalente en Titanium*.
6. Filtrar por gama deja un solo bloque; filtrar por *Aproximada* deja solo esas filas y los contadores de cabecera de cada bloque cuadran con lo que se ve.
7. Escribir `femoral` en el buscador filtra la comparativa igual que filtra la bandeja.
8. El tema oscuro no rompe ningún color (botón de la esquina inferior izquierda).
9. Estrechar la ventana por debajo de 560px apila las tres columnas y la página **no** se desplaza en horizontal.
10. Recargar en `#comparativa` vuelve a la comparativa, no a la bandeja.

- [ ] **Step 8: Actualizar el README**

En *Estructura del codigo*, añadir a la entrada de `src/metrics.py` la mención a `build_titanium_comparison` y `titanium_metrics`, y añadir una entrada nueva:

```markdown
- `import_comparativa.py` — Convierte el Excel de emparejamiento que mantiene
  producto (`data/comparativa-titanium.xlsx`) en el SQL que puebla
  `titanium_pairs` (`data/titanium_pairs.sql`). Uso manual desde el equipo
  local: necesita `openpyxl`, que no esta en la imagen a proposito, y el
  contenedor de MySQL no publica el 3306. Al aplicar el SQL, este imprime que
  emparejamientos no resuelven contra el catalogo, que es lo que hay que
  devolverle a producto.
```

Y en la sección **6. Panel local**, tras el párrafo de las dos vistas:

```markdown
La tercera pantalla, **Comparativa Titanium**, enfrenta cada maquina nuestra
con su equivalente de Titanium Strength: nosotros a la izquierda, ellos a la
derecha y la diferencia en medio, agrupado en las cuatro gamas que enfrenta
producto. El emparejamiento lo decide producto y entra por
`import_comparativa.py`; los precios son los del ultimo crawl. Ojo al color:
rojo es que somos mas caros, que es la mala noticia.
```

Y en *Roadmap*, borrar la línea `- [ ] Alertas de stock basadas en detect_availability_change` sólo si el correo de la Task 4 la cubre — **no**: esa línea habla de todos los competidores, no solo de los emparejados. Se deja.

- [ ] **Step 9: Commit**

```bash
git add dashboard.py templates/dashboard.html static/css/panel.css static/js/panel.js README.md
git commit -m "Anadir la pantalla de comparativa contra Titanium"
```

---

## Task 4: El correo diario

**Files:**
- Create: `n8n/comparativa-titanium-email.js`
- Create: `n8n/comparativa-titanium-diaria.workflow.json`
- Modify: `n8n/README.md`

**Interfaces:**
- Consumes: la tabla `titanium_pairs` de la Task 1. No consume código Python: n8n consulta MySQL por su cuenta.
- Produces: el workflow *Comparativa Titanium · aviso diario*. Nada depende de él.

- [ ] **Step 1: Montar el workflow en la interfaz de n8n**

Entrar en `https://fitnesstech.duckdns.org/` y duplicar *Notificación semanal scrapper competencia* (menú del workflow → *Duplicate*). Renombrarlo **Comparativa Titanium · aviso diario**. Duplicar y no crear de cero para heredar las credenciales ya configuradas: `MySQL scrapper` y `SMTP account 2`.

Dejarlo **desactivado** hasta el paso 6.

- [ ] **Step 2: Cambiar el Schedule Trigger a diario a las 07:00**

En el nodo *Schedule Trigger*: *Trigger Interval* → **Days**, *Days Between Triggers* → 1, *Trigger at Hour* → **7am**, *Trigger at Minute* → 0.

Las 07:00 y no antes: el crawl arranca a las 03:00 y el del 2026-09-04 tardó doce minutos.

- [ ] **Step 3: Sustituir la consulta SQL**

En el nodo *Execute a SQL query*, reemplazar la query entera por:

```sql
SELECT 'precio' AS tipo, tp.gama, tp.ft_sku, tp.ft_title,
       tp.titanium_title, tp.titanium_url,
       pe.old_price AS ti_antes, pe.new_price AS ti_ahora,
       NULL AS antes_ok, NULL AS ahora_ok, NULL AS visto,
       pe.detected_at AS fecha,
       (SELECT s.price
          FROM products fp
          JOIN competitors fc ON fc.id = fp.competitor_id
          JOIN product_snapshots s ON s.product_id = fp.id
         WHERE fc.name = 'Fitness Tech'
           AND fp.sku = tp.ft_sku
           AND fp.status = 'active'
         ORDER BY s.captured_at DESC
         LIMIT 1) AS ft_precio
FROM price_events pe
JOIN products p ON p.id = pe.product_id
JOIN competitors c ON c.id = p.competitor_id AND c.name = 'Titanium Strength'
JOIN titanium_pairs tp ON tp.titanium_url = p.url
WHERE pe.detected_at >= NOW() - INTERVAL 24 HOUR

UNION ALL

SELECT 'stock', tp.gama, tp.ft_sku, tp.ft_title,
       tp.titanium_title, tp.titanium_url,
       NULL, NULL, ae.was_available, ae.now_available, NULL, ae.detected_at,
       NULL
FROM availability_events ae
JOIN products p ON p.id = ae.product_id
JOIN competitors c ON c.id = p.competitor_id AND c.name = 'Titanium Strength'
JOIN titanium_pairs tp ON tp.titanium_url = p.url
WHERE ae.detected_at >= NOW() - INTERVAL 24 HOUR

UNION ALL

SELECT 'baja', tp.gama, tp.ft_sku, tp.ft_title,
       tp.titanium_title, tp.titanium_url,
       NULL, NULL, NULL, NULL, p.last_seen, p.removed_at,
       NULL
FROM products p
JOIN competitors c ON c.id = p.competitor_id AND c.name = 'Titanium Strength'
JOIN titanium_pairs tp ON tp.titanium_url = p.url
WHERE p.status = 'removed' AND p.removed_at >= NOW() - INTERVAL 24 HOUR

ORDER BY gama, fecha DESC;
```

El `JOIN titanium_pairs` es lo que restringe el aviso a los 67 productos emparejados en vez de a los 918 del catálogo de Titanium. La subconsulta `ft_precio` es lo que permite decir cómo queda nuestra posición, que es todo el sentido de este correo.

- [ ] **Step 4: Escribir `n8n/comparativa-titanium-email.js`**

```js
const rows = $input.all().map(i => i.json);
if (!rows.length) return [{ json: { skip: true } }];

// ---------------------------------------------------------------------------
// El aviso diario de la comparativa contra Titanium. A diferencia del correo
// semanal, que enumera cambios, este cuenta el EFECTO del cambio sobre nuestra
// posicion: no "Titanium bajo el Remo Sentado a 1.595 EUR", sino "estabamos
// 296 EUR por debajo y ahora estamos 304 por encima". Eso es lo accionable
// para producto y la razon de que sea un correo aparte.
//
// Mismo sistema visual que el panel en tema claro. Los colores son los tokens
// de static/css/panel.css, literales: en un email no valen las variables CSS.
// Y ojo con el par rojo/verde: rojo es que quedamos PEOR (mas caros), verde
// que quedamos mejor. Va al reves de lo que sugiere el signo del numero.
// ---------------------------------------------------------------------------
const BG = '#f4f6f6';
const SURF = '#ffffff';
const SURF2 = '#fafbfb';
const INK = '#0c1112';
const INK3 = '#8e9a9e';
const LINE = '#e6eaeb';
const TEAL = '#00a7af';

const MAL_BG = '#fdecec', MAL_INK = '#b3261e';   // somos mas caros
const BIEN_BG = '#e7f6ee', BIEN_INK = '#127a4a'; // somos mas baratos
const STOCK_BG = '#fdf4e3', STOCK_INK = '#8d6100';
const GONE_BG = '#f2f0ee', GONE_INK = '#6b6259';

const SANS = "font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;";
const MO = "font-family:'IBM Plex Mono',Consolas,Menlo,monospace;";
const TITULO = SANS + 'font-style:italic;font-weight:bold;text-transform:uppercase;letter-spacing:-.01em;';
const ROTULO = SANS + 'font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:' + INK3 + ';';

const hoy = new Date();
const fd = n => n.toLocaleDateString('es-ES', { day: '2-digit', month: '2-digit', year: 'numeric' });

const esc = s => String(s == null ? '' : s)
  .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

// Formato espanol, igual que el filtro `eur` del panel.
const eur = v => {
  const n = Number(v);
  if (!isFinite(n)) return '&mdash;';
  const p = n.toFixed(2).split('.');
  p[0] = p[0].replace(/\B(?=(\d{3})+(?!\d))/g, '.');
  return p[0] + ',' + p[1] + ' &euro;';
};

const eurSigno = v => {
  const n = Number(v);
  if (!isFinite(n)) return '&mdash;';
  return (n > 0 ? '+' : n < 0 ? '-' : '') + eur(Math.abs(n));
};

const dispo = v => (Number(v) ? 'Disponible' : 'Agotado');

function pildora(bg, ink, texto) {
  let s = '<span style="' + SANS + 'display:inline-block;background:' + bg + ';color:' + ink + ';';
  s += 'font-size:12px;padding:3px 9px;border-radius:999px;white-space:nowrap;">' + texto + '</span>';
  return s;
}

function cifra(rotulo, valor) {
  let s = '<td width="33%" style="padding:0 4px;" valign="top">';
  s += '<table width="100%" cellpadding="0" cellspacing="0" border="0" style="background:' + SURF + ';';
  s += 'border:1px solid ' + LINE + ';border-radius:14px;"><tr><td style="padding:13px 14px;">';
  s += '<div style="' + SANS + 'font-size:11px;color:' + INK3 + ';">' + rotulo + '</div>';
  s += '<div style="' + MO + 'font-size:22px;color:' + INK + ';padding-top:7px;">' + valor + '</div>';
  s += '</td></tr></table></td>';
  return s;
}

// La posicion antes y despues del cambio de precio. `null` cuando no se puede
// calcular: la maquina nuestra no esta publicada (la gama Advanced entera) o
// falta algun precio.
function posicion(r) {
  const ft = Number(r.ft_precio);
  const antes = Number(r.ti_antes);
  const ahora = Number(r.ti_ahora);
  if (!isFinite(ft) || !isFinite(antes) || !isFinite(ahora)) return null;
  return { antes: ft - antes, ahora: ft - ahora };
}

const lado = d => (d > 0 ? 'por encima' : d < 0 ? 'por debajo' : 'al mismo precio');

// Etiqueta, colores y detalle de cada fila.
function pinta(r) {
  if (r.tipo === 'stock') {
    return {
      etiqueta: 'Stock', bg: STOCK_BG, ink: STOCK_INK, vuelco: false,
      detalle: dispo(r.antes_ok) + ' <span style="color:' + INK3 + ';">&rarr;</span> ' + dispo(r.ahora_ok),
    };
  }

  if (r.tipo === 'baja') {
    return {
      etiqueta: 'Baja', bg: GONE_BG, ink: GONE_INK, vuelco: false,
      detalle: 'Titanium la ha retirado de su catalogo',
    };
  }

  const sube = Number(r.ti_ahora) > Number(r.ti_antes);
  // Que Titanium SUBA es buena noticia para nosotros, y al reves.
  const bg = sube ? BIEN_BG : MAL_BG;
  const ink = sube ? BIEN_INK : MAL_INK;

  let d = 'Titanium: ' + eur(r.ti_antes) + ' <span style="color:' + INK3 + ';">&rarr;</span> ' + eur(r.ti_ahora);

  const p = posicion(r);
  let vuelco = false;
  if (p) {
    // El vuelco es la noticia: pasar de estar por debajo a estar por encima
    // (o al reves) cambia el argumento comercial, y una bajada que solo
    // recorta distancia, no.
    vuelco = (p.antes > 0) !== (p.ahora > 0);
    d += '<br>Estabamos <b>' + eur(Math.abs(p.antes)) + ' ' + lado(p.antes) + '</b>';
    d += ', ahora <b>' + eur(Math.abs(p.ahora)) + ' ' + lado(p.ahora) + '</b>';
  } else {
    d += '<br><span style="color:' + INK3 + ';">Nuestra maquina no esta publicada: sin posicion que comparar</span>';
  }

  return { etiqueta: sube ? 'Suben' : 'Bajan', bg: bg, ink: ink, detalle: d, vuelco: vuelco };
}

function fila(p, r, ultima) {
  let c = '<div style="' + SANS + 'font-size:14px;line-height:1.4;color:' + INK + ';">';
  c += esc(r.ft_title);
  if (p.vuelco) {
    c += ' &nbsp;' + pildora(MAL_BG, MAL_INK, 'Cambia la posicion');
  }
  c += '</div>';
  c += '<div style="' + MO + 'font-size:11px;color:' + INK3 + ';padding-top:5px;">' + esc(r.ft_sku);
  c += ' &nbsp;&middot;&nbsp; ' + (r.titanium_url
    ? '<a href="' + esc(r.titanium_url) + '" style="color:' + INK3 + ';">' + esc(r.titanium_title) + '</a>'
    : esc(r.titanium_title)) + '</div>';
  c += '<div style="' + MO + 'font-size:12.5px;color:' + p.ink + ';padding-top:4px;">' + p.detalle + '</div>';

  let s = '<tr><td style="padding:13px 0;' + (ultima ? '' : 'border-bottom:1px solid ' + LINE + ';') + '">';
  s += '<table width="100%" cellpadding="0" cellspacing="0" border="0"><tr>';
  s += '<td width="78" valign="top" style="padding-right:12px;">' + pildora(p.bg, p.ink, p.etiqueta) + '</td>';
  s += '<td valign="top">' + c + '</td>';
  s += '</tr></table></td></tr>';
  return s;
}

const g = {};
rows.forEach(r => { (g[r.gama] = g[r.gama] || []).push(r); });

const pintados = rows.map(pinta);
const totalPrecios = rows.filter(r => r.tipo === 'precio').length;
const totalVuelcos = pintados.filter(p => p.vuelco).length;
const totalOtros = rows.length - totalPrecios;

let h = '<div style="background:' + BG + ';padding:24px 12px;">';
h += '<table width="100%" cellpadding="0" cellspacing="0" border="0" align="center" ';
h += 'style="max-width:640px;margin:0 auto;background:' + SURF + ';border:1px solid ' + LINE + ';';
h += 'border-radius:14px;overflow:hidden;' + SANS + 'color:' + INK + ';">';

h += '<tr><td style="background:#000000;padding:16px 26px;">';
h += '<span style="' + TITULO + 'font-size:16px;color:#ffffff;">Fitness Tech</span>';
h += '<span style="' + MO + 'font-size:11px;color:rgba(255,255,255,.45);"> &nbsp;Comparativa Titanium</span>';
h += '</td></tr>';

h += '<tr><td style="padding:22px 26px 18px;border-bottom:1px solid ' + LINE + ';">';
h += '<div style="' + TITULO + 'font-size:19px;color:' + INK + ';">Titanium ha movido ficha</div>';
h += '<div style="' + SANS + 'font-size:13px;color:' + INK3 + ';padding-top:6px;">';
h += 'Ultimas 24 horas &nbsp;&middot;&nbsp; ' + fd(hoy) + '</div>';
h += '</td></tr>';

h += '<tr><td style="padding:18px 22px 4px;">';
h += '<table width="100%" cellpadding="0" cellspacing="0" border="0"><tr>';
h += cifra('Cambios de precio', totalPrecios);
h += cifra('Cambian la posicion', totalVuelcos);
h += cifra('Stock y bajas', totalOtros);
h += '</tr></table></td></tr>';

for (const gama in g) {
  h += '<tr><td style="padding:22px 26px 0;">';
  h += '<div style="border-top:1px solid ' + LINE + ';padding-top:20px;">';
  h += '<span style="display:inline-block;width:7px;height:7px;border-radius:50%;background:' + TEAL + ';"></span>';
  h += '<span style="' + SANS + 'font-size:15px;font-weight:bold;color:' + INK + ';">&nbsp; ' + esc(gama) + '</span>';
  h += '<span style="' + SANS + 'font-size:12px;color:' + INK3 + ';"> &nbsp;&middot;&nbsp; ' + g[gama].length + ' cambios</span>';
  h += '</div></td></tr>';

  h += '<tr><td style="padding:4px 26px 0;">';
  h += '<table width="100%" cellpadding="0" cellspacing="0" border="0">';
  g[gama].forEach((r, i) => { h += fila(pinta(r), r, i === g[gama].length - 1); });
  h += '</table></td></tr>';
}

h += '<tr><td style="padding:28px 26px 30px;text-align:center;">';
h += '<a href="https://fitnesstech.duckdns.org/competencia#comparativa" style="' + SANS + 'display:inline-block;';
h += 'background:' + TEAL + ';color:#ffffff;text-decoration:none;font-size:14px;font-weight:bold;';
h += 'padding:13px 28px;border-radius:10px;">Abrir la comparativa</a>';
h += '<div style="' + SANS + 'font-size:12px;color:' + INK3 + ';padding-top:11px;">';
h += 'Las cuatro gamas enfrentadas, maquina a maquina</div>';
h += '</td></tr>';

h += '<tr><td style="padding:15px 26px;border-top:1px solid ' + LINE + ';background:' + SURF2 + ';">';
h += '<span style="' + ROTULO + '">Emparejamiento de producto &middot; Enviado cada dia por n8n</span>';
h += '</td></tr>';

h += '</table></div>';

return [{
  json: {
    html: h,
    skip: false,
    total: rows.length,
    totalPrecios: totalPrecios,
    totalVuelcos: totalVuelcos,
    fecha: fd(hoy),
  },
}];
```

- [ ] **Step 5: Probar el correo sin enviarlo**

El `.js` es JavaScript corriente. Con las filas reales que devuelva la consulta del paso 3 (ejecutar solo ese nodo en n8n y copiar el JSON), montar un `$input` de mentira en local y abrir el `html` en el navegador:

```bash
node -e "
const rows = require('./filas.json');
global.\$input = { all: () => rows.map(r => ({ json: r })) };
const src = require('fs').readFileSync('n8n/comparativa-titanium-email.js','utf8');
const out = new Function('return (function(){' + src + '})()')();
require('fs').writeFileSync('/tmp/correo.html', out[0].json.html);
"
```

Comprobar en el navegador: que una bajada de Titanium sale en rojo, que el vuelco de posición se marca con su píldora, que un producto sin publicar dice *sin posicion que comparar* en vez de `NaN`, y que las cifras de cabecera cuadran.

Si no hay cambios reales de las últimas 24 h con los que probar, ampliar temporalmente el `INTERVAL 24 HOUR` a `INTERVAL 30 DAY` **solo para esta prueba** y devolverlo a 24 después.

- [ ] **Step 6: Pegar el JS en el nodo, apuntar el correo y activar**

En el nodo *Code in JavaScript*, pegar el contenido de `n8n/comparativa-titanium-email.js`.
En *Send an Email*: destinatario `tech@fitnesstech.es`, asunto `Comparativa Titanium — cambios de las últimas 24 h`, cuerpo `{{ $json.html }}` en HTML.
Comprobar que el nodo *If* sigue cortando con `{{ $json.skip }}` a `true`.

Activar el workflow con el interruptor de la interfaz.

- [ ] **Step 7: Exportar el workflow al repo**

```bash
ssh deploy@168.119.241.200 \
  'docker exec -e N8N_RUNNERS_BROKER_PORT=5699 n8n n8n export:workflow --all --output=/tmp/todos.json'
scp deploy@168.119.241.200:/tmp/todos.json /tmp/todos.json
```

Extraer del array el workflow *Comparativa Titanium · aviso diario* y guardarlo como `n8n/comparativa-titanium-diaria.workflow.json`, con el mismo formato que `notificacion-semanal.workflow.json` (un array de un elemento, indentado a 2 espacios). **Comprobar antes de commitear** que las credenciales aparecen por nombre (`"name": "MySQL scrapper"`, `"name": "SMTP account 2"`) y que no hay ningún valor de secreto en el fichero.

- [ ] **Step 8: Actualizar `n8n/README.md`**

Añadir tras la sección `## notificacion-semanal`:

```markdown
## `comparativa-titanium-diaria`

Cada mañana a las 07:00 mira si Titanium ha movido algo en las ~67 maquinas
que producto ha emparejado con las nuestras (`titanium_pairs`, que puebla
`import_comparativa.py`). Si no hay nada, no manda nada.

Lo que lo distingue del semanal es que no cuenta el cambio, cuenta el
**efecto sobre nuestra posicion**: no "Titanium bajo el Remo Sentado a
1.595 EUR", sino "estabamos 296 EUR por debajo, ahora estamos 304 por
encima". Ese vuelco es lo accionable para producto, y es la razon de que sea
un correo aparte y no un bloque mas en el de los lunes.

Las 07:00 y no antes: el crawl arranca a las 03:00 y ha llegado a tardar
doce minutos.

```
Schedule Trigger (diario, 07:00)
  -> Execute a SQL query   (precio, stock y bajas de 24 h, restringidos por
  |                         JOIN a titanium_pairs; trae ademas nuestro precio
  |                         vigente por subconsulta, para calcular la posicion)
  -> Code in JavaScript    (arma el HTML del email)
  -> If                    (corta si no hay nada que contar)
  -> Send an Email
```

| Fichero | Que es |
| --- | --- |
| `comparativa-titanium-email.js` | El codigo del nodo *Code in JavaScript* |
| `comparativa-titanium-diaria.workflow.json` | El workflow entero, tal como lo exporta n8n |

Ojo al rojo/verde, que aqui significa otra cosa que en el semanal: rojo es
que **nosotros** quedamos peor (mas caros), asi que una **subida** de precio
de Titanium se pinta en verde.
```

Y en el encabezado del fichero, donde dice *«lo que hay aqui es una copia versionada de ese montaje»*, cambiar el singular por el plural para que cubra los dos workflows.

- [ ] **Step 9: Commit**

```bash
git add n8n/
git commit -m "Avisar cada dia cuando Titanium mueve un precio emparejado"
```

---

## Task 5: Desplegar

**Files:** ninguno. Es la puesta en producción de lo anterior.

- [ ] **Step 1: Comprobar que la batería pasa entera antes de subir nada**

Run: `.venv\Scripts\python -m pytest -v`
Expected: PASS, sin fallos ni errores. Si algo falla, **no seguir**.

- [ ] **Step 2: Empujar y desplegar**

```bash
git push
ssh deploy@168.119.241.200
cd /home/deploy/scraper-competidores && git pull --ff-only
docker compose up -d --build
```

El código va dentro de la imagen (`COPY . .`), así que reiniciar no basta: hay que reconstruir. Tarda ~1 min, con pip y Playwright cacheados.

- [ ] **Step 3: Comprobar que el dashboard responde**

```bash
docker exec scraper-competidores-dashboard-1 python -c \
  "import urllib.request; print(len(urllib.request.urlopen('http://127.0.0.1:5000/').read()))"
```

Expected: un número claramente mayor que antes del cambio (la comparativa añade 70 filas de marcado). Si da excepción, mirar `docker compose logs dashboard`.

- [ ] **Step 4: Comprobar la pantalla desde fuera**

Abrir `https://fitnesstech.duckdns.org/competencia#comparativa` con las credenciales de la auth básica. Un **401** sin credenciales confirma que el router de Traefik sigue bien; un **404** significaría que el enrutado se ha roto.

Repasar los diez puntos del Step 7 de la Task 3, ahora contra los datos reales.

- [ ] **Step 5: Dejar constancia de lo que producto tiene que corregir**

Del informe del Step 9 de la Task 1, pasar a producto:

- `SE-28780` está publicado como `PSE-28780`. Es un error de tecleo en su Excel.
- Los 19 SKUs de la gama Advanced (`SE-28969`…`SE-28987`) no están publicados en la tienda. Confirmar si es que la gama aún no ha salido o si los SKUs del Excel son internos y no coinciden con los de la web.

- [ ] **Step 6: Verificar el correo al día siguiente**

En n8n, *Executions* del workflow *Comparativa Titanium · aviso diario*. Comprobar que disparó a las 07:00. Si no hubo cambios, el `If` habrá cortado y no se manda nada — eso es correcto, no un fallo.

Si disparó pero no llegó el correo, revisar que el workflow estaba **activo**: n8n registra los triggers al arrancar, y un import o un cambio reciente puede dejarlo registrado con la versión anterior. Apagar y encender el interruptor desde la interfaz lo re-registra.

---

## Self-Review

**Cobertura del spec:**

| Sección del spec | Task |
| --- | --- |
| 1. `titanium_pairs` | Task 1, steps 1 y 9 |
| 2. `import_comparativa.py` + informe | Task 1, steps 2-5 y 8 |
| 3. `build_titanium_comparison` / `titanium_metrics` / `get_titanium_pairs` | Task 2 completa; Task 1 step 6 |
| 4. Pantalla (raíl, cifras, filtros, filas, responsive) | Task 3 completa |
| 5. Correo diario (schedule, SQL, JS, ficheros, despliegue) | Task 4 completa |
| Manejo de errores | Task 1 steps 2/4 (Excel), Task 3 step 4 (tabla vacía), Task 4 step 6 (`If`) |
| Pruebas | Task 1 steps 2-5, Task 2 steps 1-4, Task 4 step 5 |
| Fuera de alcance | Nada de las tasks lo toca |

**Consistencia de nombres:** `leer_pares`, `generar_sql`, `get_titanium_pairs`, `build_titanium_comparison`, `titanium_metrics`, y las claves `estado`/`delta`/`delta_pct`/`ft_price`/`titanium_price`/`titanium_available` se usan igual en las tasks 1, 2 y 3. Los `data-gama`, `data-equiv`, `data-cuenta-pares` y `data-vacio` de la plantilla (Task 3 step 4) son los mismos que busca el JS (step 6). Las columnas del SQL de n8n (`tipo`, `gama`, `ft_sku`, `ft_title`, `titanium_title`, `titanium_url`, `ti_antes`, `ti_ahora`, `antes_ok`, `ahora_ok`, `visto`, `fecha`, `ft_precio`) son las que lee el JS del correo.

**Riesgo conocido:** el `estado` `fuera_catalogo` no se puede provocar a voluntad en producción — depende de que Titanium retire una máquina. Queda cubierto por el test del Step 1 de la Task 2 y se verá en la pantalla el día que ocurra.
