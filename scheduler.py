import asyncio
import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from main import main

logger = logging.getLogger(__name__)

# Dos pasadas al dia. La de las 03:00 es la de siempre: de madrugada las
# tiendas van descargadas y quedan horas de margen para reintentar antes de
# que salgan los correos de las 08:00. La de las 13:00 es para no esperar al
# dia siguiente a ver un cambio de precio de por la manana.
CRAWL_HOURS_LOCAL = (3, 13)
CRAWL_TIMEZONE = ZoneInfo("Europe/Madrid")


def seconds_until_next_run(now: datetime, hours_local: tuple[int, ...] = CRAWL_HOURS_LOCAL,
                            tz: ZoneInfo = CRAWL_TIMEZONE) -> float:
    """Segundos hasta la proxima de las horas de hours_local, en tz.

    Convierte 'now' a la zona horaria local antes de calcular, asi que
    respeta el cambio de hora de verano/invierno sin logica aparte. Una
    hora que hoy ya paso (o que es exactamente ahora) cuenta para manana,
    y de todas las candidatas se coge la mas cercana.
    """
    now_local = now.astimezone(tz)
    proximas = []
    for hour_local in hours_local:
        target = now_local.replace(hour=hour_local, minute=0, second=0, microsecond=0)
        if target <= now_local:
            target += timedelta(days=1)
        proximas.append(target)
    return (min(proximas) - now_local).total_seconds()


async def run_forever():
    """Ejecuta main() a cada una de las CRAWL_HOURS_LOCAL en CRAWL_TIMEZONE.

    Bucle simple en vez de un demonio cron dentro del contenedor: evita
    instalar cron y lidiar con sus quirks de logging/PID 1 en Docker.
    """
    while True:
        wait = seconds_until_next_run(datetime.now(timezone.utc))
        logger.info(f"Proximo crawl en {wait / 3600:.1f} horas")
        await asyncio.sleep(wait)
        await main()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    asyncio.run(run_forever())
