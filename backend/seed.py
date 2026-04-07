"""
seed.py — Populates the Sentinel-AI DB with Thiruvananthapuram (TVM) data.
Sources:
  • data/coordinates.csv  → agencies table
  • Hardcoded TVM hospitals/shelters      → resources table
Run once after init_db().
"""

import os
import csv
from database import get_connection, init_db

# ── Raw CSV data (parsed from Category_Name_Latitude_Longitude.csv) ──────────
# Default fallback data if coordinates.csv is missing
AGENCY_SEED = [
    # (name, category, esf_role, whatsapp, latitude, longitude)
    ("District Collectorate TVM", "Admin", "ESF 5: Emergency Management", "918547610029", 8.555983, 76.961030),
    ("DHS HQ", "DHS", "ESF 8: Health & Medical", "918301838148", 8.4988, 76.9405),
    ("Fire HQ Chengalchoola", "Fire", "ESF 4: Firefighting", "919497996964", 8.4938, 76.9535),
    ("KSEB HQ Pattom", "KSEB", "ESF 12: Energy", "910000000001", 8.5244, 76.9431),
    ("Police Control Room", "Police", "ESF 13: Law Enforcement", "919400780088", 8.4975, 76.9510),
]

def load_agency_seed():
    csv_path = os.path.join(os.path.dirname(__file__), "data", "coordinates.csv")
    if not os.path.exists(csv_path):
        print(f"[WARN] {csv_path} not found. Using default TVM mock agencies.")
        return AGENCY_SEED
    
    agencies = []
    try:
        with open(csv_path, mode="r", encoding="utf-8") as f:
            # handle cases where the user's csv might have BOM or slight variations
            content = f.read().replace('\ufeff', '')
            import io
            reader = csv.DictReader(io.StringIO(content))
            # Expected columns: Category, Name, Latitude, Longitude, (optional whatsapp, esf_role)
            for row in reader:
                # Lowercase all keys to handle "Latitude" vs "latitude"
                row_lower = {k.strip().lower(): v for k, v in row.items() if k}
                name = row_lower.get("name", "Unknown Agency")
                category = row_lower.get("category", "Admin")
                lat = float(row_lower.get("latitude", 0.0))
                lon = float(row_lower.get("longitude", 0.0))
                whatsapp = row_lower.get("whatsapp", None)
                esf_role = row_lower.get("esf_role", f"ESF: {category}")
                agencies.append((name, category, esf_role, whatsapp, lat, lon))
        print(f"[INFO] Loaded {len(agencies)} agencies from coordinates.csv.")
        return agencies
    except Exception as e:
        print(f"[ERROR] Failed to parse {csv_path}: {e}")
        return AGENCY_SEED

# ── Hospital & Shelter resources (TVM) ───────────────────────────────────────
RESOURCE_SEED = [
    # (name, type, cap_total, cap_avail, er_total, er_avail, lat, lon, inclusive)
    ("General Hospital TVM",      "Hospital", 500,  45, 10, 3, 8.4977, 76.9415, 0),
    ("Medical College TVM",       "Hospital", 1200, 80, 25, 7, 8.5241, 76.9189, 1),
    ("SAT Hospital TVM",          "Hospital", 400,  30,  8, 2, 8.5148, 76.9243, 0),
    ("KIMS Hospital",             "Hospital", 300,  20,  6, 1, 8.5165, 76.9312, 1),
    ("PTP Nagar Relief Camp",     "Shelter",  200, 160, 0, 0, 8.5061, 76.9531, 1),
    ("Peroorkada Relief Camp",    "Shelter",  150, 120, 0, 0, 8.5330, 76.9740, 0),
]

def seed():
    init_db()  # ensure tables exist
    conn = get_connection()
    cur = conn.cursor()

    # Clear existing seed data (idempotent re-run)
    cur.executescript("DELETE FROM agencies; DELETE FROM resources;")

    active_agencies = load_agency_seed()

    # Insert agencies
    cur.executemany("""
        INSERT INTO agencies
            (name, category, esf_role, whatsapp, latitude, longitude, region)
        VALUES (?,?,?,?,?,?,'TVM')
    """, active_agencies)

    # Insert resources
    cur.executemany("""
        INSERT INTO resources
            (name, type, cap_total, cap_avail, er_total, er_avail,
             lat, lon, inclusive)
        VALUES (?,?,?,?,?,?,?,?,?)
    """, RESOURCE_SEED)

    conn.commit()
    conn.close()

    print(f"[SEED] Inserted {len(active_agencies)} agencies, {len(RESOURCE_SEED)} resources.")

if __name__ == "__main__":
    seed()