import asyncio
import logging
from datetime import datetime, timedelta, timezone

from main import main

logger = logging.getLogger(__name__)

CRAWL_HOUR_UTC = 6


def seconds_until_next_run(now: datetime, hour_utc: int = CRAWL_HOUR_UTC) -> float:
    """Segundos hasta la proxima ejecucion a hour_utc:00 UTC.

    Si 'now' ya paso esa hora hoy, calcula para manana.
    """
    target = now.replace(hour=hour_utc, minute=0, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


async def run_forever():
    """Ejecuta main() una vez al dia, a las CRAWL_HOUR_UTC:00 UTC.

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
