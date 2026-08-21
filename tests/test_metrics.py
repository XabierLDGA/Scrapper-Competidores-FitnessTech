from src.metrics import (
    HEAT_LEVELS,
    PRICE_BANDS,
    build_targets,
    global_metrics,
    price_histogram,
    target_code,
    target_metrics,
)


def _product(price=100.0, original=None, available=True, competitor="Acme"):
    return {
        "competitor": competitor,
        "title": "Producto",
        "sku": "SKU-1",
        "url": "https://example.com/p",
        "price": price,
        "price_original": original,
        "available": available,
        "captured_at": "2026-08-21",
    }


# ---------- codigos de objetivo ----------

def test_target_code_usa_iniciales_y_pais():
    assert target_code("Titanium Strength", "ES") == "TS·ES"


def test_target_code_no_repite_el_pais_que_ya_va_en_el_nombre():
    # "Fitness Tech FR" ya lleva el pais al final: no debe salir "FTF-FR"
    assert target_code("Fitness Tech FR", "FR") == "FT·FR"


def test_target_code_con_nombre_de_una_palabra():
    assert target_code("Decathlon", "ES") == "DE·ES"


def test_target_code_sin_pais():
    assert target_code("Titanium Strength", None) == "TS"


# ---------- histograma de precio ----------

def test_price_histogram_devuelve_un_tramo_por_banda_definida():
    assert len(price_histogram([])) == len(PRICE_BANDS)


def test_price_histogram_reparte_cada_precio_en_su_tramo():
    products = [
        _product(price=10.0),      # <50
        _product(price=49.99),     # <50
        _product(price=50.0),      # 50-100  (el limite entra en el tramo de arriba)
        _product(price=1500.0),    # 1k-2.5k
        _product(price=9000.0),    # 2.5k+
    ]

    counts = [band["count"] for band in price_histogram(products)]

    assert counts == [2, 1, 0, 0, 0, 1, 1]


def test_price_histogram_calcula_la_cuota_sobre_el_catalogo_con_precio():
    products = [_product(price=10.0), _product(price=10.0), _product(price=3000.0)]

    bands = price_histogram(products)

    assert bands[0]["share"] == 2 / 3
    assert bands[-1]["share"] == 1 / 3


def test_price_histogram_ignora_productos_sin_precio():
    bands = price_histogram([_product(price=None), _product(price=10.0)])

    assert bands[0]["count"] == 1
    assert bands[0]["share"] == 1.0


def test_price_histogram_sin_productos_deja_las_cuotas_a_cero():
    assert all(band["share"] == 0 for band in price_histogram([]))


def test_price_histogram_mete_un_precio_negativo_en_el_tramo_mas_bajo():
    # Un precio negativo es un dato corrupto, pero no puede acabar contado
    # como maquina de gama alta.
    bands = price_histogram([_product(price=-10.0)])

    assert bands[0]["count"] == 1
    assert bands[-1]["count"] == 0


# ---------- metricas por objetivo ----------

def test_target_metrics_cuenta_catalogo_y_disponibilidad():
    products = [_product(available=True), _product(available=True), _product(available=False)]

    m = target_metrics(products)

    assert m["total"] == 3
    assert m["available"] == 2
    assert m["availability_pct"] == 2 / 3 * 100


def test_target_metrics_cuenta_promociones_por_precio_tachado():
    products = [
        _product(price=80.0, original=100.0),   # rebajado
        _product(price=100.0, original=100.0),  # mismo precio, no es promo
        _product(price=100.0, original=None),   # sin precio original
    ]

    m = target_metrics(products)

    assert m["promo"] == 1
    assert m["promo_pct"] == 1 / 3 * 100


def test_target_metrics_usa_la_mediana_no_la_media():
    # Con catalogos tan sesgados (de 3 EUR a 9000 EUR) la media enganaria.
    products = [_product(price=10.0), _product(price=20.0), _product(price=3000.0)]

    assert target_metrics(products)["median_price"] == 20.0


def test_target_metrics_con_catalogo_vacio_no_divide_por_cero():
    m = target_metrics([])

    assert m["total"] == 0
    assert m["availability_pct"] == 0
    assert m["promo_pct"] == 0
    assert m["median_price"] is None


# ---------- montaje de objetivos ----------

def _competitor(name, country="ES", total=10):
    return {
        "id": 1,
        "name": name,
        "website_url": f"https://{name.lower().replace(' ', '')}.example",
        "country": country,
        "platform": "shopify",
        "total_products": total,
        "last_crawled": "2026-08-21",
    }


def test_build_targets_agrupa_las_filas_planas_por_competidor():
    targets = build_targets(
        competitors=[_competitor("Acme"), _competitor("Rival")],
        new_products=[{"competitor": "Acme", "title": "X"}],
        price_events=[],
        availability_events=[],
        removed_products=[],
        catalog=[_product(competitor="Acme"), _product(competitor="Rival")],
    )

    por_nombre = {t["name"]: t for t in targets}
    assert len(por_nombre["Acme"]["new_products"]) == 1
    assert len(por_nombre["Rival"]["new_products"]) == 0
    assert len(por_nombre["Acme"]["catalog"]) == 1


def test_build_targets_descarta_filas_de_competidores_desconocidos():
    targets = build_targets(
        competitors=[_competitor("Acme")],
        new_products=[{"competitor": "Fantasma", "title": "X"}],
        price_events=[],
        availability_events=[],
        removed_products=[],
        catalog=[],
    )

    assert targets[0]["new_products"] == []


def test_build_targets_marca_las_tiendas_propias():
    targets = build_targets(
        competitors=[_competitor("Fitness Tech"), _competitor("Titanium Strength")],
        new_products=[], price_events=[], availability_events=[],
        removed_products=[], catalog=[],
    )

    por_nombre = {t["name"]: t for t in targets}
    assert por_nombre["Fitness Tech"]["is_own_store"] is True
    assert por_nombre["Titanium Strength"]["is_own_store"] is False


def test_build_targets_pone_la_competencia_externa_primero():
    # El rival externo es lo que se vigila de verdad: encabeza la lista.
    targets = build_targets(
        competitors=[_competitor("Fitness Tech"), _competitor("Titanium Strength")],
        new_products=[], price_events=[], availability_events=[],
        removed_products=[], catalog=[],
    )

    assert targets[0]["name"] == "Titanium Strength"


def test_build_targets_genera_slug_estable_para_la_url():
    targets = build_targets(
        competitors=[_competitor("Fitness Tech FR", country="FR")],
        new_products=[], price_events=[], availability_events=[],
        removed_products=[], catalog=[],
    )

    assert targets[0]["slug"] == "fitness-tech-fr"


def test_build_targets_adjunta_metricas_e_histograma():
    targets = build_targets(
        competitors=[_competitor("Acme")],
        new_products=[], price_events=[], availability_events=[],
        removed_products=[],
        catalog=[_product(competitor="Acme", price=30.0)],
    )

    assert targets[0]["metrics"]["total"] == 1
    assert targets[0]["histogram"][0]["count"] == 1


def test_build_targets_marca_como_activo_solo_lo_crawleado_hace_poco():
    from datetime import datetime, timedelta

    reciente = _competitor("Reciente")
    reciente["last_crawled"] = datetime(2026, 8, 21, 3, 0)
    viejo = _competitor("Viejo")
    viejo["last_crawled"] = datetime(2026, 8, 21, 3, 0) - timedelta(days=10)

    targets = build_targets(
        competitors=[reciente, viejo],
        new_products=[], price_events=[], availability_events=[],
        removed_products=[], catalog=[],
        now=datetime(2026, 8, 21, 12, 0),
    )

    por_nombre = {t["name"]: t for t in targets}
    assert por_nombre["Reciente"]["is_live"] is True
    assert por_nombre["Viejo"]["is_live"] is False


def test_build_targets_sin_fecha_de_crawl_no_esta_activo():
    sin_crawl = _competitor("Nuevo")
    sin_crawl["last_crawled"] = None

    targets = build_targets(
        competitors=[sin_crawl], new_products=[], price_events=[],
        availability_events=[], removed_products=[], catalog=[],
    )

    assert targets[0]["is_live"] is False


# ---------- intensidad del mapa de calor ----------

def _catalogo(competitor, precios):
    return [_product(competitor=competitor, price=p) for p in precios]


def test_heat_levels_da_la_intensidad_maxima_al_tramo_mas_cargado():
    targets = build_targets(
        competitors=[_competitor("Acme")],
        new_products=[], price_events=[], availability_events=[],
        removed_products=[],
        catalog=_catalogo("Acme", [10.0, 10.0, 10.0, 3000.0]),
    )

    niveles = [band["level"] for band in targets[0]["histogram"]]
    assert max(niveles) == HEAT_LEVELS


def test_heat_levels_deja_a_cero_los_tramos_vacios():
    targets = build_targets(
        competitors=[_competitor("Acme")],
        new_products=[], price_events=[], availability_events=[],
        removed_products=[],
        catalog=_catalogo("Acme", [10.0]),
    )

    bands = targets[0]["histogram"]
    assert bands[0]["level"] >= 1
    assert all(b["level"] == 0 for b in bands[1:])


def test_heat_levels_se_normalizan_entre_objetivos_no_dentro_de_cada_uno():
    # Dos objetivos con la misma cuota en el mismo tramo tienen que pintarse
    # igual; si se normalizase por fila, el de catalogo pequeno enganaria.
    targets = build_targets(
        competitors=[_competitor("Grande"), _competitor("Pequeno")],
        new_products=[], price_events=[], availability_events=[],
        removed_products=[],
        catalog=(
            _catalogo("Grande", [10.0] * 8 + [3000.0] * 2)
            + _catalogo("Pequeno", [10.0] * 4 + [3000.0])
        ),
    )

    por_nombre = {t["name"]: t for t in targets}
    grande = por_nombre["Grande"]["histogram"]
    pequeno = por_nombre["Pequeno"]["histogram"]
    # Grande: 80% en <50. Pequeno: 80% en <50. Misma cuota -> mismo nivel.
    assert grande[0]["level"] == pequeno[0]["level"]
    # Pequeno tiene mas cuota en 2.5k+ (20% vs 20%): tambien empatan.
    assert grande[-1]["level"] == pequeno[-1]["level"]


def test_heat_levels_no_son_lineales_para_que_destaque_la_concentracion():
    # Con reparto lineal casi todas las celdas caian en los pasos centrales y
    # el mapa se leia como un tablero encendido. Un tramo con la cuarta parte
    # de la cuota mas alta tiene que caer al paso mas bajo, no al segundo,
    # que es lo que daria una escala lineal (ceil(0,25 * 6) = 2).
    targets = build_targets(
        competitors=[_competitor("Acme")],
        new_products=[], price_events=[], availability_events=[],
        removed_products=[],
        catalog=_catalogo("Acme", [10.0] * 8 + [3000.0] * 2),
    )

    bands = {b["label"]: b for b in targets[0]["histogram"]}
    assert bands["< 50"]["level"] == HEAT_LEVELS  # 80%, el maximo
    assert bands["2,5k +"]["level"] == 1          # 20%, un cuarto del maximo


def test_heat_levels_sin_datos_no_revienta():
    targets = build_targets(
        competitors=[_competitor("Vacio")],
        new_products=[], price_events=[], availability_events=[],
        removed_products=[], catalog=[],
    )

    assert all(b["level"] == 0 for b in targets[0]["histogram"])


# ---------- metricas globales ----------

def test_global_metrics_suma_los_catalogos_de_todos_los_objetivos():
    targets = build_targets(
        competitors=[_competitor("Acme"), _competitor("Rival")],
        new_products=[], price_events=[], availability_events=[],
        removed_products=[],
        catalog=[
            _product(competitor="Acme", available=True),
            _product(competitor="Acme", available=False),
            _product(competitor="Rival", available=True),
        ],
    )

    g = global_metrics(targets)

    assert g["products"] == 3
    assert g["targets"] == 2
    assert g["availability_pct"] == 2 / 3 * 100


def test_global_metrics_cuenta_los_eventos_de_las_ultimas_24h():
    targets = build_targets(
        competitors=[_competitor("Acme")],
        new_products=[{"competitor": "Acme"}, {"competitor": "Acme"}],
        price_events=[{"competitor": "Acme"}],
        availability_events=[],
        removed_products=[{"competitor": "Acme"}],
        catalog=[],
    )

    g = global_metrics(targets)

    assert g["events"] == 4


def test_global_metrics_admite_fechas_de_tipos_mezclados():
    # MySQL devuelve date en unas columnas y datetime en otras; compararlas
    # entre si lanza TypeError y tumbaba la pagina entera.
    from datetime import date, datetime

    uno = _competitor("Uno")
    uno["last_crawled"] = date(2026, 8, 20)
    otro = _competitor("Otro")
    otro["last_crawled"] = datetime(2026, 8, 21, 3, 0)

    g = global_metrics(build_targets(
        competitors=[uno, otro], new_products=[], price_events=[],
        availability_events=[], removed_products=[], catalog=[],
    ))

    assert g["last_crawled"] == datetime(2026, 8, 21, 3, 0)


def test_global_metrics_sin_ninguna_fecha_de_crawl():
    sin_fecha = _competitor("Nuevo")
    sin_fecha["last_crawled"] = None

    g = global_metrics(build_targets(
        competitors=[sin_fecha], new_products=[], price_events=[],
        availability_events=[], removed_products=[], catalog=[],
    ))

    assert g["last_crawled"] is None


def test_global_metrics_sin_objetivos_no_divide_por_cero():
    g = global_metrics([])

    assert g["products"] == 0
    assert g["availability_pct"] == 0
