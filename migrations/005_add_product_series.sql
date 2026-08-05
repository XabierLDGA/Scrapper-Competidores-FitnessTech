USE competitor_monitor;

ALTER TABLE products
  ADD COLUMN series VARCHAR(255) NULL AFTER sku;
