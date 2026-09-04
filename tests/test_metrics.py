from datetime import date, datetime

from src.metrics import (
    build_change_feed,
    changes_since,
    build_targets,
    global_metrics,
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


def test_build_targets_adjunta_las_metricas():
    targets = build_targets(
        competitors=[_competitor("Acme")],
        new_products=[], price_events=[], availability_events=[],
        removed_products=[],
        catalog=[_product(competitor="Acme", price=30.0)],
    )

    assert targets[0]["metrics"]["total"] == 1


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


# ---------- feed de cambios ----------

def _targets_con(**listas):
    """Monta un objetivo unico ('Acme') con las listas de eventos que se le
    pasen, para no repetir el andamiaje en cada test del feed."""
    return build_targets(
        competitors=[_competitor("Acme")],
        new_products=listas.get("new_products", []),
        price_events=listas.get("price_events", []),
        availability_events=listas.get("availability_events", []),
        removed_products=listas.get("removed_products", []),
        catalog=[],
    )


def _evento_precio(tipo="decrease", old=1499.0, new=1279.0, pct=-14.7,
                   cuando="2026-09-04T03:12:00", competitor="Acme"):
    return {
        "competitor": competitor, "title": "Half Rack HD", "sku": "TS-HR-HD",
        "event_type": tipo, "old_price": old, "new_price": new,
        "percent_change": pct, "detected_at": cuando,
    }


def test_change_feed_parte_los_eventos_de_precio_por_direccion():
    feed = build_change_feed(_targets_con(price_events=[
        _evento_precio(tipo="decrease"),
        _evento_precio(tipo="increase", old=2790.0, new=2990.0, pct=7.2),
    ]))

    assert {c["kind"] for c in feed} == {"price_down", "price_up"}


def test_change_feed_lleva_los_precios_y_el_porcentaje():
    feed = build_change_feed(_targets_con(price_events=[_evento_precio()]))

    cambio = feed[0]
    assert cambio["old_price"] == 1499.0
    assert cambio["new_price"] == 1279.0
    assert cambio["pct"] == -14.7
    assert cambio["was_available"] is None
    assert cambio["last_seen"] is None


def test_change_feed_las_altas_traen_precio_sin_precio_anterior():
    # La plantilla pinta "antes -> ahora" solo si hay old_price: un alta
    # tiene que dejarlo a None para que salga el precio suelto.
    feed = build_change_feed(_targets_con(new_products=[{
        "competitor": "Acme", "title": "Rack FT Pro", "sku": "FT-RK-20",
        "url": "https://example.com/rack", "price": 1190.0,
        "first_seen": "2026-09-04T03:07:00",
    }]))

    assert feed[0]["kind"] == "new"
    assert feed[0]["new_price"] == 1190.0
    assert feed[0]["old_price"] is None


def test_change_feed_lleva_el_antes_y_el_despues_de_disponibilidad():
    feed = build_change_feed(_targets_con(availability_events=[{
        "competitor": "Acme", "title": "Mancuernas hex", "sku": "TS-MH-30",
        "url": "https://example.com/mh", "was_available": 1,
        "now_available": False, "detected_at": "2026-09-04T03:12:00",
    }]))

    assert feed[0]["kind"] == "stock"
    # La BD devuelve 1/0 en unas filas y True/False en otras: el feed
    # normaliza a bool para que la plantilla no tenga que adivinar.
    assert feed[0]["was_available"] is True
    assert feed[0]["now_available"] is False


def test_change_feed_las_bajas_traen_la_ultima_vez_que_se_vio():
    feed = build_change_feed(_targets_con(removed_products=[{
        "competitor": "Acme", "title": "Banco plano", "sku": "TS-BP",
        "url": "https://example.com/bp", "last_seen": date(2026, 8, 31),
        "removed_at": "2026-09-04T03:12:00",
    }]))

    assert feed[0]["kind"] == "removed"
    assert feed[0]["last_seen"] == date(2026, 8, 31)


def test_change_feed_ordena_por_fecha_descendente_mezclando_tipos():
    feed = build_change_feed(_targets_con(
        price_events=[_evento_precio(cuando="2026-09-04T01:00:00")],
        new_products=[{"competitor": "Acme", "title": "Nuevo", "sku": None,
                       "url": None, "price": 10.0,
                       "first_seen": "2026-09-04T05:00:00"}],
        availability_events=[{"competitor": "Acme", "title": "Stock",
                              "sku": None, "url": None, "was_available": 0,
                              "now_available": 1,
                              "detected_at": "2026-09-04T03:00:00"}],
    ))

    assert [c["title"] for c in feed] == ["Nuevo", "Stock", "Half Rack HD"]


def test_change_feed_ordena_fechas_de_tipos_mezclados():
    # MySQL devuelve date en unas columnas y datetime en otras; compararlas
    # entre si revienta la pagina entera.
    feed = build_change_feed(_targets_con(
        removed_products=[{"competitor": "Acme", "title": "Baja",
                           "sku": None, "url": None, "last_seen": None,
                           "removed_at": date(2026, 9, 4)}],
        price_events=[_evento_precio(cuando=datetime(2026, 9, 3, 3, 12))],
    ))

    assert [c["title"] for c in feed] == ["Baja", "Half Rack HD"]


def test_change_feed_manda_al_final_lo_que_no_tiene_fecha_legible():
    feed = build_change_feed(_targets_con(
        price_events=[_evento_precio(cuando="ayer por la tarde")],
        new_products=[{"competitor": "Acme", "title": "Con fecha",
                       "sku": None, "url": None, "price": 10.0,
                       "first_seen": "2026-09-01T03:00:00"}],
    ))

    assert [c["title"] for c in feed] == ["Con fecha", "Half Rack HD"]
    assert feed[-1]["when"] is None


def test_change_feed_mezcla_las_tiendas_y_marca_las_propias():
    targets = build_targets(
        competitors=[_competitor("Titanium Strength"),
                     _competitor("Fitness Tech")],
        new_products=[],
        price_events=[_evento_precio(competitor="Titanium Strength",
                                     cuando="2026-09-04T03:12:00"),
                      _evento_precio(competitor="Fitness Tech",
                                     cuando="2026-09-04T03:07:00")],
        availability_events=[], removed_products=[], catalog=[],
    )

    feed = build_change_feed(targets)
    por_tienda = {c["store"]: c for c in feed}
    assert por_tienda["Titanium Strength"]["is_own_store"] is False
    assert por_tienda["Fitness Tech"]["is_own_store"] is True


def test_change_feed_sin_eventos_devuelve_una_lista_vacia():
    assert build_change_feed(_targets_con()) == []


def test_change_feed_sin_objetivos_devuelve_una_lista_vacia():
    assert build_change_feed([]) == []


# ---------- recorte del feed por ventana ----------

def test_changes_since_deja_solo_lo_de_dentro_de_la_ventana():
    feed = build_change_feed(_targets_con(price_events=[
        _evento_precio(cuando=datetime(2026, 9, 4, 3, 0)),
        _evento_precio(cuando=datetime(2026, 8, 30, 3, 0)),
    ]))

    recorte = changes_since(feed, datetime(2026, 9, 3, 12, 0))

    assert [c["when"] for c in recorte] == [datetime(2026, 9, 4, 3, 0)]


def test_changes_since_conserva_el_orden_del_feed():
    feed = build_change_feed(_targets_con(price_events=[
        _evento_precio(cuando=datetime(2026, 9, 4, 1, 0)),
        _evento_precio(cuando=datetime(2026, 9, 4, 5, 0)),
        _evento_precio(cuando=datetime(2026, 9, 4, 3, 0)),
    ]))

    recorte = changes_since(feed, datetime(2026, 9, 3, 0, 0))

    assert [c["when"].hour for c in recorte] == [5, 3, 1]


def test_changes_since_descarta_lo_que_no_tiene_fecha():
    # Sin fecha no se puede afirmar que sea reciente: fuera de la ventana
    # corta, aunque siga estando en el feed largo (que ya acoto MySQL).
    feed = build_change_feed(_targets_con(
        price_events=[_evento_precio(cuando="ayer por la tarde")],
    ))

    assert feed[0]["when"] is None
    assert changes_since(feed, datetime(2026, 9, 3, 0, 0)) == []


def test_changes_since_con_ventana_que_no_pilla_nada():
    feed = build_change_feed(_targets_con(price_events=[_evento_precio()]))

    assert changes_since(feed, datetime(2027, 1, 1, 0, 0)) == []
