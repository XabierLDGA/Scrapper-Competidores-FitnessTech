USE competitor_monitor;

ALTER TABLE products
  ADD COLUMN sku VARCHAR(255) NULL AFTER title;
