import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "recoverii.db"


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS patients (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            clinic_id       TEXT    NOT NULL,
            name            TEXT    NOT NULL,
            phone           TEXT    NOT NULL,
            appointment_at  TEXT    NOT NULL,
            status          TEXT    DEFAULT 'pending',
            created_at      TEXT    DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS call_logs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id  INTEGER NOT NULL REFERENCES patients(id),
            trigger     TEXT    NOT NULL,
            called_at   TEXT,
            call_id     TEXT,
            outcome     TEXT    DEFAULT 'pending'
        );
    """)
    conn.commit()
    conn.close()


if __name__ == "__main__":
    init_db()
    print("Database ready at", DB_PATH)
