CREATE DATABASE IF NOT EXISTS competitor_monitor CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE competitor_monitor;

CREATE TABLE IF NOT EXISTS competitors (
  id INT AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(255) NOT NULL UNIQUE,
  website_url VARCHAR(500) NOT NULL,
  product_api_url VARCHAR(500),
  country VARCHAR(10) DEFAULT 'ES',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_name (name)
);

CREATE TABLE IF NOT EXISTS products (
  id INT AUTO_INCREMENT PRIMARY KEY,
  competitor_id INT NOT NULL,
  external_id VARCHAR(500) NOT NULL,
  url VARCHAR(500) NOT NULL,
  title VARCHAR(500),
  first_seen DATE DEFAULT (CURRENT_DATE),
  last_seen DATE DEFAULT (CURRENT_DATE),
  status VARCHAR(50) DEFAULT 'active',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (competitor_id) REFERENCES competitors(id) ON DELETE CASCADE,
  UNIQUE KEY unique_competitor_product (competitor_id, external_id),
  INDEX idx_competitor (competitor_id),
  INDEX idx_status (status)
);

CREATE TABLE IF NOT EXISTS product_snapshots (
  id INT AUTO_INCREMENT PRIMARY KEY,
  product_id INT NOT NULL,
  captured_at DATE NOT NULL,
  price DECIMAL(10, 2),
  price_original DECIMAL(10, 2),
  currency VARCHAR(3),
  country VARCHAR(10),
  available BOOLEAN,
  shipping_text VARCHAR(500),
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE,
  UNIQUE KEY unique_snapshot (product_id, captured_at),
  INDEX idx_product (product_id),
  INDEX idx_date (captured_at)
);

CREATE TABLE IF NOT EXISTS price_events (
  id INT AUTO_INCREMENT PRIMARY KEY,
  product_id INT NOT NULL,
  event_type VARCHAR(50),
  old_price DECIMAL(10, 2),
  new_price DECIMAL(10, 2),
  percent_change DECIMAL(5, 2),
  detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  notified BOOLEAN DEFAULT FALSE,
  FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE,
  INDEX idx_product (product_id),
  INDEX idx_notified (notified),
  INDEX idx_date (detected_at)
);
