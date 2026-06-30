"""
db.py - Shared SQLite database layer for RESPIRE homelab.

Stores known devices, cluster membership, roles, and security tokens.
All other modules (device_manager, cluster, security) read/write through
this single connection helper so the schema only lives in one place.
"""

import sqlite3
import os
import time
from contextlib import contextmanager

DB_PATH = os.environ.get("RESPIRE_DB", os.path.expanduser("~/.respire/respire.db"))


def _ensure_dir():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)


SCHEMA = """
CREATE TABLE IF NOT EXISTS devices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    ip TEXT,
    hostname TEXT,
    os TEXT,
    role TEXT DEFAULT 'worker',
    approved INTEGER DEFAULT 0,
    last_seen REAL,
    cpu REAL,
    ram REAL,
    storage REAL,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS tokens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_name TEXT UNIQUE NOT NULL,
    token TEXT NOT NULL,
    created_at REAL
);

CREATE TABLE IF NOT EXISTS heartbeats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_name TEXT NOT NULL,
    timestamp REAL,
    status TEXT
);

CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp REAL,
    level TEXT,
    source TEXT,
    message TEXT
);
"""


@contextmanager
def get_conn():
    _ensure_dir()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.executescript(SCHEMA)


def log_event(level: str, source: str, message: str):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO logs (timestamp, level, source, message) VALUES (?, ?, ?, ?)",
            (time.time(), level, source, message),
        )


def get_logs(limit: int = 50):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM logs ORDER BY timestamp DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]
