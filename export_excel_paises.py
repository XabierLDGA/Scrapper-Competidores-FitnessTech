"""Exporta a Excel el catalogo de Fitness Tech (ES, FR, PT) en 3 hojas, una por pais.

Script de uso manual desde el equipo local, nada del stack lo llama. Necesita openpyxl,
que no esta en requirements.txt a proposito para no meter la dependencia en la imagen.
"""

import os
from datetime import datetime

from dotenv import load_dotenv
from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter

from src.db import Database

load_dotenv()

# competidor -> (nombre de hoja, pais)
PAISES = {
    "Fitness Tech": "España",
    "Fitness Tech FR": "Francia",
    "Fitness Tech PT": "Portugal",
}

COLUMNAS = ["sku", "title", "series", "price", "price_original", "available", "url", "captured_at"]
CABECERAS = ["SKU", "Producto", "Serie", "Precio", "Precio original", "Disponible", "URL", "Actualizado"]


def get_db() -> Database:
    return Database(
        host=os.getenv("DB_HOST", "localhost"),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", ""),
        database=os.getenv("DB_NAME", "competitor_monitor"),
        port=int(os.getenv("DB_PORT", "3306")),
    )


def write_sheet(wb: Workbook, title: str, rows: list[dict]):
    ws = wb.create_sheet(title=title)
    ws.append(CABECERAS)
    for cell in ws[1]:
        cell.font = Font(bold=True)

    for row in rows:
        ws.append([row.get(c) for c in COLUMNAS])

    for i, header in enumerate(CABECERAS, start=1):
        col_key = COLUMNAS[i - 1]
        max_len = max(
            [len(str(header))] + [len(str(row.get(col_key, ""))) for row in rows]
        )
        ws.column_dimensions[get_column_letter(i)].width = min(max_len + 2, 60)

    ws.freeze_panes = "A2"


def main():
    db = get_db()
    snapshots = db.get_latest_snapshots()

    wb = Workbook()
    wb.remove(wb.active)

    for competitor, sheet_title in PAISES.items():
        rows = [r for r in snapshots if r.get("competitor") == competitor]
        rows.sort(key=lambda r: (r.get("title") or ""))
        write_sheet(wb, sheet_title, rows)
        print(f"{sheet_title}: {len(rows)} productos")

    out_dir = "exports"
    os.makedirs(out_dir, exist_ok=True)
    filename = os.path.join(out_dir, f"fitnesstech_es_fr_pt_{datetime.now():%Y%m%d_%H%M}.xlsx")
    wb.save(filename)
    print(f"Excel generado: {filename}")


if __name__ == "__main__":
    main()
