"""
seed.py — Populates the Sentinel-AI DB with Thiruvananthapuram (TVM) data.
Sources:
  • Category_Name_Latitude_Longitude.csv  → agencies table
  • Hardcoded TVM hospitals/shelters      → resources table
Run once after init_db().
"""

from database import get_connection, init_db


# ── Raw CSV data (parsed from Category_Name_Latitude_Longitude.csv) ──────────
AGENCY_SEED = [
    # (name, category, esf_role, whatsapp, latitude, longitude)
    # Collectorates
    ("District Collectorate TVM", "Admin",
     "ESF 5: Emergency Management", "918547610029", 8.555983, 76.961030),
    ("Nedumangad Civil Station",  "Admin",
     "ESF 5: Emergency Management", None, 8.6074, 77.0047),
    ("Neyyattinkara Civil Station","Admin",
     "ESF 5: Emergency Management", None, 8.3965, 77.0825),

    # DHS / DMO
    ("DHS HQ",         "DHS", "ESF 8: Health & Medical", "918301838148", 8.4988, 76.9405),
    ("DMO Health",     "DMO", "ESF 8: Health & Medical", None,           8.4985, 76.9408),
    ("DMO ISM/Homeo",  "DMO", "ESF 8: Health & Medical", None,           8.4981, 76.9412),

    # Fire Stations
    ("Fire HQ Chengalchoola",      "Fire", "ESF 4: Firefighting", "919497996964", 8.4938, 76.9535),
    ("Fire Station Chakka",         "Fire", "ESF 4: Firefighting", None,           8.4878, 76.9182),
    ("Fire Station Kazhakootam",    "Fire", "ESF 4: Firefighting", None,           8.5663, 76.8833),
    ("Attingal Fire Station",       "Fire", "ESF 4: Firefighting", None,           8.6925, 76.8152),
    ("Vizhinjam Fire Station",      "Fire", "ESF 4: Firefighting", None,           8.3815, 76.9935),
    ("Varkala Fire Station",        "Fire", "ESF 4: Firefighting", None,           8.7350, 76.7110),
    ("Kallambalam Fire Station",    "Fire", "ESF 4: Firefighting", None,           8.7615, 76.7932),
    ("Venjarammoodu Fire Station",  "Fire", "ESF 4: Firefighting", None,           8.6750, 76.9145),
    ("Vithura Fire Station",        "Fire", "ESF 4: Firefighting", None,           8.6645, 77.1065),
    ("Kattakada Fire Station",      "Fire", "ESF 4: Firefighting", None,           8.5055, 77.0815),
    ("Neyyardam Fire Station",      "Fire", "ESF 4: Firefighting", None,           8.5284, 77.1432),
    ("Poovar Fire Station",         "Fire", "ESF 4: Firefighting", None,           8.3185, 77.0652),
    ("Parassala Fire Station",      "Fire", "ESF 4: Firefighting", None,           8.3445, 77.1534),

    # KSEB
    ("KSEB HQ Pattom",     "KSEB", "ESF 12: Energy", "910000000001", 8.5244, 76.9431),
    ("KSEB District Office","KSEB", "ESF 12: Energy", None,           8.5042, 76.9485),

    # Police
    ("Police Control Room",             "Police", "ESF 13: Law Enforcement", "919400780088", 8.4975, 76.9510),
    ("Fort Police Station",             "Police", "ESF 13: Law Enforcement", None,           8.4825, 76.9455),
    ("Thampanoor Police Station",       "Police", "ESF 13: Law Enforcement", None,           8.4875, 76.9525),
    ("Museum Police Station",           "Police", "ESF 13: Law Enforcement", None,           8.5085, 76.9535),
    ("Medical College Police Station",  "Police", "ESF 13: Law Enforcement", None,           8.5225, 76.9275),
    ("Peroorkada Police Station",       "Police", "ESF 13: Law Enforcement", None,           8.5325, 76.9745),

    # Other
    ("Forest Headquarters",          "Forest",      "ESF 9: Search & Rescue", None, 8.4980, 76.9635),
    ("PWD Public Office Complex",    "PWD",          "ESF 3: Public Works",    None, 8.5085, 76.9540),
    ("PWD Roads & Bridges Division", "PWD",          "ESF 3: Public Works",    None, 8.4972, 76.9615),
    ("Cooperation Department HQ",    "Cooperation",  "ESF 11: Food/Water",     None, 8.4947, 76.9605),
    ("Secretariat Main Block",       "Admin",        "ESF 5: Emergency Mgmt",  None, 8.4982, 76.9502),
    ("KWA Jalabhavan HQ",            "Admin",        "ESF 3: Public Works",    None, 8.5082, 76.9545),
    ("KWA Palayam Section",          "Admin",        "ESF 3: Public Works",    None, 8.5015, 76.9505),
    ("KWA Pattoor Office",           "Admin",        "ESF 3: Public Works",    None, 8.4955, 76.9365),
]


# ── Hospital & Shelter resources (TVM) ───────────────────────────────────────
RESOURCE_SEED = [
    # (name, type, cap_total, cap_avail, er_total, er_avail, lat, lon, inclusive)
    ("General Hospital TVM",      "Hospital", 500,  45, 10, 3, 8.4977, 76.9415, 0),
    ("Medical College TVM",       "Hospital", 1200, 80, 25, 7, 8.5241, 76.9189, 1),
    ("SAT Hospital TVM",          "Hospital", 400,  30,  8, 2, 8.5148, 76.9243, 0),
    ("KIMS Hospital",             "Hospital", 300,  20,  6, 1, 8.5165, 76.9312, 1),
    ("Parippally Govt Hospital",  "Hospital", 150,  15,  4, 1, 8.8730, 76.8060, 0),

    ("PTP Nagar Relief Camp",     "Shelter",  200, 160, 0, 0, 8.5061, 76.9531, 1),
    ("Peroorkada Relief Camp",    "Shelter",  150, 120, 0, 0, 8.5330, 76.9740, 0),
    ("Neyyattinkara Relief Camp", "Shelter",  250, 200, 0, 0, 8.3960, 77.0830, 0),
    ("Kazhakoottam Relief Camp",  "Shelter",  180, 140, 0, 0, 8.5660, 76.8840, 1),
    ("Varkala Relief Camp",       "Shelter",  100,  90, 0, 0, 8.7340, 76.7120, 0),
]


def seed():
    init_db()  # ensure tables exist
    conn = get_connection()
    cur = conn.cursor()

    # Clear existing seed data (idempotent re-run)
    cur.executescript("DELETE FROM agencies; DELETE FROM resources;")

    # Insert agencies
    cur.executemany("""
        INSERT INTO agencies
            (name, category, esf_role, whatsapp, latitude, longitude, region)
        VALUES (?,?,?,?,?,?,'TVM')
    """, AGENCY_SEED)

    # Insert resources
    cur.executemany("""
        INSERT INTO resources
            (name, type, cap_total, cap_avail, er_total, er_avail,
             lat, lon, inclusive)
        VALUES (?,?,?,?,?,?,?,?,?)
    """, RESOURCE_SEED)

    conn.commit()
    conn.close()

    print(f"[SEED] Inserted {len(AGENCY_SEED)} agencies, {len(RESOURCE_SEED)} resources.")


if __name__ == "__main__":
    seed()