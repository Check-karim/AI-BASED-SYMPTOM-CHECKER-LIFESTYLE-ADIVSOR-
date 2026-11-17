CREATE DATABASE IF NOT EXISTS kfh_symptom_checker
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

USE kfh_symptom_checker;

CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    full_name VARCHAR(60) NOT NULL,
    username VARCHAR(20) NOT NULL,
    email VARCHAR(120) NOT NULL,
    phone VARCHAR(20) NOT NULL,
    password_hash VARCHAR(512) NOT NULL,
    role ENUM('admin', 'professional', 'patient') NOT NULL DEFAULT 'patient',
    is_active TINYINT(1) NOT NULL DEFAULT 1,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_users_username (username),
    UNIQUE KEY uq_users_email (email),
    UNIQUE KEY uq_users_phone (phone)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS symptom_checks (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    symptoms TEXT NOT NULL,
    duration VARCHAR(40) NOT NULL,
    severity VARCHAR(20) NOT NULL,
    age_group VARCHAR(20) NOT NULL,
    pregnancy VARCHAR(20) NOT NULL DEFAULT 'no',
    notes TEXT NULL,
    urgency VARCHAR(20) NOT NULL,
    title VARCHAR(180) NOT NULL,
    summary TEXT NOT NULL,
    guidance TEXT NOT NULL,
    review_requested TINYINT(1) NOT NULL DEFAULT 0,
    review_requested_at TIMESTAMP NULL DEFAULT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY idx_checks_user (user_id),
    KEY idx_checks_urgency (urgency),
    KEY idx_checks_created (created_at),
    CONSTRAINT fk_checks_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS lifestyle_plans (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    goal VARCHAR(40) NOT NULL,
    activity VARCHAR(40) NOT NULL,
    diet VARCHAR(40) NOT NULL,
    sleep_hours VARCHAR(20) NOT NULL,
    headline VARCHAR(180) NOT NULL,
    advice TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY idx_plans_user (user_id),
    CONSTRAINT fk_plans_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS professional_reviews (
    id INT AUTO_INCREMENT PRIMARY KEY,
    check_id INT NOT NULL,
    professional_id INT NOT NULL,
    notes TEXT NULL,
    recommendation TEXT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_reviews_check (check_id),
    KEY idx_reviews_professional (professional_id),
    CONSTRAINT fk_reviews_check FOREIGN KEY (check_id) REFERENCES symptom_checks(id) ON DELETE CASCADE,
    CONSTRAINT fk_reviews_professional FOREIGN KEY (professional_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS audit_logs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NULL,
    role VARCHAR(20) NOT NULL,
    action VARCHAR(80) NOT NULL,
    detail VARCHAR(500) NOT NULL DEFAULT '',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY idx_audit_created (created_at),
    CONSTRAINT fk_audit_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS content_blocks (
    id INT AUTO_INCREMENT PRIMARY KEY,
    slug VARCHAR(40) NOT NULL,
    title VARCHAR(120) NOT NULL,
    body TEXT NOT NULL,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_content_slug (slug)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS app_settings (
    setting_key VARCHAR(40) PRIMARY KEY,
    setting_value VARCHAR(200) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
