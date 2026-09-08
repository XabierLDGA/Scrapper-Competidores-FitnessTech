# Competitor Monitor (MySQL)

Sistema de monitorizacion automatica de competidores en fitnesstech usando MySQL.

Se puede correr en local con Python + venv (para desarrollo) o con Docker
Compose (para desplegar en un VPS o servidor propio, ver
[Despliegue con Docker](#despliegue-con-docker)).

## Instalacion local

### 1. Python y dependencias

Requiere Python 3.11+. En Windows, si `python` no se reconoce en la terminal,
instala Python desde https://www.python.org/downloads/ (marca "Add to PATH"
durante la instalacion) o con `winget install Python.Python.3.11`.

```bash
python -m venv .venv
.venv\Scripts\activate      # PowerShell / cmd
pip install -r requirements.txt
```

Titanium Strength (`titaniumstrength.es`) está detrás de Cloudflare y
bloquea las peticiones HTTP normales por huella TLS, así que ese competidor
se descarga con un navegador Chromium real (Playwright) en vez de `httpx`.
No hay que configurarlo: el crawler prueba primero la vía barata y solo
abre el navegador con las tiendas que lo necesitan (Binom, que también es
Magento, no lo necesita). Tras instalar las dependencias, descarga el
binario del navegador una vez:

```bash
playwright install chromium
```

Este paso descarga ~115MB y solo hace falta ejecutarlo una vez por máquina.

### 2. MySQL

Necesitas una instancia MySQL 8.0+ corriendo en local (XAMPP, MySQL Installer,
Docker, etc.).

```bash
mysql -h localhost -u root -p < migrations/001_initial_schema.sql
```

### 3. Variables de entorno

```bash
copy .env.example .env
```

Edita `.env` con tus credenciales de MySQL.

### 4. Anadir competidores

Todavia no hay UI para esto; se hace por script. Crea un fichero temporal
(por ejemplo `add_competitor.py`) o usa una consola interactiva:

```python
from dotenv import load_dotenv
load_dotenv()
import os
from src.db import Database

db = Database(
    host=os.getenv("DB_HOST", "localhost"),
    user=os.getenv("DB_USER", "root"),
    password=os.getenv("DB_PASSWORD", ""),
    database=os.getenv("DB_NAME", "competitor_monitor"),
)

competitor_id = db.add_competitor(
    name="Garmin",
    website_url="https://garmin.com",
    product_api_url="https://garmin.com/products.json",  # opcional, solo si usa Shopify
    country="ES",
    platform="magento",  # solo si es Magento; None para Shopify/HTML
)
print(f"Competidor anadido: ID {competitor_id}")
```

**Al dar de alta uno nuevo, retrasa el `first_seen` de su primera tanda**
fuera de la ventana de 7 dias:

```sql
UPDATE products SET first_seen = CURDATE() - INTERVAL 8 DAY
WHERE competitor_id = <id> AND first_seen = CURDATE();
```

Su catalogo entero entra el mismo dia, y tanto el panel como el correo
semanal de n8n miden las altas por `first_seen`: sin esto, el lunes
siguiente el correo sale con cientos de "productos nuevos" que no son
novedades, es que empezamos a mirar (a Titanium le paso con 866 el
2026-08-05). Con Binom fueron ~700.

### 5. Ejecutar

```bash
python main.py
```

### 6. Panel local

Para ver competidores, catalogo actual y cambios de precio sin escribir SQL:

```bash
python dashboard.py
```

Abre http://localhost:5000 en el navegador. Es un servidor de desarrollo
Flask (`debug=True`) pensado solo para uso local, no para producción — lee
directamente de MySQL en cada recarga de pagina, no tiene autenticacion.

El panel es una pagina unica con dos vistas. La de **cambios** es la
portada: todo lo que se ha movido en las cinco tiendas en las ultimas 24
horas —altas, bajas, subidas y bajadas de precio y entradas y salidas de
stock— en una sola bandeja ordenada de mas reciente a mas antiguo, con
filtros por tienda y por tipo. La vista **por tienda** tiene dos pestanas,
catalogo y cambios de 24 horas, con sus propios subfiltros.

La tercera pantalla, **Comparativa Titanium**, enfrenta cada maquina nuestra
con su equivalente de Titanium Strength: nosotros a la izquierda, ellos a la
derecha y la diferencia en medio, agrupado en las cuatro gamas que enfrenta
producto. El emparejamiento lo decide producto y entra por
`import_comparativa.py`; los precios son los del ultimo crawl. Ojo al color,
que aqui va por el signo de la cifra y no por el semaforo del resto del
panel: verde es diferencia positiva, es decir, que somos mas caros.

La vista viaja en el hash de la URL (`#tienda/titanium-strength`), asi que
recargar no te devuelve al principio. `/` enfoca el buscador y `Esc` lo
limpia. El boton de la esquina inferior izquierda alterna entre tema claro
y oscuro, y la eleccion se recuerda en el navegador.

Todo se renderiza en el servidor: el JavaScript solo decide que vista se ve
y filtra lo ya pintado. Los agregados (disponibilidad, promociones, mediana
de precio y el feed de cambios) viven en `src/metrics.py` como funciones
puras, cubiertas por `tests/test_metrics.py`.

### 7. Tests

```bash
pytest -v
```

Los tests de `crawler`, `normalizer` y `detector` no requieren MySQL (usan
mocks/datos en memoria). No hay tests de integracion contra una BD real
todavia; si el proyecto crece, conviene anadir un contenedor MySQL de test
(docker-compose o `pytest` con una fixture de BD efimera).

## Despliegue con Docker

Para levantar todo el sistema (MySQL + dashboard + crawl diario) con un
solo comando, en tu maquina o en un VPS:

```bash
copy .env.example .env    # edita .env con tus credenciales
docker compose up -d
```

Esto levanta 3 servicios:

- **`mysql`**: MySQL 8.0 con un volumen persistente. Las migraciones de
  `migrations/*.sql` se aplican solas la primera vez que arranca (MySQL
  ejecuta automaticamente los `.sql` que encuentra en
  `/docker-entrypoint-initdb.d/`, en orden alfabetico — por eso estan
  numeradas 001, 002, etc). Si ya tenias datos de una instalacion local
  previa, esta es una base de datos nueva y vacia: no migra datos
  existentes automaticamente.
- **`dashboard`**: el dashboard servido con `waitress` (servidor de
  produccion, no el modo `debug` de Flask) en el puerto 5000
  (`http://localhost:5000` o `http://<ip-del-vps>:5000`). **De momento no
  tiene autenticacion ni restriccion de red** — es una decision consciente
  para esta primera version; si vas a exponerlo en un VPS con IP publica,
  considera ponerlo detras de una VPN (ej. Tailscale) o restringir el
  puerto por firewall antes de abrirlo a internet.
- **`crawler`**: ejecuta el crawl completo una vez al dia (06:00 UTC, ver
  `scheduler.py`) sin depender de cron del host ni de GitHub Actions — por
  eso ya no existe `daily_crawl.yml`, este servicio lo sustituye y no
  necesita que la BD sea alcanzable desde internet (todo corre en la misma
  red interna de Docker).

Para dar de alta competidores, la forma mas simple es entrar al contenedor
del crawler y usar el mismo snippet de Python de la seccion
[Anadir competidores](#4-anadir-competidores) (con `DB_HOST=mysql`, ya
puesto por `docker-compose.yml`):

```bash
docker compose exec crawler python
```

Para ver logs (por ejemplo, cuanto falta para el proximo crawl):

```bash
docker compose logs -f crawler
```

Para parar todo (`-v` tambien borra el volumen de MySQL, con lo que se
pierden los datos):

```bash
docker compose down       # conserva los datos
docker compose down -v    # borra tambien la base de datos
```

## CI/CD

- **`.github/workflows/tests.yml`**: corre `pytest` en cada push/PR. No
  necesita secrets ni acceso a MySQL.

## Estructura del codigo

- `src/crawler.py` — Descarga datos, con tres caminos segun `platform`
  (elegido en `crawl_competitor_products` de `main.py`): Shopify
  `/products.json` (con fallback a scraping HTML generico si no hay
  `product_api_url`), Magento recorriendo sus categorias
  (`crawl_magento_categories`), o el fallback HTML generico. Para
  Shopify tambien cruza las colecciones de la tienda cuyo titulo sugiere
  una linea de producto ("series"/"select") para rellenar el campo `series`
  de cada producto — no sale en el dashboard, pero si en los exports Excel.
  El camino Magento se adapta solo a cada tienda en dos cosas: usa `httpx`
  y solo abre el navegador si la tienda rechaza las peticiones normales
  (Titanium si, Binom no), y pide las paginas con el mayor tamano que
  ofrezca el selector de la propia tienda (`all` en Binom, 48 en Titanium),
  que es lo que hace que anadir Binom cueste ~80 peticiones y no ~200.
- `src/normalizer.py` — Convierte productos crawleados a un formato comun y
  descarta los que no tienen datos minimos (id, titulo, precio >= 0).
- `src/detector.py` — Unica fuente de verdad para "es nuevo", "cambio de
  precio >= umbral" y "cambio de disponibilidad". El umbral de precio (5%
  por defecto) se decide aqui una sola vez; nada mas lo recalcula.
- `src/db.py` — Acceso a MySQL. Convierte los `Decimal` que devuelve
  `mysql-connector` para columnas `DECIMAL` a `float` en la frontera con la
  BD, para que el resto del pipeline no tenga que lidiar con ese tipo.
- `main.py` — Orquestacion: crawlea cada competidor, persiste snapshots,
  detecta cambios y, al final, cuenta lo que ha cambiado leyendo el estado
  real de la BD (`get_new_products` / `get_unnotified_events`), no listas
  en memoria — asi el recuento es correcto aunque el crawl falle a mitad
  para algun competidor. El crawler **no avisa a nadie**: quien manda el
  correo es n8n, ver [Avisos](#avisos).
- `dashboard.py` + `templates/dashboard.html` + `static/css/panel.css` +
  `static/js/panel.js` — Panel web de solo lectura sobre MySQL. `dashboard.py`
  es una capa fina de Flask: consulta, delega el calculo en `src/metrics.py`
  y renderiza. Sin autenticacion propia (en el VPS la pone Traefik). Local:
  `python dashboard.py` (servidor de desarrollo Flask, `debug=True`).
  Docker: se sirve con `waitress` (ver
  [Despliegue con Docker](#despliegue-con-docker)).
  > Ojo al iterar en local con `waitress`: Jinja cachea la plantilla al
  > arrancar, asi que los cambios en `dashboard.html` no se ven hasta
  > reiniciar el servidor (los de CSS/JS si, son ficheros estaticos).
- `src/metrics.py` — Agregados derivados del panel (disponibilidad, % con
  precio rebajado, mediana de precio), `build_change_feed`, que aplana los
  cuatro tipos de evento de todas las tiendas en la bandeja unica de la
  portada, y `build_titanium_comparison` / `titanium_metrics`, que resuelven
  el emparejamiento de producto contra el catalogo vigente para la pantalla
  de comparativa. Funciones puras sobre las filas que devuelve `Database`: ni BD
  ni Flask, para que el calculo quede cubierto por tests.
- `import_comparativa.py` — Convierte el Excel de emparejamiento que mantiene
  producto (`data/comparativa-titanium.xlsx`) en el SQL que puebla
  `titanium_pairs` (`data/titanium_pairs.sql`). Uso manual desde el equipo
  local: necesita `openpyxl`, que no esta en la imagen a proposito, y el
  contenedor de MySQL no publica el 3306. Al aplicar el SQL, este imprime que
  emparejamientos no resuelven contra el catalogo, que es lo que hay que
  devolverle a producto.
- `scheduler.py` — Ejecuta el crawl diario dentro del contenedor `crawler`
  (bucle Python que calcula cuanto falta para las 03:00 de Europe/Madrid y
  espera, en vez de un demonio cron dentro de la imagen). La zona horaria,
  no una hora UTC fija, para que siga el cambio de verano/invierno.
- `Dockerfile` + `docker-compose.yml` — Empaquetado para desplegar en un
  VPS o servidor propio. Una sola imagen para `dashboard` y `crawler`
  (ambos necesitan Playwright/Chromium: el boton "Lanzar crawl ahora" del
  dashboard ejecuta `main.py` en el mismo proceso).
- `tests/` — Tests unitarios de crawler, normalizer, detector, scheduler y
  el helper de conversion Decimal->float de `db.py`.

## Como funciona

1. **Crawl** — Descarga catalogo del competidor (Shopify JSON, con fallback
   a scraping HTML).
2. **Normalizar** — Convierte a un formato unico y descarta productos
   invalidos.
3. **Guardar** — Inserta/actualiza el producto y guarda un snapshot de hoy
   en MySQL.
4. **Detectar** — Compara con el snapshot anterior: producto nuevo, cambio
   de precio (+-5%) o cambio de disponibilidad.
5. **Contar** — Al final, recuento de lo detectado, leido desde la BD.

## Avisos

El crawler no envia notificaciones. El aviso lo monta **n8n** por su cuenta
con el workflow *Notificacion semanal scrapper competencia*: una vez por
semana consulta el MySQL compartido, arma un email con los cambios de la
competencia de los ultimos 7 dias y lo manda a la lista de avisos
(direccion, marketing, marketplace y tech: ocho buzones internos).

Que el aviso viva entero en n8n significa que a quien se avisa, cada cuanto
y con que aspecto se cambia desde su interfaz, sin tocar este repo ni
redesplegar.

> Hasta el 2026-09-04 el crawler llamaba ademas a un webhook
> (`N8N_WEBHOOK_URL`) que nunca llego a existir en n8n: el aviso se habia
> rediseñado como el workflow semanal de arriba y la llamada se quedo sin
> quitar, dejando un `404` en el log cada noche. Se retiro.

## Troubleshooting

**"No se pudo conectar a MySQL"**
- Verifica que MySQL esta corriendo: `mysql -u root -p -e "SELECT 1;"`
- Comprueba credenciales y host/puerto en `.env`.

**El crawler corre pero no genera productos nuevos en una segunda ejecucion
el mismo dia**
- Es esperado: `product_snapshots` tiene una unica fila por
  `(product_id, captured_at)`. Si necesitas forzar un segundo snapshot el
  mismo dia (para pruebas), borra la fila de hoy en esa tabla o cambia la
  fecha del sistema.

## Roadmap

- [ ] Panel/UI para gestionar competidores en vez de scripts sueltos
- [ ] Tests de integracion contra MySQL real
- [ ] Scraping de plazos de envio reales (`crawl_shipping_time`, ya
      implementado pero no conectado al pipeline principal por coste extra
      de una request por producto)
- [ ] Alertas de stock basadas en `detect_availability_change`
- [ ] Autenticacion o VPN para el dashboard antes de exponerlo en un VPS
      con IP publica (ver [Despliegue con Docker](#despliegue-con-docker))
- [ ] Capturar la "Linea" de producto (Elite Series, Black Series, Genesis
      Series...) de Titanium Strength. El dato existe en Magento, pero solo
      en la ficha de cada producto individual (tabla de especificaciones,
      atributo "Línea"), no en la rejilla de categoria que ya se scrapea —
      capturarlo implica visitar las ~865 fichas de producto una a una, lo
      que alargaria el crawl diario de <1 min a ~20-40 min. Fitness Tech /
      Fitness Tech FR (Shopify) ya capturan su equivalente ("series") desde
      las colecciones de la tienda, sin este coste extra.
