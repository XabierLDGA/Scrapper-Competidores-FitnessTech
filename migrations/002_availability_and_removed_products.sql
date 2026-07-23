USE competitor_monitor;

CREATE TABLE IF NOT EXISTS availability_events (
  id INT AUTO_INCREMENT PRIMARY KEY,
  product_id INT NOT NULL,
  was_available BOOLEAN,
  now_available BOOLEAN,
  detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE,
  INDEX idx_product (product_id),
  INDEX idx_date (detected_at)
);

ALTER TABLE products
  ADD COLUMN removed_at TIMESTAMP NULL DEFAULT NULL AFTER status,
  ADD INDEX idx_removed_at (removed_at);
