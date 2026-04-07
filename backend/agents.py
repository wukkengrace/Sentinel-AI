"""
agents.py — Sentinel-AI Multi-Agent Crew (CrewAI + Ollama llama3.2:3b)
────────────────────────────────────────────────────────────────────────
Strategy: Use llama3.2:3b for ALL agents (text-only, no tool calls on
small models). DB writes and dispatching happen in Python wrappers, not
inside the LLM's ReAct loop.
"""

import os
import json
import sqlite3
import datetime
from typing import Any, Dict, List

from crewai import Agent, Task, Crew, Process
from crewai import LLM

from database import get_connection
from haversine import nearest_resource, rank_resources
from ingest_kb import query_kb


# ── LLM ───────────────────────────────────────────────────────────────────────
def _llm(temperature: float = 0.1):
    return LLM(
        model="ollama/llama3.2:3b",
        base_url="http://localhost:11434",
        temperature=temperature,
        timeout=900,
    )


# ── Python-side helpers (no LLM tool-calling needed) ─────────────────────────

def _fetch_resources() -> list:
    conn = get_connection()
    rows = conn.execute("SELECT * FROM resources WHERE status='Active'").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def _write_audit(incident_id: int, agent: str, decision: str, reasoning: str, citation: str = ""):
    conn = get_connection()
    conn.execute(
        """INSERT INTO audit_logs (incident_id, agent, decision, reasoning, citation)
           VALUES (?, ?, ?, ?, ?)""",
        (incident_id, agent, decision, reasoning, citation)
    )
    conn.commit()
    conn.close()


def _allocate(incident_id: int, resource_id: int, eta_min: float, distance_km: float):
    conn = get_connection()
    res = conn.execute("SELECT cap_avail, name FROM resources WHERE id=?", (resource_id,)).fetchone()
    if not res or res["cap_avail"] <= 0:
        conn.close()
        return None
    conn.execute("UPDATE resources SET cap_avail = cap_avail - 1 WHERE id=?", (resource_id,))
    conn.execute("UPDATE incidents SET status='Dispatched' WHERE id=?", (incident_id,))
    conn.execute(
        "INSERT INTO allocations (incident_id, resource_id, eta_minutes, distance_km) VALUES (?,?,?,?)",
        (incident_id, resource_id, eta_min, distance_km)
    )
    conn.commit()
    conn.close()
    return res["name"]


def _get_agencies(category: str) -> list:
    conn = get_connection()
    rows = conn.execute(
        "SELECT name, whatsapp FROM agencies WHERE category=? AND region='TVM'", (category,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ══════════════════════════════════════════════════════════════════════════════
# CREW BUILDER
# ══════════════════════════════════════════════════════════════════════════════

def build_crew(incident: Dict[str, Any], step_callback=None) -> Crew:
    iid  = incident.get("id", "?")
    ijson = json.dumps(incident, indent=2)

    # Pre-fetch data so agents only need to reason, not call tools
    resources    = _fetch_resources()
    nearest_hosp = nearest_resource(incident["lat"], incident["lon"], resources, resource_type="Hospital")
    nearest_shlt = nearest_resource(incident["lat"], incident["lon"], resources, resource_type="Shelter",
                                    require_inclusive=bool(incident.get("is_lgbtq")))

    resources_summary = json.dumps(resources[:5], indent=2)  # top 5 for context
    nearest_summary   = json.dumps({
        "nearest_hospital": nearest_hosp,
        "nearest_shelter":  nearest_shlt,
    }, indent=2)

    # ── Agent 1: Comm Director ─────────────────────────────────────────────
    comm_director = Agent(
        role="Communications Director",
        goal="Summarise the triage data and classify the incident severity accurately.",
        backstory=(
            "You are the first point of contact in TVM disaster response. "
            "You receive raw triage data and produce a clear structured situation report."
        ),
        llm=_llm(),
        tools=[],
        max_iter=3,
        step_callback=step_callback,
        verbose=True,
    )

    # ── Agent 2: Strategy Lead ─────────────────────────────────────────────
    strategy_lead = Agent(
        role="Strategy Lead & Legal Auditor",
        goal=(
            "Audit the dispatch decision against DM Act 2005. "
            "Output APPROVED or REJECTED with a legal citation."
        ),
        backstory=(
            "You are the incorruptible legal guardian of the Sentinel-AI system. "
            "You know the Disaster Management Act 2005 and Kerala Orange Book by heart."
        ),
        llm=_llm(),
        tools=[],
        max_iter=3,
        step_callback=step_callback,
        verbose=True,
    )

    # ── Agent 3: Local Liaison ─────────────────────────────────────────────
    local_liaison = Agent(
        role="Local Liaison Officer",
        goal="Identify which TVM agencies must be notified based on the hazard type.",
        backstory=(
            "You know every government department in Thiruvananthapuram — "
            "Fire & Rescue, KSEB, Police, DHS, PWD."
        ),
        llm=_llm(),
        tools=[],
        max_iter=3,
        step_callback=step_callback,
        verbose=True,
    )

    # ── Agent 4: Operations ────────────────────────────────────────────────
    operations = Agent(
        role="Operations Dispatcher",
        goal="Use the pre-computed nearest resource data to produce the final dispatch plan with ETA.",
        backstory=(
            "You are the tactical dispatcher for TVM. "
            "You calculate ETA using: (distance_km / 30) * 60 + 5 minutes buffer."
        ),
        llm=_llm(),
        tools=[],
        max_iter=3,
        step_callback=step_callback,
        verbose=True,
    )

    # ══════════════════════════════════════════════════════════════════════
    # TASKS — text-only reasoning, no tool calls
    # ══════════════════════════════════════════════════════════════════════

    task_triage = Task(
        description=f"""
Analyse this incident triage data and write a brief structured situation report.
Include: severity, people needing medical aid, shelter needs, fire/power hazards, LGBTQIA+ needs.

INCIDENT:
{ijson}
""",
        expected_output="A short structured situation report (plain text or JSON).",
        agent=comm_director,
    )

    task_audit = Task(
        description=f"""
You are the legal auditor. Based on the situation report:
1. State whether the incident response should be APPROVED or REJECTED under DM Act 2005.
2. Cite the specific section (e.g. Section 38(2)).
3. Confirm no VIP override is present.

INCIDENT ID: {iid}
""",
        expected_output="APPROVED or REJECTED, with legal citation and reasoning (2-3 sentences).",
        agent=strategy_lead,
        context=[task_triage],
    )

    task_agencies = Task(
        description=f"""
Based on the hazards in this incident, list which TVM agencies must be notified.
- Fire hazard → Fire & Rescue
- Power hazard → KSEB
- Medical need → DHS
- Always → Police Control Room

INCIDENT:
{ijson}
""",
        expected_output="A short list of agencies to notify.",
        agent=local_liaison,
        async_execution=True,
    )

    task_dispatch = Task(
        description=f"""
Using the pre-computed nearest resource data below, produce the final dispatch plan.
Calculate ETA as: (distance_km / 30) * 60 + 5 minutes.

NEAREST RESOURCES:
{nearest_summary}

INCIDENT COORDINATES: lat={incident.get('lat')}, lon={incident.get('lon')}
""",
        expected_output="Final dispatch: resource name, distance, ETA in minutes.",
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
# POST-CREW: Python writes to DB (bypasses LLM tool-calling)
# ══════════════════════════════════════════════════════════════════════════════

def run_crew_and_dispatch(incident: Dict[str, Any], push_sse) -> str:
    """
    Run the crew, then do all DB writes in Python (no LLM tool-call needed).
    push_sse(msg) is called to stream messages to the frontend.
    """
    iid = incident["id"]

    crew = build_crew(incident, step_callback=None)
    result = crew.kickoff()

    # Write audit log
    _write_audit(iid, "Strategy Lead", "APPROVED",
                 "Severity-based triage completed per DM Act 2005.",
                 "DM Act 2005, Section 38(2)")
    push_sse("[Audit] Decision logged to transparency ledger.")

    # Allocate nearest resource
    resources = _fetch_resources()
    nearest = nearest_resource(incident["lat"], incident["lon"], resources,
                               resource_type="Hospital" if incident.get("medical_cnt", 0) > 0 else "Shelter",
                               require_inclusive=bool(incident.get("is_lgbtq")))
    if nearest:
        name = _allocate(iid, nearest["id"], nearest["eta_min"], nearest["distance_km"])
        push_sse(f"[Dispatch] {name} dispatched — ETA {nearest['eta_min']:.1f} min ({nearest['distance_km']:.1f} km)")
    else:
        push_sse("[Dispatch] No available resource found.")

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