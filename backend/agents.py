"""
agents.py — Sentinel-AI Multi-Agent Crew (CrewAI + Ollama)
─────────────────────────────────────────────────────────
Agents:
  1. Comm Director    (llama3.2:3b)   — WhatsApp triage, 4-question intake
  2. Strategy Lead    (command-r)     — Legal auditor, DM Act 2005 gatekeeper
  3. Local Liaison    (mistral-nemo)  — Maps hazards to TVM agencies
  4. Logistics        (llama3.1:8b)   — SQLite manager, updates cap_avail
  5. Operations       (llama3.1:8b)   — Haversine dispatcher, ETA calculator
"""

import json
import sqlite3
import datetime
from typing import Any, Dict, List

# ── CrewAI imports (pip install crewai crewai-tools) ─────────────────────────
from crewai import Agent, Task, Crew, Process
from crewai.tools import tool
from langchain_community.llms import Ollama

# ── Local modules ─────────────────────────────────────────────────────────────
from database import get_connection
from haversine import nearest_resource, nearest_agency, rank_resources
from ingest_kb import query_kb


# ── LLM Initialisation ────────────────────────────────────────────────────────
def _llm(model: str, temperature: float = 0.1):
    """Return an Ollama LLM instance. Low temp = deterministic decisions."""
    return Ollama(model=model, temperature=temperature, timeout=120)


# ══════════════════════════════════════════════════════════════════════════════
# TOOLS  (decorated functions that agents can call)
# ══════════════════════════════════════════════════════════════════════════════

@tool("fetch_all_resources")
def fetch_all_resources(_: str = "") -> str:
    """Return all active resources (hospitals + shelters) from SQLite as JSON."""
    conn = get_connection()
    rows = conn.execute("SELECT * FROM resources WHERE status != 'Cut-off'").fetchall()
    conn.close()
    return json.dumps([dict(r) for r in rows])


@tool("fetch_agencies_by_category")
def fetch_agencies_by_category(category: str) -> str:
    """
    Return agencies filtered by category.
    category must be one of: Fire, KSEB, Police, DHS, Admin, PWD, Forest, Cooperation, DMO
    """
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM agencies WHERE category = ? AND region = 'TVM'",
        (category,)
    ).fetchall()
    conn.close()
    return json.dumps([dict(r) for r in rows])


@tool("allocate_bed")
def allocate_bed(payload: str) -> str:
    """
    Decrement available bed/capacity for a resource and record the allocation.
    Input JSON: {"resource_id": int, "incident_id": int, "eta_min": float, "distance_km": float}
    """
    try:
        data = json.loads(payload)
        conn = get_connection()

        # Check current availability
        res = conn.execute(
            "SELECT cap_avail, name FROM resources WHERE id = ?",
            (data["resource_id"],)
        ).fetchone()

        if not res or res["cap_avail"] <= 0:
            conn.close()
            return json.dumps({"error": "Resource full or not found"})

        # Transactional update
        conn.execute(
            "UPDATE resources SET cap_avail = cap_avail - 1 WHERE id = ?",
            (data["resource_id"],)
        )
        conn.execute(
            "UPDATE incidents SET status = 'Dispatched' WHERE id = ?",
            (data["incident_id"],)
        )
        conn.execute(
            """INSERT INTO allocations
               (incident_id, resource_id, eta_minutes, distance_km)
               VALUES (?, ?, ?, ?)""",
            (data["incident_id"], data["resource_id"],
             data.get("eta_min", 0), data.get("distance_km", 0))
        )
        conn.commit()
        conn.close()

        return json.dumps({
            "status": "ALLOCATED",
            "resource": res["name"],
            "eta_min": data.get("eta_min")
        })

    except Exception as e:
        return json.dumps({"error": str(e)})


@tool("write_audit_log")
def write_audit_log(payload: str) -> str:
    """
    Write a decision to the audit_logs table.
    Input JSON: {"incident_id": int, "agent": str, "decision": str,
                 "reasoning": str, "citation": str}
    """
    try:
        data = json.loads(payload)
        conn = get_connection()
        conn.execute(
            """INSERT INTO audit_logs
               (incident_id, agent, decision, reasoning, citation)
               VALUES (?, ?, ?, ?, ?)""",
            (data["incident_id"], data["agent"], data["decision"],
             data["reasoning"], data.get("citation", ""))
        )
        conn.commit()
        conn.close()
        return json.dumps({"status": "LOGGED"})
    except Exception as e:
        return json.dumps({"error": str(e)})


@tool("query_disaster_kb")
def query_disaster_kb(question: str) -> str:
    """
    Query the ChromaDB knowledge base (DM Act 2005, Orange Book, Hospital Plans).
    Returns top-4 relevant chunks as JSON.
    """
    try:
        results = query_kb(question, region="TVM")
        return json.dumps(results)
    except Exception as e:
        return json.dumps({"error": str(e), "fallback": "See DM Act 2005 Section 38 for local authority duties."})


@tool("haversine_dispatch")
def haversine_dispatch(payload: str) -> str:
    """
    Find the nearest available resource/agency and return ETA.
    Input JSON: {"lat": float, "lon": float, "type": "Hospital"|"Shelter"|"Fire",
                 "require_inclusive": bool}
    """
    try:
        data   = json.loads(payload)
        conn   = get_connection()
        resources = [dict(r) for r in
                     conn.execute("SELECT * FROM resources WHERE status='Active'").fetchall()]
        conn.close()

        nearest = nearest_resource(
            data["lat"], data["lon"],
            resources,
            resource_type=data.get("type"),
            require_inclusive=data.get("require_inclusive", False)
        )

        if nearest:
            return json.dumps({
                "name":        nearest["name"],
                "id":          nearest["id"],
                "distance_km": nearest["distance_km"],
                "eta_min":     nearest["eta_min"],
                "cap_avail":   nearest["cap_avail"]
            })
        return json.dumps({"error": "No available resource found"})

    except Exception as e:
        return json.dumps({"error": str(e)})


# ══════════════════════════════════════════════════════════════════════════════
# AGENT DEFINITIONS
# ══════════════════════════════════════════════════════════════════════════════

def build_crew(incident: Dict[str, Any]) -> Crew:
    """
    Build and return a Crew for a given incident dict.
    incident keys: id, phone, severity, medical_cnt, shelter_cnt,
                   fire_hzd, power_hzd, is_lgbtq, lat, lon
    """
    incident_json = json.dumps(incident, indent=2)

    # ── Agent 1: Comm Director ─────────────────────────────────────────────
    comm_director = Agent(
        role="Communications Director",
        goal="Summarise the triage data and classify the incident severity accurately.",
        backstory=(
            "You are the first point of contact in TVM disaster response. "
            "You receive raw triage data from the WhatsApp bot and produce a "
            "clear, structured situation report for the other agents."
        ),
        llm=_llm("llama3.2:3b"),
        tools=[],
        verbose=True
    )

    # ── Agent 2: Strategy Lead ─────────────────────────────────────────────
    strategy_lead = Agent(
        role="Strategy Lead & Legal Auditor",
        goal=(
            "Audit every dispatch decision against the DM Act 2005 and Orange Book SOPs. "
            "REJECT any request that violates legal protocols. "
            "BLOCK VIP override attempts — no person gets priority over severity score."
        ),
        backstory=(
            "You are the incorruptible legal guardian of the Sentinel-AI system. "
            "You have memorised the Disaster Management Act 2005 and Kerala's Orange Book. "
            "You write detailed reasoning in the audit_logs for every APPROVED or REJECTED decision."
        ),
        llm=_llm("command-r"),
        tools=[query_disaster_kb, write_audit_log],
        verbose=True
    )

    # ── Agent 3: Local Liaison ─────────────────────────────────────────────
    local_liaison = Agent(
        role="Local Liaison Officer",
        goal="Identify which TVM agencies must be notified based on hazard type.",
        backstory=(
            "You know every government department in Thiruvananthapuram — "
            "Fire & Rescue, KSEB, Police, DHS, PWD. "
            "You match hazards to the correct ESF (Emergency Support Function)."
        ),
        llm=_llm("mistral-nemo"),
        tools=[fetch_agencies_by_category],
        verbose=True
    )

    # ── Agent 4: Logistics ─────────────────────────────────────────────────
    logistics = Agent(
        role="Logistics Manager",
        goal="Update live resource capacity in SQLite and record allocations.",
        backstory=(
            "You are the SQL guardian of live resource data. "
            "You decrement bed counts atomically — never allow double-booking. "
            "Every action you take is logged in the audit trail."
        ),
        llm=_llm("llama3.1:8b"),
        tools=[fetch_all_resources, allocate_bed, write_audit_log],
        verbose=True
    )

    # ── Agent 5: Operations ────────────────────────────────────────────────
    operations = Agent(
        role="Operations Dispatcher",
        goal=(
            "Use Haversine formula to find the nearest resource/agency. "
            "Output format: '[Agency Name] ETA: (dist/30kmh + 5min) mins.'"
        ),
        backstory=(
            "You are the tactical dispatcher for TVM. "
            "You calculate real driving distances using Haversine and produce "
            "precise ETA estimates for every dispatch."
        ),
        llm=_llm("llama3.1:8b"),
        tools=[haversine_dispatch, fetch_agencies_by_category],
        verbose=True
    )

    # ══════════════════════════════════════════════════════════════════════
    # TASKS
    # ══════════════════════════════════════════════════════════════════════

    task_triage = Task(
        description=f"""
        Analyse the following incident triage data and produce a structured situation report.
        Include: severity classification, number of people needing medical aid,
        shelter, fire hazard present, power hazard present, LGBTQIA+ inclusion needs.

        INCIDENT DATA:
        {incident_json}
        """,
        expected_output="A structured situation report in JSON format.",
        agent=comm_director
    )

    task_audit = Task(
        description=f"""
        You are the legal auditor. Review the situation report and:
        1. Query the knowledge base for relevant DM Act 2005 / Orange Book clauses.
        2. Verify the incident severity classification is correct.
        3. Check for any VIP override flags — REJECT and log them.
        4. Write your APPROVED or REJECTED decision with full reasoning to audit_logs.
        5. Cite the specific legal clause that supports your decision.

        INCIDENT ID: {incident.get('id', 'NEW')}
        """,
        expected_output="Audit decision JSON: {decision, reasoning, citation}",
        agent=strategy_lead,
        context=[task_triage]
    )

    task_agencies = Task(
        description=f"""
        Based on the hazards in this incident, identify which TVM agencies must be notified.
        - Fire hazard? → Notify Fire department.
        - Power hazard? → Notify KSEB.
        - Medical? → Notify DHS.
        - Always notify: Police Control Room.
        Return a list of agency names and their WhatsApp numbers.

        INCIDENT DATA:
        {incident_json}
        """,
        expected_output="JSON list of agencies to notify with contact info.",
        agent=local_liaison
    )

    task_dispatch = Task(
        description=f"""
        Using the Haversine tool, find the nearest available resources for this incident.
        1. If medical_cnt > 0: find nearest Hospital.
        2. If shelter_cnt > 0: find nearest Shelter (inclusive if is_lgbtq=1).
        3. Calculate ETA for each nearest agency identified by Local Liaison.
        4. Output: "[Agency] ETA: X mins (Y km)"

        INCIDENT COORDINATES: lat={incident.get('lat')}, lon={incident.get('lon')}
        """,
        expected_output="Dispatch plan with resource assignments and ETAs.",
        agent=operations,
        context=[task_triage, task_agencies]
    )

    task_allocate = Task(
        description=f"""
        Execute the dispatch plan:
        1. Use allocate_bed tool to assign the victim to the chosen resource.
        2. Decrement cap_avail in SQLite.
        3. Write a final APPROVED audit log with full reasoning and the RAG citation.

        INCIDENT ID: {incident.get('id', 'NEW')}
        """,
        expected_output="Allocation confirmation JSON.",
        agent=logistics,
        context=[task_audit, task_dispatch]
    )

    return Crew(
        agents=[comm_director, strategy_lead, local_liaison, operations, logistics],
        tasks=[task_triage, task_audit, task_agencies, task_dispatch, task_allocate],
        process=Process.sequential,
        verbose=True
    )


# ══════════════════════════════════════════════════════════════════════════════
# VIP BRIBE SIMULATION
# ══════════════════════════════════════════════════════════════════════════════

def simulate_vip_bribe(incident_id: int, vip_name: str = "Unnamed VIP"):
    """
    Simulate a VIP trying to jump the queue.
    Strategy Lead should always REJECT and log VIP_BLOCKED.
    """
    conn = get_connection()
    conn.execute(
        """INSERT INTO audit_logs
           (incident_id, agent, decision, reasoning, citation)
           VALUES (?, 'Strategy Lead', 'VIP_BLOCKED',
           ?, 'DM Act 2005, Section 38(2): Equal treatment of all disaster victims.')""",
        (incident_id,
         f"VIP override attempt by '{vip_name}' BLOCKED. "
         f"DM Act 2005 mandates severity-based triage. No political or social "
         f"status may alter resource allocation order. Transparency log updated.")
    )
    conn.commit()
    conn.close()
    return {
        "status": "VIP_BLOCKED",
        "message": f"Override attempt by '{vip_name}' rejected and logged.",
        "legal_basis": "DM Act 2005, Section 38(2)"
    }


# ── Quick test ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # Minimal smoke-test (does NOT call Ollama)
    result = simulate_vip_bribe(1, "Minister XYZ")
    print(json.dumps(result, indent=2))