# Desplegar en el VPS de n8n y sustituir Slack por email vía n8n

Fecha: 2026-08-20

## Contexto

El proyecto ("Proyecto B" de las dos automatizaciones nuevas de FitnessTech,
ver `[[project-fitnesstech-next-automations]]` en la memoria del asistente)
está dockerizado (ver `docs/superpowers/specs/2026-08-05-dockerize-design.md`)
pero solo se ha ejecutado en local. El usuario ya tiene un VPS de Hetzner en
producción (repo `fitnesstech-infra`) con Traefik + n8n + un MySQL interno
todavía sin usar (reservado para un futuro PIM). El objetivo de este diseño
es desplegar el crawler y el dashboard en ese mismo VPS, y sustituir las
notificaciones de Slack (que el usuario no usa) por avisos por email
orquestados desde n8n.

Decisiones tomadas con el usuario:
- Se reutiliza el VPS y el MySQL ya desplegados en `fitnesstech-infra`, en
  vez de levantar un servidor o una base de datos nuevos — el VPS es de
  recursos limitados (Hetzner CPX22, 4 GB RAM).
- El dashboard se expone en el dominio temporal `fitnesstech.duckdns.org`
  (DuckDNS no permite subdominios propios) por **ruta**, no por
  subdominio, protegido con auth básica de Traefik (el dashboard en sí no
  tiene login).
- Las notificaciones no se implementan como código de email en Python: el
  crawler llama a un **webhook de n8n**, y es n8n quien decide a quién y
  cómo avisar. Esto deja la regla de "a quién va cada aviso" editable
  desde n8n sin tocar código ni redesplegar.
- Se sustituye el resumen diario de Slack (solo contaba "N nuevos, M
  cambios de precio") por un email con **detalle completo** (competidor,
  producto, precio antes/después), porque va a ser el único aviso que
  reciba el usuario.
- Se añade un segundo aviso, independiente del resumen: un email de
  **errores del día**, una vez al día por la tarde, solo si algún
  competidor falló por completo al crawlear.

## Alcance

Repo `Scrapper-Competidores-FitnessTech` (local:
`C:\Users\xlope\Desktop\Proyectos\scrapper-Competidores`):
- `src/notifier.py`: retirar el código de Slack (`slack_sdk` sale de
  `requirements.txt`); añadir el envío del payload del resumen diario al
  webhook de n8n.
- `src/db.py` + nueva migración `migrations/006_add_crawl_errors.sql`:
  tabla `crawl_errors` para persistir los fallos completos de crawl por
  competidor.
- `main.py`: al detectar que un competidor falló por completo, además de
  loguear y añadirlo a `errors` (como ya hace hoy), guardarlo en
  `crawl_errors`. Sustituir la llamada a `notifier.send_daily_digest`
  (Slack) por la llamada al webhook.
- `docker-compose.yml`: quitar el servicio `mysql` propio; `dashboard` y
  `crawler` pasan a conectarse a las redes externas `proxy`/`backend` del
  repo `fitnesstech-infra` y a `DB_HOST=mysql` (el contenedor ya
  desplegado); `dashboard` cambia el `ports: 5000:5000` directo por
  labels de Traefik (ruta + auth básica).
- `.env.example`: nuevas variables `N8N_WEBHOOK_URL`, credenciales de la
  base de datos y usuario nuevos del scraper dentro del MySQL compartido;
  se retiran `SLACK_BOT_TOKEN`/`SLACK_CHANNEL`.

Repo `fitnesstech-infra`: sin cambios de código — solo se crea a mano (o
con un script puntual) la base de datos y el usuario del scraper dentro
del contenedor `mysql` ya desplegado.

n8n (en el VPS): dos workflows nuevos —
1. **Resumen diario**: Webhook (recibe el JSON del crawler) → formatea
   email HTML con el detalle → nodo de envío SMTP (`info@fitnesstech.es`,
   IONOS) → `xlopez@fitnesstech.es`.
2. **Errores del día**: Cron (18:00 Europe/Madrid) → consulta
   `crawl_errors` del día en el MySQL compartido → si hay filas, formatea
   y manda email a `xlopez@fitnesstech.es`; si no hay ninguna, no manda
   nada.

Fuera de alcance: autenticación del dashboard más allá de auth básica de
Traefik, subdominio propio (depende de migrar a `fitnesstech.es` en
IONOS), alertas de disponibilidad/stock, panel de gestión de
competidores — todo esto ya estaba en el roadmap del README antes de este
diseño y sigue pendiente, sin relación con este trabajo.

## Diseño

### Redes y MySQL compartido

El `docker-compose.yml` del scraper declara `proxy` y `backend` como redes
**externas** (`external: true`), con los mismos nombres que ya usa
`fitnesstech-infra` (`docker-compose.yml` de ese repo, sección
`networks`). El servicio `mysql` desaparece del compose del scraper;
`dashboard` y `crawler` se conectan a `backend` (para hablar con el
`mysql` ya desplegado) y `dashboard` también a `proxy` (para que Traefik
lo descubra), igual que hace `n8n` hoy en `fitnesstech-infra` — incluida
la label `traefik.docker.network=proxy`, necesaria porque si un
contenedor está en dos redes y falta esa label, Traefik puede intentar
enrutar por la red interna equivocada (ya ocurrió con n8n, ver
`fitnesstech-infra`).

Dentro del `mysql` compartido se crea una base de datos
(`competitor_monitor`) y un usuario propios del scraper, sin tocar nada
reservado para el futuro PIM. Las migraciones `001`-`006` se aplican a
mano la primera vez (ya no hay bootstrap automático vía
`docker-entrypoint-initdb.d`, porque ese mecanismo solo corre si el
contenedor se crea con el volumen vacío, y aquí el contenedor ya existe).

### Dashboard vía Traefik

Router de Traefik con regla de **path prefix** sobre el mismo `Host`
que ya usa n8n (`fitnesstech.duckdns.org`), por ejemplo
``PathPrefix(`/competencia`)``, más un middleware `basicauth` con un
usuario/contraseña generados igual que el resto de secretos del VPS
(`openssl rand` + guardados en el `.env` del VPS y en el gestor de
contraseñas del usuario, siguiendo la práctica ya usada en
`fitnesstech-infra`). Sin esto, el dashboard quedaría abierto a
cualquiera con la URL, tal y como ya avisaba el README del propio repo.

### Resumen diario -> webhook de n8n

Al final de `main()` (donde hoy se llama a
`notifier.send_daily_digest(new_products, pending_events)`), el nuevo
método construye un JSON con la lista completa de `new_products` y
`pending_events` (mismos datos que ya devuelve `db.get_new_products` /
`db.get_unnotified_events`, sin transformarlos — el formato de email es
responsabilidad de n8n, no del scraper) y hace un `POST` a
`N8N_WEBHOOK_URL`. Igual que el notifier de Slack, es *best-effort*: un
único intento con timeout corto (ej. 10s); si falla, se loguea el error y
el crawl termina igualmente (no debe colgar ni reintentar indefinidamente).

`db.mark_events_notified(...)` se sigue llamando igual que hoy tras el
envío (da igual si el webhook fue con éxito o no — mismo comportamiento
que ya tenía con Slack, no se introduce lógica de reintento nueva).

### Errores del día -> tabla + segundo workflow

Nueva tabla `crawl_errors` (migración `006`): `id`, `competitor_name`,
`error_message`, `occurred_at`. En `main()`, donde hoy solo se hace
`errors.append(competitor["name"])` tras una excepción de
`crawl_competitor_products`, se añade `db.log_crawl_error(competitor_name,
str(exception))`.

El workflow de errores en n8n es independiente del webhook del resumen:
no depende de que el crawler llegue a ejecutarse con éxito ni de que el
webhook del resumen matutino funcione — así, si algo rompe el aviso de la
mañana, el aviso de la tarde no depende de ese mismo camino para avisar
de que algo falló. Consulta directamente el MySQL compartido (nodo MySQL
de n8n) filtrando `occurred_at` = hoy; si la consulta devuelve filas,
arma y manda el email, si no, el workflow termina sin enviar nada.

## Testing

- `tests/test_db.py`: test de `log_crawl_error` (mismo estilo mock/sin
  MySQL real que los tests actuales de `db.py`).
- `tests/test_main.py` o nuevo test de `notifier.py`: mockea la llamada
  HTTP al webhook, comprueba que el JSON enviado tiene la forma esperada
  (productos nuevos y eventos de precio con sus campos).
- Sin tests de Docker/Traefik/n8n en sí — se verifica a mano al desplegar,
  igual que ya se hizo con Traefik/n8n en `fitnesstech-infra`.
