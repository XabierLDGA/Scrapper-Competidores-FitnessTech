from datetime import datetime
from zoneinfo import ZoneInfo

from scheduler import CRAWL_HOURS_LOCAL, seconds_until_next_run

MADRID = ZoneInfo("Europe/Madrid")

UNA = (3,)


def test_seconds_until_next_run_before_target_today():
    now = datetime(2026, 8, 5, 1, 0, 0, tzinfo=MADRID)
    assert seconds_until_next_run(now, hours_local=UNA) == 2 * 3600


def test_seconds_until_next_run_after_target_today_waits_until_tomorrow():
    now = datetime(2026, 8, 5, 9, 0, 0, tzinfo=MADRID)
    seconds = seconds_until_next_run(now, hours_local=UNA)
    assert seconds == 18 * 3600


def test_seconds_until_next_run_exactly_at_target_waits_until_tomorrow():
    now = datetime(2026, 8, 5, 3, 0, 0, tzinfo=MADRID)
    seconds = seconds_until_next_run(now, hours_local=UNA)
    assert seconds == 24 * 3600


def test_seconds_until_next_run_converts_from_utc():
    # 2026-08-05 00:30 UTC es 02:30 en Madrid en verano (CEST, UTC+2)
    now = datetime(2026, 8, 5, 0, 30, 0, tzinfo=ZoneInfo("UTC"))
    seconds = seconds_until_next_run(now, hours_local=UNA)
    assert seconds == 0.5 * 3600


def test_con_dos_pasadas_coge_la_mas_cercana():
    # De madrugada toca la de las 03:00, no la de las 13:00.
    now = datetime(2026, 8, 5, 1, 0, 0, tzinfo=MADRID)
    assert seconds_until_next_run(now, hours_local=(3, 13)) == 2 * 3600


def test_entre_las_dos_pasadas_toca_la_segunda():
    now = datetime(2026, 8, 5, 9, 0, 0, tzinfo=MADRID)
    assert seconds_until_next_run(now, hours_local=(3, 13)) == 4 * 3600


def test_despues_de_la_ultima_pasada_toca_la_primera_de_manana():
    now = datetime(2026, 8, 5, 20, 0, 0, tzinfo=MADRID)
    assert seconds_until_next_run(now, hours_local=(3, 13)) == 7 * 3600


def test_justo_en_una_pasada_toca_la_siguiente_del_mismo_dia():
    # A las 03:00 en punto la de hoy ya cuenta como pasada, pero quedan 10
    # horas para la de las 13:00: no hay que esperar a manana.
    now = datetime(2026, 8, 5, 3, 0, 0, tzinfo=MADRID)
    assert seconds_until_next_run(now, hours_local=(3, 13)) == 10 * 3600


def test_el_orden_de_las_horas_da_igual():
    now = datetime(2026, 8, 5, 9, 0, 0, tzinfo=MADRID)
    assert (seconds_until_next_run(now, hours_local=(13, 3))
            == seconds_until_next_run(now, hours_local=(3, 13)))


def test_las_horas_por_defecto_son_las_dos_pasadas():
    assert CRAWL_HOURS_LOCAL == (3, 13)
