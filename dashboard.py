import asyncio
import logging
import os

from dotenv import load_dotenv
from flask import Flask, flash, redirect, render_template, url_for

import main as crawl_main
from src.db import Database

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-local-only")

OWN_STORES = {"Fitness Tech", "Fitness Tech FR", "Fitness Tech PT"}
COMPETITOR_LOGOS = {
    "Fitness Tech": "fitnesstech-es.png",
    "Fitness Tech FR": "fitnesstech-fr.png",
    "Fitness Tech PT": "fitnesstech-pt.png",
    "Titanium Strength": "titanium-strength.png",
}


def _build_competitor_groups(competitors, new_products, price_events,
                              availability_events, removed_products, catalog):
    """Agrupa las listas planas de la BD (una fila por producto/evento, sin
    distinguir competidor) en una lista por competidor, para las tarjetas
    de la landing del dashboard."""
    groups = {}
    for c in competitors:
        groups[c["name"]] = {
            **c,
            "is_own_store": c["name"] in OWN_STORES,
            "logo": COMPETITOR_LOGOS.get(c["name"]),
            "new_products": [],
            "price_events": [],
            "availability_events": [],
            "removed_products": [],
            "catalog": [],
        }

    for key, rows in (
        ("new_products", new_products),
        ("price_events", price_events),
        ("availability_events", availability_events),
        ("removed_products", removed_products),
        ("catalog", catalog),
    ):
        for row in rows:
            group = groups.get(row["competitor"])
            if group is not None:
                group[key].append(row)

    return sorted(groups.values(), key=lambda g: g["name"])


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
    competitor_groups = _build_competitor_groups(
        db.get_competitor_stats(),
        db.get_recently_added_products(hours=24),
        db.get_recent_price_events(hours=24),
        db.get_recent_availability_events(hours=24),
        db.get_recently_removed_products(hours=24),
        db.get_latest_snapshots(),
    )
    return render_template("dashboard.html", competitor_groups=competitor_groups)


@app.route("/crawl", methods=["POST"])
def trigger_crawl():
    try:
        summary = asyncio.run(crawl_main.main())
    except Exception:
        logger.exception("Error ejecutando el crawl")
        flash("Error al ejecutar el crawl. Revisa los logs de la consola.", "error")
        return redirect(url_for("index"))

    message = (
        f"Crawl completado: {summary['new_products']} productos nuevos, "
        f"{summary['pending_events']} eventos pendientes."
    )
    if summary["errors"]:
        message += f" Fallo al crawlear: {', '.join(summary['errors'])}."
        flash(message, "error")
    else:
        flash(message, "success")

    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(debug=True, port=5000)
