import pytest

openpyxl = pytest.importorskip(
    "openpyxl",
    reason="openpyxl no esta en requirements.txt a proposito: import_comparativa.py "
           "es un script de uso local y no viaja en la imagen Docker.",
)

from import_comparativa import generar_sql, leer_pares


CABECERA = [
    "SKU Fitness Tech", "Máquina Fitness Tech", "PVP FT", "Equivalencia",
    "Máquina Titanium", "PVP Titanium", "Dif. FT − Titanium",
    "Variación vs Titanium", "Enlace disponible", "URL Titanium", "Observaciones",
]


def _libro(tmp_path, hojas):
    """Un .xlsx minimo con la misma forma que el de producto."""
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for titulo, filas in hojas.items():
        ws = wb.create_sheet(titulo)
        ws.append(CABECERA)
        for fila in filas:
            ws.append(fila)
    ruta = tmp_path / "comparativa.xlsx"
    wb.save(ruta)
    return ruta


def _fila(sku="SE-1", nombre="Femoral Sentado", equivalencia="Directa",
          ti_nombre="Curl Femoral Elite", url="https://ti.es/a.html", obs="Misma funcion"):
    return [sku, nombre, 1599, equivalencia, ti_nombre, 1395, 204, 0.146, "Sí", url, obs]


def test_lee_una_fila_con_la_hoja_como_gama(tmp_path):
    ruta = _libro(tmp_path, {"Compact vs Elite": [_fila()]})

    pares = leer_pares(ruta)

    assert pares == [{
        "gama": "Compact vs Elite",
        "orden": 0,
        "ft_sku": "SE-1",
        "ft_title": "Femoral Sentado",
        "equivalencia": "Directa",
        "titanium_title": "Curl Femoral Elite",
        "titanium_url": "https://ti.es/a.html",
        "observaciones": "Misma funcion",
    }]


def test_ignora_las_columnas_de_precio_del_excel(tmp_path):
    # Son una foto del dia en que producto monto el fichero. Los precios
    # salen del scrapper, no de aqui.
    ruta = _libro(tmp_path, {"Compact vs Elite": [_fila()]})

    par = leer_pares(ruta)[0]

    assert "PVP FT" not in par
    assert 1599 not in par.values()
    assert 1395 not in par.values()


def test_numera_el_orden_dentro_de_cada_hoja(tmp_path):
    ruta = _libro(tmp_path, {
        "Compact vs Elite": [_fila(sku="SE-1"), _fila(sku="SE-2")],
        "Pro vs Black": [_fila(sku="SE-3")],
    })

    pares = leer_pares(ruta)

    assert [(p["gama"], p["orden"], p["ft_sku"]) for p in pares] == [
        ("Compact vs Elite", 0, "SE-1"),
        ("Compact vs Elite", 1, "SE-2"),
        ("Pro vs Black", 0, "SE-3"),
    ]


def test_localiza_las_columnas_por_rotulo_no_por_posicion(tmp_path):
    # Producto puede anadir una columna al Excel; eso no debe romper nada.
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    ws = wb.create_sheet("Compact vs Elite")
    ws.append(["Notas internas"] + CABECERA)
    ws.append(["lo que sea"] + _fila())
    ruta = tmp_path / "movida.xlsx"
    wb.save(ruta)

    assert leer_pares(ruta)[0]["ft_sku"] == "SE-1"


def test_salta_las_filas_en_blanco(tmp_path):
    ruta = _libro(tmp_path, {"Compact vs Elite": [
        _fila(sku="SE-1"),
        [None] * len(CABECERA),
        _fila(sku="SE-2"),
    ]})

    assert [p["ft_sku"] for p in leer_pares(ruta)] == ["SE-1", "SE-2"]


def test_una_fila_sin_equivalente_deja_vacio_el_lado_de_titanium(tmp_path):
    ruta = _libro(tmp_path, {"Pro vs Black": [
        ["SE-9", "Elevaciones Laterales", 1699, "Sin equivalente",
         None, None, None, None, None, None, "Black Series no la tiene"],
    ]})

    par = leer_pares(ruta)[0]

    assert par["equivalencia"] == "Sin equivalente"
    assert par["titanium_title"] is None
    assert par["titanium_url"] is None


def test_dos_filas_pueden_compartir_la_url_de_titanium(tmp_path):
    # SE-28972 y SE-28974 compiten los dos contra el Remo Bajo Black RX.
    ruta = _libro(tmp_path, {"Advanced vs Black RX": [
        _fila(sku="SE-1", url="https://ti.es/remo.html"),
        _fila(sku="SE-2", url="https://ti.es/remo.html"),
    ]})

    assert len(leer_pares(ruta)) == 2


def test_un_sku_duplicado_aborta_diciendo_donde_esta(tmp_path):
    ruta = _libro(tmp_path, {
        "Compact vs Elite": [_fila(sku="SE-1")],
        "Pro vs Black": [_fila(sku="SE-1")],
    })

    with pytest.raises(ValueError, match="SE-1"):
        leer_pares(ruta)


def test_una_columna_que_falta_aborta_diciendo_hoja_y_rotulo(tmp_path):
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    ws = wb.create_sheet("Compact vs Elite")
    ws.append([c for c in CABECERA if c != "URL Titanium"])
    ruta = tmp_path / "coja.xlsx"
    wb.save(ruta)

    with pytest.raises(ValueError, match="URL Titanium"):
        leer_pares(ruta)


def test_el_sql_envuelve_el_reemplazo_en_una_transaccion(tmp_path):
    sql = generar_sql(leer_pares(_libro(tmp_path, {"Compact vs Elite": [_fila()]})))

    assert "START TRANSACTION;" in sql
    assert "DELETE FROM titanium_pairs;" in sql
    assert sql.index("DELETE FROM titanium_pairs;") < sql.index("INSERT INTO titanium_pairs")
    assert "COMMIT;" in sql


def test_el_sql_escapa_las_comillas_del_texto(tmp_path):
    # Las observaciones de producto son prosa: llevan apostrofes.
    ruta = _libro(tmp_path, {"Compact vs Elite": [
        _fila(obs="Titanium lo llama 'Elite', nosotros no"),
    ]})

    sql = generar_sql(leer_pares(ruta))

    assert "\\'Elite\\'" in sql


def test_el_sql_escribe_null_y_no_la_palabra_none(tmp_path):
    ruta = _libro(tmp_path, {"Pro vs Black": [
        ["SE-9", "Elevaciones", 1699, "Sin equivalente",
         None, None, None, None, None, None, None],
    ]})

    sql = generar_sql(leer_pares(ruta))

    assert "NULL" in sql
    assert "'None'" not in sql


def test_advanced_va_la_ultima_aunque_el_excel_la_ponga_la_tercera(tmp_path):
    # Es la unica gama que no esta publicada en nuestra tienda: sus filas
    # salen con el lado nuestro vacio y abrian la pantalla con un bloque
    # entero sin precios.
    ruta = _libro(tmp_path, {
        "Compact vs Elite": [_fila(sku="SE-1")],
        "Pro vs Black": [_fila(sku="SE-2")],
        "Advanced vs Black RX": [_fila(sku="SE-3")],
        "Pro Tech vs Genesis": [_fila(sku="SE-4")],
    })

    gamas = list(dict.fromkeys(p["gama"] for p in leer_pares(ruta)))

    assert gamas == ["Compact vs Elite", "Pro vs Black",
                     "Pro Tech vs Genesis", "Advanced vs Black RX"]


def test_una_gama_que_no_conocemos_va_detras_sin_romper_nada(tmp_path):
    # Si producto renombra una hoja o anade una gama nueva, el importador no
    # puede perderla ni reventar: se coloca al final.
    ruta = _libro(tmp_path, {
        "Advanced vs Black RX": [_fila(sku="SE-1")],
        "Nueva gama vs Lo que sea": [_fila(sku="SE-2")],
        "Compact vs Elite": [_fila(sku="SE-3")],
    })

    gamas = list(dict.fromkeys(p["gama"] for p in leer_pares(ruta)))

    assert gamas == ["Compact vs Elite", "Advanced vs Black RX",
                     "Nueva gama vs Lo que sea"]


def test_reordenar_las_gamas_no_toca_el_orden_de_sus_filas(tmp_path):
    ruta = _libro(tmp_path, {
        "Advanced vs Black RX": [_fila(sku="SE-1"), _fila(sku="SE-2")],
        "Compact vs Elite": [_fila(sku="SE-3"), _fila(sku="SE-4")],
    })

    pares = leer_pares(ruta)

    assert [(p["gama"], p["orden"], p["ft_sku"]) for p in pares] == [
        ("Compact vs Elite", 0, "SE-3"),
        ("Compact vs Elite", 1, "SE-4"),
        ("Advanced vs Black RX", 0, "SE-1"),
        ("Advanced vs Black RX", 1, "SE-2"),
    ]
