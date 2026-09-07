# Comparativa Titanium: pantalla y aviso diario

Fecha: 2026-09-07

## Contexto

El panel vigila cuatro escaparates (Fitness Tech ES/FR/PT y Titanium
Strength) y responde a una pregunta: *qué se movió anoche*. No responde a
la que se hace producto: *dónde estamos por encima y dónde por debajo de
Titanium, máquina por máquina*.

El departamento de producto ha preparado esa correspondencia a mano en
`Comparativa PVP Fitness Tech vs Titanium Strength.xlsx`: cuatro hojas, una
por gama enfrentada (*Compact vs Elite*, *Pro vs Black*, *Advanced vs Black
RX*, *Pro Tech vs Genesis*), 70 filas en total, cada una emparejando una
máquina nuestra con su equivalente en Titanium.

El rediseño del panel del 2026-09-04 ya reservó el hueco: en el raíl hay una
sección *Análisis* con la entrada `Comparativa Titanium` pintada inerte y
una píldora *Pronto* (`templates/dashboard.html:147-155`). Este documento la
convierte en pantalla real y añade el correo que la acompaña.

### Lo que se comprobó antes de diseñar

Contra la base de datos del VPS, el 2026-09-07:

- **Las 67 URLs de Titanium del Excel existen en `products` con URL
  exacta.** El emparejamiento del lado del competidor es fiable al 100 % y
  no necesita coincidencia aproximada por título.
- **50 de los 70 SKUs nuestros existen; 20 no.** Uno es un error de tecleo
  (`SE-28780` está publicado como `PSE-28780`) y los otros 19 son la gama
  **Advanced** entera (`SE-28969`…`SE-28987`), que todavía no está en la
  tienda.
- Hay dos filas *Sin equivalente* (`PSE-28568` y `SE-28981`), sin producto
  ni URL de Titanium.
- Dos filas distintas (`SE-28972` y `SE-28974`) apuntan a la misma URL de
  Titanium. `titanium_url` **no** es único; `ft_sku` sí.

### Decisiones tomadas con el usuario

- **Los precios del Excel no valen.** Son una foto del día en que producto
  lo montó. El Excel aporta **solo el emparejamiento**; todos los precios,
  la disponibilidad y las diferencias salen vivos del scrapper y se
  calculan en el momento.
- **El lado nuestro es Fitness Tech ES**, que es contra quien compite
  `titaniumstrength.es`. FR y PT quedan fuera.
- **El emparejamiento entra por tabla e importador**, no por una pantalla de
  subida ni por un fichero leído al arrancar.
- **El aviso es diario y solo si hay movimiento**, a `tech@fitnesstech.es`.
  Un correo aparte del semanal que ya existe.
- **La pantalla son filas enfrentadas agrupadas por gama**, con nosotros a
  la izquierda, Titanium a la derecha y la diferencia en el centro.

## Arquitectura

Cuatro piezas, cada una con una responsabilidad y una frontera clara:

```
Excel de producto
      │  import_comparativa.py  (a mano, cuando producto revise)
      ▼
MySQL: titanium_pairs ──┐
                        ├─► src/metrics.py: build_titanium_comparison()  ─► pantalla
MySQL: products +       │        (función pura, sin BD ni Flask)
       product_snapshots┘
                        └─► n8n: consulta SQL propia ─► correo diario
```

La pantalla y el correo **no comparten código**: leen las mismas tablas por
su cuenta. Es la misma separación que ya rige entre el panel y el correo
semanal, y es deliberada — que a quién se avisa y con qué aspecto se cambie
desde n8n sin tocar este repo ni redesplegar.

## 1. Datos: `titanium_pairs`

Migración `migrations/007_titanium_pairs.sql`:

```sql
USE competitor_monitor;

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
  UNIQUE KEY unique_ft_sku (ft_sku),
  INDEX idx_gama (gama),
  INDEX idx_titanium_url (titanium_url)
);
```

- `gama` es el nombre de la hoja del Excel tal cual (*Compact vs Elite*).
- `orden` es la posición de la fila dentro de su hoja, para que la pantalla
  respete el orden que le dio producto.
- `equivalencia` toma los tres valores del Excel: `Directa`, `Aproximada`,
  `Sin equivalente`.
- `titanium_url` **no** es único: dos máquinas nuestras pueden competir
  contra la misma suya.
- No hay clave foránea a `products`. El emparejamiento es un juicio de
  producto y debe sobrevivir a que una máquina desaparezca del catálogo de
  Titanium; esa desaparición es precisamente uno de los avisos.

Las migraciones se aplican solas en el arranque inicial de MySQL
(`/docker-entrypoint-initdb.d/`), pero la base del VPS ya está creada, así
que esta hay que aplicarla a mano igual que se hizo con la `006`.

## 2. Importador: `import_comparativa.py`

Script en la raíz, junto a los `export_excel*.py` que ya hay. Lee el `.xlsx`
con `openpyxl` y hace **reemplazo completo dentro de una transacción**:
`DELETE FROM titanium_pairs` seguido de los `INSERT`. Sin lógica de
diferencias ni de borrado que mantener, y si producto quita una fila del
Excel, desaparece también aquí.

El fichero se versiona en `data/comparativa-titanium.xlsx`, y el script lo
toma por defecto de ahí, admitiendo otra ruta como argumento.

Reglas de lectura:

- Una hoja = una gama. El nombre de la hoja es el valor de `gama`.
- La primera fila es la cabecera y se descarta. Las columnas se localizan
  **por su rótulo**, no por posición, para que añadir una columna al Excel no
  rompa el importador.
- Se leen: *SKU Fitness Tech*, *Máquina Fitness Tech*, *Equivalencia*,
  *Máquina Titanium*, *URL Titanium*, *Observaciones*. Las columnas de
  precio y diferencia del Excel **se ignoran a propósito**.
- Una fila sin SKU se salta en silencio (filas en blanco al final de la
  hoja). Una fila con SKU duplicado **aborta la importación** con el SKU y la
  hoja donde aparece: es un error de producto y hay que verlo, no
  resolverlo por él.

Al terminar, el script **informa de lo que no cuadra** en vez de callárselo,
consultando `products`:

```
Importados 70 pares en 4 gamas.

URLs de Titanium que no existen en la BD: ninguna.

SKUs nuestros sin publicar en Fitness Tech ES (20):
  SE-28780  Extensión de Cuádriceps y Femoral · Dual   ¿PSE-28780?
  SE-28969  Press de Pecho
  ...
```

La pista `¿PSE-28780?` sale de buscar el mismo número con otro prefijo. Es
**solo un aviso**: el importador no corrige el dato. Corregirlo en silencio
escondería un error que producto debe arreglar en su fichero, y la próxima
importación volvería a traerlo.

## 3. Cálculo: `build_titanium_comparison()`

Función pura en `src/metrics.py`, al lado de `build_change_feed` y con la
misma disciplina: recibe filas, devuelve estructuras, ni BD ni Flask, y
queda cubierta por `tests/test_metrics.py`.

Son **dos** funciones, con el mismo reparto que ya tienen `build_targets` y
`global_metrics`: una arma la estructura, la otra la resume.

```python
def build_titanium_comparison(pairs: list[dict], catalog: list[dict]) -> list[dict]:
    """Los pares de producto resueltos contra el catálogo vigente, agrupados
    por gama."""

def titanium_metrics(gamas: list[dict], changes_week: list[dict]) -> dict:
    """Las cinco cifras de cabecera de la comparativa."""
```

`catalog` es lo que devuelve `Database.get_latest_snapshots()` y
`changes_week` es el feed de siete días que ya construye `build_change_feed`.
`dashboard.index()` **ya calcula ambos** para las tiendas. La pantalla nueva
no añade ni una consulta más allá de `get_titanium_pairs()`.

Resolución:

- **Lado Titanium**, por `url` exacta contra las filas cuyo `competitor` es
  `Titanium Strength`.
- **Lado nuestro**, por `sku` exacto contra las filas cuyo `competitor` es
  `Fitness Tech`.
- `get_latest_snapshots()` excluye los productos `removed`, así que una URL
  que no aparezca significa que Titanium la retiró del catálogo.

Cada par sale con un `estado` que la plantilla usa para decidir qué pinta:

| `estado` | Qué pasó | Cómo se pinta |
| --- | --- | --- |
| `ok` | Ambos lados resueltos | Fila completa con Δ |
| `sin_equivalente` | Producto no le encontró rival | Lado Titanium vacío |
| `sin_publicar` | Nuestro SKU no está en la tienda | Lado nuestro vacío |
| `fuera_catalogo` | La URL de Titanium ya no está vigente | Lado Titanium en gris |

**Δ = nuestro PVP − PVP Titanium**, y el porcentaje sobre el precio de
Titanium. Solo se calcula en `ok`; en el resto es `None` y la columna
central queda vacía.

**El signo y el color.** Δ positivo (somos más caros) va en **rojo**, Δ
negativo (somos más baratos) en **verde**. Es la convención del panel y del
correo semanal, y va al revés de lo que uno esperaría de una cifra: rojo
es mala noticia para nosotros, no número negativo.

`Database.get_titanium_pairs()` en `src/db.py` es un `SELECT * FROM
titanium_pairs ORDER BY gama, orden`, sin más.

## 4. Pantalla

La entrada del raíl deja de ser un letrero: `navitem--pronto` pasa a ser un
`<a class="navitem" href="#comparativa" data-view="comparativa">` con el
mismo icono de barras. Las reglas `.navitem--pronto` y `.pill-pronto` de
`static/css/panel.css` se **borran**: no quedan otros letreros pendientes, y
si algún día hace falta uno, está en el historial de git.

La vista es una `<section class="view" data-view="comparativa">` más, de las
que ya maneja `static/js/panel.js` por el hash de la URL. No hay ruta nueva
en Flask: `index()` pasa un `comparativa` más al contexto.

**Cabecera.** Cinco cifras en el bloque `.cifras` que ya existe:

| Rótulo | Qué cuenta |
| --- | --- |
| Pares vigilados | Filas con ambos lados resueltos |
| Somos más caros | Pares con Δ > 0 |
| Somos más baratos | Pares con Δ < 0 |
| Diferencia mediana | Mediana del Δ % de los pares resueltos |
| Cambios 7 días | Eventos de Titanium en productos emparejados |

Mediana y no media, por el mismo motivo que en `target_metrics`: cuatro
prensas de pierna desplazarían la media hasta hacerla inútil.

La última cifra sale de filtrar `changes_week` por `store == "Titanium
Strength"` y por que su `url` esté entre las emparejadas — el feed ya lleva
`url` en las cuatro clases de evento (`src/metrics.py:153`). Ninguna consulta
nueva.

**Filtros.** Dos grupos de `.pastilla` sobre el patrón de la vista de
tienda: por gama (Todas + las cuatro) y por equivalencia (Todas, Directa,
Aproximada, Sin equivalente). Filtran en cliente sobre lo ya pintado, como
todo lo demás del panel. El buscador global sigue funcionando: cada fila
lleva su `data-busca` con SKU y ambos títulos.

**Las filas.** Cuatro bloques `.bloque`, uno por gama, con su cabecera
*Compact Series vs Elite Series · 17 pares*. Dentro, una tabla de tres
columnas:

```
 FITNESS TECH                │   Δ    │  TITANIUM STRENGTH
────────────────────────────┼────────┼──────────────────────────
 Femoral Sentado            │ +204 € │  Curl Femoral Sentado Elite
 SE-28774                   │        │  ● Disponible · Directa
 1.599,00 €                 │ +14,6% │  1.395,00 €
────────────────────────────┼────────┼──────────────────────────
 Femoral Tumbado            │ −296 € │  Femoral Tumbado Elite
 SE-28775                   │        │  ○ Agotado · Directa
 1.599,00 €                 │ −15,6% │  1.895,00 €
```

Los títulos de ambos lados enlazan a la ficha del producto en pestaña
nueva, como en la bandeja de cambios. Las *Observaciones* de producto van en
un `title` sobre la etiqueta de equivalencia, para no ensuciar la fila con
texto que casi nunca se lee.

En pantallas estrechas las tres columnas se apilan y la Δ queda entre
ambas máquinas, que es donde se entiende.

## 5. Correo diario

Workflow nuevo en n8n, **independiente** del semanal, con su misma forma:

```
Schedule Trigger (diario, 07:00 Europe/Madrid)
  -> Execute a SQL query   (cambios de 24 h, restringidos por JOIN a titanium_pairs)
  -> Code in JavaScript    (arma el HTML del email)
  -> If                    (corta si no hay nada)
  -> Send an Email         -> tech@fitnesstech.es
```

Las 07:00 dan margen sobrado sobre el crawl de las 03:00 (el del 2026-09-04
tardó doce minutos).

**La consulta.** Tres ramas `UNION ALL` sobre `price_events`,
`availability_events` y los `products` dados de baja, todas con `JOIN
titanium_pairs tp ON tp.titanium_url = p.url` y `WHERE detected_at >= NOW() -
INTERVAL 24 HOUR`. Ese `JOIN` es lo que restringe el aviso a los 67 productos
de Titanium emparejados, en vez de a los 918 de su catálogo. Cada fila trae además, por subconsulta, **el precio
vigente de nuestra máquina** (por `tp.ft_sku` contra Fitness Tech ES), que es
lo que permite lo siguiente.

**Lo que lo hace distinto del semanal:** no cuenta el cambio, cuenta el
**efecto sobre nuestra posición**. No *"Titanium bajó el Remo Sentado a
1.595 €"*, sino:

> **Remo Sentado** · Pro vs Black
> Titanium: 2.195,00 € → 1.595,00 € (−27,3 %)
> Estábamos **296 € por debajo**, ahora estamos **304 € por encima**

Ese vuelco de posición es lo accionable para producto, y es la razón de
tener un correo aparte en vez de un bloque más en el de los lunes. Los
cambios que **no** dan la vuelta a la posición se listan igual, pero sin
destacar.

Para los cambios de stock y las bajas de catálogo no hay posición que
recalcular: se listan con su píldora y su detalle, como en el semanal.

**Aspecto.** El mismo sistema visual que el correo semanal: banda negra de
marca, píldoras de tipo, cifras en monoespaciada, colores literales de
`static/css/panel.css` (en un email no valen las variables CSS) y caída a
Helvetica y a la monoespaciada del sistema. Rojo y verde con el mismo
sentido que en la pantalla: rojo es que quedamos peor.

**Ficheros**, siguiendo lo que ya hay en `n8n/`:

- `n8n/comparativa-titanium-diaria.workflow.json` — el workflow completo,
  tal como lo exporta n8n, con las credenciales **por nombre**.
- `n8n/comparativa-titanium-email.js` — el código del nodo *Code*, que es lo
  único que se toca a menudo.

**Despliegue**, por el camino documentado en `n8n/README.md`: `scp` +
`docker cp` + `import:workflow` con `N8N_RUNNERS_BROKER_PORT=5699`. Y las dos
cosas que muerden después: el import **desactiva** el workflow, y n8n
registra los triggers al arrancar, así que hay que apagar y encender el
interruptor desde la interfaz para que lo re-registre.

## Manejo de errores

- **Importador con Excel ilegible o columna que falta:** aborta nombrando
  la hoja y el rótulo que no encuentra, sin tocar la tabla. La transacción
  garantiza que o entra todo o no entra nada.
- **SKU duplicado en el Excel:** aborta indicando SKU y hoja.
- **Emparejamientos que no resuelven:** no son un error. Se informan al
  importar y la pantalla los pinta con su `estado`, porque son información
  para producto, no un fallo del sistema.
- **Tabla `titanium_pairs` vacía** (aún no importada): la vista se pinta con
  un `.vacio` que dice cómo poblarla. El resto del panel no se entera.
- **Correo sin cambios:** el nodo `If` corta y no se envía nada, igual que
  el semanal.

## Pruebas

- `tests/test_metrics.py` — `build_titanium_comparison` con catálogos en
  memoria: los cuatro `estado`, el signo de Δ y las dos filas que comparten
  URL de Titanium. Y `titanium_metrics`: los recuentos de más caros y más
  baratos, la mediana con lista vacía, y que los cambios de otras tiendas y
  los de productos no emparejados no entran en la cifra de 7 días.
- `tests/test_import_comparativa.py` — lectura del `.xlsx`: columnas por
  rótulo, filas en blanco, SKU duplicado, columnas de precio ignoradas.
  Sobre un fichero mínimo generado en el test, no sobre el de producción.
- Sin tests de integración contra MySQL, que sigue siendo la carencia
  conocida del repo y no se aborda aquí.
- El correo se prueba como el semanal: el `.js` es JavaScript corriente, se
  le pasa un `$input` de mentira con filas reales de MySQL y se abre en el
  navegador el `html` que devuelve, sin mandar nada a nadie.

## Fuera de alcance

- Pantalla de subida del Excel. Producto revisa esto cada pocos meses; una
  ruta de subida convertiría un panel de solo lectura en uno que escribe, y
  no compensa todavía.
- Comparativas contra Fitness Tech FR y PT.
- Histórico de la diferencia (cómo evolucionó el Δ de un par en el tiempo).
  Los datos están en `product_snapshots` para hacerlo el día que se pida.
- Corregir en el importador el prefijo `SE-`/`PSE-`. Se avisa; lo arregla
  producto en su fichero.
