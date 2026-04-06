"""
main.py — FastAPI backend for Sentinel-AI Incorruptible Dispatcher (TVM)
Endpoints:
  GET  /api/resources          — Live resource capacity
  GET  /api/agencies           — All TVM agencies
  GET  /api/incidents          — All incidents
  GET  /api/audit              — Audit log (Transparency Ledger)
  GET  /api/allocations        — Dispatch records
  POST /api/incident           — Submit new SOS triage
  POST /api/vip-bribe          — Simulate VIP bribe (test)
  GET  /api/stream/{id}        — SSE stream of agent thought trace
"""

import json
import asyncio
import threading
from datetime import datetime
from typing import Optional, AsyncGenerator

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from database import get_connection, init_db
from haversine import rank_resources, nearest_agency
from agents import build_crew, simulate_vip_bribe

# ── App setup ─────────────────────────────────────────────────────────────────
app = FastAPI(title="Sentinel-AI", version="1.0", description="Incorruptible TVM Dispatcher")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # tighten in production
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory SSE event queue: incident_id → list of messages
sse_queues: dict[int, list[str]] = {}


@app.on_event("startup")
def on_startup():
    init_db()
    print("[API] Sentinel-AI started.")


# ══════════════════════════════════════════════════════════════════════════════
# REQUEST MODELS
# ══════════════════════════════════════════════════════════════════════════════

class IncidentIn(BaseModel):
    phone:       str
    victim_name: Optional[str] = None
    severity:    str = Field(..., pattern="^(Critical|High|Medium|Low)$")
    medical_cnt: int = 0
    shelter_cnt: int = 0
    fire_hzd:    int = 0
    power_hzd:   int = 0
    is_lgbtq:    int = 0
    lat:         float
    lon:         float


class VipBribeIn(BaseModel):
    incident_id: int
    vip_name:    str = "Unknown VIP"


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _rows_to_list(rows) -> list[dict]:
    return [dict(r) for r in rows]


def _push_sse(incident_id: int, message: str):
    """Append a message to the SSE queue for an incident."""
    if incident_id not in sse_queues:
        sse_queues[incident_id] = []
    sse_queues[incident_id].append(message)


def _run_crew_async(incident: dict):
    """Run the CrewAI crew in a background thread, pushing updates to SSE."""
    incident_id = incident["id"]
    _push_sse(incident_id, f"[Comm Director] Received triage for incident #{incident_id}")
    _push_sse(incident_id, f"[Strategy Lead] Starting legal audit...")

    try:
        crew = build_crew(incident)
        result = crew.kickoff()
        _push_sse(incident_id, f"[Operations] Dispatch complete.")
        _push_sse(incident_id, f"[DONE] {str(result)[:300]}")
    except Exception as e:
        _push_sse(incident_id, f"[ERROR] Agent crew failed: {str(e)}")


# ══════════════════════════════════════════════════════════════════════════════
# ROUTES — READ
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/resources")
def get_resources():
    conn = get_connection()
    rows = conn.execute("SELECT * FROM resources ORDER BY name").fetchall()
    conn.close()
    return _rows_to_list(rows)


@app.get("/api/agencies")
def get_agencies(category: Optional[str] = None):
    conn = get_connection()
    if category:
        rows = conn.execute(
            "SELECT * FROM agencies WHERE category=? AND region='TVM'",
            (category,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM agencies WHERE region='TVM' ORDER BY category, name"
        ).fetchall()
    conn.close()
    return _rows_to_list(rows)


@app.get("/api/incidents")
def get_incidents(status: Optional[str] = None):
    conn = get_connection()
    if status:
        rows = conn.execute(
            "SELECT * FROM incidents WHERE status=? ORDER BY timestamp DESC", (status,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM incidents ORDER BY timestamp DESC"
        ).fetchall()
    conn.close()
    return _rows_to_list(rows)


@app.get("/api/audit")
def get_audit(incident_id: Optional[int] = None):
    conn = get_connection()
    if incident_id:
        rows = conn.execute(
            "SELECT * FROM audit_logs WHERE incident_id=? ORDER BY timestamp DESC",
            (incident_id,)
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


@app.get("/api/nearest")
def get_nearest(lat: float, lon: float, type: str = "Hospital", inclusive: int = 0):
    """Return ranked top-3 nearest resources for a coordinate."""
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
    Submit a new SOS triage. Kicks off the CrewAI agent pipeline asynchronously.
    Returns the new incident ID immediately.
    """
    conn = get_connection()
    cur  = conn.execute(
        """INSERT INTO incidents
           (phone, victim_name, severity, medical_cnt, shelter_cnt,
            fire_hzd, power_hzd, is_lgbtq, lat, lon, status)
           VALUES (?,?,?,?,?,?,?,?,?,?,'Pending')""",
        (data.phone, data.victim_name, data.severity,
         data.medical_cnt, data.shelter_cnt,
         data.fire_hzd, data.power_hzd, data.is_lgbtq,
         data.lat, data.lon)
    )
    incident_id = cur.lastrowid
    conn.commit()
    conn.close()

    incident = data.model_dump()
    incident["id"] = incident_id

    # Kick off agent crew in background thread
    background_tasks.add_task(
        threading.Thread(target=_run_crew_async, args=(incident,), daemon=True).start
    )

    return {"incident_id": incident_id, "status": "Pending"}


@app.post("/api/vip-bribe")
def vip_bribe(data: VipBribeIn):
    """
    Test endpoint: simulate a VIP bribe attempt.
    Strategy Lead always rejects it and logs VIP_BLOCKED.
    """
    result = simulate_vip_bribe(data.incident_id, data.vip_name)
    return result


# ══════════════════════════════════════════════════════════════════════════════
# SSE — Thought Trace stream
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/stream/{incident_id}")
async def stream_thought_trace(incident_id: int):
    """
    Server-Sent Events stream for real-time agent thought trace.
    The React frontend subscribes to this with EventSource.
    """
    async def event_generator() -> AsyncGenerator[str, None]:
        sent = 0
        timeout = 120  # seconds
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
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )


# ══════════════════════════════════════════════════════════════════════════════
# HEALTH
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/health")
def health():
    conn = get_connection()
    counts = {
        "incidents":  conn.execute("SELECT COUNT(*) FROM incidents").fetchone()[0],
        "resources":  conn.execute("SELECT COUNT(*) FROM resources").fetchone()[0],
        "agencies":   conn.execute("SELECT COUNT(*) FROM agencies").fetchone()[0],
        "audit_logs": conn.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0],
    }
    conn.close()
    return {"status": "ok", "db_counts": counts}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)