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
Tras instalar las dependencias, descarga el binario del navegador una vez:

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

Edita `.env` con tus credenciales de MySQL. `SLACK_BOT_TOKEN` es opcional: si
se deja vacio, `Notifier` simplemente loguea y no intenta enviar nada a Slack.

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
)
print(f"Competidor anadido: ID {competitor_id}")
```

### 5. Ejecutar

```bash
python main.py
```

### 6. Dashboard local

Para ver competidores, catalogo actual y cambios de precio sin escribir SQL:

```bash
python dashboard.py
```

Abre http://localhost:5000 en el navegador. Es un servidor de desarrollo
Flask (`debug=True`) pensado solo para uso local, no para producción — lee
directamente de MySQL en cada recarga de pagina, no tiene autenticacion.

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

- `src/crawler.py` — Descarga datos: Shopify `/products.json` (via
  `crawl_competitor_products` en `main.py`) con fallback automatico a
  scraping HTML generico si el competidor no expone ese endpoint.
- `src/normalizer.py` — Convierte productos crawleados a un formato comun y
  descarta los que no tienen datos minimos (id, titulo, precio >= 0).
- `src/detector.py` — Unica fuente de verdad para "es nuevo", "cambio de
  precio >= umbral" y "cambio de disponibilidad". El umbral de precio (5%
  por defecto) se decide aqui una sola vez; nada mas lo recalcula.
- `src/notifier.py` — Envia alertas a Slack (o solo loguea si no hay token).
- `src/db.py` — Acceso a MySQL. Convierte los `Decimal` que devuelve
  `mysql-connector` para columnas `DECIMAL` a `float` en la frontera con la
  BD, para que el resto del pipeline no tenga que lidiar con ese tipo.
- `main.py` — Orquestacion: crawlea cada competidor, persiste snapshots,
  detecta cambios, notifica, y al final construye el digest diario leyendo
  el estado real de la BD (`get_new_products` / `get_unnotified_events`),
  no listas en memoria — asi el digest es correcto aunque el crawl falle a
  mitad para algun competidor.
- `dashboard.py` + `templates/dashboard.html` — Vista web de solo lectura
  sobre MySQL (competidores, catalogo actual, cambios de precio recientes).
  Sin autenticacion. Local: `python dashboard.py` (servidor de desarrollo
  Flask, `debug=True`). Docker: se sirve con `waitress` (ver
  [Despliegue con Docker](#despliegue-con-docker)).
- `scheduler.py` — Ejecuta el crawl diario dentro del contenedor `crawler`
  (bucle Python que calcula cuanto falta para las 06:00 UTC y espera, en
  vez de un demonio cron dentro de la imagen).
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
5. **Alertar** — Notifica a Slack producto por producto segun se detecta.
6. **Digest** — Al final, resumen diario leido desde la BD.

## Troubleshooting

**"No se pudo conectar a MySQL"**
- Verifica que MySQL esta corriendo: `mysql -u root -p -e "SELECT 1;"`
- Comprueba credenciales y host/puerto en `.env`.

**"Slack no configurado"**
- Obten un token en https://api.slack.com/apps con permisos `chat:write` y
  `chat:write.public`, y ponlo en `SLACK_BOT_TOKEN`.

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
