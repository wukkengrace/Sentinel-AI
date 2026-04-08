"""
database.py — SQLite schema for Sentinel-AI v2.0
Thiruvananthapuram (TVM) focused.
"""

import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "sentinel.db")


def get_connection():
    """Return a SQLite connection with row_factory for dict-like access."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """Create all tables if they don't exist yet."""
    conn = get_connection()
    cur = conn.cursor()

    cur.executescript("""
    -- ── 1. AGENCIES ──────────────────────────────────────────────────────────
    CREATE TABLE IF NOT EXISTS agencies (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        name            TEXT    NOT NULL,
        category        TEXT    NOT NULL CHECK(category IN
                            ('Fire','KSEB','Police','DHS','Admin',
                             'PWD','Forest','Cooperation','DMO','KWA','NDRF','Navy','Army')),
        esf_role        TEXT,
        whatsapp        TEXT,
        latitude        REAL,
        longitude       REAL,
        region          TEXT DEFAULT 'TVM'
    );

    -- ── 2. RESOURCES (Hospitals & Relief Shelters) ───────────────────────────
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
        inclusive       INTEGER DEFAULT 0,
        shelter_type    TEXT DEFAULT 'General' CHECK(shelter_type IN
                            ('General','Male','Female_Children','Disability','LGBTQIA+')),
        status          TEXT DEFAULT 'Active' CHECK(status IN ('Active','Full','Cut-off'))
    );

    -- ── 3. RESCUE UNITS (Synthetic Fleet) ───────────────────────────────────
    CREATE TABLE IF NOT EXISTS rescue_units (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        name                TEXT    NOT NULL,
        unit_type           TEXT    NOT NULL CHECK(unit_type IN
                                ('Fire_Rescue','Fishermen','NDRF','IAF_Navy','Army')),
        boat_type           TEXT    CHECK(boat_type IN
                                ('IRB','Dinghy','Fishermen_Boat','OBM_Boat',
                                 'Helicopter_Light','Helicopter_Medium','Engineering_Column')),
        crew_size           INTEGER DEFAULT 1,
        victim_capacity     INTEGER DEFAULT 1,
        status              TEXT DEFAULT 'Available' CHECK(status IN
                                ('Available','Deployed','Returning','Standby')),
        current_incident_id INTEGER,
        base_lat            REAL,
        base_lon            REAL,
        sorties_completed   INTEGER DEFAULT 0,
        FOREIGN KEY (current_incident_id) REFERENCES incidents(id)
    );

    -- ── 4. INCIDENTS (SOS Triage) — v2.0 schema ────────────────────────────
    CREATE TABLE IF NOT EXISTS incidents (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        -- Contact
        phone           TEXT    NOT NULL,
        victim_name     TEXT,
        aadhar_id       TEXT,
        -- Demographics
        male_cnt        INTEGER DEFAULT 0,
        female_cnt      INTEGER DEFAULT 0,
        child_cnt       INTEGER DEFAULT 0,
        total_victims   INTEGER DEFAULT 0,
        -- Priority
        severity        TEXT    CHECK(severity IN ('Critical','High','Medium','Low')),
        priority        TEXT    DEFAULT 'Standard' CHECK(priority IN ('Standard','ULTRA_PRIORITY')),
        -- Needs
        medical_cnt     INTEGER DEFAULT 0,
        shelter_cnt     INTEGER DEFAULT 0,
        is_lgbtq        INTEGER DEFAULT 0,
        is_disability   INTEGER DEFAULT 0,
        -- Hazards
        fire_hzd        INTEGER DEFAULT 0,
        power_hzd       INTEGER DEFAULT 0,
        emergency_type  TEXT    CHECK(emergency_type IN
                            ('Fire','Electrical','Sewage','Flood','Road','Tree','Other')),
        flood_level     INTEGER DEFAULT 0 CHECK(flood_level BETWEEN 0 AND 5),
        -- Security
        vip_flagged     INTEGER DEFAULT 0,
        extra_comments  TEXT,
        -- Location
        lat             REAL,
        lon             REAL,
        -- Status
        timestamp       DATETIME DEFAULT CURRENT_TIMESTAMP,
        status          TEXT DEFAULT 'Pending'
                            CHECK(status IN ('Pending','Triage_Complete',
                                             'Dispatched','Rescue_Complete','Resolved'))
    );

    -- ── 5. VICTIMS (Individual Tracking) ────────────────────────────────────
    CREATE TABLE IF NOT EXISTS victims (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        incident_id         INTEGER NOT NULL,
        name                TEXT,
        phone               TEXT,
        aadhar_id           TEXT,
        gender              TEXT    CHECK(gender IN ('Male','Female','Child')),
        needs_medical       INTEGER DEFAULT 0,
        is_lgbtq            INTEGER DEFAULT 0,
        is_disability       INTEGER DEFAULT 0,
        severity            TEXT    DEFAULT 'Low' CHECK(severity IN ('Critical','High','Medium','Low')),
        status              TEXT    DEFAULT 'Reported' CHECK(status IN
                                ('Reported','Evacuated','In_Transit','Admitted','Sheltered')),
        assigned_resource_id INTEGER,
        placed_at           DATETIME,
        FOREIGN KEY (incident_id) REFERENCES incidents(id),
        FOREIGN KEY (assigned_resource_id) REFERENCES resources(id)
    );

    -- ── 6. RESCUE UNIT ASSIGNMENTS ───────────────────────────────────────────
    CREATE TABLE IF NOT EXISTS rescue_unit_assignments (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        incident_id         INTEGER NOT NULL,
        unit_id             INTEGER NOT NULL,
        assigned_at         DATETIME DEFAULT CURRENT_TIMESTAMP,
        dispatched_at       DATETIME,
        rescue_completed_at DATETIME,
        returned_at         DATETIME,
        victims_rescued     INTEGER DEFAULT 0,
        eta_minutes         REAL,
        distance_km         REAL,
        status              TEXT DEFAULT 'Assigned' CHECK(status IN
                                ('Assigned','Dispatched','Rescue_Complete','Returned')),
        FOREIGN KEY (incident_id) REFERENCES incidents(id),
        FOREIGN KEY (unit_id) REFERENCES rescue_units(id)
    );

    -- ── 7. DISPATCH EVENTS (Incident Timeline) ──────────────────────────────
    CREATE TABLE IF NOT EXISTS dispatch_events (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        incident_id INTEGER NOT NULL,
        unit_id     INTEGER,
        event_type  TEXT    CHECK(event_type IN
                        ('UNIT_ASSIGNED','DISPATCHED','RESCUE_COMPLETE',
                         'VICTIM_PLACED','UNIT_RETURNED','FRAUD_ALERT',
                         'VIP_BLOCKED','ULTRA_PRIORITY','TRIAGE_COMPLETE','OVERRIDE',
                         'ADMISSION_START','ADMISSION_COMPLETE','SHELTER_FALLBACK')),
        message     TEXT    NOT NULL,
        timestamp   DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (incident_id) REFERENCES incidents(id)
    );

    -- ── 8. AUDIT LOG (Thought Trace / Transparency Ledger) ──────────────────
    CREATE TABLE IF NOT EXISTS audit_logs (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        incident_id     INTEGER,
        aadhar_id       TEXT,
        agent           TEXT,
        decision        TEXT    CHECK(decision IN ('APPROVED','REJECTED','REDIRECTED','VIP_BLOCKED','FRAUD_ALERT','OVERRIDE','CONSENSUS')),
        reasoning       TEXT,
        citation        TEXT,
        fleet_check     TEXT,
        consensus_score REAL,
        timestamp       DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (incident_id) REFERENCES incidents(id)
    );

    -- ── 9. ALLOCATIONS (Dispatch Records — kept for backward compat) ─────────
    CREATE TABLE IF NOT EXISTS allocations (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        incident_id     INTEGER,
        resource_id     INTEGER,
        agency_ids      TEXT,
        eta_minutes     REAL,
        distance_km     REAL,
        assignment_time DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (incident_id) REFERENCES incidents(id),
        FOREIGN KEY (resource_id) REFERENCES resources(id)
    );

    -- ── 10. FRAUD DATABASE ───────────────────────────────────────────────────
    CREATE TABLE IF NOT EXISTS fraud_db (
        aadhar_id   TEXT PRIMARY KEY,
        reason      TEXT,
        flagged_at  DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    """)

    conn.commit()
    conn.close()
    print("[DB] v2.0 Schema initialised at", DB_PATH)


if __name__ == "__main__":
    init_db()