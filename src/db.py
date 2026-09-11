import logging
from contextlib import contextmanager
from decimal import Decimal

import mysql.connector
from mysql.connector import Error

logger = logging.getLogger(__name__)

MYSQL_ERR_DUPLICATE_ENTRY = 1062


def _to_float(value):
    """mysql-connector devuelve Decimal para columnas DECIMAL; el resto del
    pipeline (crawler/normalizer/detector) trabaja en float, asi que se
    normaliza aqui, en la frontera con la base de datos."""
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    return value


class Database:
    def __init__(self, host: str, user: str, password: str, database: str, port: int = 3306):
        self.config = {
            "host": host,
            "user": user,
            "password": password,
            "database": database,
            "port": port,
            "autocommit": True,
            "charset": "utf8mb4",
            "use_unicode": True,
        }

    @contextmanager
    def get_connection(self):
        conn = None
        try:
            conn = mysql.connector.connect(**self.config)
            yield conn
        except Error as err:
            if err.errno == 2003:
                logger.error("No se pudo conectar a MySQL - verifica host, usuario y contrasena")
            else:
                logger.error(f"Error MySQL: {err}")
            raise
        finally:
            if conn and conn.is_connected():
                conn.close()

    def insert_or_update_product(self, competitor_id: int, external_id: str,
                                  url: str, title: str, sku: str = None,
                                  series: str = None) -> int:
        """Inserta un producto o actualiza last_seen/title/sku/series si ya existe.

        LAST_INSERT_ID(id) hace que cursor.lastrowid devuelva el id existente
        tambien en la rama de UPDATE, evitando una segunda consulta SELECT.
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("""
                    INSERT INTO products (competitor_id, external_id, url, title, sku, series)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        last_seen = CURDATE(),
                        title = VALUES(title),
                        sku = VALUES(sku),
                        series = VALUES(series),
                        status = 'active',
                        removed_at = NULL,
                        id = LAST_INSERT_ID(id)
                """, (competitor_id, external_id, url, title, sku, series))
                conn.commit()
                return cursor.lastrowid
            finally:
                cursor.close()

    def insert_snapshot(self, product_id: int, price: float, price_original: float,
                         currency: str, country: str, available: bool, shipping_text: str):
        """Guarda la lectura de hoy. Solo hay una fila por producto y dia
        (`unique_snapshot`), asi que un segundo crawl del mismo dia PISA la
        del primero: manda siempre la ultima lectura.

        Antes se descartaba en silencio, y eso duplicaba eventos en cuanto
        se crawleaba dos veces el mismo dia. El caso real: el 2026-09-07 la
        Bionic Bike XL de Titanium subio de 1.999 a 2.195 EUR; la pasada de
        las 07:24 lo detecto y creo el evento, pero el snapshot se quedo en
        1.999, asi que la de las 14:10 volvio a comparar contra 1.999, vio
        2.195 y creo el evento OTRA VEZ. El mismo cambio contado dos veces
        en el panel y en el correo. Con la pasada de las 13:00 fija eso
        pasaria a diario."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("""
                    INSERT INTO product_snapshots
                    (product_id, captured_at, price, price_original, currency, country, available, shipping_text)
                    VALUES (%s, CURDATE(), %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        price = VALUES(price),
                        price_original = VALUES(price_original),
                        currency = VALUES(currency),
                        country = VALUES(country),
                        available = VALUES(available),
                        shipping_text = VALUES(shipping_text)
                """, (product_id, price, price_original, currency, country, available, shipping_text))
                conn.commit()
            finally:
                cursor.close()

    def get_last_snapshot(self, product_id: int) -> dict | None:
        """Obtiene el snapshot mas reciente de un producto (precios como float)."""
        with self.get_connection() as conn:
            cursor = conn.cursor(dictionary=True)
            try:
                cursor.execute("""
                    SELECT * FROM product_snapshots
                    WHERE product_id = %s
                    ORDER BY captured_at DESC LIMIT 1
                """, (product_id,))
                row = cursor.fetchone()
                if row:
                    row["price"] = _to_float(row.get("price"))
                    row["price_original"] = _to_float(row.get("price_original"))
                return row
            finally:
                cursor.close()

    def create_price_event(self, product_id: int, event_type: str,
                            old_price: float, new_price: float, percent_change: float):
        """Persiste un evento de precio ya clasificado por ChangeDetector.

        El umbral (%) se decide una unica vez en ChangeDetector.detect_price_change;
        aqui solo se guarda el resultado, para no duplicar esa logica.
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("""
                    INSERT INTO price_events
                    (product_id, event_type, old_price, new_price, percent_change)
                    VALUES (%s, %s, %s, %s, %s)
                """, (product_id, event_type, old_price, new_price, percent_change))
                conn.commit()
                logger.info(f"Evento de precio creado: {event_type} {percent_change:.1f}%")
            finally:
                cursor.close()

    def create_availability_event(self, product_id: int, was_available: bool, now_available: bool):
        """Persiste un cambio de disponibilidad detectado por ChangeDetector."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("""
                    INSERT INTO availability_events (product_id, was_available, now_available)
                    VALUES (%s, %s, %s)
                """, (product_id, was_available, now_available))
                conn.commit()
                logger.info(f"Evento de disponibilidad creado: {was_available} -> {now_available}")
            finally:
                cursor.close()

    def get_recent_availability_events(self, hours: int = 24) -> list[dict]:
        """Cambios de disponibilidad de las ultimas N horas, para el dashboard."""
        with self.get_connection() as conn:
            cursor = conn.cursor(dictionary=True)
            try:
                cursor.execute("""
                    SELECT ae.*, p.title, p.sku, p.series, p.url, c.name AS competitor
                    FROM availability_events ae
                    JOIN products p ON ae.product_id = p.id
                    JOIN competitors c ON p.competitor_id = c.id
                    WHERE ae.detected_at >= DATE_SUB(NOW(), INTERVAL %s HOUR)
                    ORDER BY ae.detected_at DESC
                """, (hours,))
                return cursor.fetchall()
            finally:
                cursor.close()

    def mark_superseded_variants(self, competitor_id: int) -> int:
        """Reclasifica como 'superseded' las variantes que han sido
        reemplazadas: no se han visto hoy, pero otra variante de SU MISMA
        ficha si. Devuelve cuantas.

        En Shopify seguimos una fila por VARIANTE, pero la url que guardamos
        es la del producto. Al editar las opciones de un producto, Shopify
        destruye la variante y crea otra con id y sku nuevos, asi que la
        vieja desaparece del products.json aunque la ficha no se haya
        movido. Caso real: `set-barra-olimpica-y-2-mancuernas-...` paso de
        FT-28127..30 a FT-29089..96 al renumerar los pesos de 30/60/90/120 kg
        a 27/62/92/122 kg. Antes eso se apuntaba como 4 bajas y 4 altas de un
        producto que nunca se movio.

        Ni 'removed' ni 'active': de baja no esta, porque la ficha sigue
        publicada y el panel no debe anunciarla; pero dejarla 'active' seria
        peor, porque esa variante ya no existe, nunca volvera a tener
        snapshot y se quedaria de fantasma inflando el catalogo. El estado
        propio las saca de las dos consultas -catalogo y feed de bajas- sin
        mentir en ninguna.

        El hermano tiene que haberse visto HOY, no solo estar activo: si no,
        dos variantes que desaparecen a la vez se taparian la una a la otra
        y no se daria de baja ninguna.
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                # El hermano va por tabla derivada y no por subconsulta:
                # MySQL no deja leer en un WHERE la misma tabla que se esta
                # actualizando ("You can't specify target table for update").
                cursor.execute("""
                    UPDATE products p
                    JOIN (
                        SELECT DISTINCT competitor_id, url
                        FROM products
                        WHERE competitor_id = %s
                          AND status = 'active'
                          AND last_seen >= CURDATE()
                    ) vistos_hoy
                      ON vistos_hoy.competitor_id = p.competitor_id
                     AND vistos_hoy.url = p.url
                    SET p.status = 'superseded', p.removed_at = NOW()
                    WHERE p.competitor_id = %s
                      AND p.status = 'active'
                      AND p.last_seen < CURDATE()
                """, (competitor_id, competitor_id))
                conn.commit()
                if cursor.rowcount:
                    logger.info(f"{cursor.rowcount} variantes reemplazadas (no son bajas)")
                return cursor.rowcount
            finally:
                cursor.close()

    def get_removal_candidates(self, competitor_id: int) -> list[dict]:
        """Productos que hoy no han aparecido en el catalogo del competidor.

        Es una lista de sospechosos, no de bajas: quien decide es la
        comprobacion de la ficha en `main.retire_missing_products`. Se llama
        despues de `mark_superseded_variants`, asi que las variantes
        reemplazadas ya se han apartado y no gastan una comprobacion.
        """
        with self.get_connection() as conn:
            cursor = conn.cursor(dictionary=True)
            try:
                cursor.execute("""
                    SELECT id, external_id, url, title
                    FROM products
                    WHERE competitor_id = %s
                      AND status = 'active'
                      AND last_seen < CURDATE()
                """, (competitor_id,))
                return cursor.fetchall()
            finally:
                cursor.close()

    def mark_products_removed(self, product_ids: list[int]) -> None:
        """Marca como 'removed' los productos indicados, que son los que han
        pasado la comprobacion de ficha (404/410). Antes esto era un UPDATE
        a ciegas sobre todo lo no visto hoy, y de ahi salian las bajas
        falsas."""
        if not product_ids:
            return
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                marcadores = ", ".join(["%s"] * len(product_ids))
                cursor.execute(f"""
                    UPDATE products
                    SET status = 'removed', removed_at = NOW()
                    WHERE id IN ({marcadores})
                """, tuple(product_ids))
                conn.commit()
                logger.info(f"{cursor.rowcount} productos marcados como eliminados")
            finally:
                cursor.close()

    def get_recently_removed_products(self, hours: int = 24) -> list[dict]:
        """Productos marcados como eliminados en las ultimas N horas, para el dashboard."""
        with self.get_connection() as conn:
            cursor = conn.cursor(dictionary=True)
            try:
                cursor.execute("""
                    SELECT c.name AS competitor, p.title, p.sku, p.series, p.url, p.last_seen, p.removed_at
                    FROM products p
                    JOIN competitors c ON c.id = p.competitor_id
                    WHERE p.status = 'removed' AND p.removed_at >= DATE_SUB(NOW(), INTERVAL %s HOUR)
                    ORDER BY p.removed_at DESC
                """, (hours,))
                return cursor.fetchall()
            finally:
                cursor.close()

    def get_unnotified_events(self) -> list[dict]:
        """Obtiene eventos de precio no notificados."""
        with self.get_connection() as conn:
            cursor = conn.cursor(dictionary=True)
            try:
                cursor.execute("""
                    SELECT pe.*, p.title, p.sku, p.series, c.name as competitor
                    FROM price_events pe
                    JOIN products p ON pe.product_id = p.id
                    JOIN competitors c ON p.competitor_id = c.id
                    WHERE pe.notified = FALSE
                    ORDER BY pe.detected_at DESC
                """)
                rows = cursor.fetchall()
                for row in rows:
                    row["old_price"] = _to_float(row.get("old_price"))
                    row["new_price"] = _to_float(row.get("new_price"))
                    row["percent_change"] = _to_float(row.get("percent_change"))
                return rows
            finally:
                cursor.close()

    def mark_events_notified(self, event_ids: list):
        """Marca eventos como notificados."""
        if not event_ids:
            return

        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                placeholders = ",".join(["%s"] * len(event_ids))
                cursor.execute(f"""
                    UPDATE price_events SET notified = TRUE
                    WHERE id IN ({placeholders})
                """, event_ids)
                conn.commit()
                logger.info(f"Marcados {len(event_ids)} eventos como notificados")
            finally:
                cursor.close()

    def get_new_products(self, days: int = 1) -> list[dict]:
        """Obtiene productos vistos por primera vez en los ultimos N dias."""
        with self.get_connection() as conn:
            cursor = conn.cursor(dictionary=True)
            try:
                cursor.execute("""
                    SELECT p.*, c.name as competitor
                    FROM products p
                    JOIN competitors c ON p.competitor_id = c.id
                    WHERE p.first_seen >= DATE_SUB(CURDATE(), INTERVAL %s DAY)
                    ORDER BY p.first_seen DESC
                """, (days,))
                return cursor.fetchall()
            finally:
                cursor.close()

    def add_competitor(self, name: str, website_url: str,
                        product_api_url: str = None, country: str = "ES",
                        platform: str = None) -> int:
        """Anade un competidor a la BD."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("""
                    INSERT INTO competitors (name, website_url, product_api_url, country, platform)
                    VALUES (%s, %s, %s, %s, %s)
                """, (name, website_url, product_api_url, country, platform))
                conn.commit()
                return cursor.lastrowid
            except mysql.connector.Error as err:
                if err.errno == MYSQL_ERR_DUPLICATE_ENTRY:
                    logger.warning(f"Competidor {name} ya existe")
                    cursor.execute("SELECT id FROM competitors WHERE name = %s", (name,))
                    return cursor.fetchone()[0]
                raise
            finally:
                cursor.close()

    def get_competitors(self) -> list[dict]:
        """Obtiene todos los competidores."""
        with self.get_connection() as conn:
            cursor = conn.cursor(dictionary=True)
            try:
                cursor.execute("SELECT * FROM competitors ORDER BY name")
                return cursor.fetchall()
            finally:
                cursor.close()

    def get_competitor_stats(self) -> list[dict]:
        """Resumen por competidor: total de productos y ultimo crawl, para el dashboard."""
        with self.get_connection() as conn:
            cursor = conn.cursor(dictionary=True)
            try:
                cursor.execute("""
                    SELECT c.id, c.name, c.website_url, c.country, c.platform,
                           COUNT(DISTINCT p.id) AS total_products,
                           MAX(p.last_seen) AS last_crawled
                    FROM competitors c
                    LEFT JOIN products p ON p.competitor_id = c.id
                    GROUP BY c.id, c.name, c.website_url, c.country, c.platform
                    ORDER BY c.name
                """)
                return cursor.fetchall()
            finally:
                cursor.close()

    def get_latest_snapshots(self) -> list[dict]:
        """Ultimo snapshot de cada producto activo (catalogo actual), para el dashboard.

        Los productos marcados como 'removed' se excluyen: dejaron de verse
        en el catalogo del competidor y se muestran aparte, no como vigentes.
        """
        with self.get_connection() as conn:
            cursor = conn.cursor(dictionary=True)
            try:
                cursor.execute("""
                    SELECT competitor, title, sku, series, url, price, price_original, available, captured_at
                    FROM (
                        SELECT c.name AS competitor, p.title, p.sku, p.series, p.url, s.price, s.price_original,
                               s.available, s.captured_at,
                               ROW_NUMBER() OVER (PARTITION BY p.id ORDER BY s.captured_at DESC) AS rn
                        FROM products p
                        JOIN competitors c ON c.id = p.competitor_id
                        JOIN product_snapshots s ON s.product_id = p.id
                        WHERE p.status = 'active'
                    ) ranked
                    WHERE rn = 1
                    ORDER BY competitor, title
                """)
                rows = cursor.fetchall()
                for row in rows:
                    row["price"] = _to_float(row.get("price"))
                    row["price_original"] = _to_float(row.get("price_original"))
                return rows
            finally:
                cursor.close()

    def get_recent_price_events(self, hours: int = 24) -> list[dict]:
        """Eventos de precio de las ultimas N horas, notificados o no, para el dashboard."""
        with self.get_connection() as conn:
            cursor = conn.cursor(dictionary=True)
            try:
                cursor.execute("""
                    SELECT pe.*, p.title, p.sku, p.series, c.name AS competitor
                    FROM price_events pe
                    JOIN products p ON pe.product_id = p.id
                    JOIN competitors c ON p.competitor_id = c.id
                    WHERE pe.detected_at >= DATE_SUB(NOW(), INTERVAL %s HOUR)
                    ORDER BY pe.detected_at DESC
                """, (hours,))
                rows = cursor.fetchall()
                for row in rows:
                    row["old_price"] = _to_float(row.get("old_price"))
                    row["new_price"] = _to_float(row.get("new_price"))
                    row["percent_change"] = _to_float(row.get("percent_change"))
                return rows
            finally:
                cursor.close()

    def get_recently_added_products(self, hours: int = 24) -> list[dict]:
        """Productos vistos por primera vez en las ultimas N horas, con el
        precio del dia en que se descubrieron, para el dashboard."""
        with self.get_connection() as conn:
            cursor = conn.cursor(dictionary=True)
            try:
                cursor.execute("""
                    SELECT c.name AS competitor, p.title, p.sku, p.series, p.url, p.first_seen,
                           s.price, s.available
                    FROM products p
                    JOIN competitors c ON c.id = p.competitor_id
                    LEFT JOIN product_snapshots s
                        ON s.product_id = p.id AND s.captured_at = p.first_seen
                    WHERE p.first_seen >= DATE_SUB(NOW(), INTERVAL %s HOUR)
                    ORDER BY p.first_seen DESC, c.name, p.title
                """, (hours,))
                rows = cursor.fetchall()
                for row in rows:
                    row["price"] = _to_float(row.get("price"))
                return rows
            finally:
                cursor.close()

    def log_crawl_error(self, competitor_name: str, error_message: str):
        """Persiste un fallo completo de crawl de un competidor.

        Hoy no la lee nadie: se documento que n8n la consultaba cada tarde
        para un email de errores, pero ese workflow no existe (comprobado
        el 2026-09-07 contra los 13 workflows del VPS). Un competidor puede
        estar cayendose dias sin que suene nada; el unico rastro esta en
        esta tabla y en el punto de "ultima lectura" del panel."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("""
                    INSERT INTO crawl_errors (competitor_name, error_message)
                    VALUES (%s, %s)
                """, (competitor_name, error_message))
                conn.commit()
                logger.info(f"Error de crawl registrado para {competitor_name}")
            finally:
                cursor.close()

    def get_titanium_pairs(self) -> list[dict]:
        """El emparejamiento contra Titanium que mantiene producto.

        Sin precios: los pone `build_titanium_comparison` cruzando esto con el
        catalogo vigente. Se puebla con `import_comparativa.py`.

        `ORDER BY id` y no `ORDER BY gama, orden`: el importador borra la tabla
        entera y reinserta hoja por hoja, asi que el id reproduce el orden del
        Excel de producto, que va de la gama de entrada a la alta (Compact,
        Pro, Advanced, Pro Tech). Ordenar por `gama` lo alfabetiza y pone
        Advanced la primera, que no dice nada.
        """
        with self.get_connection() as conn:
            cursor = conn.cursor(dictionary=True)
            try:
                cursor.execute("""
                    SELECT id, gama, orden, ft_sku, ft_title, equivalencia,
                           titanium_title, titanium_url, observaciones
                    FROM titanium_pairs
                    ORDER BY id
                """)
                return cursor.fetchall()
            finally:
                cursor.close()
