import { useState, useEffect, useRef, useCallback } from "react";

// ── Constants ──────────────────────────────────────────────────────────────
const API = "http://localhost:8000/api";

const SEVERITY_COLOR = {
  Critical: "#ff2d2d",
  High: "#ff8c00",
  Medium: "#f5c518",
  Low: "#00e676",
};

const DECISION_COLOR = {
  APPROVED: "#00e676",
  REJECTED: "#ff2d2d",
  REDIRECTED: "#f5c518",
  VIP_BLOCKED: "#bf00ff",
};

// ── Fake demo data for preview when backend offline ───────────────────────
const DEMO_INCIDENTS = [
  { id: 1, phone: "919876543210", victim_name: "Rajan K", severity: "Critical", medical_cnt: 3, fire_hzd: 0, power_hzd: 1, is_lgbtq: 0, lat: 8.4982, lon: 76.9502, status: "Dispatched", timestamp: "2024-07-12T08:22:11" },
  { id: 2, phone: "919845112233", victim_name: "Ammu V", severity: "High", medical_cnt: 1, fire_hzd: 1, power_hzd: 0, is_lgbtq: 1, lat: 8.5150, lon: 76.9300, status: "Triage_Complete", timestamp: "2024-07-12T08:45:01" },
  { id: 3, phone: "919745009988", victim_name: "Sivan M", severity: "Medium", medical_cnt: 0, fire_hzd: 0, power_hzd: 0, is_lgbtq: 0, lat: 8.4870, lon: 76.9600, status: "Resolved", timestamp: "2024-07-12T07:10:55" },
];
const DEMO_RESOURCES = [
  { id: 1, name: "General Hospital TVM", type: "Hospital", cap_total: 500, cap_avail: 45, er_total: 10, er_avail: 3, lat: 8.4977, lon: 76.9415, inclusive: 0, status: "Active" },
  { id: 2, name: "Medical College TVM", type: "Hospital", cap_total: 1200, cap_avail: 80, er_total: 25, er_avail: 7, lat: 8.5241, lon: 76.9189, inclusive: 1, status: "Active" },
  { id: 3, name: "PTP Nagar Relief Camp", type: "Shelter", cap_total: 200, cap_avail: 160, er_total: 0, er_avail: 0, lat: 8.5061, lon: 76.9531, inclusive: 1, status: "Active" },
  { id: 4, name: "Peroorkada Relief Camp", type: "Shelter", cap_total: 150, cap_avail: 120, er_total: 0, er_avail: 0, lat: 8.5330, lon: 76.9740, inclusive: 0, status: "Active" },
  { id: 5, name: "SAT Hospital TVM", type: "Hospital", cap_total: 400, cap_avail: 0, er_total: 8, er_avail: 0, lat: 8.5148, lon: 76.9243, inclusive: 0, status: "Full" },
];
const DEMO_AUDIT = [
  { id: 1, incident_id: 1, agent: "Strategy Lead", decision: "APPROVED", reasoning: "Severity Critical confirmed per DM Act 2005 triage protocol. Nearest hospital with ER capacity assigned.", citation: "Orange Book 2025, Ch.4 §2", timestamp: "2024-07-12T08:22:15" },
  { id: 2, incident_id: 1, agent: "Operations", decision: "APPROVED", reasoning: "General Hospital TVM: 0.7 km, ETA 6.4 min. Haversine verified.", citation: "", timestamp: "2024-07-12T08:22:18" },
  { id: 3, incident_id: 2, agent: "Strategy Lead", decision: "VIP_BLOCKED", reasoning: "VIP override attempt by 'Minister XYZ' BLOCKED. Equal treatment mandated.", citation: "DM Act 2005 §38(2)", timestamp: "2024-07-12T08:45:10" },
  { id: 4, incident_id: 2, agent: "Local Liaison", decision: "APPROVED", reasoning: "Fire hazard: Fire HQ Chengalchoola notified. LGBTQIA+ flag: Medical College TVM (inclusive) preferred.", citation: "Orange Book 2025, Ch.7", timestamp: "2024-07-12T08:45:20" },
];
const DEMO_AGENCIES = [
  { id: 1, name: "Fire HQ Chengalchoola", category: "Fire", whatsapp: "919497996964", latitude: 8.4938, longitude: 76.9535 },
  { id: 2, name: "DHS HQ", category: "DHS", whatsapp: "918301838148", latitude: 8.4988, longitude: 76.9405 },
  { id: 3, name: "KSEB HQ Pattom", category: "KSEB", whatsapp: "910000000001", latitude: 8.5244, longitude: 76.9431 },
  { id: 4, name: "Police Control Room", category: "Police", whatsapp: "919400780088", latitude: 8.4975, longitude: 76.9510 },
];

// ── API helpers ───────────────────────────────────────────────────────────
async function apiFetch(path, opts = {}) {
  try {
    const r = await fetch(API + path, { headers: { "Content-Type": "application/json" }, ...opts });
    if (!r.ok) throw new Error(r.statusText);
    return await r.json();
  } catch { return null; }
}

// ── Haversine (client-side for map display) ───────────────────────────────
function haversine(lat1, lon1, lat2, lon2) {
  const R = 6371, toRad = d => d * Math.PI / 180;
  const dLat = toRad(lat2 - lat1), dLon = toRad(lon2 - lon1);
  const a = Math.sin(dLat / 2) ** 2 + Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2;
  return R * 2 * Math.asin(Math.sqrt(a));
}
function eta(dist) { return (dist / 30 * 60 + 5).toFixed(1); }

// ══════════════════════════════════════════════════════════════════════════
// SUB-COMPONENTS
// ══════════════════════════════════════════════════════════════════════════

function StatCard({ label, value, sub, accent }) {
  return (
    <div style={{
      background: "rgba(10,20,35,0.85)", border: `1px solid ${accent}33`,
      borderRadius: 8, padding: "18px 22px", position: "relative", overflow: "hidden"
    }}>
      <div style={{ position: "absolute", top: 0, left: 0, width: 3, height: "100%", background: accent }} />
      <div style={{ fontSize: 11, color: "#607080", letterSpacing: 2, textTransform: "uppercase", marginBottom: 6 }}>{label}</div>
      <div style={{ fontSize: 32, fontFamily: "'Courier New',monospace", fontWeight: 700, color: accent }}>{value}</div>
      {sub && <div style={{ fontSize: 11, color: "#607080", marginTop: 4 }}>{sub}</div>}
    </div>
  );
}

function SeverityBadge({ s }) {
  return <span style={{
    background: SEVERITY_COLOR[s] + "22", color: SEVERITY_COLOR[s],
    border: `1px solid ${SEVERITY_COLOR[s]}66`, borderRadius: 4,
    padding: "2px 8px", fontSize: 11, fontWeight: 700, letterSpacing: 1
  }}>{s}</span>;
}

function DecisionBadge({ d }) {
  const c = DECISION_COLOR[d] || "#607080";
  return <span style={{
    background: c + "22", color: c, border: `1px solid ${c}66`,
    borderRadius: 4, padding: "2px 8px", fontSize: 10, fontWeight: 700, letterSpacing: 1
  }}>{d}</span>;
}

function CapBar({ avail, total, inclusive }) {
  const pct = total > 0 ? (avail / total) * 100 : 0;
  const color = pct > 30 ? "#00e676" : pct > 10 ? "#f5c518" : "#ff2d2d";
  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, color: "#607080", marginBottom: 3 }}>
        <span>{avail}/{total} available</span>
        {inclusive ? <span style={{ color: "#bf00ff" }}>♿ Inclusive</span> : null}
      </div>
      <div style={{ height: 5, background: "#1a2535", borderRadius: 3 }}>
        <div style={{ height: "100%", width: `${pct}%`, background: color, borderRadius: 3, transition: "width 0.6s" }} />
      </div>
    </div>
  );
}

// ── Leaflet Map (loaded via CDN) ──────────────────────────────────────────
function LeafletMap({ incidents, resources, agencies }) {
  const mapRef = useRef(null);
  const mapInstance = useRef(null);

  useEffect(() => {
    if (mapInstance.current || !mapRef.current) return;
    if (!window.L) return;

    const L = window.L;
    const map = L.map(mapRef.current, { center: [8.5150, 76.9300], zoom: 12 });
    mapInstance.current = map;

    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: "© OpenStreetMap", maxZoom: 18
    }).addTo(map);

    // Custom icons
    const mkIcon = (color, symbol) => L.divIcon({
      className: "", iconSize: [28, 28], iconAnchor: [14, 14],
      html: `<div style="width:28px;height:28px;border-radius:50%;background:${color};
            border:2px solid #fff;display:flex;align-items:center;justify-content:center;
            font-size:14px;box-shadow:0 0 10px ${color}88">${symbol}</div>`
    });

    const severityIcon = (s) => {
      const c = SEVERITY_COLOR[s] || "#607080";
      return L.divIcon({
        className: "", iconSize: [24, 24], iconAnchor: [12, 12],
        html: `<div style="width:24px;height:24px;border-radius:50%;background:${c};
              border:2px solid #fff;box-shadow:0 0 12px ${c};animation:pulse 1.5s infinite">&nbsp;</div>`
      });
    };

    // Incidents
    incidents.forEach(inc => {
      if (!inc.lat || !inc.lon) return;
      L.marker([inc.lat, inc.lon], { icon: severityIcon(inc.severity) })
        .addTo(map)
        .bindPopup(`<b>INC #${inc.id}</b><br>${inc.victim_name || inc.phone}<br>
                    Severity: ${inc.severity}<br>Status: ${inc.status}`);
    });

    // Resources
    resources.forEach(r => {
      if (!r.lat || !r.lon) return;
      const symbol = r.type === "Hospital" ? "🏥" : r.type === "Shelter" ? "⛺" : "🚒";
      const color = r.status === "Full" ? "#ff2d2d" : r.status === "Cut-off" ? "#607080" : "#00e676";
      L.marker([r.lat, r.lon], { icon: mkIcon(color, symbol) })
        .addTo(map)
        .bindPopup(`<b>${r.name}</b><br>Beds: ${r.cap_avail}/${r.cap_total}<br>Status: ${r.status}`);
    });

    // Agencies (Fire stations etc.)
    agencies.slice(0, 8).forEach(a => {
      if (!a.latitude || !a.longitude) return;
      const symbol = a.category === "Fire" ? "🚒" : a.category === "Police" ? "🚔" : a.category === "KSEB" ? "⚡" : "🏛️";
      L.marker([a.latitude, a.longitude], { icon: mkIcon("#2979ff", symbol) })
        .addTo(map)
        .bindPopup(`<b>${a.name}</b><br>${a.category}<br>${a.whatsapp || "No contact"}`);
    });

  }, [incidents, resources, agencies]);

  return (
    <div style={{ position: "relative" }}>
      <div ref={mapRef} style={{ height: 420, borderRadius: 8, border: "1px solid #1e3050", zIndex: 1 }} />
      <div style={{
        position: "absolute", top: 10, right: 10, background: "rgba(5,12,24,0.9)",
        border: "1px solid #1e3050", borderRadius: 6, padding: "8px 12px", zIndex: 1000, fontSize: 11
      }}>
        <div style={{ color: "#ff2d2d", marginBottom: 3 }}>● Critical Incident</div>
        <div style={{ color: "#00e676", marginBottom: 3 }}>🏥 Hospital (available)</div>
        <div style={{ color: "#00e676", marginBottom: 3 }}>⛺ Shelter</div>
        <div style={{ color: "#2979ff" }}>🚒 Agency</div>
      </div>
    </div>
  );
}

// ── Thought Trace Terminal ────────────────────────────────────────────────
function ThoughtTrace({ incidentId }) {
  const [lines, setLines] = useState([]);
  const [active, setActive] = useState(false);
  const termRef = useRef(null);

  const startStream = useCallback(() => {
    if (!incidentId) return;
    setLines([]);
    setActive(true);
    const es = new EventSource(`${API}/stream/${incidentId}`);
    es.onmessage = (e) => {
      const data = JSON.parse(e.data);
      setLines(prev => [...prev, data.message]);
      if (data.message === "[STREAM_END]") { es.close(); setActive(false); }
    };
    es.onerror = () => { es.close(); setActive(false); };
    return () => es.close();
  }, [incidentId]);

  useEffect(() => {
    if (termRef.current) termRef.current.scrollTop = termRef.current.scrollHeight;
  }, [lines]);

  // Demo mode: fake trace
  const runDemo = () => {
    const msgs = [
      "[Comm Director] Received triage for incident #1 — Severity: Critical",
      "[Comm Director] 3 medical cases, power hazard flagged.",
      "[Strategy Lead] Querying DM Act 2005 knowledge base...",
      "[Strategy Lead] ✓ Severity confirmed per Orange Book 2025, Ch.4 §2",
      "[Strategy Lead] No VIP override detected. Decision: APPROVED",
      "[Local Liaison] Power hazard → KSEB HQ Pattom notified (WhatsApp)",
      "[Local Liaison] Police Control Room → always notified",
      "[Operations] Haversine: General Hospital TVM = 0.72 km, ETA 6.4 min",
      "[Operations] General Hospital TVM ETA: 6.4 mins (0.72 km) ✓",
      "[Logistics] Decrementing cap_avail: 45 → 44",
      "[Logistics] audit_log written — APPROVED by Strategy Lead",
      "[DONE] Incident #1 dispatched to General Hospital TVM.",
    ];
    setLines([]);
    setActive(true);
    msgs.forEach((m, i) => setTimeout(() => {
      setLines(prev => [...prev, m]);
      if (i === msgs.length - 1) setActive(false);
    }, i * 600));
  };

  const AGENT_COLOR = {
    "[Comm Director]": "#2979ff",
    "[Strategy Lead]": "#bf00ff",
    "[Local Liaison]": "#00e676",
    "[Operations]": "#f5c518",
    "[Logistics]": "#ff8c00",
    "[ERROR]": "#ff2d2d",
    "[DONE]": "#00e676",
  };

  const colorLine = (line) => {
    for (const [prefix, color] of Object.entries(AGENT_COLOR)) {
      if (line.startsWith(prefix)) return color;
    }
    return "#a0b0c0";
  };

  return (
    <div>
      <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
        <button onClick={runDemo} style={btnStyle("#2979ff")}>▶ Demo Trace</button>
        <button onClick={startStream} style={btnStyle("#00e676")} disabled={!incidentId}>
          ⚡ Live Stream #{incidentId || "?"}
        </button>
        {active && <span style={{ color: "#00e676", fontSize: 11, alignSelf: "center" }}>● STREAMING</span>}
      </div>
      <div ref={termRef} style={{
        background: "#020c14", border: "1px solid #0d2030", borderRadius: 6,
        padding: "14px 16px", height: 280, overflowY: "auto", fontFamily: "'Courier New',monospace", fontSize: 12
      }}>
        {lines.length === 0
          ? <span style={{ color: "#304050" }}>» Awaiting agent output…</span>
          : lines.map((l, i) => (
            <div key={i} style={{ color: colorLine(l), marginBottom: 3, lineHeight: 1.6 }}>
              <span style={{ color: "#304050", marginRight: 8 }}>{String(i + 1).padStart(2, "0")}</span>{l}
            </div>
          ))}
      </div>
    </div>
  );
}

// ── Triage Form ───────────────────────────────────────────────────────────
function TriageForm({ onSubmit }) {
  const [form, setForm] = useState({
    phone: "919876543210", victim_name: "", severity: "High",
    medical_cnt: 1, shelter_cnt: 0, fire_hzd: 0, power_hzd: 0, is_lgbtq: 0,
    lat: 8.5000, lon: 76.9500
  });
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState(null);

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));

  const submit = async () => {
    setSubmitting(true);
    const res = await apiFetch("/incident", {
      method: "POST", body: JSON.stringify({
        ...form,
        medical_cnt: +form.medical_cnt, shelter_cnt: +form.shelter_cnt,
        fire_hzd: +form.fire_hzd, power_hzd: +form.power_hzd,
        is_lgbtq: +form.is_lgbtq, lat: +form.lat, lon: +form.lon
      })
    });
    setSubmitting(false);
    if (res) { setResult(res); onSubmit && onSubmit(res); }
    else setResult({ error: "Backend offline — demo mode." });
  };

  return (
    <div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
        {[
          ["Phone", "phone", "text"],
          ["Victim Name", "victim_name", "text"],
          ["Latitude", "lat", "number"],
          ["Longitude", "lon", "number"],
          ["Medical Cnt", "medical_cnt", "number"],
          ["Shelter Cnt", "shelter_cnt", "number"],
        ].map(([label, key, type]) => (
          <label key={key} style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            <span style={{ fontSize: 10, color: "#607080", letterSpacing: 1, textTransform: "uppercase" }}>{label}</span>
            <input type={type} value={form[key]}
              onChange={e => set(key, e.target.value)}
              style={inputStyle} />
          </label>
        ))}
      </div>

      <div style={{ marginTop: 12, display: "grid", gridTemplateColumns: "1fr 1fr 1fr 1fr", gap: 8 }}>
        <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <span style={{ fontSize: 10, color: "#607080", letterSpacing: 1, textTransform: "uppercase" }}>Severity</span>
          <select value={form.severity} onChange={e => set("severity", e.target.value)} style={inputStyle}>
            {["Critical", "High", "Medium", "Low"].map(s => <option key={s}>{s}</option>)}
          </select>
        </label>
        {[["🔥 Fire Hzd", "fire_hzd"], ["⚡ Power Hzd", "power_hzd"], ["🏳️‍🌈 LGBTQIA+", "is_lgbtq"]].map(([label, key]) => (
          <label key={key} style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            <span style={{ fontSize: 10, color: "#607080", letterSpacing: 1, textTransform: "uppercase" }}>{label}</span>
            <select value={form[key]} onChange={e => set(key, e.target.value)} style={inputStyle}>
              <option value={0}>No</option>
              <option value={1}>Yes</option>
            </select>
          </label>
        ))}
      </div>

      <div style={{ marginTop: 14, display: "flex", gap: 10 }}>
        <button onClick={submit} disabled={submitting} style={btnStyle("#ff2d2d", 140)}>
          {submitting ? "Dispatching…" : "🚨 SUBMIT SOS"}
        </button>
      </div>

      {result && (
        <div style={{
          marginTop: 10, padding: "10px 14px", borderRadius: 6,
          background: result.error ? "#ff2d2d22" : "#00e67622",
          border: `1px solid ${result.error ? "#ff2d2d44" : "#00e67644"}`,
          fontSize: 12, color: result.error ? "#ff2d2d" : "#00e676"
        }}>
          {result.error || `✓ Incident #${result.incident_id} created — ${result.status}`}
        </div>
      )}
    </div>
  );
}

// ── VIP Bribe Simulator ───────────────────────────────────────────────────
function VipBribe({ incidents }) {
  const [incId, setIncId] = useState(1);
  const [vipName, setVip] = useState("Minister XYZ");
  const [result, setResult] = useState(null);

  const fire = async () => {
    // First try real API, fallback to simulated response
    const res = await apiFetch("/vip-bribe", {
      method: "POST", body: JSON.stringify({ incident_id: +incId, vip_name: vipName })
    });
    setResult(res || {
      status: "VIP_BLOCKED",
      message: `Override attempt by '${vipName}' rejected and logged.`,
      legal_basis: "DM Act 2005, Section 38(2)"
    });
  };

  return (
    <div>
      <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
        <label style={{ display: "flex", flexDirection: "column", gap: 4, flex: 1 }}>
          <span style={{ fontSize: 10, color: "#607080", letterSpacing: 1, textTransform: "uppercase" }}>Incident ID</span>
          <input type="number" value={incId} onChange={e => setIncId(e.target.value)} style={{ ...inputStyle, width: 80 }} />
        </label>
        <label style={{ display: "flex", flexDirection: "column", gap: 4, flex: 2 }}>
          <span style={{ fontSize: 10, color: "#607080", letterSpacing: 1, textTransform: "uppercase" }}>VIP Name</span>
          <input value={vipName} onChange={e => setVip(e.target.value)} style={inputStyle} />
        </label>
        <button onClick={fire} style={{ ...btnStyle("#bf00ff"), alignSelf: "flex-end", height: 38 }}>
          💰 Attempt Bribe
        </button>
      </div>
      {result && (
        <div style={{
          marginTop: 12, padding: "14px 16px", borderRadius: 6,
          background: "#bf00ff11", border: "1px solid #bf00ff44", fontSize: 12
        }}>
          <div style={{ color: "#bf00ff", fontWeight: 700, marginBottom: 6 }}>
            ⛔ {result.status}
          </div>
          <div style={{ color: "#a080c0", marginBottom: 4 }}>{result.message}</div>
          <div style={{ color: "#607080" }}>Legal basis: {result.legal_basis}</div>
        </div>
      )}
    </div>
  );
}

// ── Styles ────────────────────────────────────────────────────────────────
const inputStyle = {
  background: "#0a1624", border: "1px solid #1e3050", borderRadius: 5,
  color: "#c8d8e8", padding: "7px 10px", fontSize: 12, width: "100%",
  fontFamily: "'Courier New',monospace"
};
const btnStyle = (color, minW = 120) => ({
  background: color + "22", border: `1px solid ${color}66`, color,
  borderRadius: 5, padding: "8px 16px", cursor: "pointer", fontSize: 12,
  fontWeight: 700, letterSpacing: 1, minWidth: minW, transition: "all 0.2s"
});

// ══════════════════════════════════════════════════════════════════════════
// MAIN DASHBOARD
// ══════════════════════════════════════════════════════════════════════════

export default function SentinelDashboard() {
  const [tab, setTab] = useState("map");

  const [incidents, setIncidents] = useState(DEMO_INCIDENTS);
  const [resources, setResources] = useState(DEMO_RESOURCES);
  const [audit, setAudit] = useState(DEMO_AUDIT);
  const [agencies, setAgencies] = useState(DEMO_AGENCIES);
  const [streamId, setStreamId] = useState(1);
  const [online, setOnline] = useState(false);

  // Load Leaflet CSS+JS lazily
  useEffect(() => {
    if (!document.getElementById("leaflet-css")) {
      const link = document.createElement("link");
      link.id = "leaflet-css"; link.rel = "stylesheet";
      link.href = "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css";
      document.head.appendChild(link);
    }
    if (!window.L) {
      const s = document.createElement("script");
      s.src = "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js";
      document.head.appendChild(s);
    }
  }, []);

  // Poll backend every 10s
  useEffect(() => {
    const refresh = async () => {
      const h = await apiFetch("/health");
      if (h) {
        setOnline(true);
        const [inc, res, aud, ag] = await Promise.all([
          apiFetch("/incidents"), apiFetch("/resources"),
          apiFetch("/audit"), apiFetch("/agencies"),
        ]);
        if (inc) setIncidents(inc);
        if (res) setResources(res);
        if (aud) setAudit(aud);
        if (ag) setAgencies(ag);
      }
    };
    refresh();
    const iv = setInterval(refresh, 10000);
    return () => clearInterval(iv);
  }, []);

  // Stats
  const criticalCount = incidents.filter(i => i.severity === "Critical").length;
  const activeHospitals = resources.filter(r => r.type === "Hospital" && r.status === "Active").length;
  const totalBeds = resources.reduce((s, r) => s + r.cap_avail, 0);
  const dispatchedCount = incidents.filter(i => i.status === "Dispatched").length;

  const TABS = [
    { id: "map", label: "🗺 Live Map" },
    { id: "triage", label: "🚨 SOS Triage" },
    { id: "resources", label: "🏥 Resources" },
    { id: "audit", label: "📋 Transparency Ledger" },
    { id: "trace", label: "🧠 Thought Trace" },
    { id: "vip", label: "💰 VIP Test" },
  ];

  return (
    <div style={{
      minHeight: "100vh", background: "#030b16",
      color: "#c8d8e8", fontFamily: "'Courier New',monospace",
      padding: 0
    }}>
      {/* Scanline overlay */}
      <div style={{
        position: "fixed", inset: 0, pointerEvents: "none", zIndex: 9999,
        backgroundImage: "repeating-linear-gradient(0deg,transparent,transparent 2px,rgba(0,0,0,0.07) 2px,rgba(0,0,0,0.07) 4px)"
      }} />

      {/* Header */}
      <div style={{
        background: "rgba(2,12,24,0.97)", borderBottom: "1px solid #0d2535",
        padding: "16px 28px", display: "flex", alignItems: "center", gap: 16
      }}>
        <div style={{
          width: 36, height: 36, borderRadius: 6,
          background: "linear-gradient(135deg,#ff2d2d,#2979ff)",
          display: "flex", alignItems: "center", justifyContent: "center", fontSize: 18
        }}>⚡</div>
        <div>
          <div style={{ fontSize: 16, fontWeight: 700, letterSpacing: 2, color: "#e8f0f8" }}>
            SENTINEL-AI
          </div>
          <div style={{ fontSize: 10, color: "#607080", letterSpacing: 3 }}>
            INCORRUPTIBLE DISPATCHER · THIRUVANANTHAPURAM ESC
          </div>
        </div>
        <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 20 }}>
          <div style={{ fontSize: 10, color: online ? "#00e676" : "#ff8c00" }}>
            {online ? "● BACKEND LIVE" : "● DEMO MODE"}
          </div>
          <div style={{ fontSize: 10, color: "#607080" }}>
            {new Date().toLocaleTimeString("en-IN", { hour12: false })} IST
          </div>
        </div>
      </div>

      <div style={{ padding: "20px 24px" }}>

        {/* Stats row */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 12, marginBottom: 20 }}>
          <StatCard label="Critical Incidents" value={criticalCount} sub="Active now" accent="#ff2d2d" />
          <StatCard label="Dispatched" value={dispatchedCount} sub="Since last hour" accent="#2979ff" />
          <StatCard label="Active Hospitals" value={activeHospitals} sub="TVM network" accent="#00e676" />
          <StatCard label="Available Beds" value={totalBeds} sub="All resources" accent="#f5c518" />
        </div>

        {/* Tab nav */}
        <div style={{ display: "flex", gap: 4, marginBottom: 16, flexWrap: "wrap" }}>
          {TABS.map(t => (
            <button key={t.id} onClick={() => setTab(t.id)} style={{
              background: tab === t.id ? "#2979ff22" : "transparent",
              border: `1px solid ${tab === t.id ? "#2979ff88" : "#1e3050"}`,
              color: tab === t.id ? "#2979ff" : "#607080",
              borderRadius: 5, padding: "7px 14px", cursor: "pointer",
              fontSize: 11, fontWeight: 700, letterSpacing: 1
            }}>{t.label}</button>
          ))}
        </div>

        {/* ── TAB: MAP ── */}
        {tab === "map" && (
          <div style={panel}>
            <SectionTitle>Live Incident Map — Thiruvananthapuram</SectionTitle>
            <LeafletMap incidents={incidents} resources={resources} agencies={agencies} />
            <div style={{ marginTop: 12, display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 10 }}>
              {incidents.slice(0, 3).map(inc => (
                <div key={inc.id} style={{
                  background: "#0a1624", border: `1px solid ${SEVERITY_COLOR[inc.severity]}44`,
                  borderRadius: 6, padding: "10px 12px"
                }}>
                  <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
                    <span style={{ color: "#607080", fontSize: 10 }}>INC #{inc.id}</span>
                    <SeverityBadge s={inc.severity} />
                  </div>
                  <div style={{ color: "#c8d8e8", fontSize: 12, marginBottom: 2 }}>
                    {inc.victim_name || inc.phone}
                  </div>
                  <div style={{ fontSize: 10, color: "#607080" }}>
                    {inc.lat.toFixed(4)}, {inc.lon.toFixed(4)} · {inc.status}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* ── TAB: TRIAGE ── */}
        {tab === "triage" && (
          <div style={panel}>
            <SectionTitle>New SOS Triage</SectionTitle>
            <TriageForm onSubmit={r => { setStreamId(r.incident_id); setTab("trace"); }} />
            <div style={{ marginTop: 24 }}>
              <SectionTitle>Recent Incidents</SectionTitle>
              <div style={{ overflowX: "auto" }}>
                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11 }}>
                  <thead>
                    <tr style={{ borderBottom: "1px solid #1e3050" }}>
                      {["ID", "Phone", "Severity", "Medical", "Fire", "Power", "LGBTQ+", "Status", "Time"].map(h => (
                        <th key={h} style={{ padding: "8px 10px", color: "#607080", textAlign: "left", whiteSpace: "nowrap" }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {incidents.map(inc => (
                      <tr key={inc.id} style={{ borderBottom: "1px solid #0d1f30" }}>
                        <td style={td}>{inc.id}</td>
                        <td style={td}>{inc.phone.slice(-10)}</td>
                        <td style={td}><SeverityBadge s={inc.severity} /></td>
                        <td style={td}>{inc.medical_cnt}</td>
                        <td style={td}>{inc.fire_hzd ? "🔥" : "—"}</td>
                        <td style={td}>{inc.power_hzd ? "⚡" : "—"}</td>
                        <td style={td}>{inc.is_lgbtq ? "🏳️‍🌈" : "—"}</td>
                        <td style={td}>{inc.status}</td>
                        <td style={td}>{new Date(inc.timestamp).toLocaleTimeString("en-IN")}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {/* ── TAB: RESOURCES ── */}
        {tab === "resources" && (
          <div style={panel}>
            <SectionTitle>Live Resource Capacity</SectionTitle>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill,minmax(280px,1fr))", gap: 12 }}>
              {resources.map(r => (
                <div key={r.id} style={{
                  background: "#080f1c", border: `1px solid #1e3050`,
                  borderRadius: 8, padding: "14px 16px",
                  borderLeft: `3px solid ${r.status === "Active" ? "#00e676" : r.status === "Full" ? "#ff2d2d" : "#607080"}`
                }}>
                  <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8 }}>
                    <div style={{ fontSize: 13, color: "#e8f0f8", fontWeight: 700 }}>{r.name}</div>
                    <span style={{ fontSize: 10, color: r.status === "Active" ? "#00e676" : r.status === "Full" ? "#ff2d2d" : "#607080" }}>
                      {r.status}
                    </span>
                  </div>
                  <div style={{ fontSize: 10, color: "#607080", marginBottom: 8 }}>
                    {r.type} · {r.lat.toFixed(4)}, {r.lon.toFixed(4)}
                  </div>
                  <CapBar avail={r.cap_avail} total={r.cap_total} inclusive={r.inclusive} />
                  {r.type === "Hospital" && (
                    <div style={{ marginTop: 8, fontSize: 10, color: "#607080" }}>
                      ER rooms: <span style={{ color: "#f5c518" }}>{r.er_avail}/{r.er_total}</span>
                    </div>
                  )}
                </div>
              ))}
            </div>

            <div style={{ marginTop: 20 }}>
              <SectionTitle>Agency Directory</SectionTitle>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill,minmax(240px,1fr))", gap: 10 }}>
                {agencies.map(a => (
                  <div key={a.id} style={{
                    background: "#080f1c", border: "1px solid #1e3050",
                    borderRadius: 6, padding: "10px 14px"
                  }}>
                    <div style={{ fontSize: 12, color: "#e8f0f8", marginBottom: 3 }}>{a.name}</div>
                    <div style={{ fontSize: 10, color: "#607080", marginBottom: 4 }}>
                      {a.esf_role || a.category}
                    </div>
                    {a.whatsapp && (
                      <div style={{ fontSize: 10, color: "#00e676" }}>📱 +{a.whatsapp}</div>
                    )}
                    {a.latitude && (
                      <div style={{ fontSize: 10, color: "#304050", marginTop: 3 }}>
                        {a.latitude.toFixed(4)}, {a.longitude.toFixed(4)}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* ── TAB: AUDIT ── */}
        {tab === "audit" && (
          <div style={panel}>
            <SectionTitle>Transparency Ledger — AI Decision Audit Log</SectionTitle>
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11 }}>
                <thead>
                  <tr style={{ borderBottom: "1px solid #1e3050" }}>
                    {["#", "Inc", "Agent", "Decision", "Reasoning", "Citation", "Time"].map(h => (
                      <th key={h} style={{ padding: "9px 12px", color: "#607080", textAlign: "left", whiteSpace: "nowrap" }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {audit.map(log => (
                    <tr key={log.id} style={{ borderBottom: "1px solid #0a1624" }}>
                      <td style={td}>{log.id}</td>
                      <td style={td}><span style={{ color: "#2979ff" }}>#{log.incident_id}</span></td>
                      <td style={td}>{log.agent}</td>
                      <td style={td}><DecisionBadge d={log.decision} /></td>
                      <td style={{ ...td, maxWidth: 320, whiteSpace: "normal", lineHeight: 1.5 }}>
                        {log.reasoning}
                      </td>
                      <td style={{ ...td, color: "#607080", whiteSpace: "nowrap" }}>
                        {log.citation || "—"}
                      </td>
                      <td style={{ ...td, whiteSpace: "nowrap" }}>
                        {new Date(log.timestamp).toLocaleTimeString("en-IN")}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* ── TAB: THOUGHT TRACE ── */}
        {tab === "trace" && (
          <div style={panel}>
            <SectionTitle>Agent Thought Trace (Real-Time SSE)</SectionTitle>
            <div style={{ marginBottom: 12, display: "flex", gap: 10, alignItems: "center" }}>
              <span style={{ fontSize: 11, color: "#607080" }}>Incident ID:</span>
              <input type="number" value={streamId} onChange={e => setStreamId(+e.target.value)}
                style={{ ...inputStyle, width: 80 }} />
            </div>
            <ThoughtTrace incidentId={streamId} />

            {/* Dispatch feed */}
            <div style={{ marginTop: 20 }}>
              <SectionTitle>Dispatch Feed</SectionTitle>
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {[
                  { agency: "General Hospital TVM", dist: 0.72, eta: 6.4, type: "🏥" },
                  { agency: "Fire HQ Chengalchoola", dist: 1.10, eta: 7.2, type: "🚒" },
                  { agency: "KSEB HQ Pattom", dist: 1.80, eta: 8.6, type: "⚡" },
                  { agency: "Police Control Room", dist: 0.95, eta: 6.9, type: "🚔" },
                ].map((d, i) => (
                  <div key={i} style={{
                    background: "#0a1624", border: "1px solid #1e3050",
                    borderRadius: 6, padding: "10px 16px",
                    display: "flex", alignItems: "center", gap: 14
                  }}>
                    <span style={{ fontSize: 18 }}>{d.type}</span>
                    <div style={{ flex: 1 }}>
                      <div style={{ color: "#e8f0f8", fontSize: 12, fontWeight: 700 }}>{d.agency}</div>
                      <div style={{ color: "#607080", fontSize: 10 }}>{d.dist} km away</div>
                    </div>
                    <div style={{
                      background: "#00e67622", border: "1px solid #00e67644",
                      borderRadius: 4, padding: "4px 10px", color: "#00e676", fontSize: 11, fontWeight: 700
                    }}>
                      ETA {d.eta} min
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* ── TAB: VIP BRIBE ── */}
        {tab === "vip" && (
          <div style={panel}>
            <SectionTitle>⚠️ VIP Bribe Simulation — Strategy Lead Test</SectionTitle>
            <div style={{
              background: "#bf00ff11", border: "1px solid #bf00ff33",
              borderRadius: 6, padding: "12px 16px", marginBottom: 16, fontSize: 12, color: "#8060a0"
            }}>
              This test simulates a VIP/politician attempting to skip the triage queue.
              The Strategy Lead agent should always <strong style={{ color: "#bf00ff" }}>REJECT</strong> it
              and log <code style={{ color: "#bf00ff" }}>VIP_BLOCKED</code> with DM Act 2005 §38(2) citation.
            </div>
            <VipBribe incidents={incidents} />

            <div style={{ marginTop: 20 }}>
              <SectionTitle>VIP Block History</SectionTitle>
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                {audit.filter(a => a.decision === "VIP_BLOCKED").map(log => (
                  <div key={log.id} style={{
                    background: "#0a1624", border: "1px solid #bf00ff33",
                    borderRadius: 6, padding: "10px 14px"
                  }}>
                    <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
                      <DecisionBadge d="VIP_BLOCKED" />
                      <span style={{ fontSize: 10, color: "#607080" }}>
                        {new Date(log.timestamp).toLocaleString("en-IN")}
                      </span>
                    </div>
                    <div style={{ fontSize: 11, color: "#a080c0", marginBottom: 3 }}>{log.reasoning}</div>
                    <div style={{ fontSize: 10, color: "#607080" }}>📜 {log.citation}</div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

      </div>
    </div>
  );
}

// Tiny helpers
const panel = {
  background: "rgba(8,16,28,0.9)", border: "1px solid #1e3050",
  borderRadius: 10, padding: "20px 22px"
};
const td = { padding: "8px 10px", color: "#a0b8c8", verticalAlign: "middle", whiteSpace: "nowrap" };
const SectionTitle = ({ children }) => (
  <div style={{
    fontSize: 11, color: "#607080", letterSpacing: 3, textTransform: "uppercase",
    marginBottom: 14, paddingBottom: 6, borderBottom: "1px solid #0d2035"
  }}>{children}</div>
);