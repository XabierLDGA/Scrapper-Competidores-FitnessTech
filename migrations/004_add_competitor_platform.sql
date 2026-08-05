USE competitor_monitor;

ALTER TABLE competitors
  ADD COLUMN platform VARCHAR(20) NULL AFTER product_api_url;
