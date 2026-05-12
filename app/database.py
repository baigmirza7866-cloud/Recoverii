"""
DATABASE LAYER — teaches you how patient + call data is stored.

Two tables:
  patients   → one row per appointment
  call_logs  → one row per call attempt (up to 3 per patient)
"""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "recoverii.db"


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # lets you access columns by name
    return conn


def init_db():
    """Create tables if they don't exist yet."""
    conn = get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS patients (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            clinic_id       TEXT    NOT NULL,
            name            TEXT    NOT NULL,
            phone           TEXT    NOT NULL,
            appointment_at  TEXT    NOT NULL,  -- ISO 8601 datetime string
            status          TEXT    DEFAULT 'pending',  -- pending | confirmed | cancelled
            created_at      TEXT    DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS call_logs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id  INTEGER NOT NULL REFERENCES patients(id),
            trigger     TEXT    NOT NULL,   -- '3_days' | '1_day' | '1_hour'
            called_at   TEXT,              -- when the call was actually made
            twilio_sid  TEXT,              -- Twilio call SID for tracking
            outcome     TEXT    DEFAULT 'pending'  -- pending | confirmed | cancelled | no_answer
        );
    """)
    conn.commit()
    conn.close()
    print("Database ready at", DB_PATH)


if __name__ == "__main__":
    init_db()
