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
    CREATE TABLE IF NOT EXISTS messages (
        id INT AUTO_INCREMENT PRIMARY KEY,
        name VARCHAR(60) NOT NULL,
        email VARCHAR(120) NOT NULL,
        phone VARCHAR(20) NOT NULL,
        subject VARCHAR(120) NOT NULL,
        body TEXT NOT NULL,
        is_read TINYINT(1) NOT NULL DEFAULT 0,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
]


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
