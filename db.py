import json

import pymysql
from flask import g
from pymysql.cursors import DictCursor

from config import (
    ADMIN_EMAIL,
    ADMIN_NAME,
    ADMIN_PASSWORD,
    ADMIN_PHONE,
    ADMIN_USERNAME,
    Config,
)
from werkzeug.security import generate_password_hash


def _database_name():
    name = Config.MYSQL_DATABASE
    if not name.replace("_", "").isalnum():
        raise RuntimeError("MYSQL_DATABASE may contain only letters, numbers, and underscores.")
    return name


def connect(database=None):
    kwargs = dict(
        host=Config.MYSQL_HOST,
        port=Config.MYSQL_PORT,
        user=Config.MYSQL_USER,
        password=Config.MYSQL_PASSWORD,
        charset="utf8mb4",
        cursorclass=DictCursor,
        autocommit=True,
        connect_timeout=5,
    )
    if database:
        kwargs["database"] = database
    return pymysql.connect(**kwargs)


def get_db():
    if "db" not in g:
        g.db = connect(_database_name())
    return g.db


def close_db(_exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def fetch_all(sql, params=None):
    with get_db().cursor() as cursor:
        cursor.execute(sql, params or ())
        return cursor.fetchall()


def fetch_one(sql, params=None):
    with get_db().cursor() as cursor:
        cursor.execute(sql, params or ())
        return cursor.fetchone()


def execute(sql, params=None):
    with get_db().cursor() as cursor:
        cursor.execute(sql, params or ())
        return cursor.lastrowid


def parse_json(value, fallback):
    if value is None or value == "":
        return fallback
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return fallback


SCHEMA = [
    """
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
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
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
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
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
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
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
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS audit_logs (
        id INT AUTO_INCREMENT PRIMARY KEY,
        user_id INT NULL,
        role VARCHAR(20) NOT NULL,
        action VARCHAR(80) NOT NULL,
        detail VARCHAR(500) NOT NULL DEFAULT '',
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        KEY idx_audit_created (created_at),
        CONSTRAINT fk_audit_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS content_blocks (
        id INT AUTO_INCREMENT PRIMARY KEY,
        slug VARCHAR(40) NOT NULL,
        title VARCHAR(120) NOT NULL,
        body TEXT NOT NULL,
        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        UNIQUE KEY uq_content_slug (slug)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS app_settings (
        setting_key VARCHAR(40) PRIMARY KEY,
        setting_value VARCHAR(200) NOT NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
]


DEFAULT_CONTENT = [
    (
        "safety_notice",
        "Safety notice",
        "This checker is not a diagnosis and not an emergency service. "
        "If you have chest pain, trouble breathing, fainting, confusion, heavy bleeding, "
        "or thoughts of suicide or self-harm, call for emergency help or go to the nearest emergency department. "
        "Do not wait for this application.",
    ),
    (
        "disclaimer",
        "Disclaimer",
        "This is a student case study about King Faisal Hospital Rwanda. "
        "It is not the hospital’s website, not part of IHMIS, and not a medical device.\n\n"
        "Symptom results come from fixed safety rules. They can miss serious illness, "
        "and they can flag something that turns out to be minor. "
        "Only a clinician who can examine you can make that judgment.\n\n"
        "Lifestyle pages are general information about food, movement, sleep, and habits. "
        "They are not personal medical nutrition, physiotherapy, or mental-health treatment.\n\n"
        "For a child, or if you are pregnant or might be, involve a clinician before using medicine.",
    ),
    (
        "symptom_intro",
        "Before you enter symptoms",
        "Select every symptom that applies today. You will see a preliminary care level and general next steps. "
        "You can optionally ask an authorized healthcare professional to review that summary. "
        "A professional cannot open a check you did not send.",
    ),
    (
        "lifestyle_intro",
        "About lifestyle recommendations",
        "These recommendations are general habits for food, movement, and sleep. "
        "They are not a personal diet, exercise prescription, or treatment plan.",
    ),
]

DEFAULT_SETTINGS = {
    "registration_open": "1",
    "reviews_open": "1",
    "emergency_ambulance": "912",
    "emergency_general": "112",
}


def _has_column(cursor, database, table, column):
    cursor.execute(
        """
        SELECT COUNT(*) AS total
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s AND COLUMN_NAME = %s
        """,
        (database, table, column),
    )
    return int(cursor.fetchone()["total"]) > 0


def init_db():
    database = _database_name()
    server = connect(None)
    try:
        with server.cursor() as cursor:
            cursor.execute(
                f"CREATE DATABASE IF NOT EXISTS `{database}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
    finally:
        server.close()

    conn = connect(database)
    try:
        with conn.cursor() as cursor:
            for statement in SCHEMA:
                cursor.execute(statement)
            if not _has_column(cursor, database, "symptom_checks", "review_requested"):
                cursor.execute(
                    """
                    ALTER TABLE symptom_checks
                    ADD COLUMN review_requested TINYINT(1) NOT NULL DEFAULT 0
                    """
                )
            if not _has_column(cursor, database, "symptom_checks", "review_requested_at"):
                cursor.execute(
                    """
                    ALTER TABLE symptom_checks
                    ADD COLUMN review_requested_at TIMESTAMP NULL DEFAULT NULL
                    """
                )
            for slug, title, body in DEFAULT_CONTENT:
                cursor.execute("SELECT id FROM content_blocks WHERE slug = %s", (slug,))
                if cursor.fetchone() is None:
                    cursor.execute(
                        "INSERT INTO content_blocks (slug, title, body) VALUES (%s, %s, %s)",
                        (slug, title, body),
                    )
            for key, value in DEFAULT_SETTINGS.items():
                cursor.execute(
                    """
                    INSERT IGNORE INTO app_settings (setting_key, setting_value)
                    VALUES (%s, %s)
                    """,
                    (key, value),
                )
            cursor.execute("SELECT id FROM users WHERE username = %s", (ADMIN_USERNAME,))
            if cursor.fetchone() is None:
                cursor.execute(
                    """
                    INSERT INTO users
                        (full_name, username, email, phone, password_hash, role, is_active)
                    VALUES (%s, %s, %s, %s, %s, 'admin', 1)
                    """,
                    (
                        ADMIN_NAME,
                        ADMIN_USERNAME,
                        ADMIN_EMAIL,
                        ADMIN_PHONE,
                        generate_password_hash(ADMIN_PASSWORD),
                    ),
                )
    finally:
        conn.close()
