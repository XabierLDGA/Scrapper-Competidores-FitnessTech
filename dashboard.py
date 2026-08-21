import asyncio
import logging
import os
from datetime import date, datetime
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, flash, redirect, render_template, url_for

import main as crawl_main
from src.db import Database
from src.metrics import PRICE_BANDS, build_targets, global_metrics

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


def get_db() -> Database:
    return Database(
        host=os.getenv("DB_HOST", "localhost"),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", ""),
        database=os.getenv("DB_NAME", "competitor_monitor"),
        port=int(os.getenv("DB_PORT", "3306")),
    )


@app.route("/")
def index():
    db = get_db()
    targets = build_targets(
        competitors=db.get_competitor_stats(),
        new_products=db.get_recently_added_products(hours=24),
        price_events=db.get_recent_price_events(hours=24),
        availability_events=db.get_recent_availability_events(hours=24),
        removed_products=db.get_recently_removed_products(hours=24),
        catalog=db.get_latest_snapshots(),
    )
    return render_template(
        "dashboard.html",
        targets=targets,
        totals=global_metrics(targets),
        price_bands=PRICE_BANDS,
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
