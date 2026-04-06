"""
database.py — SQLite schema for Sentinel-AI Incorruptible Dispatcher
Thiruvananthapuram (TVM) focused.
"""

import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "sentinel.db")


def get_connection():
    """Return a SQLite connection with row_factory for dict-like access."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row          # lets you do row["col_name"]
    conn.execute("PRAGMA journal_mode=WAL") # better concurrent reads
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """Create all tables if they don't exist yet."""
    conn = get_connection()
    cur = conn.cursor()

    # ── 1. AGENCIES ─────────────────────────────────────────────────────────
    cur.executescript("""
    CREATE TABLE IF NOT EXISTS agencies (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        name            TEXT    NOT NULL,
        category        TEXT    NOT NULL CHECK(category IN
                            ('Fire','KSEB','Police','DHS','Admin',
                             'PWD','Forest','Cooperation','DMO')),
        esf_role        TEXT,
        whatsapp        TEXT,
        latitude        REAL,
        longitude       REAL,
        region          TEXT DEFAULT 'TVM'
    );

    -- ── 2. RESOURCES (Hospitals & Relief Shelters) ──────────────────────
    CREATE TABLE IF NOT EXISTS resources (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        name            TEXT    NOT NULL,
        type            TEXT    NOT NULL CHECK(type IN ('Hospital','Shelter','Fire')),
        cap_total       INTEGER DEFAULT 0,
        cap_avail       INTEGER DEFAULT 0,
        er_total        INTEGER DEFAULT 0,
        er_avail        INTEGER DEFAULT 0,
        lat             REAL,
        lon             REAL,
        inclusive       INTEGER DEFAULT 0,  -- 1 = LGBTQIA+/disability ready
        status          TEXT DEFAULT 'Active' CHECK(status IN ('Active','Full','Cut-off'))
    );

    -- ── 3. INCIDENTS (SOS Triage) ────────────────────────────────────────
    CREATE TABLE IF NOT EXISTS incidents (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        phone           TEXT    NOT NULL,
        victim_name     TEXT,
        severity        TEXT    CHECK(severity IN ('Critical','High','Medium','Low')),
        medical_cnt     INTEGER DEFAULT 0,
        shelter_cnt     INTEGER DEFAULT 0,
        fire_hzd        INTEGER DEFAULT 0,  -- boolean 0/1
        power_hzd       INTEGER DEFAULT 0,  -- boolean 0/1
        is_lgbtq        INTEGER DEFAULT 0,  -- boolean 0/1
        lat             REAL,
        lon             REAL,
        timestamp       DATETIME DEFAULT CURRENT_TIMESTAMP,
        status          TEXT DEFAULT 'Triage_Complete'
                            CHECK(status IN ('Pending','Triage_Complete',
                                             'Dispatched','Resolved'))
    );

    -- ── 4. AUDIT LOG (Thought Trace / Transparency Ledger) ───────────────
    CREATE TABLE IF NOT EXISTS audit_logs (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        incident_id     INTEGER,
        agent           TEXT,
        decision        TEXT    CHECK(decision IN ('APPROVED','REJECTED','REDIRECTED','VIP_BLOCKED')),
        reasoning       TEXT,
        citation        TEXT,   -- RAG source: "Orange Book 2025, Page X"
        timestamp       DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (incident_id) REFERENCES incidents(id)
    );

    -- ── 5. ALLOCATIONS (Dispatch Records) ────────────────────────────────
    CREATE TABLE IF NOT EXISTS allocations (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        incident_id     INTEGER,
        resource_id     INTEGER,
        agency_ids      TEXT,   -- JSON array of agency IDs notified
        eta_minutes     REAL,
        distance_km     REAL,
        assignment_time DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (incident_id) REFERENCES incidents(id),
        FOREIGN KEY (resource_id) REFERENCES resources(id)
    );
    """)

    conn.commit()
    conn.close()
    print("[DB] Schema initialised at", DB_PATH)


if __name__ == "__main__":
    init_db()