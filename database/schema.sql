USE reputation_app;

CREATE TABLE users (
  user_id            INT AUTO_INCREMENT PRIMARY KEY,
  username           VARCHAR(50) NOT NULL UNIQUE,
  password_hash      VARCHAR(255) NOT NULL,
  business_name      VARCHAR(100),
  google_review_link VARCHAR(500),
  created_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE customers (
  customer_id    INT AUTO_INCREMENT PRIMARY KEY,
  user_id        INT NOT NULL,
  name           VARCHAR(100) NOT NULL,
  email          VARCHAR(255) NOT NULL,
  status         ENUM('active','completed','opted_out','limit_reached') DEFAULT 'active',
  nudges_sent    TINYINT DEFAULT 0,
  next_send_at   DATETIME,
  created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (user_id) REFERENCES users(user_id)
);

CREATE TABLE email_events (
  event_id      INT AUTO_INCREMENT PRIMARY KEY,
  customer_id   INT NOT NULL,
  nudge_number  TINYINT NOT NULL,
  sent_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  link_clicked  BOOLEAN DEFAULT FALSE,
  FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
);

CREATE TABLE logs (
  log_id      INT AUTO_INCREMENT PRIMARY KEY,
  source      VARCHAR(30),
  level       ENUM('INFO','WARN','ERROR'),
  message     TEXT,
  created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
