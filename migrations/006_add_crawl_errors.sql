USE competitor_monitor;

CREATE TABLE crawl_errors (
    id INT AUTO_INCREMENT PRIMARY KEY,
    competitor_name VARCHAR(255) NOT NULL,
    error_message TEXT NOT NULL,
    occurred_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);
