import os

from dotenv import load_dotenv
from flask import Flask, render_template

from src.db import Database

load_dotenv()

app = Flask(__name__)


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
    return render_template(
        "dashboard.html",
        competitors=db.get_competitor_stats(),
        new_products=db.get_recently_added_products(hours=24),
        events=db.get_recent_price_events(hours=24),
        availability_events=db.get_recent_availability_events(hours=24),
        removed_products=db.get_recently_removed_products(hours=24),
        products=db.get_latest_snapshots(),
    )


if __name__ == "__main__":
    app.run(debug=True, port=5000)
