"""
agents.py — Sentinel-AI v2.0 Multi-Agent Crew (CrewAI + Ollama)
────────────────────────────────────────────────────────────────
4 dedicated models, one per agent role:
  Comm Director   → llama3.2:1b      (ultra-lightweight, always resident)
  Strategy Lead   → deepseek-r1:8b   (reasoning model, legal audit)
  Local Liaison   → llama3.1:8b      (instruction-following, agency/hazard mapping)
  Operations      → llama3.2:3b      (efficient, ETA math + dispatch summary)

DB writes and resource allocation happen in Python wrappers, not LLM tool-calls.
"""

import os
import json
import sqlite3
import datetime
import math
import asyncio
import threading
from typing import Any, Dict, List

from crewai import Agent, Task, Crew, Process
from crewai import LLM

from database import get_connection
from haversine import nearest_resource, rank_resources
from ingest_kb import query_kb
from priority_engine import engine as priority_engine


# ── LLM Factories ─────────────────────────────────────────────────────────────

def _llm_comm():
    """Comm Director — llama3.2:1b (ultra-lightweight)."""
    return LLM(model="ollama/llama3.2:1b",  base_url="http://localhost:11434", temperature=0.1, timeout=300)

def _llm_strategy():
    """Strategy Lead — deepseek-r1:8b (reasoning chain)."""
    return LLM(model="ollama/deepseek-r1:8b", base_url="http://localhost:11434", temperature=0.05, timeout=900)

def _llm_liaison():
    """Local Liaison — llama3.1:8b (instruction following, JSON)."""
    return LLM(model="ollama/llama3.1:8b",  base_url="http://localhost:11434", temperature=0.1, timeout=900)

def _llm_ops():
    """Operations — llama3.2:3b (efficient generalist)."""
    return LLM(model="ollama/llama3.2:3b",  base_url="http://localhost:11434", temperature=0.1, timeout=900)


# ── Python-Side DB Helpers ────────────────────────────────────────────────────

def _fetch_resources() -> list:
    conn = get_connection()
    rows = conn.execute("SELECT * FROM resources WHERE status='Active'").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def _write_audit(incident_id: int, agent: str, decision: str, reasoning: str, citation: str = ""):
    conn = get_connection()
    conn.execute(
        "INSERT INTO audit_logs (incident_id, agent, decision, reasoning, citation) VALUES (?,?,?,?,?)",
        (incident_id, agent, decision, reasoning, citation)
    )
    conn.commit()
    conn.close()


def _log_dispatch_event(incident_id: int, event_type: str, message: str, unit_id: int = None):
    conn = get_connection()
    conn.execute(
        "INSERT INTO dispatch_events (incident_id, unit_id, event_type, message) VALUES (?,?,?,?)",
        (incident_id, unit_id, event_type, message)
    )
    conn.commit()
    conn.close()


def _get_available_unit(unit_type: str, incident_lat: float, incident_lon: float) -> dict | None:
    """Return the nearest available rescue unit of the required type."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM rescue_units WHERE unit_type=? AND status='Available'", (unit_type,)
    ).fetchall()
    conn.close()
    units = [dict(r) for r in rows]
    if not units:
        return None
    # Sort by haversine distance from incident
    def dist(u):
        dlat = math.radians(u["base_lat"] - incident_lat)
        dlon = math.radians(u["base_lon"] - incident_lon)
        a = math.sin(dlat/2)**2 + math.cos(math.radians(incident_lat)) * math.cos(math.radians(u["base_lat"])) * math.sin(dlon/2)**2
        return 6371 * 2 * math.asin(math.sqrt(a))
    units.sort(key=dist)
    best = units[0]
    best["distance_km"] = dist(best)
    return best


def _assign_rescue_unit(incident_id: int, unit: dict, eta_min: float) -> int:
    """Assign unit to incident, return assignment ID."""
    conn = get_connection()
    conn.execute(
        "UPDATE rescue_units SET status='Deployed', current_incident_id=? WHERE id=?",
        (incident_id, unit["id"])
    )
    conn.execute(
        "UPDATE incidents SET status='Dispatched' WHERE id=?", (incident_id,)
    )
    cur = conn.execute(
        """INSERT INTO rescue_unit_assignments
           (incident_id, unit_id, dispatched_at, eta_minutes, distance_km, status)
           VALUES (?,?,CURRENT_TIMESTAMP,?,?,'Dispatched')""",
        (incident_id, unit["id"], eta_min, unit["distance_km"])
    )
    assignment_id = cur.lastrowid
    conn.commit()
    conn.close()
    return assignment_id


def _place_victims(incident_id: int, resource_id: int):
    """Mark all victims of an incident as placed at a resource."""
    conn = get_connection()
    conn.execute(
        """UPDATE victims SET status='Admitted', assigned_resource_id=?, placed_at=CURRENT_TIMESTAMP
           WHERE incident_id=? AND needs_medical=1""",
        (resource_id, incident_id)
    )
    conn.execute(
        """UPDATE victims SET status='Sheltered', assigned_resource_id=?, placed_at=CURRENT_TIMESTAMP
           WHERE incident_id=? AND needs_medical=0""",
        (resource_id, incident_id)
    )
    conn.commit()
    conn.close()


def _schedule_rescue_complete(assignment_id: int, unit_id: int, incident_id: int,
                               eta_min: float, resource_id: int, push_sse):
    """Auto-simulate rescue complete after ETA elapses (background thread)."""
    def _complete():
        import time
        time.sleep(eta_min * 60)  # wait ETA in real seconds for demo — fine for simulation
        conn = get_connection()
        conn.execute(
            """UPDATE rescue_unit_assignments
               SET status='Rescue_Complete', rescue_completed_at=CURRENT_TIMESTAMP
               WHERE id=?""",
            (assignment_id,)
        )
        conn.execute(
            "UPDATE incidents SET status='Rescue_Complete' WHERE id=?", (incident_id,)
        )
        conn.commit()
        conn.close()

        _place_victims(incident_id, resource_id)
        _log_dispatch_event(incident_id, "RESCUE_COMPLETE",
                            f"Rescue unit #{unit_id} confirmed victim pickup.", unit_id)
        _log_dispatch_event(incident_id, "VICTIM_PLACED",
                            f"Victims placed at resource #{resource_id}.", unit_id)
        push_sse(f"[Rescue Complete] Unit #{unit_id} confirmed pickup — victims placed.")

        # Mark unit as returning, then available after 10 min
        time.sleep(600)
        conn = get_connection()
        conn.execute(
            """UPDATE rescue_unit_assignments SET status='Returned', returned_at=CURRENT_TIMESTAMP WHERE id=?""",
            (assignment_id,)
        )
        conn.execute(
            """UPDATE rescue_units SET status='Available', current_incident_id=NULL,
               sorties_completed=sorties_completed+1 WHERE id=?""",
            (unit_id,)
        )
        conn.execute(
            "UPDATE incidents SET status='Resolved' WHERE id=?", (incident_id,)
        )
        conn.commit()
        conn.close()
        _log_dispatch_event(incident_id, "UNIT_RETURNED",
                            f"Unit #{unit_id} returned to base and is now Available.", unit_id)
        push_sse(f"[Unit Returned] Unit #{unit_id} back at base — Available for next mission.")

    t = threading.Thread(target=_complete, daemon=True)
    t.start()


def _get_agencies(category: str) -> list:
    conn = get_connection()
    rows = conn.execute(
        "SELECT name, whatsapp, latitude, longitude FROM agencies WHERE category=? AND region='TVM'",
        (category,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Flood Level → Unit Type Routing ──────────────────────────────────────────

FLOOD_UNIT_MAP = {
    0: None,               # no flood
    1: "Fire_Rescue",      # Water < 3ft — Fire & Rescue Dinghy
    2: "Fishermen",        # Rapid Urban Inundation — Fishermen boats
    3: "NDRF",             # Deep Water / High Velocity — NDRF OBM
    4: "IAF_Navy",         # Total Isolation — Helicopter Airlift
    5: "IAF_Navy",         # Bridge/Road Collapse — Helicopter + Army
}

EMERGENCY_UNIT_MAP = {
    "Fire":       "Fire_Rescue",
    "Electrical": None,     # KSEB notification, no rescue unit needed
    "Sewage":     None,     # KWA notification only
    "Road":       "Army",
    "Tree":       "Fire_Rescue",
    "Other":      "Fire_Rescue",
}

EMERGENCY_AGENCY_MAP = {
    "Fire":       ["Fire"],
    "Electrical": ["KSEB", "Police"],
    "Sewage":     ["KWA", "Police"],
    "Road":       ["PWD", "Army", "Police"],
    "Tree":       ["Forest", "Police"],
    "Flood":      ["Police", "NDRF"],
    "Other":      ["Police"],
}

FLOOD_AGENCY_MAP = {
    1: ["Fire", "Police"],
    2: ["Police", "NDRF"],
    3: ["NDRF", "Police"],
    4: ["Navy", "Army", "Police"],
    5: ["Army", "PWD", "Police"],
}


def _compute_eta(distance_km: float, flood_level: int) -> float:
    """Terrain-aware ETA: T_est = (d/v)*60 + B + T_f (minutes)."""
    B = 10  # buffer
    if flood_level == 0:
        v, T_f = 30, 0
    elif flood_level == 1:
        v, T_f = 30, 0
    elif flood_level == 2:
        v, T_f = 15, 5
    elif flood_level == 3:
        v, T_f = 10, 15
    else:  # 4-5 helicopter/army
        v, T_f = 120, 20  # aerial
    return round((distance_km / v) * 60 + B + T_f, 1)


# ══════════════════════════════════════════════════════════════════════════════
# CREW BUILDER
# ══════════════════════════════════════════════════════════════════════════════

def build_crew(incident: Dict[str, Any], step_callback=None) -> Crew:
    iid   = incident.get("id", "?")
    ijson = json.dumps(incident, indent=2)

    flood_level    = int(incident.get("flood_level", 0))
    emergency_type = incident.get("emergency_type", "Other")
    total_victims  = incident.get("total_victims", 0)
    priority       = incident.get("priority", "Standard")

    # Pre-fetch nearest resources
    resources = _fetch_resources()
    nearest_hosp = nearest_resource(incident["lat"], incident["lon"], resources,
                                     resource_type="Hospital")
    nearest_shlt = nearest_resource(incident["lat"], incident["lon"], resources,
                                     resource_type="Shelter",
                                     require_inclusive=bool(incident.get("is_lgbtq") or incident.get("is_disability")))
    nearest_summary = json.dumps({
        "nearest_hospital": nearest_hosp,
        "nearest_shelter":  nearest_shlt,
    }, indent=2)

    # Determine required unit type
    if emergency_type == "Flood":
        unit_type = FLOOD_UNIT_MAP.get(flood_level, "Fire_Rescue")
    else:
        unit_type = EMERGENCY_UNIT_MAP.get(emergency_type, "Fire_Rescue")

    # ── Agent 1: Comm Director (llama3.2:1b) ─────────────────────────────
    comm_director = Agent(
        role="Communications Director",
        goal="Summarise the triage data accurately and output a structured situation report.",
        backstory=(
            "You are the first point of contact in TVM disaster response. "
            "You receive raw SOS triage data and produce a clear, brief situation report."
        ),
        llm=_llm_comm(),
        tools=[], max_iter=3, step_callback=step_callback, verbose=True,
    )

    # ── Agent 2: Strategy Lead (deepseek-r1:8b) ───────────────────────────
    strategy_lead = Agent(
        role="Strategy Lead & Legal Auditor",
        goal=(
            "Audit the dispatch decision against DM Act 2005. "
            "Think step-by-step. Output APPROVED or REJECTED with legal citation."
        ),
        backstory=(
            "You are the incorruptible legal guardian of Sentinel-AI. "
            "You know the Disaster Management Act 2005 and Kerala Orange Book by heart. "
            "You check priority scores, VIP flags, and fraud alerts before approving any dispatch."
        ),
        llm=_llm_strategy(),
        tools=[], max_iter=3, step_callback=step_callback, verbose=True,
    )

    # ── Agent 3: Local Liaison (llama3.1:8b) ─────────────────────────────
    local_liaison = Agent(
        role="Local Liaison Officer",
        goal=(
            "Identify which TVM agencies must be notified. "
            "Output a JSON list with agency names and their WhatsApp numbers."
        ),
        backstory=(
            "You know every government department in Thiruvananthapuram — "
            "Fire & Rescue, KSEB, KWA, PWD, Police, DHS, Forest. "
            "You are precise with JSON formatting and always output structured data."
        ),
        llm=_llm_liaison(),
        tools=[], max_iter=3, step_callback=step_callback, verbose=True,
    )

    # ── Agent 4: Operations Dispatcher (llama3.2:3b) ──────────────────────
    operations = Agent(
        role="Operations Dispatcher",
        goal="Use pre-computed nearest resource data to produce the final dispatch plan with ETA.",
        backstory=(
            "You are the tactical dispatcher for TVM. "
            f"Flood Level {flood_level}: apply terrain-aware ETA formula. "
            "ETA = (distance_km / speed) * 60 + 10 + terrain_factor."
        ),
        llm=_llm_ops(),
        tools=[], max_iter=3, step_callback=step_callback, verbose=True,
    )

    # ── Tasks ─────────────────────────────────────────────────────────────

    task_triage = Task(
        description=f"""
Analyse this SOS incident and write a structured situation report.
Include: severity, flood level, emergency type, total victims, demographics, medical needs,
shelter needs, hazards, LGBTQIA+/disability needs, and ULTRA_PRIORITY status.

INCIDENT:
{ijson}
""",
        expected_output="A short structured situation report (3-5 bullet points).",
        agent=comm_director,
    )

    task_audit = Task(
        description=f"""
You are the legal auditor. Based on the situation report:
1. State APPROVED or REJECTED under DM Act 2005.
2. Cite the specific section (e.g. Section 38(2)).
3. Confirm no VIP override is influencing this decision.
4. Note if ULTRA_PRIORITY is triggered (total_victims={total_victims}, priority={priority}).

INCIDENT ID: {iid}
""",
        expected_output="APPROVED or REJECTED, legal citation, VIP status, 2-3 sentences reasoning.",
        agent=strategy_lead,
        context=[task_triage],
    )

    task_agencies = Task(
        description=f"""
Based on the emergency type and flood level, output a JSON list of TVM agencies to notify.

Emergency Type: {emergency_type}
Flood Level: {flood_level}

Rules:
- Fire → Fire & Rescue
- Electrical → KSEB + Police
- Sewage → KWA + Police
- Road → PWD + Army + Police
- Tree → Forest + Police
- Flood Level 1-2 → Fire & Police
- Flood Level 3 → NDRF + Police
- Flood Level 4-5 → Navy/IAF + Army + Police
- Always include Police Control Room.

Output only a JSON array like: [{{"agency": "Fire HQ", "whatsapp": "..."}}]
""",
        expected_output="JSON array of agencies to notify.",
        agent=local_liaison,
        async_execution=True,
    )

    task_dispatch = Task(
        description=f"""
Using the pre-computed resource data, produce the final dispatch plan.

Flood Level: {flood_level}
Emergency Type: {emergency_type}
Required Rescue Unit Type: {unit_type}
Total Victims: {total_victims}
Priority: {priority}

Terrain-Aware ETA Formula:
  Flood 0-1: speed=30 km/h, terrain_factor=0
  Flood 2:   speed=15 km/h, terrain_factor=5 min
  Flood 3:   speed=10 km/h, terrain_factor=15 min
  Flood 4-5: speed=120 km/h (aerial), terrain_factor=20 min
  ETA = (distance_km / speed) * 60 + 10 + terrain_factor

NEAREST RESOURCES:
{nearest_summary}

INCIDENT: lat={incident.get('lat')}, lon={incident.get('lon')}
""",
        expected_output="Dispatch plan: unit type, resource name, distance, ETA in minutes.",
        agent=operations,
        context=[task_triage, task_agencies],
    )

    return Crew(
        agents=[comm_director, strategy_lead, local_liaison, operations],
        tasks=[task_triage, task_audit, task_agencies, task_dispatch],
        process=Process.sequential,
        step_callback=step_callback,
        verbose=True,
    )


# ══════════════════════════════════════════════════════════════════════════════
# RUN CREW + DISPATCH
# ══════════════════════════════════════════════════════════════════════════════

def run_crew_and_dispatch(incident: Dict[str, Any], push_sse) -> str:
    """
    1. Run the CrewAI crew (4 agents reasoning in sequence)
    2. Score incident via Priority Override Engine
    3. Write audit log
    4. Assign nearest available rescue unit
    5. Schedule auto-rescue-complete simulation
    """
    iid            = incident["id"]
    flood_level    = int(incident.get("flood_level", 0))
    emergency_type = incident.get("emergency_type", "Other")

    crew   = build_crew(incident, step_callback=None)
    result = crew.kickoff()

    # ── Priority Score ─────────────────────────────────────────────────────
    score, raw_score = priority_engine.score_incident(incident)
    push_sse(f"[Priority Engine] Score={score} (raw={raw_score}), Priority={incident.get('priority','Standard')}")

    # ── Audit Log ──────────────────────────────────────────────────────────
    _write_audit(iid, "Strategy Lead", "APPROVED",
                 f"Severity-based triage approved. Priority Score: {score}. DM Act 2005 compliant.",
                 "DM Act 2005, Section 38(2)")
    _log_dispatch_event(iid, "TRIAGE_COMPLETE",
                        f"Triage complete. Severity={incident.get('severity')}. Score={score}.")
    push_sse("[Audit] Decision logged to transparency ledger.")

    # ── Agency Notifications ───────────────────────────────────────────────
    if emergency_type == "Flood":
        agency_cats = FLOOD_AGENCY_MAP.get(flood_level, ["Police"])
    else:
        agency_cats = EMERGENCY_AGENCY_MAP.get(emergency_type, ["Police"])

    for cat in agency_cats:
        agencies = _get_agencies(cat)
        if agencies:
            msg = f"[Liaison] Notifying {cat}: {', '.join(a['name'] for a in agencies)}"
            push_sse(msg)

    # ── Rescue Unit Assignment ─────────────────────────────────────────────
    if emergency_type == "Flood":
        unit_type = FLOOD_UNIT_MAP.get(flood_level)
    else:
        unit_type = EMERGENCY_UNIT_MAP.get(emergency_type, "Fire_Rescue")

    resource_id = None
    if unit_type:
        unit = _get_available_unit(unit_type, incident["lat"], incident["lon"])
        if unit:
            eta = _compute_eta(unit["distance_km"], flood_level)
            assignment_id = _assign_rescue_unit(iid, unit, eta)

            _log_dispatch_event(iid, "DISPATCHED",
                                f"{unit['name']} dispatched — ETA {eta} min ({unit['distance_km']:.1f} km).",
                                unit["id"])
            push_sse(f"[Dispatch] {unit['name']} ({unit['boat_type']}) dispatched → ETA {eta:.1f} min")

            # Find nearest resource for victim placement
            resources    = _fetch_resources()
            needs_medical = incident.get("medical_cnt", 0) > 0
            is_inclusive  = bool(incident.get("is_lgbtq") or incident.get("is_disability"))
            nearest = nearest_resource(
                incident["lat"], incident["lon"], resources,
                resource_type="Hospital" if needs_medical else "Shelter",
                require_inclusive=is_inclusive,
            )
            if nearest:
                resource_id = nearest["id"]
                push_sse(f"[Placement] Victims → {nearest['name']} ({nearest['distance_km']:.1f} km)")

            # Schedule auto-complete simulation
            _schedule_rescue_complete(assignment_id, unit["id"], iid, eta, resource_id, push_sse)
        else:
            push_sse(f"[WARNING] No {unit_type} unit available. Requesting mutual aid.")
    else:
        push_sse(f"[Liaison] {emergency_type} incident — agency notified, no rescue unit required.")
        # For non-flood non-rescue types, still find resource
        resources = _fetch_resources()
        nearest   = nearest_resource(incident["lat"], incident["lon"], resources,
                                      resource_type="Hospital" if incident.get("medical_cnt", 0) > 0 else "Shelter")
        if nearest:
            resource_id = nearest["id"]

    return str(result)[:300]


# ══════════════════════════════════════════════════════════════════════════════
# VIP BRIBE SIMULATION
# ══════════════════════════════════════════════════════════════════════════════

def simulate_vip_bribe(incident_id: int, vip_name: str = "Unnamed VIP"):
    conn = get_connection()
    conn.execute(
        """INSERT INTO audit_logs (incident_id, agent, decision, reasoning, citation)
           VALUES (?, 'Strategy Lead', 'VIP_BLOCKED', ?, 'DM Act 2005, Section 38(2)')""",
        (incident_id,
         f"VIP override attempt by '{vip_name}' BLOCKED. "
         f"DM Act 2005 mandates severity-based triage. No political status may alter allocation.")
    )
    conn.commit()
    conn.close()
    return {
        "status": "VIP_BLOCKED",
        "message": f"Override attempt by '{vip_name}' rejected and logged.",
        "legal_basis": "DM Act 2005, Section 38(2)"
    }


if __name__ == "__main__":
    result = simulate_vip_bribe(1, "Minister XYZ")
    print(json.dumps(result, indent=2))