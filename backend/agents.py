"""
agents.py — Sentinel-AI v2.0 Multi-Agent Crew (CrewAI + Ollama)
────────────────────────────────────────────────────────────────
4 dedicated models, one per agent role:
  Comm Director   → llama3.2:1b      (ultra-lightweight, always resident)
  Strategy Lead   → deepseek-r1:8b   (reasoning model, legal audit)
  Local Liaison   → llama3.1:8b      (instruction-following, agency/hazard mapping)
  Operations      → llama3.2:3b      (efficient, ETA math + dispatch summary)

v2.0 Changes:
  - 10-minute admission simulation (configurable via ADMISSION_DELAY_SECONDS)
  - Fleet-specific override gate (only activates when specific fleet is 100% occupied)
  - External shelter fallback (search beyond local zone when capacity = 0)
  - Multi-agent consensus scoring (20% weight)
  - DM Act 2005 Sections 30 & 34 citations in audit trail
  - Aadhaar ID logged in audit entries
  - Sewage → Fishermen dispatch default

DB writes and resource allocation happen in Python wrappers, not LLM tool-calls.
"""

import os
import json
import sqlite3
import datetime
import math
import asyncio
import threading
import time
from typing import Any, Dict, List

from crewai import Agent, Task, Crew, Process
from crewai import LLM

from database import get_connection
from haversine import nearest_resource, rank_resources
from ingest_kb import query_kb
from priority_engine import engine as priority_engine, DM_ACT_CITATIONS

# ── Configurable Admission Delay ──────────────────────────────────────────────
ADMISSION_DELAY_SECONDS = int(os.getenv("ADMISSION_DELAY_SECONDS", "600"))


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


def _write_audit(incident_id: int, agent: str, decision: str, reasoning: str,
                 citation: str = "", aadhar_id: str = None, fleet_check: str = None,
                 consensus_score: float = None):
    conn = get_connection()
    conn.execute(
        """INSERT INTO audit_logs (incident_id, aadhar_id, agent, decision, reasoning,
                                   citation, fleet_check, consensus_score)
           VALUES (?,?,?,?,?,?,?,?)""",
        (incident_id, aadhar_id, agent, decision, reasoning, citation, fleet_check, consensus_score)
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
    def dist(u):
        dlat = math.radians(u["base_lat"] - incident_lat)
        dlon = math.radians(u["base_lon"] - incident_lon)
        a = math.sin(dlat/2)**2 + math.cos(math.radians(incident_lat)) * math.cos(math.radians(u["base_lat"])) * math.sin(dlon/2)**2
        return 6371 * 2 * math.asin(math.sqrt(a))
    units.sort(key=dist)
    best = units[0]
    best["distance_km"] = dist(best)
    return best


def _get_deployed_unit(unit_type: str, incident_lat: float, incident_lon: float) -> dict | None:
    """Return the nearest DEPLOYED unit for override reassignment."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM rescue_units WHERE unit_type=? AND status='Deployed'", (unit_type,)
    ).fetchall()
    conn.close()
    units = [dict(r) for r in rows]
    if not units:
        return None
    def dist(u):
        dlat = math.radians(u["base_lat"] - incident_lat)
        dlon = math.radians(u["base_lon"] - incident_lon)
        a = math.sin(dlat/2)**2 + math.cos(math.radians(incident_lat)) * math.cos(math.radians(u["base_lat"])) * math.sin(dlon/2)**2
        return 6371 * 2 * math.asin(math.sqrt(a))
    units.sort(key=dist)
    best = units[0]
    best["distance_km"] = dist(best)
    return best


def _get_fleet_status() -> dict:
    """Get availability counts for each fleet type (for fleet-specific gate check)."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT unit_type,
               COUNT(*) as total,
               SUM(CASE WHEN status='Available' THEN 1 ELSE 0 END) as available
        FROM rescue_units GROUP BY unit_type
    """).fetchall()
    conn.close()
    return {dict(r)["unit_type"]: {"total": dict(r)["total"], "available": dict(r)["available"]} for r in rows}


def _get_active_mission_contexts() -> list:
    """
    Return score/progress context dicts for all currently dispatched missions.
    Used by evaluate_multi_override to compute aggregate residual cost.
    """
    conn = get_connection()
    rows = conn.execute("""
        SELECT i.*,
               a.eta_minutes,
               a.distance_km,
               (CAST((julianday('now') - julianday(a.dispatched_at)) * 24 * 60 AS REAL)) AS elapsed_min
        FROM incidents i
        JOIN rescue_unit_assignments a ON a.incident_id = i.id
        WHERE i.status = 'Dispatched' AND a.status = 'Dispatched'
    """).fetchall()
    conn.close()

    missions = []
    for r in [dict(row) for row in rows]:
        elapsed  = r.get("elapsed_min") or 0.0
        eta      = r.get("eta_minutes") or 1.0
        progress = min(1.0, elapsed / max(eta, 1.0))
        score, raw_score = priority_engine.score_incident(r)
        missions.append({
            "score":      score,
            "raw_score":  raw_score,
            "progress":   progress,
            "distance_m": (r.get("distance_km") or 5.0) * 1000,
        })
    return missions


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


def _place_victims_in_transit(incident_id: int):
    """Mark all victims of an incident as In_Transit (before admission simulation)."""
    conn = get_connection()
    conn.execute(
        "UPDATE victims SET status='In_Transit' WHERE incident_id=? AND status='Reported'",
        (incident_id,)
    )
    conn.commit()
    conn.close()


def _complete_admission(incident_id: int, resource_id: int, push_sse):
    """
    Simulate hospital/shelter check-in with configurable delay.
    Resource capacity is ONLY decremented AFTER the delay completes.
    """
    _log_dispatch_event(incident_id, "ADMISSION_START",
                        f"Admission simulation started ({ADMISSION_DELAY_SECONDS}s delay). Victims In-Transit.")
    push_sse(f"[Admission] 🏥 Check-in simulation started — {ADMISSION_DELAY_SECONDS}s delay...")

    # The 10-minute mock sleep (configurable)
    time.sleep(ADMISSION_DELAY_SECONDS)

    conn = get_connection()
    if resource_id:
        # Medical victims → Admitted at Hospital
        conn.execute(
            """UPDATE victims SET status='Admitted', assigned_resource_id=?, placed_at=CURRENT_TIMESTAMP
               WHERE incident_id=? AND needs_medical=1 AND status='In_Transit'""",
            (resource_id, incident_id)
        )
        # Non-medical victims → Sheltered
        conn.execute(
            """UPDATE victims SET status='Sheltered', assigned_resource_id=?, placed_at=CURRENT_TIMESTAMP
               WHERE incident_id=? AND needs_medical=0 AND status='In_Transit'""",
            (resource_id, incident_id)
        )
        # NOW decrement resource capacity (only after admission complete)
        victim_count = conn.execute(
            "SELECT COUNT(*) FROM victims WHERE incident_id=? AND assigned_resource_id=?",
            (incident_id, resource_id)
        ).fetchone()[0]
        conn.execute(
            "UPDATE resources SET cap_avail = MAX(0, cap_avail - ?) WHERE id=?",
            (victim_count, resource_id)
        )
        # Check if resource is now full
        resource = conn.execute("SELECT cap_avail FROM resources WHERE id=?", (resource_id,)).fetchone()
        if resource and dict(resource)["cap_avail"] <= 0:
            conn.execute("UPDATE resources SET status='Full' WHERE id=?", (resource_id,))
    conn.commit()
    conn.close()

    _log_dispatch_event(incident_id, "ADMISSION_COMPLETE",
                        f"Admission complete. Resource #{resource_id} capacity decremented.")
    push_sse(f"[Admission Complete] ✅ Victims admitted — resource capacity updated.")


def _schedule_rescue_complete(assignment_id: int, unit_id: int, incident_id: int,
                               eta_min: float, resource_id: int, push_sse):
    """
    v2.0: Auto-simulate rescue complete after ETA, then run 10-minute admission.
    Fleet unit returns to Available INSTANTLY after victim pickup.
    Resource capacity decrements ONLY after admission delay.
    """
    def _complete():
        time.sleep(2)  # fast simulation wait for rescue to complete

        # ── Step 1: Rescue complete — pick up victims ─────────────────────
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

        # Set victims to In-Transit
        _place_victims_in_transit(incident_id)

        _log_dispatch_event(incident_id, "RESCUE_COMPLETE",
                            f"Rescue unit #{unit_id} confirmed victim pickup.", unit_id)
        push_sse(f"[Rescue Complete] Unit #{unit_id} confirmed pickup — victims now In-Transit.")

        # ── Step 2: Fleet unit returns IMMEDIATELY (no admission wait) ────
        time.sleep(1)
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
        conn.commit()
        conn.close()
        _log_dispatch_event(incident_id, "UNIT_RETURNED",
                            f"Unit #{unit_id} returned to base — Available for next mission.", unit_id)
        push_sse(f"[Unit Returned] Unit #{unit_id} back at base — Available for next mission.")

        # ── Step 3: Start admission simulation (10-minute delay) ──────────
        _complete_admission(incident_id, resource_id, push_sse)

        # Mark incident as resolved after admission
        conn = get_connection()
        conn.execute(
            "UPDATE incidents SET status='Resolved' WHERE id=?", (incident_id,)
        )
        conn.commit()
        conn.close()

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


def _find_external_resource(lat: float, lon: float, resource_type: str, push_sse) -> dict | None:
    """
    External Shelter Fallback: When all local resources are full,
    search for the nearest available facility without strict type filter.
    """
    resources = _fetch_resources()

    # Try same type first (even if status is 'Full', look for any with remaining cap)
    for r in resources:
        if r.get("type") == resource_type and r.get("cap_avail", 0) > 0:
            return r

    # Fallback: any resource with capacity
    available = [r for r in resources if r.get("cap_avail", 0) > 0]
    if available:
        # Sort by distance
        def dist(r):
            dlat = math.radians(r["lat"] - lat)
            dlon = math.radians(r["lon"] - lon)
            a = math.sin(dlat/2)**2 + math.cos(math.radians(lat)) * math.cos(math.radians(r["lat"])) * math.sin(dlon/2)**2
            return 6371 * 2 * math.asin(math.sqrt(a))
        available.sort(key=dist)
        fallback = available[0]
        push_sse(f"[Shelter Fallback] ⚠️ Local {resource_type} capacity exhausted. Routing to {fallback['name']} ({fallback['type']}).")
        return fallback

    push_sse(f"[CRITICAL] ❌ ALL resources at zero capacity. Manual intervention required.")
    return None


# ── Flood Level → Unit Type Routing ──────────────────────────────────────────

FLOOD_UNIT_MAP = {
    0: None,               # no flood
    1: "Fire_Rescue",      # Level 1: Ankle — Fire & Rescue Dinghy
    2: "Fishermen",        # Level 2: Waist — Fishermen boats
    3: "NDRF",             # Level 3: Overhead — NDRF OBM
    4: "IAF_Navy",         # Total Isolation — Helicopter Airlift (internal)
    5: "IAF_Navy",         # Bridge/Road Collapse — Helicopter + Army (internal)
}

EMERGENCY_UNIT_MAP = {
    "Fire":       "Fire_Rescue",
    "Electrical": None,          # KSEB notification, no rescue unit needed
    "Sewage":     "Fishermen",   # v2.0: Default to fishermen for sewage/water rescue
    "Road":       "Army",
    "Tree":       "Fire_Rescue",
    "Flood":      "Fishermen",   # Default flood → fishermen
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
            "Audit the dispatch decision against DM Act 2005 (Sections 30, 34, 38). "
            "Think step-by-step. Output APPROVED or REJECTED with legal citation. "
            "Also provide a consensus priority score (0-150) based on your assessment."
        ),
        backstory=(
            "You are the incorruptible legal guardian of Sentinel-AI. "
            "You know the Disaster Management Act 2005 and Kerala Orange Book by heart. "
            "You check priority scores, VIP flags, and fraud alerts before approving any dispatch. "
            "You always cite DM Act 2005 Section 30 (State Authority override powers) and "
            "Section 34 (District Authority duties) in your reasoning."
        ),
        llm=_llm_strategy(),
        tools=[], max_iter=3, step_callback=step_callback, verbose=True,
    )

    # ── Agent 3: Local Liaison (llama3.1:8b) ─────────────────────────────
    local_liaison = Agent(
        role="Local Liaison Officer",
        goal=(
            "Identify which TVM agencies must be notified. "
            "Route LGBTQIA+ victims to safe-space shelters (no priority change). "
            "Output a JSON list with agency names and their WhatsApp numbers."
        ),
        backstory=(
            "You know every government department in Thiruvananthapuram — "
            "Fire & Rescue, KSEB, KWA, PWD, Police, DHS, Forest. "
            "You handle LGBTQIA+ shelter routing: their status earns ZERO priority points, "
            "but you ensure they are directed to inclusive/safe-space shelters. "
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
2. Cite the specific section (Section 30 for state override, Section 34 for district duties).
3. Confirm no VIP override is influencing this decision.
4. Note if ULTRA_PRIORITY is triggered (total_victims={total_victims}, priority={priority}).
5. Provide your consensus priority score (0-150) as a single integer on the last line, prefixed with CONSENSUS_SCORE:

INCIDENT ID: {iid}
""",
        expected_output="APPROVED or REJECTED, legal citation (DM Act 2005 Sec 30/34), VIP status, consensus score.",
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
- Sewage → KWA + Police + Fishermen dispatch
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
# CONSENSUS SCORE EXTRACTION
# ══════════════════════════════════════════════════════════════════════════════

def _extract_consensus_score(crew_output: str) -> float:
    """
    Parse the crew output for a CONSENSUS_SCORE line from the Strategy Lead.
    Returns the score or a fallback based on APPROVED/REJECTED status.
    """
    try:
        for line in str(crew_output).split("\n"):
            if "CONSENSUS_SCORE:" in line.upper():
                score_str = line.split(":")[-1].strip()
                return min(150.0, max(0.0, float(score_str)))
    except (ValueError, IndexError):
        pass
    # Fallback: if APPROVED is in output, give a moderate consensus score
    output_text = str(crew_output).upper()
    if "APPROVED" in output_text:
        return 100.0
    return 50.0


# ══════════════════════════════════════════════════════════════════════════════
# RUN CREW + DISPATCH
# ══════════════════════════════════════════════════════════════════════════════

def run_crew_and_dispatch(incident: Dict[str, Any], push_sse) -> str:
    """
    1. Run the CrewAI crew (4 agents reasoning in sequence)
    2. Extract consensus score from Strategy Lead
    3. Compute final score with 20% consensus weight
    4. Fleet-specific override gate
    5. Write audit log with Aadhaar + fleet check + DM Act citation
    6. Assign nearest available rescue unit
    7. Schedule rescue + admission simulation
    """
    iid            = incident["id"]
    flood_level    = int(incident.get("flood_level", 0))
    emergency_type = incident.get("emergency_type", "Other")
    aadhar_id      = incident.get("aadhar_id")

    crew   = build_crew(incident, step_callback=None)
    result = crew.kickoff()

    # ── Priority Score with Multi-Agent Consensus ──────────────────────────
    base_score, raw_score = priority_engine.score_incident(incident)
    consensus_score = _extract_consensus_score(str(result))
    final_score = priority_engine.score_with_consensus(base_score, consensus_score)

    push_sse(f"[Priority Engine] Base={base_score} (raw={raw_score}), Consensus={consensus_score}")
    push_sse(f"[Priority Engine] Final Score={final_score} (80% base + 20% consensus)")
    push_sse(f"[Priority Engine] Priority={incident.get('priority','Standard')}")

    # ── Fleet-Specific Gate Check ──────────────────────────────────────────
    if emergency_type == "Flood":
        unit_type = FLOOD_UNIT_MAP.get(flood_level)
    else:
        unit_type = EMERGENCY_UNIT_MAP.get(emergency_type, "Fire_Rescue")

    fleet_status = _get_fleet_status()
    fleet_check_msg = None
    if unit_type:
        gate_result = priority_engine.check_fleet_gate(unit_type, fleet_status)
        fleet_check_msg = gate_result["reason"]
        push_sse(f"[Fleet Gate] {gate_result['reason']}")

    # ── Override Check against Active Missions ─────────────────────────────
    override_result = {"override_approved": True}  # default: always dispatch
    if unit_type and fleet_status.get(unit_type, {}).get("available", 1) == 0:
        # Only check override if specific fleet is 100% occupied
        active_missions = _get_active_mission_contexts()
        if active_missions:
            inc_input = {
                "hazard":     emergency_type,
                "medical":    [incident.get("severity", "low")] * max(1, incident.get("medical_cnt", 1)),
                "vulnerable": "disability" if incident.get("is_disability") else "standard",
                "env": "camp" if flood_level > 0 else "home",
            }
            override_result = priority_engine.evaluate_multi_override(inc_input, active_missions)
            fleet_check_msg = (fleet_check_msg or "") + f" | Override: S_new={override_result['s_new']} vs Σ_cost={override_result['total_residual_cost']}"
            push_sse(
                f"[Priority Engine] Override check: S_new={override_result['s_new']} vs "
                f"Σ_cost={override_result['total_residual_cost']} → "
                f"{'OVERRIDE APPROVED ✓' if override_result['override_approved'] else 'HOLD — insufficient priority ✗'}"
            )

    # ── Audit Log with Aadhaar + Fleet Check + DM Act Citation ─────────────
    citation = DM_ACT_CITATIONS["triage_approval"]
    _write_audit(
        iid, "Strategy Lead", "APPROVED",
        f"Severity-based triage approved. Final Score: {final_score} (Base: {base_score}, Consensus: {consensus_score}). "
        f"DM Act 2005 compliant. Priority: {incident.get('priority', 'Standard')}.",
        citation=citation,
        aadhar_id=aadhar_id,
        fleet_check=fleet_check_msg,
        consensus_score=consensus_score,
    )
    _log_dispatch_event(iid, "TRIAGE_COMPLETE",
                        f"Triage complete. Severity={incident.get('severity')}. Final Score={final_score}.")
    push_sse(f"[Audit] Decision logged to transparency ledger. Legal basis: {citation}")

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
    resource_id = None
    if unit_type:
        unit = _get_available_unit(unit_type, incident["lat"], incident["lon"])

        # No available unit — attempt override reassignment if approved
        if not unit:
            if override_result.get("override_approved"):
                unit = _get_deployed_unit(unit_type, incident["lat"], incident["lon"])
                if unit:
                    push_sse(
                        f"[Override] Priority override approved — reassigning "
                        f"{unit['name']} from active mission #{unit.get('current_incident_id', '?')}."
                    )
                    _log_dispatch_event(
                        iid, "OVERRIDE",
                        f"Unit {unit['name']} reassigned via priority override (Score={final_score}). "
                        f"{fleet_check_msg}. Legal: {DM_ACT_CITATIONS['override']}",
                        unit["id"]
                    )
                    _write_audit(
                        iid, "Strategy Lead", "OVERRIDE",
                        f"Fleet override executed: {unit['name']} reassigned. {fleet_check_msg}",
                        citation=DM_ACT_CITATIONS["override"],
                        aadhar_id=aadhar_id,
                        fleet_check=fleet_check_msg,
                    )
                else:
                    push_sse(f"[WARNING] Override approved but no {unit_type} unit found. Requesting mutual aid.")
            else:
                push_sse(
                    f"[WARNING] No {unit_type} unit available and override NOT approved "
                    f"(S_new={final_score} ≤ Σ_cost={override_result.get('total_residual_cost', '?')}). Queuing incident."
                )

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

            # External shelter fallback
            if not nearest:
                nearest = _find_external_resource(
                    incident["lat"], incident["lon"],
                    "Hospital" if needs_medical else "Shelter",
                    push_sse,
                )
                if nearest:
                    _log_dispatch_event(iid, "SHELTER_FALLBACK",
                                        f"Local capacity exhausted. Fallback to {nearest['name']}.")

            if nearest:
                resource_id = nearest["id"]
                push_sse(f"[Placement] Victims → {nearest['name']} ({nearest.get('distance_km', '?')} km)")

            # Schedule rescue + admission simulation
            _schedule_rescue_complete(assignment_id, unit["id"], iid, eta, resource_id, push_sse)
    else:
        push_sse(f"[Liaison] {emergency_type} incident — agency notified, no rescue unit required.")
        resources = _fetch_resources()
        nearest   = nearest_resource(incident["lat"], incident["lon"], resources,
                                      resource_type="Hospital" if incident.get("medical_cnt", 0) > 0 else "Shelter")
        if not nearest:
            nearest = _find_external_resource(
                incident["lat"], incident["lon"],
                "Hospital" if incident.get("medical_cnt", 0) > 0 else "Shelter",
                push_sse,
            )
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
           VALUES (?, 'Strategy Lead', 'VIP_BLOCKED', ?, ?)""",
        (incident_id,
         f"VIP override attempt by '{vip_name}' BLOCKED. "
         f"DM Act 2005 mandates severity-based triage. No political status may alter allocation.",
         DM_ACT_CITATIONS["triage_approval"])
    )
    conn.commit()
    conn.close()
    return {
        "status": "VIP_BLOCKED",
        "message": f"Override attempt by '{vip_name}' rejected and logged.",
        "legal_basis": DM_ACT_CITATIONS["triage_approval"],
    }


if __name__ == "__main__":
    result = simulate_vip_bribe(1, "Minister XYZ")
    print(json.dumps(result, indent=2))