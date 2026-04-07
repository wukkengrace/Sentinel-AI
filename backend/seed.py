"""
seed.py — Populates the Sentinel-AI v2.0 DB with Thiruvananthapuram (TVM) data.

Tables seeded:
  • agencies        → from data/coordinates.csv (+ KWA, NDRF, Navy, Army)
  • resources       → hospitals + categorised shelters
  • rescue_units    → synthetic fleet (Fire/Rescue, Fishermen, NDRF, IAF/Navy, Army)
  • fraud_db        → 10 synthetic blacklisted Aadhar IDs

Run once (idempotent) after init_db():
  python seed.py
"""

import os
import csv
import io
import random
from database import get_connection, init_db

# ── Fraud DB ───────────────────────────────────────────────────────────────────
FRAUD_AADHAR_SEED = [
    ("1234-5678-9012", "Known false reporter - Flood 2024"),
    ("9876-5432-1098", "Duplicate SOS spam account"),
    ("1111-2222-3333", "Blacklisted - insurance fraud attempt"),
    ("4444-5555-6666", "Repeated hoax calls"),
    ("7777-8888-9999", "Identity impersonation"),
    ("2468-1357-8024", "Fraudulent VIP claim"),
    ("1357-2468-9135", "Known misinformation actor"),
    ("8642-9753-0864", "Previous arrest - SOS misuse"),
    ("1928-3746-5564", "Refugee camp false report"),
    ("5544-3322-1100", "Cross-district fraudster"),
]

# ── Agencies (fallback if CSV missing) ────────────────────────────────────────
AGENCY_SEED_FALLBACK = [
    ("District Collectorate TVM", "Admin",  "ESF 5: Emergency Management", "918547610029", 8.555983, 76.961030),
    ("DHS HQ",                    "DHS",    "ESF 8: Health & Medical",     "918301838148", 8.4988,  76.9405),
    ("Fire HQ Chengalchoola",     "Fire",   "ESF 4: Firefighting",         "919497996964", 8.4938,  76.9535),
    ("KSEB HQ Pattom",            "KSEB",   "ESF 12: Energy",              "910000000001", 8.5244,  76.9431),
    ("Police Control Room",       "Police", "ESF 13: Law Enforcement",     "919400780088", 8.4975,  76.9510),
    ("KWA Jalabhavan HQ",         "KWA",    "ESF 3: Public Works & Water", "910000000002", 8.5082,  76.9545),
    ("PWD Public Office Complex", "PWD",    "ESF 1: Transportation",       "910000000003", 8.5085,  76.9540),
    ("Forest Headquarters TVM",   "Forest", "ESF 11: Agriculture/Nat Res", "910000000004", 8.4980,  76.9635),
    ("NDRF 119 Bn HQ",            "NDRF",   "ESF 9: Urban Search & Rescue","910000000005", 8.5100,  76.9500),
    ("INS Garuda (Navy Base)",    "Navy",   "ESF 9: Search & Rescue",      "910000000006", 8.4100,  76.9800),
    ("Army 21 Engr Rgt TVM",      "Army",   "ESF 1: Transportation/Engrg", "910000000007", 8.5200,  76.9400),
]

# ── Resources: Hospitals ───────────────────────────────────────────────────────
HOSPITAL_SEED = [
    # (name, cap_total, cap_avail, er_total, er_avail, lat, lon, inclusive)
    ("General Hospital TVM",      500,  45, 10, 3, 8.4977, 76.9415, 1),
    ("Medical College TVM",      1200,  80, 25, 7, 8.5241, 76.9189, 1),
    ("SAT Hospital TVM",          400,  30,  8, 2, 8.5148, 76.9243, 0),
    ("KIMS Hospital",             300,  20,  6, 1, 8.5165, 76.9312, 1),
    ("Ananthapuri Hospital",      350,  25,  8, 2, 8.5230, 76.9280, 1),
    ("Cosmopolitan Hospital",     280,  18,  5, 1, 8.5142, 76.9357, 0),
    ("SUT Hospital",              320,  22,  7, 2, 8.5210, 76.9200, 1),
    ("Chaithanya Hospital",       150,  10,  3, 1, 8.5063, 76.9478, 0),
    ("District Hospital Neyyatinkara", 200, 15,  4, 1, 8.3965, 77.0825, 0),
    ("Taluk Hospital Attingal",   180,  12,  4, 1, 8.6930, 76.8152, 0),
]

# ── Resources: Shelters (categorised) ─────────────────────────────────────────
SHELTER_SEED = [
    # (name, cap_total, cap_avail, lat, lon, inclusive, shelter_type)
    ("PTP Nagar Relief Camp",        200, 160, 8.5061, 76.9531, 1, "LGBTQIA+"),
    ("Peroorkada Relief Camp",       150, 120, 8.5330, 76.9740, 0, "Male"),
    ("Kesavadasapuram Community Hall",120,  90, 8.5190, 76.9410, 0, "Female_Children"),
    ("Ambalamukku Relief Camp",      100,  80, 8.5290, 76.9450, 1, "Disability"),
    ("Kazhakootam Relief Camp",      180, 140, 8.5663, 76.8833, 0, "General"),
    ("Vanchiyoor School Camp",        80,  60, 8.4960, 76.9490, 0, "Male"),
    ("Attingal Town Hall Camp",      100,  75, 8.6930, 76.8152, 0, "Female_Children"),
    ("Neyyatinkara Govt School",      90,  70, 8.3965, 77.0825, 1, "LGBTQIA+"),
    ("Parassala Relief Centre",       70,  55, 8.3445, 77.1534, 0, "General"),
    ("Varkala Community Centre",     110,  85, 8.7350, 76.7110, 1, "Disability"),
]

# ── Rescue Fleet ──────────────────────────────────────────────────────────────
# (name, unit_type, boat_type, crew_size, victim_capacity, base_lat, base_lon)
RESCUE_UNIT_SEED = [
    # Fire & Rescue — IRB (Inflatable Rescue Boat)
    ("TVM Fire IRB-1",       "Fire_Rescue", "IRB",              4,  15, 8.4938, 76.9535),
    ("TVM Fire IRB-2",       "Fire_Rescue", "IRB",              4,  15, 8.4878, 76.9182),
    ("Kazha Fire IRB",       "Fire_Rescue", "IRB",              3,  12, 8.5663, 76.8833),
    # Fire & Rescue — Dinghy (narrow lane evacuations)
    ("TVM Fire Dinghy-1",    "Fire_Rescue", "Dinghy",           2,   5, 8.4938, 76.9535),
    ("TVM Fire Dinghy-2",    "Fire_Rescue", "Dinghy",           2,   5, 8.4878, 76.9182),
    ("Attingal Dinghy",      "Fire_Rescue", "Dinghy",           2,   5, 8.6925, 76.8152),
    # Fishermen (Operation Jalaraksha)
    ("Vizhinjam Fishermen-1","Fishermen",   "Fishermen_Boat",   5,  35, 8.3815, 76.9935),
    ("Vizhinjam Fishermen-2","Fishermen",   "Fishermen_Boat",   5,  30, 8.3815, 76.9935),
    ("Poovar Fishermen-1",   "Fishermen",   "Fishermen_Boat",   4,  25, 8.3185, 77.0652),
    ("Poovar Fishermen-2",   "Fishermen",   "Fishermen_Boat",   4,  25, 8.3185, 77.0652),
    ("Varkala Fishermen",    "Fishermen",   "Fishermen_Boat",   6,  50, 8.7350, 76.7110),
    ("Kollam Road Fishermen","Fishermen",   "Fishermen_Boat",   5,  40, 8.7615, 76.7932),
    ("Kovalam Fishermen",    "Fishermen",   "Fishermen_Boat",   4,  20, 8.3930, 76.9800),
    ("Anchuthengu Fishermen","Fishermen",   "Fishermen_Boat",   5,  30, 8.6750, 76.6900),
    # NDRF — OBM Power Boats / Divers
    ("NDRF Squad Alpha",     "NDRF",        "OBM_Boat",         7,  20, 8.5100, 76.9500),
    ("NDRF Squad Bravo",     "NDRF",        "OBM_Boat",         7,  20, 8.5100, 76.9500),
    ("NDRF Squad Charlie",   "NDRF",        "OBM_Boat",         6,  18, 8.5100, 76.9500),
    # IAF / Navy Helicopters
    ("Navy Chetak (Light)",  "IAF_Navy",    "Helicopter_Light",  4,   3, 8.4100, 76.9800),
    ("IAF Mi-17 Alpha",      "IAF_Navy",    "Helicopter_Medium", 5,  20, 8.4100, 76.9800),
    ("IAF Mi-17 Bravo",      "IAF_Navy",    "Helicopter_Medium", 5,  20, 8.4100, 76.9800),
    # Army Engineering Column
    ("Army Engr Column-1",   "Army",        "Engineering_Column",45,   0, 8.5200, 76.9400),
]


def load_agency_seed():
    csv_path = os.path.join(os.path.dirname(__file__), "data", "coordinates.csv")
    # Also try the raw filename as stored on disk
    alt_path = os.path.join(os.path.dirname(__file__), "data", "Category,Name,Latitude,Longitude.csv")

    target = csv_path if os.path.exists(csv_path) else (alt_path if os.path.exists(alt_path) else None)
    if not target:
        print("[WARN] coordinates.csv not found. Using fallback agency data.")
        return AGENCY_SEED_FALLBACK

    agencies = []
    try:
        with open(target, mode="r", encoding="utf-8") as f:
            content = f.read().replace("\ufeff", "")
            reader = csv.DictReader(io.StringIO(content))
            for row in reader:
                r = {k.strip().lower(): v.strip() for k, v in row.items() if k}
                name     = r.get("name", "Unknown Agency")
                category = r.get("category", "Admin")
                lat      = float(r.get("latitude", 0.0) or 0.0)
                lon      = float(r.get("longitude", 0.0) or 0.0)
                whatsapp = r.get("whatsapp", None)
                esf_role = r.get("esf_role", f"ESF: {category}")
                # Map CSV categories to DB CHECK constraint values
                cat_map = {
                    "collectorate": "Admin", "dho": "Admin",
                    "fire station": "Fire", "fire": "Fire",
                    "kseb": "KSEB", "police control room": "Police",
                    "dhs": "DHS", "dmo": "DMO",
                    "forest department": "Forest", "forest": "Forest",
                    "pwd": "PWD", "cooperation": "Cooperation",
                    "other admin": "Admin", "kwa": "KWA",
                    "ndrf": "NDRF", "navy": "Navy", "army": "Army",
                }
                db_cat = cat_map.get(category.lower(), "Admin")
                agencies.append((name, db_cat, esf_role, whatsapp, lat, lon))
        print(f"[INFO] Loaded {len(agencies)} agencies from {os.path.basename(target)}.")
        return agencies
    except Exception as e:
        print(f"[ERROR] Failed to parse CSV: {e}")
        return AGENCY_SEED_FALLBACK


def seed():
    init_db()
    conn = get_connection()
    cur  = conn.cursor()

    # ── Clear existing seed data (idempotent) ──────────────────────────────
    cur.executescript("""
        DELETE FROM rescue_units;
        DELETE FROM agencies;
        DELETE FROM resources;
        DELETE FROM fraud_db;
    """)

    # ── Agencies ───────────────────────────────────────────────────────────
    active_agencies = load_agency_seed()
    cur.executemany("""
        INSERT INTO agencies (name, category, esf_role, whatsapp, latitude, longitude, region)
        VALUES (?,?,?,?,?,?,'TVM')
    """, active_agencies)

    # ── Hospitals ──────────────────────────────────────────────────────────
    for h in HOSPITAL_SEED:
        name, cap_total, cap_avail, er_total, er_avail, lat, lon, inclusive = h
        cur.execute("""
            INSERT INTO resources (name, type, cap_total, cap_avail, er_total, er_avail,
                                   lat, lon, inclusive, shelter_type)
            VALUES (?,?,?,?,?,?,?,?,?,'General')
        """, (name, "Hospital", cap_total, cap_avail, er_total, er_avail, lat, lon, inclusive))

    # ── Shelters ───────────────────────────────────────────────────────────
    for s in SHELTER_SEED:
        name, cap_total, cap_avail, lat, lon, inclusive, shelter_type = s
        cur.execute("""
            INSERT INTO resources (name, type, cap_total, cap_avail, er_total, er_avail,
                                   lat, lon, inclusive, shelter_type)
            VALUES (?,?,?,?,0,0,?,?,?,?)
        """, (name, "Shelter", cap_total, cap_avail, lat, lon, inclusive, shelter_type))

    # ── Rescue Units ───────────────────────────────────────────────────────
    cur.executemany("""
        INSERT INTO rescue_units (name, unit_type, boat_type, crew_size, victim_capacity,
                                   status, base_lat, base_lon)
        VALUES (?,?,?,?,?,'Available',?,?)
    """, RESCUE_UNIT_SEED)

    # ── Fraud DB ───────────────────────────────────────────────────────────
    cur.executemany("""
        INSERT INTO fraud_db (aadhar_id, reason) VALUES (?,?)
    """, FRAUD_AADHAR_SEED)

    conn.commit()
    conn.close()

    print(f"[SEED] {len(active_agencies)} agencies")
    print(f"[SEED] {len(HOSPITAL_SEED)} hospitals + {len(SHELTER_SEED)} shelters")
    print(f"[SEED] {len(RESCUE_UNIT_SEED)} rescue units")
    print(f"[SEED] {len(FRAUD_AADHAR_SEED)} fraud Aadhar IDs")
    print("[SEED] Done ✓")


if __name__ == "__main__":
    seed()