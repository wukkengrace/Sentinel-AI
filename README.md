# SENTINEL-AI — Incorruptible Disaster Dispatcher
## Thiruvananthapuram Emergency Support Centre (TVM-ESC)

---

## Architecture

```
React + Leaflet (Frontend)
        │  REST + SSE
FastAPI (Backend / main.py)
        │
  ┌─────┴──────┐
  │            │
SQLite      ChromaDB
(Live State) (RAG / KB)
        │
   CrewAI Crew
  (5 Ollama agents)
```

---

## Quick Start

### Step 1 — Install Python dependencies
```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### Step 2 — Install Ollama & pull models
```bash
# Install: https://ollama.ai
ollama pull llama3.2:3b         # Comm Director
ollama pull command-r            # Strategy Lead (legal auditor)
ollama pull mistral-nemo         # Local Liaison
ollama pull llama3.1:8b          # Logistics + Operations
ollama pull nomic-embed-text     # RAG embeddings
```

### Step 3 — Initialise database & seed TVM data
```bash
python database.py   # creates sentinel.db
python seed.py       # loads 34 agencies + 10 resources
```

### Step 4 — Ingest knowledge base
```bash
mkdir pdfs
# Copy your PDFs (from metadata.txt list) into ./pdfs/
# Files: Orange-Book-2025.pdf, Disaster-Management-Act-2005.pdf, etc.
python ingest_kb.py
```

### Step 5 — Start FastAPI backend
```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
# API docs: http://localhost:8000/docs
```

### Step 6 — Start React frontend
```bash
cd frontend
npm create vite@latest . -- --template react
npm install
# Copy Dashboard.jsx → src/App.jsx
npm run dev
# Opens: http://localhost:5173
```

---

## API Endpoints

| Method | Path                    | Description                          |
|--------|-------------------------|--------------------------------------|
| GET    | /api/resources          | Live bed/capacity counts             |
| GET    | /api/agencies           | TVM department directory             |
| GET    | /api/incidents          | All SOS incidents                    |
| GET    | /api/audit              | Transparency ledger                  |
| GET    | /api/allocations        | Dispatch records                     |
| POST   | /api/incident           | Submit new SOS triage                |
| POST   | /api/vip-bribe          | Simulate VIP override (always BLOCKED)|
| GET    | /api/stream/{id}        | SSE: real-time agent thought trace   |
| GET    | /api/nearest            | Find nearest resource by coordinates |

---

## Agent Crew

| Agent           | Model         | Role                                          |
|-----------------|---------------|-----------------------------------------------|
| Comm Director   | llama3.2:3b   | Triage intake, severity classification        |
| Strategy Lead   | command-r     | Legal auditor, DM Act 2005, VIP blocker       |
| Local Liaison   | mistral-nemo  | Maps hazards → TVM agencies                   |
| Logistics       | llama3.1:8b   | SQLite manager, bed allocation                |
| Operations      | llama3.1:8b   | Haversine ETA, nearest resource dispatcher    |

---

## ETA Formula
```
ETA (min) = (distance_km / 30 km/h) × 60 + 5 min buffer
```
Speed = 30 km/h (urban TVM disaster-mode assumption)
Buffer = 5 min gear-up/preparation time

---

## Data Sources
- **Agencies**: Category_Name_Latitude_Longitude.csv (34 TVM locations)
- **RAG**: metadata.txt → 21 disaster management documents
- **Schema**: structure_sqlite.txt → 5-table SQLite design

---

## VIP Bribe Test
POST /api/vip-bribe with `{"incident_id": 1, "vip_name": "Minister XYZ"}`

Strategy Lead always responds:
- Decision: `VIP_BLOCKED`
- Citation: `DM Act 2005, Section 38(2)`
- Logged to audit_logs permanently