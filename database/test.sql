USE reputation_app;

CREATE TABLE IF NOT EXISTS connection_test (
  test_id    INT AUTO_INCREMENT PRIMARY KEY,
  message    VARCHAR(100) NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO connection_test (message)
SELECT 'Hello from the ARMS database' FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM connection_test);
