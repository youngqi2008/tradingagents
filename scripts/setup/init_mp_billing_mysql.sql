-- Ares 用户/计费模块 MySQL 初始化脚本
-- 用法: mysql -u root -p < scripts/setup/init_mp_billing_mysql.sql

CREATE DATABASE IF NOT EXISTS ares_ops
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_unicode_ci;

USE ares_ops;

CREATE TABLE IF NOT EXISTS membership_levels (
  id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(64) NOT NULL,
  code VARCHAR(32) NOT NULL,
  sort_order INT NOT NULL DEFAULT 0,
  monthly_free_generations INT NOT NULL DEFAULT 0,
  per_generation_price DECIMAL(10, 2) NOT NULL DEFAULT 9.90,
  monthly_free_asks INT NOT NULL DEFAULT 0,
  per_ask_price DECIMAL(10, 2) NOT NULL DEFAULT 9.90,
  monthly_price DECIMAL(10, 2) NOT NULL DEFAULT 0.00,
  description VARCHAR(512) NOT NULL DEFAULT '',
  is_default TINYINT(1) NOT NULL DEFAULT 0,
  is_active TINYINT(1) NOT NULL DEFAULT 1,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  UNIQUE KEY uk_membership_code (code),
  KEY idx_membership_sort (sort_order)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS users (
  id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  username VARCHAR(50) NOT NULL,
  email VARCHAR(255) NOT NULL,
  hashed_password VARCHAR(128) NOT NULL,
  is_active TINYINT(1) NOT NULL DEFAULT 1,
  is_verified TINYINT(1) NOT NULL DEFAULT 0,
  is_admin TINYINT(1) NOT NULL DEFAULT 0,
  user_type VARCHAR(16) NOT NULL DEFAULT 'admin',
  openid VARCHAR(64) NULL,
  unionid VARCHAR(64) NULL,
  nickname VARCHAR(128) NULL,
  avatar_url VARCHAR(512) NULL,
  phone VARCHAR(32) NULL,
  membership_level_id BIGINT NULL,
  balance DECIMAL(12, 2) NOT NULL DEFAULT 0.00,
  preferences JSON NULL,
  favorite_stocks JSON NULL,
  daily_quota INT NOT NULL DEFAULT 1000,
  concurrent_limit INT NOT NULL DEFAULT 3,
  total_analyses INT NOT NULL DEFAULT 0,
  successful_analyses INT NOT NULL DEFAULT 0,
  failed_analyses INT NOT NULL DEFAULT 0,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  last_login DATETIME(6) NULL,
  UNIQUE KEY uk_users_username (username),
  UNIQUE KEY uk_users_openid (openid),
  KEY idx_users_type (user_type),
  KEY idx_users_membership (membership_level_id),
  CONSTRAINT fk_users_membership FOREIGN KEY (membership_level_id) REFERENCES membership_levels (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS billing_records (
  id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  user_id BIGINT NOT NULL,
  action_type VARCHAR(32) NOT NULL,
  amount DECIMAL(12, 2) NOT NULL,
  balance_before DECIMAL(12, 2) NOT NULL,
  balance_after DECIMAL(12, 2) NOT NULL,
  is_free TINYINT(1) NOT NULL DEFAULT 0,
  stock_code VARCHAR(32) NULL,
  task_id VARCHAR(64) NULL,
  report_id VARCHAR(64) NULL,
  order_no VARCHAR(64) NULL,
  membership_level_id BIGINT NULL,
  membership_level_name VARCHAR(64) NULL,
  remark TEXT NOT NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  KEY idx_billing_user_created (user_id, created_at),
  KEY idx_billing_action (action_type),
  KEY idx_billing_order (order_no),
  CONSTRAINT fk_billing_user FOREIGN KEY (user_id) REFERENCES users (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS payment_orders (
  id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  order_no VARCHAR(64) NOT NULL,
  user_id BIGINT NOT NULL,
  openid VARCHAR(64) NOT NULL,
  amount DECIMAL(12, 2) NOT NULL,
  status VARCHAR(32) NOT NULL DEFAULT 'pending',
  wx_prepay_id VARCHAR(128) NULL,
  wx_transaction_id VARCHAR(64) NULL,
  description VARCHAR(255) NOT NULL DEFAULT '',
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  paid_at DATETIME(6) NULL,
  updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  UNIQUE KEY uk_payment_order_no (order_no),
  KEY idx_payment_user_created (user_id, created_at),
  KEY idx_payment_status (status),
  KEY idx_payment_wx_tx (wx_transaction_id),
  CONSTRAINT fk_payment_user FOREIGN KEY (user_id) REFERENCES users (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS user_quota_usage (
  id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  user_id BIGINT NOT NULL,
  period CHAR(7) NOT NULL COMMENT 'YYYY-MM',
  free_generations_used INT NOT NULL DEFAULT 0,
  free_asks_used INT NOT NULL DEFAULT 0,
  membership_fee_charged TINYINT(1) NOT NULL DEFAULT 0,
  updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  UNIQUE KEY uniq_user_period (user_id, period),
  CONSTRAINT fk_quota_user FOREIGN KEY (user_id) REFERENCES users (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 默认会员等级（若不存在则插入）
INSERT INTO membership_levels (name, code, sort_order, monthly_free_generations, per_generation_price, monthly_free_asks, per_ask_price, monthly_price, description, is_default, is_active)
SELECT * FROM (
  SELECT '普通会员' AS name, 'normal' AS code, 0 AS sort_order, 0 AS monthly_free_generations,
         9.90 AS per_generation_price, 0 AS monthly_free_asks, 1.90 AS per_ask_price, 0.00 AS monthly_price,
         '按次付费，无月费' AS description, 1 AS is_default, 1 AS is_active
  UNION ALL
  SELECT 'VIP会员', 'vip', 1, 3, 6.90, 10, 0.90, 29.90, '月费29.9元，含3次免费研报+10次免费问股', 0, 1
) AS defaults
WHERE NOT EXISTS (SELECT 1 FROM membership_levels LIMIT 1);
