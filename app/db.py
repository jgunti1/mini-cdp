"""Database connection and table definitions."""
import os
import sqlite3

DB_PATH = os.environ.get("DATABASE_PATH", "cdp.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS profiles (
    id     INTEGER PRIMARY KEY,
    email  TEXT UNIQUE            -- normalized; NULL if we don't know it yet
);

CREATE TABLE IF NOT EXISTS subscribers (
    profile_id          INTEGER PRIMARY KEY REFERENCES profiles(id),
    signup_date         TEXT NOT NULL,
    status              TEXT NOT NULL,
    acquisition_source  TEXT,
    last_open_date      TEXT
);

CREATE TABLE IF NOT EXISTS app_users (
    user_id     TEXT PRIMARY KEY,
    profile_id  INTEGER NOT NULL REFERENCES profiles(id),
    created_at  TEXT
);

CREATE TABLE IF NOT EXISTS web_events (
    id          INTEGER PRIMARY KEY,
    visitor_id  TEXT NOT NULL,
    page        TEXT NOT NULL,
    timestamp   TEXT NOT NULL,
    utm_source  TEXT,
    profile_id  INTEGER REFERENCES profiles(id)   -- NULL = anonymous visitor
);

CREATE TABLE IF NOT EXISTS rejected_rows (
    id           INTEGER PRIMARY KEY,
    source_file  TEXT NOT NULL,
    row_number   INTEGER NOT NULL,
    reason       TEXT NOT NULL,
    raw_data     TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_web_events_visitor ON web_events(visitor_id);
CREATE INDEX IF NOT EXISTS idx_web_events_profile ON web_events(profile_id);
"""


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    conn = get_connection()
    conn.executescript(SCHEMA)
    conn.close()