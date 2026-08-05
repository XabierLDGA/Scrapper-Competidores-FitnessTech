from datetime import datetime, timezone

from scheduler import seconds_until_next_run


def test_seconds_until_next_run_before_target_today():
    now = datetime(2026, 8, 5, 3, 0, 0, tzinfo=timezone.utc)
    assert seconds_until_next_run(now, hour_utc=6) == 3 * 3600


def test_seconds_until_next_run_after_target_today_waits_until_tomorrow():
    now = datetime(2026, 8, 5, 9, 0, 0, tzinfo=timezone.utc)
    seconds = seconds_until_next_run(now, hour_utc=6)
    assert seconds == 21 * 3600


def test_seconds_until_next_run_exactly_at_target_waits_until_tomorrow():
    now = datetime(2026, 8, 5, 6, 0, 0, tzinfo=timezone.utc)
    seconds = seconds_until_next_run(now, hour_utc=6)
    assert seconds == 24 * 3600
