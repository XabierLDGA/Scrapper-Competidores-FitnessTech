-- Consulta del nodo "Execute a SQL query" del workflow "Salud del crawl -
-- aviso de fallos". Copia versionada de lo que hay dentro de n8n; el
-- original vive en su SQLite.
--
-- Mirar solo `crawl_errors` no bastaria: ahi se registra lo que lanza
-- excepcion, y los dos fallos mas graves son silenciosos. Por eso van tres
-- ramas.
--
--   1. `error`          lo que fallo con excepcion, incluido el catalogo
--                       vacio desde el 2026-09-08 (main.py lo registra).
--   2. `sin_lecturas`   la tienda no ha dejado ni una lectura hoy. Cubre el
--                       caso de que el contenedor `crawler` este parado: si
--                       no corrio nadie, salen TODAS las tiendas.
--   3. `pocas_lecturas` ha dejado menos de la mitad de lo normal. Una caida
--                       parcial no deja rastro en ningun sitio: el catalogo
--                       se descarga a medias y el crawl termina "bien".
--
-- La fila `resumen` va siempre, aunque no haya nada que avisar: es lo que
-- permite al nodo Code decir "0 de las 4.133 lecturas de un dia normal" y
-- distinguir un crawler parado de una tienda concreta caida. El Code la
-- aparta y, si no queda ningun problema, corta el envio.

SELECT 'error' AS tipo,
       ce.competitor_name AS tienda,
       ce.error_message AS detalle,
       ce.occurred_at AS cuando,
       NULL AS hoy,
       NULL AS normal
FROM crawl_errors ce
WHERE ce.occurred_at >= NOW() - INTERVAL 24 HOUR

UNION ALL

-- Se compara contra la media de los 7 dias anteriores, no contra el numero
-- de productos activos: una tienda que de verdad ha encogido no deberia
-- avisar para siempre. Las tiendas sin historial (`normal IS NULL`) quedan
-- fuera, o una recien anadida avisaria el primer dia.
SELECT CASE WHEN COALESCE(h.n, 0) = 0 THEN 'sin_lecturas' ELSE 'pocas_lecturas' END,
       c.name,
       NULL,
       NULL,
       COALESCE(h.n, 0),
       ROUND(r.media)
FROM competitors c
LEFT JOIN (
    SELECT p.competitor_id AS cid, COUNT(*) AS n
    FROM product_snapshots s
    JOIN products p ON p.id = s.product_id
    WHERE s.captured_at = CURDATE()
    GROUP BY p.competitor_id
) h ON h.cid = c.id
LEFT JOIN (
    SELECT p.competitor_id AS cid,
           COUNT(*) / COUNT(DISTINCT s.captured_at) AS media
    FROM product_snapshots s
    JOIN products p ON p.id = s.product_id
    WHERE s.captured_at BETWEEN CURDATE() - INTERVAL 7 DAY AND CURDATE() - INTERVAL 1 DAY
    GROUP BY p.competitor_id
) r ON r.cid = c.id
WHERE r.media IS NOT NULL
  AND COALESCE(h.n, 0) < r.media * 0.5

UNION ALL

SELECT 'resumen',
       NULL,
       NULL,
       NULL,
       (SELECT COUNT(*) FROM product_snapshots WHERE captured_at = CURDATE()),
       (SELECT ROUND(COUNT(*) / COUNT(DISTINCT captured_at)) FROM product_snapshots
         WHERE captured_at BETWEEN CURDATE() - INTERVAL 7 DAY AND CURDATE() - INTERVAL 1 DAY)

ORDER BY tipo, tienda;
