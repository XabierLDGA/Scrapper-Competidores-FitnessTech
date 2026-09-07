"""Agregados derivados para el panel de vigilancia.

Todo lo de aqui son funciones puras sobre las filas que ya devuelve
`Database`: no toca la base de datos ni Flask. El dashboard se limita a
consultar y a pasar el resultado a la plantilla, de forma que el calculo
(que es donde se puede meter la pata) queda cubierto por tests.

Ninguna cifra que se muestra en el panel se inventa aqui: todas salen del
catalogo real o de los eventos de las ultimas 24 horas.
"""

import unicodedata
from datetime import date, datetime, timedelta
from statistics import median

# Tiendas propias del usuario (fitnesstech.es/.fr/.pt). Se vigilan igual que
# la competencia, pero no son competencia: el panel las separa.
OWN_STORES = {"Fitness Tech", "Fitness Tech FR", "Fitness Tech PT"}

# Un objetivo se considera "en linea" si se ha crawleado en las ultimas 48h:
# el crawler corre a diario, asi que dos vueltas sin datos es una senal real
# de que algo va mal, no un margen arbitrario.
LIVE_WINDOW = timedelta(hours=48)


def slugify(value: str) -> str:
    """Identificador estable para las URLs del panel (`#objetivo/<slug>`)."""
    normalized = unicodedata.normalize("NFKD", value or "")
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii").lower()
    return "-".join(part for part in ascii_only.replace("/", " ").split() if part)


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
            "is_own_store": name in OWN_STORES,
            # `last_crawled` se deja como venga de la BD para pintarlo; las
            # comparaciones usan la version normalizada, porque MySQL puede
            # devolver date en unas columnas y datetime en otras y mezclarlas
            # en un max() revienta la pagina entera.
            "last_crawled_at": last_crawled,
            "is_live": bool(last_crawled and now - last_crawled <= LIVE_WINDOW),
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
        target["event_count"] = sum(
            len(target[key])
            for key in ("new_products", "price_events",
                        "availability_events", "removed_products")
        )
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
        "last_crawled": max(
            (t["last_crawled_at"] for t in targets if t.get("last_crawled_at")),
            default=None,
        ),
    }


def _bool_o_none(value) -> bool | None:
    """MySQL devuelve 1/0 en unas filas y True/False en otras. La plantilla
    no deberia tener que distinguirlas, asi que el feed normaliza aqui."""
    return None if value is None else bool(value)


def build_change_feed(targets: list[dict]) -> list[dict]:
    """Aplana los cuatro tipos de evento de todos los objetivos en una sola
    lista, ordenada de mas reciente a mas antiguo.

    Es lo que alimenta la bandeja de la pantalla principal: la pregunta que
    se le hace al panel cada manana es "que se movio anoche", y esa
    respuesta no deberia estar repartida en cuatro tablas.

    No compone texto: guarda los valores y deja que la plantilla los pinte
    con los filtros de formato, para que el formato espanol viva en un solo
    sitio.
    """
    feed = []

    for target in targets:
        comun = {"store": target["name"],
                 "is_own_store": target["is_own_store"]}

        for event in target["price_events"]:
            feed.append({
                **comun,
                "kind": "price_down" if event.get("event_type") == "decrease" else "price_up",
                "sku": event.get("sku"),
                "title": event.get("title"),
                "url": event.get("url"),
                "when": _as_datetime(event.get("detected_at")),
                "old_price": event.get("old_price"),
                "new_price": event.get("new_price"),
                "pct": event.get("percent_change"),
                "was_available": None,
                "now_available": None,
                "last_seen": None,
            })

        for product in target["new_products"]:
            feed.append({
                **comun,
                "kind": "new",
                "sku": product.get("sku"),
                "title": product.get("title"),
                "url": product.get("url"),
                "when": _as_datetime(product.get("first_seen")),
                # Sin precio anterior: la plantilla pinta el precio suelto.
                "old_price": None,
                "new_price": product.get("price"),
                "pct": None,
                "was_available": None,
                "now_available": None,
                "last_seen": None,
            })

        for event in target["availability_events"]:
            feed.append({
                **comun,
                "kind": "stock",
                "sku": event.get("sku"),
                "title": event.get("title"),
                "url": event.get("url"),
                "when": _as_datetime(event.get("detected_at")),
                "old_price": None,
                "new_price": None,
                "pct": None,
                "was_available": _bool_o_none(event.get("was_available")),
                "now_available": _bool_o_none(event.get("now_available")),
                "last_seen": None,
            })

        for product in target["removed_products"]:
            feed.append({
                **comun,
                "kind": "removed",
                "sku": product.get("sku"),
                "title": product.get("title"),
                "url": product.get("url"),
                "when": _as_datetime(product.get("removed_at")),
                "old_price": None,
                "new_price": None,
                "pct": None,
                "was_available": None,
                "now_available": None,
                "last_seen": product.get("last_seen"),
            })

    # datetime.min para las fechas ilegibles: ordenar con None dentro de la
    # lista lanza TypeError y se lleva por delante la pagina entera. Van al
    # final, que es donde molestan menos.
    feed.sort(key=lambda c: c["when"] or datetime.min, reverse=True)
    return feed


def changes_since(feed: list[dict], since: datetime) -> list[dict]:
    """Recorta un feed de cambios a los posteriores a `since`.

    El panel pide a la BD una semana entera de eventos y saca de ahi las dos
    ventanas que ensena -24 horas y 7 dias-, en vez de consultar dos veces:
    la de un dia es siempre un subconjunto de la de la semana.

    Los cambios sin fecha legible se quedan fuera: si no se puede situar un
    evento en el tiempo, no hay razon para afirmar que es de hoy.
    """
    return [c for c in feed if c["when"] is not None and c["when"] >= since]


# ---------------------------------------------------------------------------
# Comparativa contra Titanium Strength
#
# El emparejamiento lo decide producto y vive en `titanium_pairs`; aqui solo
# se cruza con el catalogo vigente para ponerle precios de hoy. Se referencia
# a las tiendas por nombre y no por id: los ids son de la base de produccion
# y no significan nada en un test.
# ---------------------------------------------------------------------------

# `NOSOTROS` es la tienda espanola en concreto, no el conjunto `OWN_STORES`
# de mas arriba: la comparativa enfrenta precios de ES contra
# titaniumstrength.es, y colar aqui la de Francia o Portugal daria un lado
# nuestro de otro pais.
NOSOTROS = "Fitness Tech"
TITANIUM = "Titanium Strength"
SIN_EQUIVALENTE = "Sin equivalente"


def build_titanium_comparison(pairs: list[dict], catalog: list[dict]) -> list[dict]:
    """Los pares de producto resueltos contra el catalogo vigente, agrupados
    por gama y en el orden en que los dejo producto.

    `catalog` es lo que devuelve `get_latest_snapshots()`, que el panel ya
    consulta para las tiendas: esta pantalla no cuesta ni una consulta mas.
    """
    por_sku = {p["sku"]: p for p in catalog
               if p.get("competitor") == NOSOTROS and p.get("sku")}
    por_url = {p["url"]: p for p in catalog
               if p.get("competitor") == TITANIUM and p.get("url")}

    gamas: list[dict] = []
    for pair in pairs:
        nuestro = por_sku.get(pair["ft_sku"])
        suyo = por_url.get(pair["titanium_url"]) if pair.get("titanium_url") else None

        # El orden importa. `sin_equivalente` primero porque es un juicio de
        # producto y no un hueco en los datos. Y `fuera_catalogo` antes que
        # `sin_publicar` porque, si Titanium ha retirado la maquina, el par
        # esta muerto tengamos nosotros SKU publicado o no.
        if pair["equivalencia"] == SIN_EQUIVALENTE:
            estado = "sin_equivalente"
        elif suyo is None:
            estado = "fuera_catalogo"
        elif nuestro is None:
            estado = "sin_publicar"
        else:
            estado = "ok"

        delta = delta_pct = None
        if estado == "ok" and nuestro.get("price") is not None \
                and suyo.get("price") is not None:
            delta = nuestro["price"] - suyo["price"]
            if suyo["price"]:
                delta_pct = delta / suyo["price"] * 100

        if not gamas or gamas[-1]["gama"] != pair["gama"]:
            gamas.append({"gama": pair["gama"],
                          "slug": slugify(pair["gama"]),
                          "pares": []})

        gamas[-1]["pares"].append({
            # Los nombres son los del Excel y no los de las tiendas: producto
            # llama "Femoral Sentado" a lo que la web titula "Cuadriceps y
            # femoral | Maquina selectorizada dual - Compact Series", y en una
            # tabla de comparacion mandan los suyos.
            "ft_sku": pair["ft_sku"],
            "ft_title": pair["ft_title"],
            "ft_url": nuestro["url"] if nuestro else None,
            "ft_price": nuestro["price"] if nuestro else None,
            "titanium_title": pair["titanium_title"],
            "titanium_url": pair["titanium_url"],
            "titanium_price": suyo["price"] if suyo else None,
            "titanium_available": _bool_o_none(suyo["available"]) if suyo else None,
            "equivalencia": pair["equivalencia"],
            "observaciones": pair["observaciones"],
            "estado": estado,
            "delta": delta,
            "delta_pct": delta_pct,
        })

    return gamas


def titanium_metrics(gamas: list[dict], changes_week: list[dict]) -> dict:
    """Las cifras de cabecera de la comparativa."""
    pares = [p for g in gamas for p in g["pares"]]
    resueltos = [p for p in pares if p["delta"] is not None]
    pcts = [p["delta_pct"] for p in resueltos if p["delta_pct"] is not None]

    emparejadas = {p["titanium_url"] for p in pares if p["titanium_url"]}
    cambios = [c for c in changes_week
               if c.get("store") == TITANIUM and c.get("url") in emparejadas]

    return {
        "pares": len(resueltos),
        "mas_caros": sum(1 for p in resueltos if p["delta"] > 0),
        "mas_baratos": sum(1 for p in resueltos if p["delta"] < 0),
        # Mediana y no media, por lo mismo que en `target_metrics`: una prensa
        # de pierna 1.096 EUR por debajo desplazaria la media hasta hacerla
        # inutil.
        "delta_pct_mediano": median(pcts) if pcts else None,
        "cambios_semana": len(cambios),
    }
