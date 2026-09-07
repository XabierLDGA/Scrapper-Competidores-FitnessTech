-- Consulta del nodo "Execute a SQL query" del workflow
-- "Comparativa Titanium - aviso diario". Copia versionada de lo que hay
-- dentro de n8n; el original vive en su SQLite.
--
-- El JOIN a titanium_pairs es lo que restringe el aviso a los 67 productos
-- emparejados en vez de a los 918 del catalogo de Titanium. Y la subconsulta
-- ft_precio trae nuestro precio vigente, que es lo que permite contar como
-- queda nuestra posicion y no solo que Titanium ha movido algo.

SELECT 'precio' AS tipo, tp.gama, tp.ft_sku, tp.ft_title,
       tp.titanium_title, tp.titanium_url,
       pe.old_price AS ti_antes, pe.new_price AS ti_ahora,
       NULL AS antes_ok, NULL AS ahora_ok, NULL AS visto,
       pe.detected_at AS fecha,
       (SELECT s.price
          FROM products fp
          JOIN competitors fc ON fc.id = fp.competitor_id
          JOIN product_snapshots s ON s.product_id = fp.id
         WHERE fc.name = 'Fitness Tech'
           AND fp.sku = tp.ft_sku
           AND fp.status = 'active'
         ORDER BY s.captured_at DESC
         LIMIT 1) AS ft_precio
FROM price_events pe
JOIN products p ON p.id = pe.product_id
JOIN competitors c ON c.id = p.competitor_id AND c.name = 'Titanium Strength'
JOIN titanium_pairs tp ON tp.titanium_url = p.url
WHERE pe.detected_at >= NOW() - INTERVAL 24 HOUR

UNION ALL

SELECT 'stock', tp.gama, tp.ft_sku, tp.ft_title,
       tp.titanium_title, tp.titanium_url,
       NULL, NULL, ae.was_available, ae.now_available, NULL, ae.detected_at,
       NULL
FROM availability_events ae
JOIN products p ON p.id = ae.product_id
JOIN competitors c ON c.id = p.competitor_id AND c.name = 'Titanium Strength'
JOIN titanium_pairs tp ON tp.titanium_url = p.url
WHERE ae.detected_at >= NOW() - INTERVAL 24 HOUR

UNION ALL

SELECT 'baja', tp.gama, tp.ft_sku, tp.ft_title,
       tp.titanium_title, tp.titanium_url,
       NULL, NULL, NULL, NULL, p.last_seen, p.removed_at,
       NULL
FROM products p
JOIN competitors c ON c.id = p.competitor_id AND c.name = 'Titanium Strength'
JOIN titanium_pairs tp ON tp.titanium_url = p.url
WHERE p.status = 'removed' AND p.removed_at >= NOW() - INTERVAL 24 HOUR

ORDER BY gama, fecha DESC;
