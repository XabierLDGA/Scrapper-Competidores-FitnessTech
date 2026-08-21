"""Agregados derivados para el panel de vigilancia.

Todo lo de aqui son funciones puras sobre las filas que ya devuelve
`Database`: no toca la base de datos ni Flask. El dashboard se limita a
consultar y a pasar el resultado a la plantilla, de forma que el calculo
(que es donde se puede meter la pata) queda cubierto por tests.

Ninguna cifra que se muestra en el panel se inventa aqui: todas salen del
catalogo real o de los eventos de las ultimas 24 horas.
"""

import math
import unicodedata
from bisect import bisect_right
from datetime import date, datetime, timedelta
from statistics import median

# Tiendas propias del usuario (fitnesstech.es/.fr/.pt). Se vigilan igual que
# la competencia, pero no son competencia: el panel las separa.
OWN_STORES = {"Fitness Tech", "Fitness Tech FR", "Fitness Tech PT"}

COMPETITOR_LOGOS = {
    "Fitness Tech": "fitnesstech-es.png",
    "Fitness Tech FR": "fitnesstech-fr.png",
    "Fitness Tech PT": "fitnesstech-pt.png",
    "Titanium Strength": "titanium-strength.png",
}

# Un objetivo se considera "en linea" si se ha crawleado en las ultimas 48h:
# el crawler corre a diario, asi que dos vueltas sin datos es una senal real
# de que algo va mal, no un margen arbitrario.
LIVE_WINDOW = timedelta(hours=48)

# Tramos de precio del mapa de posicionamiento. Los cortes estan elegidos
# sobre el catalogo real: separan accesorio (<50) de material de sala
# (100-500) y de maquina grande (1k+), que es donde esta la frontera entre
# el surtido propio y el de Titanium Strength.
PRICE_BANDS = [
    (0, 50, "< 50"),
    (50, 100, "50-100"),
    (100, 250, "100-250"),
    (250, 500, "250-500"),
    (500, 1000, "500-1k"),
    (1000, 2500, "1k-2,5k"),
    (2500, None, "2,5k +"),
]
_BAND_EDGES = [low for low, _, _ in PRICE_BANDS]

# Pasos de la rampa ambar del mapa de calor (0 = tramo vacio, sin pintar).
HEAT_LEVELS = 6

# Exponente de la escala de color del mapa. Con reparto lineal casi todas
# las celdas caian en los pasos centrales y el mapa se leia como un tablero
# encendido, sin decir nada. Por encima de 1 la escala empuja las cuotas
# medias hacia abajo, y solo la concentracion real destaca -que es
# justamente lo que hay que ver: donde amontona su catalogo cada tienda.
# El valor exacto de cada celda no se pierde: va impreso en la propia celda
# y en la lectura del cursor.
HEAT_GAMMA = 1.5


def slugify(value: str) -> str:
    """Identificador estable para las URLs del panel (`#objetivo/<slug>`)."""
    normalized = unicodedata.normalize("NFKD", value or "")
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii").lower()
    return "-".join(part for part in ascii_only.replace("/", " ").split() if part)


def target_code(name: str, country: str | None) -> str:
    """Codigo corto de un objetivo, del estilo `TS·ES`.

    Se deriva del nombre y el pais reales, sin inventar nomenclatura: las
    iniciales de las palabras del nombre mas el pais. Si el nombre ya
    termina en el pais ("Fitness Tech FR") no se cuenta dos veces.
    """
    words = (name or "").split()
    if country and words and words[-1].upper() == country.upper():
        words = words[:-1]

    if not words:
        initials = "?"
    elif len(words) == 1:
        initials = words[0][:2].upper()
    else:
        initials = "".join(word[0] for word in words[:3]).upper()

    return f"{initials}·{country.upper()}" if country else initials


def price_histogram(products: list[dict]) -> list[dict]:
    """Reparto del catalogo por tramo de precio, en unidades y en cuota.

    La cuota se calcula sobre los productos *con precio* del propio
    objetivo, no sobre el total del panel: asi dos tiendas de tamano
    distinto son comparables fila con fila.
    """
    prices = [p["price"] for p in products if p.get("price") is not None]
    counts = [0] * len(PRICE_BANDS)
    for price in prices:
        # max(0, ...) por si llegase un precio negativo: sin el, bisect da
        # indice -1 y el producto acabaria contado en el tramo mas caro.
        counts[max(0, bisect_right(_BAND_EDGES, price) - 1)] += 1

    total = len(prices)
    return [
        {
            "label": label,
            "low": low,
            "high": high,
            "count": count,
            "share": count / total if total else 0,
            "level": 0,
        }
        for (low, high, label), count in zip(PRICE_BANDS, counts)
    ]


def target_metrics(catalog: list[dict]) -> dict:
    """Cifras de cabecera de un objetivo, todas sobre su catalogo vigente."""
    total = len(catalog)
    available = sum(1 for p in catalog if p.get("available"))
    promo = sum(
        1
        for p in catalog
        if p.get("price") is not None
        and p.get("price_original") is not None
        and p["price_original"] > p["price"]
    )
    prices = [p["price"] for p in catalog if p.get("price") is not None]

    return {
        "total": total,
        "available": available,
        "availability_pct": available / total * 100 if total else 0,
        "promo": promo,
        "promo_pct": promo / total * 100 if total else 0,
        # Mediana y no media: los catalogos van de 3 EUR a 9.995 EUR y unas
        # pocas maquinas grandes desplazarian la media hasta hacerla inutil.
        "median_price": median(prices) if prices else None,
        "max_price": max(prices) if prices else None,
    }


def _as_datetime(value) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None


def _apply_heat_levels(targets: list[dict]) -> None:
    """Escala los tramos de todos los objetivos contra la cuota mas alta del
    panel, para que una celda oscura signifique lo mismo en todas las filas.

    Normalizar fila a fila haria que el tramo mayor de cada tienda saliese
    siempre al maximo, y el mapa dejaria de comparar nada.
    """
    shares = [band["share"] for t in targets for band in t["histogram"]]
    top = max(shares, default=0)
    for target in targets:
        for band in target["histogram"]:
            if band["share"] <= 0 or top <= 0:
                band["level"] = 0
            else:
                intensidad = (band["share"] / top) ** HEAT_GAMMA
                band["level"] = min(
                    HEAT_LEVELS, max(1, math.ceil(intensidad * HEAT_LEVELS))
                )


def build_targets(competitors: list[dict], new_products: list[dict],
                  price_events: list[dict], availability_events: list[dict],
                  removed_products: list[dict], catalog: list[dict],
                  now: datetime | None = None) -> list[dict]:
    """Convierte las seis listas planas de la BD en un objetivo por tienda.

    La competencia externa va primero: es lo que de verdad se vigila, y las
    tiendas propias se miran despues como contraste.
    """
    now = now or datetime.now()

    targets = {}
    for competitor in competitors:
        name = competitor["name"]
        last_crawled = _as_datetime(competitor.get("last_crawled"))
        targets[name] = {
            **competitor,
            "slug": slugify(name),
            "code": target_code(name, competitor.get("country")),
            "is_own_store": name in OWN_STORES,
            # `last_crawled` se deja como venga de la BD para pintarlo; las
            # comparaciones usan la version normalizada, porque MySQL puede
            # devolver date en unas columnas y datetime en otras y mezclarlas
            # en un max() revienta la pagina entera.
            "last_crawled_at": last_crawled,
            "is_live": bool(last_crawled and now - last_crawled <= LIVE_WINDOW),
            "logo": COMPETITOR_LOGOS.get(name),
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
            target = targets.get(row["competitor"])
            if target is not None:
                target[key].append(row)

    ordered = sorted(targets.values(), key=lambda t: (t["is_own_store"], t["name"]))
    for target in ordered:
        target["metrics"] = target_metrics(target["catalog"])
        target["histogram"] = price_histogram(target["catalog"])
        target["event_count"] = sum(
            len(target[key])
            for key in ("new_products", "price_events",
                        "availability_events", "removed_products")
        )
    _apply_heat_levels(ordered)
    return ordered


def global_metrics(targets: list[dict]) -> dict:
    """Totales del panel: la suma de los objetivos, sin dobles conteos."""
    products = sum(t["metrics"]["total"] for t in targets)
    available = sum(t["metrics"]["available"] for t in targets)
    promo = sum(t["metrics"]["promo"] for t in targets)

    return {
        "products": products,
        "targets": len(targets),
        "live_targets": sum(1 for t in targets if t["is_live"]),
        "availability_pct": available / products * 100 if products else 0,
        "promo_pct": promo / products * 100 if products else 0,
        "events": sum(t["event_count"] for t in targets),
        # Cuota mas alta del mapa de calor: es contra esta contra la que se
        # escalan las celdas, asi que la leyenda tiene que poder citarla.
        "top_share": max(
            (band["share"] for t in targets for band in t["histogram"]),
            default=0,
        ),
        "last_crawled": max(
            (t["last_crawled_at"] for t in targets if t.get("last_crawled_at")),
            default=None,
        ),
    }
