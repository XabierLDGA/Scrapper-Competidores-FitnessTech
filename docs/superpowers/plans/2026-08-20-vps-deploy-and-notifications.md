# Desplegar en el VPS de n8n y sustituir Slack por email vía n8n Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Desplegar el crawler y el dashboard en el VPS de Hetzner que ya
tiene n8n/Traefik/MySQL corriendo, y sustituir el notifier de Slack (no
usado) por un aviso diario y un aviso de errores enviados por email desde
n8n.

**Architecture:** El scraper deja de llevar su propio MySQL y se conecta al
`mysql` ya desplegado (red Docker `backend`, externa). El dashboard se
expone vía Traefik en el mismo dominio que n8n, por ruta (`/competencia`),
protegido con auth básica. `src/notifier.py` deja de hablar con Slack y en
su lugar hace un único `POST` best-effort a un webhook de n8n con el
resumen diario completo; un segundo workflow de n8n, independiente,
consulta por Cron una tabla nueva (`crawl_errors`) cada tarde y manda un
email solo si hubo fallos de crawl ese día.

**Tech Stack:** Python 3.11, `httpx` (ya usado por el crawler, se reutiliza
para el webhook — sin dependencias HTTP nuevas), `mysql-connector-python`,
Docker Compose, Traefik (ya desplegado), n8n (ya desplegado).

**Spec:** `docs/superpowers/specs/2026-08-20-vps-deploy-and-notifications-design.md`

## Global Constraints

- El VPS es un Hetzner CPX22 (2 vCPU, 4 GB RAM) — no se levanta un segundo
  MySQL; se reutiliza el `mysql` ya desplegado en `fitnesstech-infra`.
- Las redes Docker `proxy` y `backend` ya existen (creadas por el
  `docker-compose.yml` de `fitnesstech-infra`) — en el compose del scraper
  se declaran como `external: true`, nunca recreadas.
- Dominio: `fitnesstech.duckdns.org` (temporal). El dashboard se expone en
  ese mismo host por **ruta** (`/competencia`), no por subdominio (DuckDNS
  no permite subdominios propios).
- El resumen diario se dispara justo al terminar el crawl programado
  (06:00 UTC, `scheduler.py`, sin cambios) mediante `POST` a
  `N8N_WEBHOOK_URL`. Un único intento, timeout de 10s, sin reintentos — si
  falla, se loguea y el crawl continúa igual (mismo comportamiento
  best-effort que tenía el notifier de Slack).
- El aviso de errores es un workflow de n8n **separado**, disparado por
  Cron a las **18:00 Europe/Madrid**, que consulta `crawl_errors` del día;
  no depende de que el webhook del resumen matutino funcione.
- Ambos emails van a `xlopez@fitnesstech.es`, enviados desde
  `info@fitnesstech.es` vía SMTP de IONOS — estas direcciones se
  configuran dentro de n8n (credencial SMTP + nodo de envío), nunca en
  código ni en variables de entorno del scraper.
- `slack-sdk` se retira de `requirements.txt` (dependencia sin uso tras
  este cambio).

---

## File Structure

- **Create `migrations/006_add_crawl_errors.sql`** — tabla `crawl_errors`.
- **Modify `src/db.py`** — nuevo método `log_crawl_error`.
- **Modify `main.py`** — persiste el fallo en `crawl_errors` cuando un
  competidor falla por completo; construye `Notifier` con `webhook_url` en
  vez de `slack_token`.
- **Modify `src/notifier.py`** — se retira todo el código de Slack; el
  método `send_daily_digest` pasa a hacer `POST` a un webhook de n8n.
- **Create `tests/test_notifier.py`** — tests del nuevo `send_daily_digest`.
- **Modify `requirements.txt`** — se retira `slack-sdk`.
- **Modify `.env.example`** — se retiran `SLACK_BOT_TOKEN`/`SLACK_CHANNEL`,
  se añaden `N8N_WEBHOOK_URL`, `DASHBOARD_HOST`, `DASHBOARD_BASIC_AUTH`.
- **Modify `docker-compose.yml`** — se quita el servicio `mysql` propio;
  `dashboard` y `crawler` se conectan a las redes externas
  `proxy`/`backend`; `dashboard` gana labels de Traefik (ruta + auth
  básica) en vez de publicar el puerto 5000 directamente.
- Despliegue en el VPS y workflows de n8n — pasos operativos (SSH, SQL,
  configuración de n8n vía UI), no ficheros de este repo.

---

### Task 1: Tabla `crawl_errors` y `Database.log_crawl_error`

**Files:**
- Create: `migrations/006_add_crawl_errors.sql`
- Modify: `src/db.py` (nuevo método al final de la clase, tras
  `get_recently_added_products`, línea 390)

**Interfaces:**
- Produces: `Database.log_crawl_error(competitor_name: str, error_message: str) -> None`

- [ ] **Step 1: Crear la migración**

Crea `migrations/006_add_crawl_errors.sql`:

```sql
USE competitor_monitor;

CREATE TABLE crawl_errors (
    id INT AUTO_INCREMENT PRIMARY KEY,
    competitor_name VARCHAR(255) NOT NULL,
    error_message TEXT NOT NULL,
    occurred_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

- [ ] **Step 2: Aplicar la migración contra MySQL local**

Run: `mysql -h localhost -u root -p competitor_monitor < migrations/006_add_crawl_errors.sql`

Expected: sin errores. Verifica con:
`mysql -h localhost -u root -p -e "DESCRIBE competitor_monitor.crawl_errors;"`
La salida debe listar las columnas `id`, `competitor_name`,
`error_message`, `occurred_at`.

- [ ] **Step 3: Añadir `log_crawl_error` a `src/db.py`**

Al final de la clase `Database` (después del método
`get_recently_added_products`), añade:

```python
    def log_crawl_error(self, competitor_name: str, error_message: str):
        """Persiste un fallo completo de crawl de un competidor.

        n8n consulta esta tabla cada tarde (18:00 Europe/Madrid) para el
        email de errores del dia; no tiene relacion con el resumen diario
        de productos/precios, que se dispara aparte via webhook."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("""
                    INSERT INTO crawl_errors (competitor_name, error_message)
                    VALUES (%s, %s)
                """, (competitor_name, error_message))
                conn.commit()
                logger.info(f"Error de crawl registrado para {competitor_name}")
            finally:
                cursor.close()
```

- [ ] **Step 4: Verificar manualmente contra MySQL local**

Con el `.env` local apuntando a tu MySQL de desarrollo:

```bash
python -c "
from dotenv import load_dotenv
load_dotenv()
import os
from src.db import Database
db = Database(host=os.getenv('DB_HOST','localhost'), user=os.getenv('DB_USER','root'),
               password=os.getenv('DB_PASSWORD',''), database=os.getenv('DB_NAME','competitor_monitor'))
db.log_crawl_error('Test Competitor', 'error de prueba')
"
mysql -h localhost -u root -p -e "SELECT * FROM competitor_monitor.crawl_errors;"
```

Expected: una fila con `competitor_name = 'Test Competitor'`. Borra la fila
de prueba después: `mysql -h localhost -u root -p -e "DELETE FROM competitor_monitor.crawl_errors WHERE competitor_name = 'Test Competitor';"`

- [ ] **Step 5: Commit**

```bash
git add migrations/006_add_crawl_errors.sql src/db.py
git commit -m "feat: add crawl_errors table and Database.log_crawl_error"
```

---

### Task 2: Registrar los fallos de crawl completos

**Files:**
- Modify: `main.py:146-148`

**Interfaces:**
- Consumes: `Database.log_crawl_error(competitor_name, error_message)` (Task 1)

- [ ] **Step 1: Capturar el mensaje de la excepción y persistirlo**

En `main.py`, dentro de `main()`, sustituye:

```python
            except Exception:
                logger.exception(f"  Error crawleando {competitor['name']}")
                errors.append(competitor["name"])
```

por:

```python
            except Exception as exc:
                logger.exception(f"  Error crawleando {competitor['name']}")
                errors.append(competitor["name"])
                db.log_crawl_error(competitor["name"], str(exc))
```

- [ ] **Step 2: Verificar manualmente con un competidor roto**

Con MySQL local levantado y al menos un competidor dado de alta, rompe
temporalmente su `website_url` (ej. `https://esto-no-existe.invalid`) con
una consulta directa:

```bash
mysql -h localhost -u root -p -e "UPDATE competitor_monitor.competitors SET website_url = 'https://esto-no-existe.invalid', product_api_url = NULL WHERE name = '<nombre-del-competidor>';"
```

Ejecuta `python main.py`. Expected: el log muestra
`Error crawleando <nombre>`, el proceso termina sin excepción sin capturar,
y:

```bash
mysql -h localhost -u root -p -e "SELECT competitor_name, error_message, occurred_at FROM competitor_monitor.crawl_errors ORDER BY occurred_at DESC LIMIT 1;"
```

muestra la fila nueva. Revierte la `website_url` al valor real después de
verificar.

- [ ] **Step 3: Correr la suite de tests para confirmar que no hay regresión**

Run: `pytest -v`
Expected: todos los tests existentes siguen en PASS (este cambio no toca
ninguna ruta cubierta por `tests/test_main.py`, que solo testea
`crawl_competitor_products`).

- [ ] **Step 4: Commit**

```bash
git add main.py
git commit -m "feat: persist full crawl failures to crawl_errors"
```

---

### Task 3: `Notifier` — de Slack a webhook de n8n

**Files:**
- Modify: `src/notifier.py` (reescritura completa, 103 líneas actuales)
- Test: `tests/test_notifier.py` (nuevo)

**Interfaces:**
- Produces: `Notifier(webhook_url: str | None = None)`,
  `Notifier.send_daily_digest(new_products: list[dict], price_events: list[dict]) -> None`.
  Cada `dict` de `new_products` trae al menos `competitor`, `title`, `url`,
  y opcionalmente `sku` (mismas keys que devuelve
  `Database.get_new_products`). Cada `dict` de `price_events` trae
  `competitor`, `title`, `old_price`, `new_price`, `percent_change`, y
  opcionalmente `sku` (mismas keys que devuelve
  `Database.get_unnotified_events`).
- Consumes: nada nuevo — sigue llamándose igual que el `Notifier` de Slack
  desde `main.py` (`notifier.send_daily_digest(new_products, pending_events)`
  no cambia su firma de llamada).

- [ ] **Step 1: Escribir el test que falla**

Crea `tests/test_notifier.py`:

```python
from unittest.mock import MagicMock, patch

from src.notifier import Notifier


def test_send_daily_digest_posts_expected_payload(monkeypatch):
    monkeypatch.setenv("N8N_WEBHOOK_URL", "https://n8n.example/webhook/digest")
    notifier = Notifier()

    new_products = [{"competitor": "Titanium Strength", "title": "Barra Z",
                      "sku": "TS-1", "url": "https://x/1"}]
    price_events = [{"competitor": "Fitness Tech", "title": "Rack", "sku": "FT-2",
                      "old_price": 100.0, "new_price": 90.0, "percent_change": -10.0}]

    with patch("src.notifier.httpx.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=200)
        notifier.send_daily_digest(new_products, price_events)

    assert mock_post.called
    args, kwargs = mock_post.call_args
    assert args[0] == "https://n8n.example/webhook/digest"
    assert kwargs["json"]["new_products"][0]["title"] == "Barra Z"
    assert kwargs["json"]["price_events"][0]["percent_change"] == -10.0
    assert kwargs["timeout"] == 10.0


def test_send_daily_digest_skips_when_webhook_not_configured(monkeypatch):
    monkeypatch.delenv("N8N_WEBHOOK_URL", raising=False)
    notifier = Notifier()

    with patch("src.notifier.httpx.post") as mock_post:
        notifier.send_daily_digest(
            [{"competitor": "X", "title": "Y", "url": "https://z"}], [])

    mock_post.assert_not_called()


def test_send_daily_digest_skips_when_nothing_to_report(monkeypatch):
    monkeypatch.setenv("N8N_WEBHOOK_URL", "https://n8n.example/webhook/digest")
    notifier = Notifier()

    with patch("src.notifier.httpx.post") as mock_post:
        notifier.send_daily_digest([], [])

    mock_post.assert_not_called()


def test_send_daily_digest_logs_and_continues_on_http_error(monkeypatch, caplog):
    monkeypatch.setenv("N8N_WEBHOOK_URL", "https://n8n.example/webhook/digest")
    notifier = Notifier()

    with patch("src.notifier.httpx.post", side_effect=Exception("boom")):
        notifier.send_daily_digest(
            [{"competitor": "X", "title": "Y", "url": "https://z"}], [])
```

- [ ] **Step 2: Ejecutar los tests para confirmar que fallan**

Run: `pytest tests/test_notifier.py -v`
Expected: FAIL — `src.notifier.Notifier` todavía solo acepta `slack_token`
y no tiene lógica de `httpx.post`.

- [ ] **Step 3: Reescribir `src/notifier.py`**

Sustituye el fichero completo por:

```python
import logging
import os
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


class Notifier:
    def __init__(self, webhook_url: Optional[str] = None):
        self.webhook_url = webhook_url or os.getenv("N8N_WEBHOOK_URL")

    def send_daily_digest(self, new_products: list, price_events: list):
        """Envia el resumen diario completo (productos nuevos y cambios de
        precio, con todo el detalle) a un webhook de n8n. n8n decide a
        quien y como avisar (email, hoy) - este metodo no sabe nada de
        destinatarios ni formato de email, solo manda los datos.

        Best-effort: un unico intento con timeout corto. Si falla, se
        loguea y no se relanza - un fallo aqui no debe tumbar el crawl
        (mismo comportamiento que tenia el notifier de Slack)."""
        if not self.webhook_url:
            logger.warning("N8N_WEBHOOK_URL no configurado, saltando notificacion")
            return

        if not new_products and not price_events:
            return

        payload = {
            "new_products": [
                {
                    "competitor": p["competitor"],
                    "title": p["title"],
                    "sku": p.get("sku"),
                    "url": p["url"],
                }
                for p in new_products
            ],
            "price_events": [
                {
                    "competitor": e["competitor"],
                    "title": e["title"],
                    "sku": e.get("sku"),
                    "old_price": e["old_price"],
                    "new_price": e["new_price"],
                    "percent_change": e["percent_change"],
                }
                for e in price_events
            ],
        }

        try:
            response = httpx.post(self.webhook_url, json=payload, timeout=10.0)
            response.raise_for_status()
            logger.info(
                f"Resumen diario enviado a n8n: {len(new_products)} nuevos, "
                f"{len(price_events)} cambios de precio"
            )
        except Exception as exc:
            logger.error(f"Error enviando resumen diario a n8n: {exc}")
```

- [ ] **Step 4: Ejecutar los tests para confirmar que pasan**

Run: `pytest tests/test_notifier.py -v`
Expected: 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/notifier.py tests/test_notifier.py
git commit -m "feat: replace Slack notifier with n8n webhook digest"
```

---

### Task 4: Conectar `main.py` al nuevo `Notifier` y retirar Slack del proyecto

**Files:**
- Modify: `main.py:109`
- Modify: `requirements.txt:6`
- Modify: `.env.example`

**Interfaces:**
- Consumes: `Notifier(webhook_url=...)` (Task 3)

- [ ] **Step 1: Actualizar la construcción del `Notifier` en `main.py`**

Sustituye:

```python
    notifier = Notifier(slack_token=os.getenv("SLACK_BOT_TOKEN"))
```

por:

```python
    notifier = Notifier(webhook_url=os.getenv("N8N_WEBHOOK_URL"))
```

- [ ] **Step 2: Retirar `slack-sdk` de `requirements.txt`**

Elimina la línea `slack-sdk==3.26.1`.

- [ ] **Step 3: Actualizar `.env.example`**

Sustituye el bloque:

```
# Slack (opcional; si se deja vacio, el notifier no envia nada y solo loguea)
SLACK_BOT_TOKEN=xoxb-your-token-here
SLACK_CHANNEL=#product-alerts
```

por:

```
# n8n (opcional; si se deja vacio, el notifier no envia nada y solo loguea)
N8N_WEBHOOK_URL=https://fitnesstech.duckdns.org/webhook/competencia-resumen-diario

# Solo para despliegue en el VPS (docker-compose.yml): dominio publico del
# dashboard (mismo host que n8n, se accede por /competencia) y credenciales
# de auth basica de Traefik. Ver el runbook de despliegue (Task 6) para
# como generar DASHBOARD_BASIC_AUTH.
DASHBOARD_HOST=fitnesstech.duckdns.org
DASHBOARD_BASIC_AUTH=admin:tu-hash-generado-con-openssl
```

- [ ] **Step 4: Reinstalar dependencias y correr la suite completa**

Run:
```bash
pip install -r requirements.txt
pytest -v
```

Expected: todos los tests en PASS, sin `slack_sdk` instalado.

- [ ] **Step 5: Commit**

```bash
git add main.py requirements.txt .env.example
git commit -m "chore: drop slack-sdk, wire main.py to n8n webhook notifier"
```

---

### Task 5: `docker-compose.yml` — MySQL compartido y dashboard vía Traefik

**Files:**
- Modify: `docker-compose.yml` (reescritura completa, 43 líneas actuales)

**Interfaces:**
- Consumes: redes Docker externas `proxy` y `backend` (ya creadas por
  `fitnesstech-infra`), contenedor `mysql` de ese mismo stack alcanzable
  por hostname `mysql` dentro de la red `backend`.

- [ ] **Step 1: Sustituir `docker-compose.yml` completo**

```yaml
services:
  dashboard:
    build: .
    restart: unless-stopped
    command: waitress-serve --host=0.0.0.0 --port=5000 dashboard:app
    env_file: .env
    environment:
      DB_HOST: mysql
    networks:
      - proxy
      - backend
    labels:
      - "traefik.enable=true"
      - "traefik.docker.network=proxy"
      - "traefik.http.routers.competencia.rule=Host(`${DASHBOARD_HOST}`) && PathPrefix(`/competencia`)"
      - "traefik.http.routers.competencia.entrypoints=websecure"
      - "traefik.http.routers.competencia.tls.certresolver=letsencrypt"
      - "traefik.http.routers.competencia.middlewares=competencia-auth"
      - "traefik.http.middlewares.competencia-auth.basicauth.users=${DASHBOARD_BASIC_AUTH}"
      - "traefik.http.services.competencia.loadbalancer.server.port=5000"

  crawler:
    build: .
    restart: unless-stopped
    command: python scheduler.py
    env_file: .env
    environment:
      DB_HOST: mysql
    networks:
      - proxy
      - backend

networks:
  proxy:
    external: true
  backend:
    external: true
```

Nota sobre por qué `crawler` también lleva `proxy`: la red `backend` de
`fitnesstech-infra` está declarada `internal: true` (sin salida a
internet, a propósito, para que MySQL nunca sea alcanzable desde fuera).
Si `crawler` solo se conectara a `backend`, se quedaría sin poder salir a
crawlear las webs de la competencia. `proxy` es la única red del stack con
salida a internet, así que `crawler` se une también a ella — sin labels de
Traefik, así que no queda expuesto a internet por ello, solo gana la ruta
de salida. Mismo motivo por el que `dashboard` también necesita `proxy`
(en su caso además para que Traefik lo descubra).

Nota sobre `DASHBOARD_BASIC_AUTH`: el valor completo (`usuario:hash`) vive
en `.env`, referenciado aquí como variable — así el hash no lleva ningún
`$` literal dentro de este fichero. Si en algún momento se escribiera el
hash directamente en este YAML en vez de en `.env`, cada `$` del hash
tendría que duplicarse como `$$` (Docker Compose interpreta `$` como
inicio de variable si no).

Nota sobre `mysql_data` (volumen del compose anterior): se elimina del
fichero porque este compose ya no gestiona su propio MySQL — el volumen
de datos real vive en el compose de `fitnesstech-infra`.

- [ ] **Step 2: Validar la sintaxis del compose sin desplegar**

Run: `docker compose config`
Expected: sin errores. Si `DASHBOARD_HOST`/`DASHBOARD_BASIC_AUTH` no están
en tu `.env` local, `docker compose config` avisará de variables vacías —
esperado en local (son solo relevantes para el despliegue en el VPS,
Task 6).

- [ ] **Step 3: Commit**

```bash
git add docker-compose.yml
git commit -m "feat: join scraper stack to the shared VPS networks and MySQL"
```

---

### Task 6: Desplegar en el VPS

Trabajo operativo sobre el VPS (`168.119.241.200`,
`fitnesstech.duckdns.org`), sin cambios en este repo. Sigue el mismo
patrón de acceso ya usado para `fitnesstech-infra` (sesión `root` para lo
que necesita permisos de root, usuario `deploy` — grupo `docker` — para
`docker compose`).

- [ ] **Step 1: Crear la base de datos y el usuario del scraper en el MySQL compartido**

Desde la sesión `root` del VPS, dentro del contenedor `mysql` de
`fitnesstech-infra`:

```bash
docker exec -it mysql mysql -uroot -p"$MYSQL_ROOT_PASSWORD"
```

Y dentro del cliente MySQL:

```sql
CREATE DATABASE IF NOT EXISTS competitor_monitor;
CREATE USER 'scraper'@'%' IDENTIFIED BY '<contrasena-fuerte-generada-con-openssl-rand>';
GRANT ALL PRIVILEGES ON competitor_monitor.* TO 'scraper'@'%';
FLUSH PRIVILEGES;
```

Genera la contraseña con `openssl rand -base64 24`, igual que el resto de
secretos del VPS (ver `fitnesstech-infra`).

- [ ] **Step 2: Aplicar las migraciones 001-006 a mano**

Como el contenedor `mysql` ya existía (el volumen no está vacío), el
mecanismo automático de `docker-entrypoint-initdb.d` no se dispara. Aplica
cada migración en orden, desde el repo del scraper ya clonado en el VPS
(ver Step 3):

```bash
for f in migrations/*.sql; do
  docker exec -i mysql mysql -uroot -p"$MYSQL_ROOT_PASSWORD" < "$f"
done
```

Expected: sin errores. Verifica con
`docker exec -it mysql mysql -uroot -p"$MYSQL_ROOT_PASSWORD" -e "SHOW TABLES FROM competitor_monitor;"`
— deben aparecer `competitors`, `products`, `product_snapshots`,
`price_events`, `availability_events`, `crawl_errors`.

- [ ] **Step 3: Clonar el repo del scraper en el VPS**

Como `root` (mismo patrón que `fitnesstech-infra`):

```bash
cd /opt
git clone https://github.com/XabierLDGA/Scrapper-Competidores-FitnessTech.git scraper-competidores
chown -R deploy:deploy /opt/scraper-competidores
```

- [ ] **Step 4: Configurar `.env` en el VPS**

Como `deploy`, en `/opt/scraper-competidores`:

```bash
cp .env.example .env
```

Edita `.env` con:
- `DB_HOST=mysql`, `DB_USER=scraper`, `DB_PASSWORD=<la-generada-en-Step-1>`, `DB_NAME=competitor_monitor`
- `N8N_WEBHOOK_URL=https://fitnesstech.duckdns.org/webhook/competencia-resumen-diario` (debe coincidir exactamente con el path del nodo Webhook que se crea en Task 7)
- `DASHBOARD_HOST=fitnesstech.duckdns.org`
- `DASHBOARD_BASIC_AUTH=admin:<hash>`, generado con:
  ```bash
  openssl passwd -apr1 '<contrasena-elegida>'
  ```
  y compuesto a mano como `admin:<salida-del-comando-anterior>`.

- [ ] **Step 5: Levantar el stack**

```bash
docker compose up -d --build
docker compose logs -f crawler
```

Expected: `dashboard` y `crawler` arrancan sanos (`docker compose ps`
muestra ambos `Up`); el log de `crawler` muestra el cálculo de cuánto
falta para el próximo crawl (06:00 UTC), sin errores de conexión a MySQL.

- [ ] **Step 6: Verificar el dashboard a través de Traefik**

Visita `https://fitnesstech.duckdns.org/competencia` en el navegador.
Expected: prompt de auth básica; tras introducir `admin`/`<contrasena-elegida>`,
se ve el dashboard (vacío de catálogo hasta el primer crawl, pero sin
errores 502/504).

- [ ] **Step 7: Lanzar un crawl manual de prueba**

```bash
docker compose exec crawler python main.py
```

Expected: termina sin excepciones; `docker exec -it mysql mysql -uroot -p"$MYSQL_ROOT_PASSWORD" -e "SELECT COUNT(*) FROM competitor_monitor.products;"`
devuelve más de 0.

---

### Task 7: Workflows de n8n

Trabajo en la UI de n8n (`https://fitnesstech.duckdns.org`), sin ficheros
de código. Requiere que Task 6 esté desplegado (para poder mandar un
evento de prueba al webhook) y las credenciales SMTP de IONOS para
`info@fitnesstech.es` a mano.

- [ ] **Step 1: Crear la credencial SMTP en n8n**

En n8n: `Credentials` → `New` → `SMTP`. Host/puerto de IONOS (SMTP:
`smtp.ionos.es`, puerto `587`, STARTTLS), usuario `info@fitnesstech.es`,
contraseña de esa cuenta. Guarda como `IONOS - info@fitnesstech.es`.

- [ ] **Step 2: Workflow "Resumen diario competencia"**

Nodos:
1. **Webhook** (trigger): método `POST`, path `competencia-resumen-diario`
   (debe coincidir con `N8N_WEBHOOK_URL` del `.env` del scraper, Task 6
   Step 4). Modo de respuesta: `Immediately` (no bloquear al crawler
   esperando que se termine de mandar el email).
2. **Set/Code**: construye el asunto y el cuerpo HTML a partir de
   `{{$json.new_products}}` y `{{$json.price_events}}` — una lista por
   cada producto nuevo (competidor, título, SKU, enlace) y cada cambio de
   precio (competidor, título, precio antes → después, % de cambio).
3. **Send Email** (usando la credencial SMTP de Step 1): De
   `info@fitnesstech.es`, para `xlopez@fitnesstech.es`, asunto tipo
   `Resumen competencia {{$now.format('dd/MM/yyyy')}}`, cuerpo HTML del
   nodo anterior.

Activa el workflow (`Active`).

- [ ] **Step 3: Verificar el workflow con un evento de prueba**

Desde cualquier máquina con acceso a internet:

```bash
curl -X POST https://fitnesstech.duckdns.org/webhook/competencia-resumen-diario \
  -H "Content-Type: application/json" \
  -d '{"new_products":[{"competitor":"Test","title":"Producto prueba","sku":"T-1","url":"https://example.com"}],"price_events":[]}'
```

Expected: llega un email a `xlopez@fitnesstech.es` con el producto de
prueba listado.

- [ ] **Step 4: Workflow "Errores crawl competencia"**

Nodos:
1. **Cron** (trigger): `18:00`, zona horaria `Europe/Madrid`, todos los
   días.
2. **MySQL** (usando una credencial de n8n hacia el `mysql` compartido,
   base `competitor_monitor`, usuario `scraper`): query
   ```sql
   SELECT competitor_name, error_message, occurred_at
   FROM crawl_errors
   WHERE DATE(occurred_at) = CURDATE()
   ORDER BY occurred_at;
   ```
3. **If**: `{{$json.length}} > 0` (rama verdadera continúa, rama falsa
   termina el workflow sin hacer nada).
4. **Send Email** (misma credencial SMTP): De `info@fitnesstech.es`, para
   `xlopez@fitnesstech.es`, asunto tipo
   `Errores de crawl {{$now.format('dd/MM/yyyy')}}`, cuerpo listando cada
   fila (competidor, mensaje de error, hora).

Activa el workflow (`Active`).

- [ ] **Step 5: Verificar el workflow de errores manualmente**

Inserta una fila de prueba y ejecuta el workflow a mano desde el editor de
n8n (botón "Execute Workflow", sin esperar a las 18:00):

```bash
docker exec -it mysql mysql -uroot -p"$MYSQL_ROOT_PASSWORD" competitor_monitor \
  -e "INSERT INTO crawl_errors (competitor_name, error_message) VALUES ('Test', 'error de prueba');"
```

Expected: llega un email a `xlopez@fitnesstech.es` listando la fila de
prueba. Bórrala después:

```bash
docker exec -it mysql mysql -uroot -p"$MYSQL_ROOT_PASSWORD" competitor_monitor \
  -e "DELETE FROM crawl_errors WHERE competitor_name = 'Test';"
```
