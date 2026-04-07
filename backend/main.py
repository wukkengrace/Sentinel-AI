"""
main.py — FastAPI backend for Sentinel-AI v2.0 Incorruptible Dispatcher (TVM)

Endpoints:
  GET  /api/resources            — Live resource capacity
  GET  /api/agencies             — All TVM agencies
  GET  /api/incidents            — All incidents
  GET  /api/audit                — Audit log (Transparency Ledger)
  GET  /api/allocations          — Dispatch records
  GET  /api/rescue-units         — Live rescue fleet status
  GET  /api/victims              — Victim placement tracking
  GET  /api/dispatch-events/{id} — Incident timeline
  POST /api/incident             — Submit new SOS triage
  POST /api/vip-bribe            — Simulate VIP bribe (test)
  GET  /api/stream/{id}          — SSE stream of agent thought trace
  GET  /api/health               — DB health check
"""

import os
from dotenv import load_dotenv
load_dotenv()

import json
import asyncio
import threading
from datetime import datetime
from typing import Optional, AsyncGenerator, List

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from database import get_connection, init_db
from haversine import rank_resources, nearest_agency
from agents import run_crew_and_dispatch, simulate_vip_bribe
from priority_engine import engine as priority_engine

# ── App Setup ─────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Sentinel-AI",
    version="2.0",
    description="Incorruptible TVM Disaster Response Dispatcher",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory SSE event queue: incident_id → list of messages
sse_queues: dict[int, list[str]] = {}

VIP_KEYWORDS = {"vip", "minister", "celebrity", "mla", "mp", "ias", "ips", "collector",
                "politician", "officer", "influential", "important person"}


@app.on_event("startup")
def on_startup():
    init_db()
    print("[API] Sentinel-AI v2.0 started.")


# ══════════════════════════════════════════════════════════════════════════════
# REQUEST MODELS
# ══════════════════════════════════════════════════════════════════════════════

class IncidentIn(BaseModel):
    # Contact
    phone:          str
    victim_name:    Optional[str] = None
    aadhar_id:      Optional[str] = None
    # Demographics
    male_cnt:       int = 0
    female_cnt:     int = 0
    child_cnt:      int = 0
    # Medical
    severity:       str = Field(..., pattern="^(Critical|High|Medium|Low)$")
    medical_cnt:    int = 0
    shelter_cnt:    int = 0
    # Special needs
    is_lgbtq:       int = 0
    is_disability:  int = 0
    # Hazards
    fire_hzd:       int = 0
    power_hzd:      int = 0
    emergency_type: str = Field(default="Other",
                                pattern="^(Fire|Electrical|Sewage|Flood|Road|Tree|Other)$")
    flood_level:    int = Field(default=0, ge=0, le=5)
    # Security
    extra_comments: Optional[str] = None
    # Location
    lat:            float
    lon:            float


class VipBribeIn(BaseModel):
    incident_id: int
    vip_name:    str = "Unknown VIP"


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _rows_to_list(rows) -> list[dict]:
    return [dict(r) for r in rows]


def _push_sse(incident_id: int, message: str):
    if incident_id not in sse_queues:
        sse_queues[incident_id] = []
    sse_queues[incident_id].append(message)


def _check_fraud(aadhar_id: str) -> bool:
    """Returns True if Aadhar is blacklisted."""
    if not aadhar_id:
        return False
    conn = get_connection()
    row = conn.execute(
        "SELECT aadhar_id FROM fraud_db WHERE aadhar_id=?", (aadhar_id,)
    ).fetchone()
    conn.close()
    return row is not None


def _check_vip(comments: str) -> bool:
    """Returns True if VIP keywords found in comments."""
    if not comments:
        return False
    text = comments.lower()
    return any(kw in text for kw in VIP_KEYWORDS)


def _log_dispatch_event_api(incident_id: int, event_type: str, message: str):
    conn = get_connection()
    conn.execute(
        "INSERT INTO dispatch_events (incident_id, event_type, message) VALUES (?,?,?)",
        (incident_id, event_type, message)
    )
    conn.commit()
    conn.close()


def _insert_victims(incident_id: int, data: IncidentIn):
    """Create individual victim records from demographics."""
    conn = get_connection()
    records = []
    severity = data.severity

    for i in range(data.male_cnt):
        records.append((incident_id, f"Male-{i+1}", data.phone, data.aadhar_id if i == 0 else None,
                        "Male", 1 if data.medical_cnt > 0 else 0,
                        data.is_lgbtq, data.is_disability, severity))
    for i in range(data.female_cnt):
        records.append((incident_id, f"Female-{i+1}", data.phone, None,
                        "Female", 1 if data.medical_cnt > 0 else 0,
                        data.is_lgbtq, data.is_disability, severity))
    for i in range(data.child_cnt):
        records.append((incident_id, f"Child-{i+1}", data.phone, None,
                        "Child", 1 if data.medical_cnt > 0 else 0,
                        data.is_lgbtq, data.is_disability, severity))

    conn.executemany("""
        INSERT INTO victims (incident_id, name, phone, aadhar_id, gender,
                             needs_medical, is_lgbtq, is_disability, severity)
        VALUES (?,?,?,?,?,?,?,?,?)
    """, records)
    conn.commit()
    conn.close()


def _run_crew_async(incident: dict):
    """Run the CrewAI crew in a background thread, pushing to SSE."""
    incident_id = incident["id"]
    _push_sse(incident_id, f"[Comm Director] Received triage for incident #{incident_id}")
    _push_sse(incident_id, f"[Priority: {incident.get('priority','Standard')}] "
                           f"Total victims: {incident.get('total_victims',0)}")
    _push_sse(incident_id, f"[Strategy Lead] Starting legal audit...")

    def push(msg: str):
        _push_sse(incident_id, msg)

    try:
        result = run_crew_and_dispatch(incident, push)
        _push_sse(incident_id, f"[DONE] {result}")
    except Exception as e:
        _push_sse(incident_id, f"[ERROR] {str(e)}")


# ══════════════════════════════════════════════════════════════════════════════
# ROUTES — READ
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/resources")
def get_resources():
    conn = get_connection()
    rows = conn.execute("SELECT * FROM resources ORDER BY type, name").fetchall()
    conn.close()
    return _rows_to_list(rows)


@app.get("/api/agencies")
def get_agencies(category: Optional[str] = None):
    conn = get_connection()
    if category:
        rows = conn.execute(
            "SELECT * FROM agencies WHERE category=? AND region='TVM'", (category,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM agencies WHERE region='TVM' ORDER BY category, name"
        ).fetchall()
    conn.close()
    return _rows_to_list(rows)


@app.get("/api/incidents")
def get_incidents(status: Optional[str] = None, priority: Optional[str] = None):
    conn = get_connection()
    if status and priority:
        rows = conn.execute(
            "SELECT * FROM incidents WHERE status=? AND priority=? ORDER BY timestamp DESC",
            (status, priority)
        ).fetchall()
    elif status:
        rows = conn.execute(
            "SELECT * FROM incidents WHERE status=? ORDER BY timestamp DESC", (status,)
        ).fetchall()
    elif priority:
        rows = conn.execute(
            "SELECT * FROM incidents WHERE priority=? ORDER BY timestamp DESC", (priority,)
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM incidents ORDER BY timestamp DESC").fetchall()
    conn.close()
    return _rows_to_list(rows)


@app.get("/api/audit")
def get_audit(incident_id: Optional[int] = None):
    conn = get_connection()
    if incident_id:
        rows = conn.execute(
            "SELECT * FROM audit_logs WHERE incident_id=? ORDER BY timestamp DESC", (incident_id,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM audit_logs ORDER BY timestamp DESC LIMIT 100"
        ).fetchall()
    conn.close()
    return _rows_to_list(rows)


@app.get("/api/allocations")
def get_allocations():
    conn = get_connection()
    rows = conn.execute("""
        SELECT a.*, r.name as resource_name, r.type as resource_type,
               i.phone, i.severity, i.lat, i.lon
        FROM allocations a
        JOIN resources  r ON a.resource_id  = r.id
        JOIN incidents  i ON a.incident_id  = i.id
        ORDER BY a.assignment_time DESC
    """).fetchall()
    conn.close()
    return _rows_to_list(rows)


@app.get("/api/rescue-units")
def get_rescue_units(unit_type: Optional[str] = None, status: Optional[str] = None):
    """Live rescue fleet status."""
    conn = get_connection()
    query = "SELECT * FROM rescue_units"
    params = []
    conditions = []
    if unit_type:
        conditions.append("unit_type=?")
        params.append(unit_type)
    if status:
        conditions.append("status=?")
        params.append(status)
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY unit_type, name"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return _rows_to_list(rows)


@app.get("/api/victims")
def get_victims(incident_id: Optional[int] = None, status: Optional[str] = None):
    """Individual victim tracking with placement info."""
    conn = get_connection()
    base = """
        SELECT v.*, r.name as placed_at_name, r.type as placed_at_type,
               r.lat as resource_lat, r.lon as resource_lon
        FROM victims v
        LEFT JOIN resources r ON v.assigned_resource_id = r.id
    """
    conditions = []
    params = []
    if incident_id:
        conditions.append("v.incident_id=?")
        params.append(incident_id)
    if status:
        conditions.append("v.status=?")
        params.append(status)
    if conditions:
        base += " WHERE " + " AND ".join(conditions)
    base += " ORDER BY v.incident_id DESC, v.id"
    rows = conn.execute(base, params).fetchall()
    conn.close()
    return _rows_to_list(rows)


@app.get("/api/dispatch-events/{incident_id}")
def get_dispatch_events(incident_id: int):
    """Full incident timeline."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM dispatch_events WHERE incident_id=? ORDER BY timestamp ASC",
        (incident_id,)
    ).fetchall()
    conn.close()
    return _rows_to_list(rows)


@app.get("/api/nearest")
def get_nearest(lat: float, lon: float, type: str = "Hospital", inclusive: int = 0):
    conn = get_connection()
    resources = _rows_to_list(conn.execute("SELECT * FROM resources WHERE status='Active'").fetchall())
    conn.close()
    ranked = rank_resources(lat, lon, resources, resource_type=type, top_n=3)
    return ranked


# ══════════════════════════════════════════════════════════════════════════════
# ROUTES — WRITE
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/api/incident", status_code=201)
def create_incident(data: IncidentIn, background_tasks: BackgroundTasks):
    """
    Submit a new SOS. Runs fraud check, VIP filter, ULTRA_PRIORITY logic,
    creates victim records, then kicks off the agent crew in background.
    """

    # ── Fraud Check ───────────────────────────────────────────────────────
    if _check_fraud(data.aadhar_id):
        raise HTTPException(
            status_code=400,
            detail={
                "status": "FRAUD_ALERT",
                "message": "Aadhar ID is blacklisted. Request rejected.",
                "aadhar": data.aadhar_id,
            }
        )

    # ── VIP Filter ────────────────────────────────────────────────────────
    vip_flagged = 1 if _check_vip(data.extra_comments) else 0

    # ── Demographics & Priority ───────────────────────────────────────────
    total_victims = data.male_cnt + data.female_cnt + data.child_cnt
    priority      = "ULTRA_PRIORITY" if total_victims > 20 else "Standard"

    # ── Priority Score (for logging) ──────────────────────────────────────
    incident_dict = data.model_dump()
    incident_dict["total_victims"] = total_victims
    incident_dict["priority"]      = priority
    score, raw_score = priority_engine.score_incident(incident_dict)

    # ── Insert Incident ───────────────────────────────────────────────────
    conn = get_connection()
    cur = conn.execute("""
        INSERT INTO incidents
        (phone, victim_name, aadhar_id,
         male_cnt, female_cnt, child_cnt, total_victims,
         severity, priority, medical_cnt, shelter_cnt,
         is_lgbtq, is_disability, fire_hzd, power_hzd,
         emergency_type, flood_level, vip_flagged, extra_comments,
         lat, lon, status)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'Pending')
    """, (
        data.phone, data.victim_name, data.aadhar_id,
        data.male_cnt, data.female_cnt, data.child_cnt, total_victims,
        data.severity, priority, data.medical_cnt, data.shelter_cnt,
        data.is_lgbtq, data.is_disability, data.fire_hzd, data.power_hzd,
        data.emergency_type, data.flood_level, vip_flagged, data.extra_comments,
        data.lat, data.lon,
    ))
    incident_id = cur.lastrowid
    conn.commit()
    conn.close()

    # ── Insert Victims ────────────────────────────────────────────────────
    _insert_victims(incident_id, data)

    # ── Log Events ───────────────────────────────────────────────────────
    if vip_flagged:
        _log_dispatch_event_api(incident_id, "VIP_BLOCKED",
                                "VIP reference detected in comments. Request will proceed on merit only.")
    if priority == "ULTRA_PRIORITY":
        _log_dispatch_event_api(incident_id, "ULTRA_PRIORITY",
                                f"ULTRA_PRIORITY triggered: {total_victims} victims detected.")

    # ── Kick Off Agent Crew ───────────────────────────────────────────────
    full_incident = incident_dict.copy()
    full_incident["id"] = incident_id

    background_tasks.add_task(
        threading.Thread(target=_run_crew_async, args=(full_incident,), daemon=True).start
    )

    return {
        "incident_id": incident_id,
        "status":      "Pending",
        "priority":    priority,
        "total_victims": total_victims,
        "priority_score": score,
        "vip_flagged": bool(vip_flagged),
    }


@app.post("/api/vip-bribe")
def vip_bribe(data: VipBribeIn):
    result = simulate_vip_bribe(data.incident_id, data.vip_name)
    return result


# ══════════════════════════════════════════════════════════════════════════════
# SSE — Thought Trace Stream
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/stream/{incident_id}")
async def stream_thought_trace(incident_id: int):
    async def event_generator() -> AsyncGenerator[str, None]:
        sent    = 0
        timeout = 900
        elapsed = 0

        while elapsed < timeout:
            msgs = sse_queues.get(incident_id, [])
            while sent < len(msgs):
                msg = msgs[sent]
                yield f"data: {json.dumps({'message': msg, 'ts': datetime.utcnow().isoformat()})}\n\n"
                sent += 1

            if sent > 0 and msgs and msgs[-1].startswith("[DONE]"):
                break

            await asyncio.sleep(0.5)
            elapsed += 0.5

        yield f"data: {json.dumps({'message': '[STREAM_END]', 'ts': datetime.utcnow().isoformat()})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ══════════════════════════════════════════════════════════════════════════════
# HEALTH
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/health")
def health():
    conn = get_connection()
    counts = {
        "incidents":     conn.execute("SELECT COUNT(*) FROM incidents").fetchone()[0],
        "resources":     conn.execute("SELECT COUNT(*) FROM resources").fetchone()[0],
        "agencies":      conn.execute("SELECT COUNT(*) FROM agencies").fetchone()[0],
        "rescue_units":  conn.execute("SELECT COUNT(*) FROM rescue_units").fetchone()[0],
        "victims":       conn.execute("SELECT COUNT(*) FROM victims").fetchone()[0],
        "audit_logs":    conn.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0],
        "fraud_entries": conn.execute("SELECT COUNT(*) FROM fraud_db").fetchone()[0],
    }
    conn.close()
    return {"status": "ok", "version": "2.0", "db_counts": counts}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)