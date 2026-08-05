# Dockerizar Competitor Monitor

Fecha: 2026-08-05

## Contexto

El proyecto corre hoy en local via venv + MySQL instalado a mano. El
objetivo es empaquetarlo para poder levantarlo con un solo comando en
cualquier VPS o servidor propio que se contrate mas adelante, sin depender
de que la BD sea alcanzable desde internet (lo que bloqueaba activar
`.github/workflows/daily_crawl.yml`, ver comentario en ese fichero).

Decisiones tomadas con el usuario:
- MySQL se incluye dentro del propio `docker-compose` (autocontenido).
- El crawl diario se programa con un scheduler dentro de un contenedor, no
  con GitHub Actions (ya no hace falta exponer la BD a internet) ni con
  cron del host (no depender de configurar nada fuera de Docker).
- El dashboard se sirve con un servidor de produccion (`waitress`) en vez
  del servidor de desarrollo de Flask (`debug=True` es un riesgo real si el
  contenedor queda expuesto).
- **Sin autenticacion por ahora** (decision explicita del usuario): el
  dashboard queda completamente abierto en esta iteracion. Se ha hablado de
  anadir mas adelante una VPN (ej. Tailscale) a nivel de red cuando exista
  el VPS — eso no requiere tocar nada de este trabajo, se monta aparte.

## Alcance

- `Dockerfile` (una imagen, usada por dashboard y crawler).
- `docker-compose.yml` (servicios `mysql`, `dashboard`, `crawler`).
- `scheduler.py` (bucle de programacion diaria, puro Python).
- `.dockerignore`.
- Retirar `.github/workflows/daily_crawl.yml` (sustituido por el
  scheduler en contenedor; ya no aplica su bloqueo original).
- Documentar el despliegue Docker en el README.

Fuera de alcance: autenticacion del dashboard, VPN, reverse proxy/TLS,
dominio — se decidiran cuando exista el VPS real. `dashboard.py` no
necesita cambios de codigo (waitress sirve el mismo `app` de Flask
directamente, sin pasar por el bloque `if __name__ == "__main__"`).

## Diseno

### Imagen (`Dockerfile`)

Una sola imagen para ambos servicios: el boton "Lanzar crawl ahora" del
dashboard ejecuta `main.py` en el mismo proceso Flask (`crawl_main.main()`
en `dashboard.py`), asi que el dashboard tambien necesita Playwright y
Chromium disponibles, igual que el crawler.

Base `python:3.11-slim` + `pip install -r requirements.txt` +
`playwright install --with-deps chromium` (el flag `--with-deps` instala
tambien las librerias de sistema que Chromium necesita via `apt`, sin tener
que enumerarlas a mano — mas robusto que apostar por una imagen
preconstruida de Playwright con un tag que podria no existir para esta
version exacta).

### `docker-compose.yml`

- **`mysql`**: imagen oficial `mysql:8.0`. Monta `./migrations` en
  `/docker-entrypoint-initdb.d/` — MySQL ejecuta esos `.sql` en orden
  alfabetico la primera vez que el volumen de datos esta vacio, asi que las
  migraciones 001-004 se aplican solas en el primer arranque. Volumen
  nombrado para persistir los datos entre reinicios. Healthcheck
  (`mysqladmin ping`) para que los otros servicios esperen a que este listo.
- **`dashboard`**: build de la misma imagen, comando
  `waitress-serve --host=0.0.0.0 --port=5000 dashboard:app`. Puerto 5000
  publicado. `depends_on: mysql` con `condition: service_healthy`.
- **`crawler`**: build de la misma imagen, comando `python scheduler.py`.
  Mismo `depends_on`.
- `DB_HOST=mysql` fijado directamente en el `environment` de `dashboard` y
  `crawler` (el nombre del servicio es el hostname dentro de la red de
  Docker) — no depende de lo que tenga `DB_HOST` en `.env`, que sigue
  siendo `localhost` para cuando se corre fuera de Docker. El resto de
  variables (`DB_USER`, `DB_PASSWORD`, `DB_NAME`, `SLACK_*`) se leen de
  `.env` via `env_file`.

### `scheduler.py`

En vez de un cron de verdad (que obligaria a instalar un demonio cron
dentro de la imagen, con sus quirks de logging/PID 1 en Docker), un bucle
Python simple:

```python
def seconds_until_next_run(now, hour_utc=6) -> float:
    target = now.replace(hour=hour_utc, minute=0, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()

async def run_forever():
    while True:
        await asyncio.sleep(seconds_until_next_run(datetime.now(timezone.utc)))
        await main()
```

Mismo horario (06:00 UTC) que tenia el workflow de GitHub Actions retirado.
`seconds_until_next_run` es una funcion pura (recibe `now` como parametro
en vez de leerlo internamente) para poder testearla sin esperar horas de
verdad.

### Limpieza

`.github/workflows/daily_crawl.yml` se elimina: su bloqueo ("no lo actives
hasta que la BD sea alcanzable desde internet") deja de aplicar porque ya
no hace falta exponer la BD — el scheduler corre en el mismo Docker network
que MySQL. `tests.yml` no se toca (sigue corriendo `pytest` en cada push).

### Dependencias

`requirements.txt` gana `waitress` (servidor WSGI de produccion, sin
dependencias nativas, funciona igual en Windows que en Linux — no rompe el
flujo local actual con `python dashboard.py`, que se deja tal cual para
desarrollo local).

## Testing

- `tests/test_scheduler.py`: test de `seconds_until_next_run` con varios
  `now` fijos (antes de las 6:00, despues de las 6:00, exactamente a las
  6:00) para verificar que calcula bien cuando el objetivo es "hoy mas
  tarde" vs "manana".
- Sin tests de Docker/compose en si (no hay forma razonable de testear eso
  con pytest); se verifica a mano con `docker compose up` una vez escrito.
