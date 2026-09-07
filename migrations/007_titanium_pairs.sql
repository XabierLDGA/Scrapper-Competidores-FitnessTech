USE competitor_monitor;

-- El emparejamiento entre nuestras maquinas y las de Titanium, tal como lo
-- decide el departamento de producto. No lleva precios: los precios salen
-- vivos del scrapper y esta tabla solo dice quien compite contra quien.
CREATE TABLE titanium_pairs (
  id INT AUTO_INCREMENT PRIMARY KEY,
  gama VARCHAR(100) NOT NULL,
  orden INT NOT NULL,
  ft_sku VARCHAR(255) NOT NULL,
  ft_title VARCHAR(500),
  equivalencia VARCHAR(30) NOT NULL,
  titanium_title VARCHAR(500),
  titanium_url VARCHAR(500),
  observaciones TEXT,
  -- Un SKU nuestro sale una sola vez en todo el Excel. Que sea unico hace
  -- que un duplicado reviente al aplicar el SQL en vez de duplicar filas en
  -- la pantalla sin que nadie se entere.
  UNIQUE KEY unique_ft_sku (ft_sku),
  INDEX idx_gama (gama),
  -- Deliberadamente NO unico: dos maquinas nuestras pueden competir contra
  -- la misma suya (SE-28972 y SE-28974 comparten el Remo Bajo Black RX).
  INDEX idx_titanium_url (titanium_url)
);
