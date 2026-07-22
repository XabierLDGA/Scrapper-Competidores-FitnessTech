# Competitor Monitor (MySQL)

Sistema de monitorizacion automatica de competidores en fitnesstech usando MySQL.

Pensado para correr **en local primero** y, cuando este validado, activar el
workflow de GitHub Actions para producción.

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

## CI/CD

- **`.github/workflows/tests.yml`**: corre `pytest` en cada push/PR. No
  necesita secrets ni acceso a MySQL.
- **`.github/workflows/daily_crawl.yml`**: cron diario que ejecuta
  `main.py` contra MySQL en produccion. **No lo actives hasta que la BD
  sea alcanzable desde internet** (IP publica, firewall con reglas para los
  rangos de IP de GitHub Actions, un runner self-hosted, o un tunel SSH) —
  los runners de `ubuntu-latest` tienen IP dinamica. Secrets necesarios:
  `DB_HOST`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`, `DB_PORT`,
  `SLACK_BOT_TOKEN`, `SLACK_CHANNEL`, `SLACK_WEBHOOK_URL` (opcional, solo
  para la notificacion de fallo).

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
- `dashboard.py` + `templates/dashboard.html` — Vista web local de solo
  lectura sobre MySQL (competidores, catalogo actual, cambios de precio
  recientes). Servidor de desarrollo Flask, sin autenticacion: solo para
  uso local.
- `tests/` — Tests unitarios de crawler, normalizer, detector y el helper de
  conversion Decimal->float de `db.py`.

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
- [ ] Tests de integracion contra MySQL real (docker-compose)
- [ ] Scraping de plazos de envio reales (`crawl_shipping_time`, ya
      implementado pero no conectado al pipeline principal por coste extra
      de una request por producto)
- [ ] Alertas de stock basadas en `detect_availability_change`
- [ ] Activar `daily_crawl.yml` cuando la BD este accesible desde produccion
