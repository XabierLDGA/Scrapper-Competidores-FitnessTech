from datetime import datetime
from zoneinfo import ZoneInfo

from scheduler import seconds_until_next_run

MADRID = ZoneInfo("Europe/Madrid")


def test_seconds_until_next_run_before_target_today():
    now = datetime(2026, 8, 5, 1, 0, 0, tzinfo=MADRID)
    assert seconds_until_next_run(now, hour_local=3) == 2 * 3600


def test_seconds_until_next_run_after_target_today_waits_until_tomorrow():
    now = datetime(2026, 8, 5, 9, 0, 0, tzinfo=MADRID)
    seconds = seconds_until_next_run(now, hour_local=3)
    assert seconds == 18 * 3600


def test_seconds_until_next_run_exactly_at_target_waits_until_tomorrow():
    now = datetime(2026, 8, 5, 3, 0, 0, tzinfo=MADRID)
    seconds = seconds_until_next_run(now, hour_local=3)
    assert seconds == 24 * 3600


def test_seconds_until_next_run_converts_from_utc():
    # 2026-08-05 00:30 UTC es 02:30 en Madrid en verano (CEST, UTC+2)
    now = datetime(2026, 8, 5, 0, 30, 0, tzinfo=ZoneInfo("UTC"))
    seconds = seconds_until_next_run(now, hour_local=3)
    assert seconds == 0.5 * 3600
