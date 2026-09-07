import asyncio
import logging
import os
from datetime import date, datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, flash, redirect, render_template, url_for

import main as crawl_main
from src.db import Database
from src.metrics import (
    build_change_feed,
    build_targets,
    build_titanium_comparison,
    changes_since,
    global_metrics,
    titanium_metrics,
)

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-local-only")


class PrefixMiddleware:
    """Antepone SCRIPT_NAME a las URLs generadas por Flask (url_for, favicon,
    /static/...) cuando la app vive detras de un proxy que le quita un
    prefijo antes de reenviar la peticion (Traefik con stripprefix aqui).
    Sin esto, url_for genera rutas absolutas como /static/logos/x.png que
    no coinciden con el PathPrefix(/competencia) del router y dan 404."""

    def __init__(self, wsgi_app, prefix=""):
        self.wsgi_app = wsgi_app
        self.prefix = prefix

    def __call__(self, environ, start_response):
        if self.prefix:
            environ["SCRIPT_NAME"] = self.prefix
        return self.wsgi_app(environ, start_response)


app.wsgi_app = PrefixMiddleware(app.wsgi_app, prefix=os.getenv("SCRIPT_NAME", ""))

STATIC_DIR = Path(app.static_folder)


def asset(filename: str) -> str:
    """URL de un estatico con la fecha del fichero pegada, para que al
    desplegar una version nueva del CSS/JS el navegador no sirva la vieja
    de cache. Flask ya manda ETag, pero el proxy y los navegadores del
    equipo no siempre revalidan."""
    path = STATIC_DIR / filename
    stamp = int(path.stat().st_mtime) if path.exists() else 0
    return url_for("static", filename=filename, v=stamp)


app.jinja_env.globals["asset"] = asset


def _es_number(value: float, decimals: int) -> str:
    """Formato espanol: punto para los miles, coma para los decimales.
    Python solo sabe hacerlo al reves, asi que se intercambian al final."""
    formatted = f"{value:,.{decimals}f}"
    return formatted.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


@app.template_filter("miles")
def fmt_miles(value) -> str:
    return "—" if value is None else _es_number(value, 0)


@app.template_filter("pct")
def fmt_pct(value) -> str:
    return "—" if value is None else _es_number(value, 1)


@app.template_filter("eur")
def fmt_eur(value) -> str:
    return "—" if value is None else _es_number(value, 2) + " €"


@app.template_filter("fecha")
def fmt_fecha(value, with_time: bool = False) -> str:
    """Fecha en el formato corto que usa la consola (21.08.2026)."""
    if value is None:
        return "sin datos"
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            return value
    if isinstance(value, datetime):
        return value.strftime("%d.%m.%Y · %H:%M" if with_time else "%d.%m.%Y")
    if isinstance(value, date):
        return value.strftime("%d.%m.%Y")
    return str(value)


@app.template_filter("eur_signo")
def fmt_eur_signo(value) -> str:
    """Como `eur`, pero con el signo siempre delante. La diferencia contra
    Titanium no se entiende sin el: 204 y -204 se leerian igual."""
    if value is None:
        return "—"
    signo = "+" if value > 0 else "-" if value < 0 else ""
    return signo + _es_number(abs(value), 2) + " €"


@app.template_filter("pct_signo")
def fmt_pct_signo(value) -> str:
    if value is None:
        return "—"
    signo = "+" if value > 0 else "-" if value < 0 else ""
    return signo + _es_number(abs(value), 1) + " %"


def get_db() -> Database:
    return Database(
        host=os.getenv("DB_HOST", "localhost"),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", ""),
        database=os.getenv("DB_NAME", "competitor_monitor"),
        port=int(os.getenv("DB_PORT", "3306")),
    )


# El panel ensena dos ventanas de cambios: las ultimas 24 horas y la semana
# (que es la que resume el correo de n8n cada lunes). Se pide a la BD la
# semana entera una sola vez y la de un dia se recorta de ahi: consultar dos
# veces solo para quedarse con un subconjunto no tiene sentido.
WEEK_HOURS = 24 * 7


@app.route("/")
def index():
    db = get_db()
    # Se saca a variable porque ahora lo usan dos cosas: las tiendas y la
    # comparativa. Consultarlo dos veces serian 3.400 filas de mas por carga.
    catalog = db.get_latest_snapshots()
    targets = build_targets(
        competitors=db.get_competitor_stats(),
        new_products=db.get_recently_added_products(hours=WEEK_HOURS),
        price_events=db.get_recent_price_events(hours=WEEK_HOURS),
        availability_events=db.get_recent_availability_events(hours=WEEK_HOURS),
        removed_products=db.get_recently_removed_products(hours=WEEK_HOURS),
        catalog=catalog,
    )
    week = build_change_feed(targets)
    comparativa = build_titanium_comparison(db.get_titanium_pairs(), catalog)
    return render_template(
        "dashboard.html",
        targets=targets,
        totals=global_metrics(targets),
        changes=changes_since(week, datetime.now() - timedelta(hours=24)),
        changes_week=week,
        comparativa=comparativa,
        comparativa_totals=titanium_metrics(comparativa, week),
    )


@app.route("/crawl", methods=["POST"])
def trigger_crawl():
    try:
        summary = asyncio.run(crawl_main.main())
    except Exception:
        logger.exception("Error ejecutando el crawl")
        flash("La sincronizacion ha fallado. Revisa los logs del contenedor.", "error")
        return redirect(url_for("index"))

    message = (
        f"Sincronizacion completada: {summary['new_products']} productos nuevos, "
        f"{summary['pending_events']} cambios detectados."
    )
    if summary["errors"]:
        message += f" No se pudo leer: {', '.join(summary['errors'])}."
        flash(message, "error")
    else:
        flash(message, "success")

    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(debug=True, port=5000)
