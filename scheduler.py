import asyncio
import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from main import main

logger = logging.getLogger(__name__)

CRAWL_HOUR_LOCAL = 3
CRAWL_TIMEZONE = ZoneInfo("Europe/Madrid")


def seconds_until_next_run(now: datetime, hour_local: int = CRAWL_HOUR_LOCAL,
                            tz: ZoneInfo = CRAWL_TIMEZONE) -> float:
    """Segundos hasta la proxima ejecucion a hour_local:00 en tz.

    Convierte 'now' a la zona horaria local antes de calcular, asi que
    respeta el cambio de hora de verano/invierno sin logica aparte. Si
    'now' ya paso esa hora hoy (en local), calcula para manana.
    """
    now_local = now.astimezone(tz)
    target = now_local.replace(hour=hour_local, minute=0, second=0, microsecond=0)
    if target <= now_local:
        target += timedelta(days=1)
    return (target - now_local).total_seconds()


async def run_forever():
    """Ejecuta main() una vez al dia, a las CRAWL_HOUR_LOCAL:00 en CRAWL_TIMEZONE.

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
