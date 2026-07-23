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
                                  url: str, title: str) -> int:
        """Inserta un producto o actualiza last_seen/title si ya existe.

        LAST_INSERT_ID(id) hace que cursor.lastrowid devuelva el id existente
        tambien en la rama de UPDATE, evitando una segunda consulta SELECT.
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("""
                    INSERT INTO products (competitor_id, external_id, url, title)
                    VALUES (%s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        last_seen = CURDATE(),
                        title = VALUES(title),
                        status = 'active',
                        removed_at = NULL,
                        id = LAST_INSERT_ID(id)
                """, (competitor_id, external_id, url, title))
                conn.commit()
                return cursor.lastrowid
            finally:
                cursor.close()

    def insert_snapshot(self, product_id: int, price: float, price_original: float,
                         currency: str, country: str, available: bool, shipping_text: str):
        """Inserta el snapshot de hoy. Si ya existe uno para hoy (se ha
        corrido el crawler dos veces), se ignora en silencio."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("""
                    INSERT INTO product_snapshots
                    (product_id, captured_at, price, price_original, currency, country, available, shipping_text)
                    VALUES (%s, CURDATE(), %s, %s, %s, %s, %s, %s)
                """, (product_id, price, price_original, currency, country, available, shipping_text))
                conn.commit()
            except mysql.connector.Error as err:
                if err.errno == MYSQL_ERR_DUPLICATE_ENTRY:
                    logger.debug(f"Snapshot ya existe hoy para producto {product_id}")
                else:
                    raise
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
                    SELECT ae.*, p.title, p.url, c.name AS competitor
                    FROM availability_events ae
                    JOIN products p ON ae.product_id = p.id
                    JOIN competitors c ON p.competitor_id = c.id
                    WHERE ae.detected_at >= DATE_SUB(NOW(), INTERVAL %s HOUR)
                    ORDER BY ae.detected_at DESC
                """, (hours,))
                return cursor.fetchall()
            finally:
                cursor.close()

    def mark_missing_products_removed(self, competitor_id: int):
        """Marca como 'removed' los productos activos de un competidor que no
        se han visto en el crawl de hoy (su last_seen no se actualizo hoy).

        Se llama una vez por competidor, y solo tras procesar con exito su
        catalogo, para no marcar productos como eliminados por un fallo
        parcial del crawl.
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("""
                    UPDATE products
                    SET status = 'removed', removed_at = NOW()
                    WHERE competitor_id = %s AND status = 'active' AND last_seen < CURDATE()
                """, (competitor_id,))
                conn.commit()
                if cursor.rowcount:
                    logger.info(f"{cursor.rowcount} productos marcados como eliminados")
            finally:
                cursor.close()

    def get_recently_removed_products(self, hours: int = 24) -> list[dict]:
        """Productos marcados como eliminados en las ultimas N horas, para el dashboard."""
        with self.get_connection() as conn:
            cursor = conn.cursor(dictionary=True)
            try:
                cursor.execute("""
                    SELECT c.name AS competitor, p.title, p.url, p.last_seen, p.removed_at
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
                    SELECT pe.*, p.title, c.name as competitor
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
                        product_api_url: str = None, country: str = "ES") -> int:
        """Anade un competidor a la BD."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("""
                    INSERT INTO competitors (name, website_url, product_api_url, country)
                    VALUES (%s, %s, %s, %s)
                """, (name, website_url, product_api_url, country))
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
                    SELECT c.id, c.name, c.website_url, c.country,
                           COUNT(DISTINCT p.id) AS total_products,
                           MAX(p.last_seen) AS last_crawled
                    FROM competitors c
                    LEFT JOIN products p ON p.competitor_id = c.id
                    GROUP BY c.id, c.name, c.website_url, c.country
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
                    SELECT competitor, title, url, price, price_original, available, captured_at
                    FROM (
                        SELECT c.name AS competitor, p.title, p.url, s.price, s.price_original,
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
                    SELECT pe.*, p.title, c.name AS competitor
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
                    SELECT c.name AS competitor, p.title, p.url, p.first_seen,
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
