import { useState, useEffect, useRef, useCallback } from "react";

const API = "http://localhost:8000/api";

const SEVERITY_COLOR = {
  Critical: "text-[#ff2d2d] border-[#ff2d2d]/60 bg-[#ff2d2d]/10 font-bold",
  High: "text-[#ff8c00] border-[#ff8c00]/60 bg-[#ff8c00]/10",
  Medium: "text-[#f5c518] border-[#f5c518]/60 bg-[#f5c518]/10",
  Low: "text-[#00e676] border-[#00e676]/60 bg-[#00e676]/10",
};

const DECISION_COLOR = {
  APPROVED: "text-[#00e676] border-[#00e676]/60 bg-[#00e676]/10",
  REJECTED: "text-[#ff2d2d] border-[#ff2d2d]/60 bg-[#ff2d2d]/10",
  REDIRECTED: "text-[#f5c518] border-[#f5c518]/60 bg-[#f5c518]/10",
  VIP_BLOCKED: "text-[#bf00ff] border-[#bf00ff]/60 bg-[#bf00ff]/10",
};

const DEMO_INCIDENTS = [
  { id: 1, phone: "919876543210", victim_name: "Rajan K", severity: "Critical", medical_cnt: 3, fire_hzd: 0, power_hzd: 1, is_lgbtq: 0, lat: 8.4982, lon: 76.9502, status: "Dispatched", timestamp: "2024-07-12T08:22:11" },
  { id: 2, phone: "919845112233", victim_name: "Ammu V", severity: "High", medical_cnt: 1, fire_hzd: 1, power_hzd: 0, is_lgbtq: 1, lat: 8.5150, lon: 76.9300, status: "Triage_Complete", timestamp: "2024-07-12T08:45:01" },
];
const DEMO_RESOURCES = [
  { id: 1, name: "General Hospital TVM", type: "Hospital", cap_total: 500, cap_avail: 45, er_total: 10, er_avail: 3, lat: 8.4977, lon: 76.9415, inclusive: 0, status: "Active" },
  { id: 2, name: "Medical College TVM", type: "Hospital", cap_total: 1200, cap_avail: 80, er_total: 25, er_avail: 7, lat: 8.5241, lon: 76.9189, inclusive: 1, status: "Active" },
];
const DEMO_AUDIT = [
  { id: 1, incident_id: 1, agent: "Strategy Lead", decision: "APPROVED", reasoning: "Severity Critical confirmed per DM Act 2005 triage protocol.", citation: "Orange Book 2025, Ch.4", timestamp: "2024-07-12T08:22:15" },
];
const DEMO_AGENCIES = [
  { id: 1, name: "Fire HQ Chengalchoola", category: "Fire", whatsapp: "919497996964", latitude: 8.4938, longitude: 76.9535 },
];

async function apiFetch(path, opts = {}) {
  try {
    const r = await fetch(API + path, { ...opts, headers: { "Content-Type": "application/json", ...opts.headers } });
    if (!r.ok) return null;
    return await r.json();
  } catch { return null; }
}

function StatCard({ label, value, sub, borderColorCls, textCls }) {
  return (
    <div className={`glass-panel p-5 relative border-l-[3px] ${borderColorCls}`}>
      <div className="text-[10px] text-gray-500 uppercase tracking-widest mb-1">{label}</div>
      <div className={`text-3xl font-mono font-bold ${textCls}`}>{value}</div>
      {sub && <div className="text-[11px] text-gray-400 mt-2">{sub}</div>}
    </div>
  );
}

function CapBar({ avail, total, inclusive }) {
  const pct = total > 0 ? (avail / total) * 100 : 0;
  const color = pct > 30 ? "bg-[#00e676]" : pct > 10 ? "bg-[#f5c518]" : "bg-[#ff2d2d]";
  return (
    <div className="mt-3">
      <div className="flex justify-between text-[10px] text-gray-400 mb-1 font-mono">
        <span>{avail}/{total} OPEN</span>
        {inclusive ? <span className="text-[#bf00ff]">♿ INCLUSIVE</span> : null}
      </div>
      <div className="h-1.5 bg-[#1a2535] rounded-full overflow-hidden">
        <div className={`h-full ${color} transition-all duration-700`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

function LeafletMap({ incidents, resources, agencies }) {
  const mapRef = useRef(null);
  const mapInstance = useRef(null);

  useEffect(() => {
    if (mapInstance.current || !mapRef.current) return;
    if (!window.L) return;

    const L = window.L;
    const map = L.map(mapRef.current, { center: [8.5150, 76.9300], zoom: 12 });
    mapInstance.current = map;

    L.tileLayer("https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png", {
      attribution: "© OpenStreetMap © CARTO", maxZoom: 18
    }).addTo(map);

    const mkIcon = (color, symbol) => L.divIcon({
      className: "", iconSize: [28, 28], iconAnchor: [14, 14],
      html: `<div style="width:28px;height:28px;border-radius:50%;background:${color}22;
            border:1.5px solid ${color};display:flex;align-items:center;justify-content:center;
            font-size:14px;box-shadow:0 0 10px ${color}88 backdrop-filter:blur(4px);">${symbol}</div>`
    });

    const severityIcon = (s) => {
      const c = s === 'Critical' ? '#ff2d2d' : s === 'High' ? '#ff8c00' : s === 'Medium' ? '#f5c518' : '#00e676';
      return L.divIcon({
        className: "", iconSize: [24, 24], iconAnchor: [12, 12],
        html: `<div class="${s === 'Critical' ? 'animate-pulse' : ''}" style="width:20px;height:20px;border-radius:50%;background:${c};
              border:2px solid #fff;box-shadow:0 0 12px ${c};">&nbsp;</div>`
      });
    };

    incidents.forEach(inc => {
      if (!inc.lat || !inc.lon) return;
      L.marker([inc.lat, inc.lon], { icon: severityIcon(inc.severity) })
        .addTo(map)
        .bindPopup(`<b>INC #${inc.id}</b><br>${inc.victim_name || inc.phone}<br>Severity: ${inc.severity}`);
    });

    resources.forEach(r => {
      if (!r.lat || !r.lon) return;
      const symbol = r.type === "Hospital" ? "🏥" : r.type === "Shelter" ? "⛺" : "🚒";
      const color = r.status === "Full" ? "#ff2d2d" : "#00e676";
      L.marker([r.lat, r.lon], { icon: mkIcon(color, symbol) })
        .addTo(map)
        .bindPopup(`<b>${r.name}</b><br>Beds: ${r.cap_avail}/${r.cap_total}`);
    });

    agencies.slice(0, 8).forEach(a => {
      if (!a.latitude || !a.longitude) return;
      const symbol = a.category === "Fire" ? "🚒" : a.category === "Police" ? "🚔" : a.category === "KSEB" ? "⚡" : "🏛️";
      L.marker([a.latitude, a.longitude], { icon: mkIcon("#2979ff", symbol) })
        .addTo(map).bindPopup(`<b>${a.name}</b>`);
    });

  }, [incidents, resources, agencies]);

  return (
    <div className="relative">
      <div ref={mapRef} className="h-[420px] rounded-xl border border-[rgba(30,48,80,0.5)] shadow-[0_0_20px_rgba(41,121,255,0.1)] z-10" />
      <div className="absolute top-3 right-3 bg-[rgba(5,12,24,0.85)] backdrop-blur border border-[rgba(30,48,80,0.5)] rounded-lg p-2 z-[1000] text-[10px] space-y-1 text-gray-300 shadow-lg">
        <div className="text-[#ff2d2d] font-bold">● Critical Incident</div>
        <div className="text-[#00e676]">🏥 Hospital</div>
        <div className="text-[#00e676]">⛺ Shelter</div>
        <div className="text-[#2979ff]">🚒 Agency</div>
      </div>
    </div>
  );
}

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

  const runDemo = () => {
    const msgs = [
      "[Comm Director] Received triage for incident #1 — Severity: Critical",
      "[Strategy Lead] Querying DM Act 2005 knowledge base...",
      "[Strategy Lead] ✓ Severity confirmed per Orange Book 2025, Ch.4 §2",
      "[Local Liaison] Power hazard → KSEB HQ Pattom notified (WhatsApp)",
      "[Operations] Haversine: General Hospital TVM = 0.72 km, ETA 6.4 min",
      "[Logistics] Decrementing cap_avail: 45 → 44",
      "[DONE] Incident #1 dispatched to General Hospital TVM.",
    ];
    setLines([]);
    setActive(true);
    msgs.forEach((m, i) => setTimeout(() => {
      setLines(prev => [...prev, m]);
      if (i === msgs.length - 1) setActive(false);
    }, i * 600));
  };

  const getLogColor = (l) => {
    if(l.startsWith("[Comm")) return "text-[#2979ff]";
    if(l.startsWith("[Stra")) return "text-[#bf00ff]";
    if(l.startsWith("[Loca")) return "text-[#00e676]";
    if(l.startsWith("[Oper")) return "text-[#f5c518]";
    if(l.startsWith("[Logi")) return "text-[#ff8c00]";
    if(l.startsWith("[DONE]")) return "text-[#00e676] bg-[#00e676]/10 inline p-1 rounded font-bold";
    if(l.startsWith("[ERROR]")) return "text-[#ff2d2d] bg-[#ff2d2d]/10 inline p-1 rounded font-bold";
    return "text-gray-400";
  };

  return (
    <div className="flex flex-col h-full">
      <div className="flex gap-3 mb-3">
        <button onClick={runDemo} className="btn-primary">▶ Demo Trace</button>
        <button onClick={startStream} disabled={!incidentId} className="btn-success">
          ⚡ Live Stream #{incidentId || "?"}
        </button>
        {active && <span className="text-[#00e676] text-xs self-center font-bold animate-pulse tracking-widest uppercase">● Streaming Model Thoughts</span>}
      </div>
      <div ref={termRef} className="bg-[#020813] border border-[#0d2535] rounded-xl p-4 flex-1 min-h-[300px] overflow-y-auto font-mono text-xs shadow-inner relative">
        <div className="absolute inset-0 pointer-events-none opacity-20" style={{background: 'linear-gradient(180deg, transparent 50%, rgba(41,121,255,0.05) 50%)', backgroundSize:'100% 4px'}}></div>
        {lines.length === 0 ? <span className="text-gray-600 italic">» Awaiting multi-agent consensus...</span> : 
          lines.map((l, i) => (
            <div key={i} className={`mb-1.5 leading-relaxed tracking-wide ${getLogColor(l)}`}>
              <span className="text-gray-600 mr-2">{String(i + 1).padStart(2, "0")}</span>{l}
            </div>
          ))
        }
      </div>
    </div>
  );
}

export default function SentinelDashboard() {
  const [tab, setTab] = useState("map");
  const [incidents, setIncidents] = useState(DEMO_INCIDENTS);
  const [resources, setResources] = useState(DEMO_RESOURCES);
  const [audit, setAudit] = useState(DEMO_AUDIT);
  const [agencies, setAgencies] = useState(DEMO_AGENCIES);
  const [streamId, setStreamId] = useState(1);
  const [online, setOnline] = useState(false);

  // Form State
  const [phone, setPhone] = useState("919876543210");
  const [victimName, setVictimName] = useState("");
  const [lat, setLat] = useState("8.5000");
  const [lon, setLon] = useState("76.9500");
  const [severity, setSeverity] = useState("Critical");
  const [fireHzd, setFireHzd] = useState(0);

  const handleDispatch = async () => {
    const payload = {
      phone,
      victim_name: victimName,
      lat: parseFloat(lat),
      lon: parseFloat(lon),
      severity,
      fire_hzd: parseInt(fireHzd),
      medical_cnt: severity === "Critical" ? 3 : 1, // mock typical values
      power_hzd: 0,
      is_lgbtq: 0
    };
    alert("Dispatching incident...");
    const res = await fetch("http://localhost:8000/api/incident", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    if (res.ok) {
      const data = await res.json();
      setStreamId(data.id);
      setTab("trace");
    } else {
      alert("Error dispatching incident.");
    }
  };

  const handleGetLocation = () => {
    if ("geolocation" in navigator) {
      navigator.geolocation.getCurrentPosition(
        (position) => {
          setLat(position.coords.latitude.toFixed(6));
          setLon(position.coords.longitude.toFixed(6));
        },
        (error) => {
          console.error(error);
          alert("Could not detect location. Make sure you allow location permissions in your browser.");
        }
      );
    } else {
      alert("Geolocation is not supported by your browser.");
    }
  };

  useEffect(() => {
    if (!document.getElementById("leaflet-css")) {
      const link = document.createElement("link"); link.id = "leaflet-css"; link.rel = "stylesheet"; link.href = "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css"; document.head.appendChild(link);
    }
    if (!window.L) {
      const s = document.createElement("script"); s.src = "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js"; document.head.appendChild(s);
    }
  }, []);

  useEffect(() => {
    const refresh = async () => {
      const h = await apiFetch("/health");
      if (h) {
        setOnline(true);
        const [inc, res, aud, ag] = await Promise.all([apiFetch("/incidents"), apiFetch("/resources"), apiFetch("/audit"), apiFetch("/agencies")]);
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

  const TABS = [
    { id: "map", label: "🗺 Live Map" },
    { id: "triage", label: "🚨 SOS Triage" },
    { id: "resources", label: "🏥 Resources" },
    { id: "audit", label: "📋 AI Ledger" },
    { id: "trace", label: "🧠 Thought Trace" },
  ];

  return (
    <div className="min-h-screen relative text-gray-200">
      <div className="fixed inset-0 pointer-events-none z-[9999] scanline" />
      
      {/* Header */}
      <header className="bg-[rgba(2,12,24,0.95)] border-b border-[#0d2535] py-4 px-6 flex items-center gap-4 sticky top-0 z-[5000] backdrop-blur-lg">
        <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-[#ff2d2d] to-[#2979ff] flex items-center justify-center text-xl shadow-[0_0_15px_rgba(41,121,255,0.5)] border border-white/20">⚡</div>
        <div>
          <h1 className="text-xl font-bold tracking-[0.2em] text-[#e8f0f8] drop-shadow-md">SENTINEL-AI</h1>
          <div className="text-[10px] text-[#607080] tracking-[0.3em] font-mono mt-0.5">INCORRUPTIBLE DISPATCHER · TVM ESC</div>
        </div>
        <div className="ml-auto flex items-center gap-6">
          <div className={`text-[10px] uppercase font-bold tracking-widest flex items-center gap-2 ${online ? "text-[#00e676]" : "text-[#ff8c00]"}`}>
            <span className={`w-2 h-2 rounded-full ${online ? "bg-[#00e676] animate-pulse" : "bg-[#ff8c00]"}`}></span>
            {online ? "BACKEND LIVE" : "DEMO MODE"}
          </div>
        </div>
      </header>

      <main className="p-6 max-w-[1600px] mx-auto">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
          <StatCard label="Critical Incidents" value={incidents.filter(i=>i.severity==="Critical").length} sub="Active now" borderColorCls="border-[#ff2d2d]" textCls="text-[#ff2d2d]" />
          <StatCard label="Dispatched" value={incidents.filter(i=>i.status==="Dispatched").length} sub="Successfully dispatched" borderColorCls="border-[#2979ff]" textCls="text-[#2979ff]" />
          <StatCard label="Active Hospitals" value={resources.filter(r=>r.type==="Hospital").length} sub="TVM network" borderColorCls="border-[#00e676]" textCls="text-[#00e676]" />
          <StatCard label="Available Beds" value={resources.reduce((s, r)=>s+r.cap_avail, 0)} sub="All resources" borderColorCls="border-[#f5c518]" textCls="text-[#f5c518]" />
        </div>

        <div className="flex flex-wrap gap-2 mb-6 bg-[#06101c] p-2 rounded-xl border border-[#0d2535]">
          {TABS.map(t => (
            <button key={t.id} onClick={() => setTab(t.id)} className={`px-5 py-2.5 rounded-lg text-xs font-bold tracking-widest uppercase transition-all duration-300 ${tab === t.id ? 'bg-[#2979ff] text-white shadow-[0_0_15px_rgba(41,121,255,0.4)]' : 'text-[#607080] hover:bg-[#1e3050] hover:text-white'}`}>
              {t.label}
            </button>
          ))}
        </div>

        {tab === "map" && (
          <div className="glass-panel p-6">
            <h2 className="text-sm font-bold text-gray-400 tracking-widest uppercase mb-4 font-mono border-b border-[#1e3050] pb-2">Live Incident Map</h2>
            <LeafletMap incidents={incidents} resources={resources} agencies={agencies} />
          </div>
        )}

        {tab === "triage" && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div className="glass-panel p-6">
              <div className="flex justify-between items-center mb-4 border-b border-[#1e3050] pb-2">
                <h2 className="text-sm font-bold text-gray-400 tracking-widest uppercase font-mono">New SOS Triage</h2>
                <button onClick={handleGetLocation} className="text-[10px] bg-[#2979ff]/10 hover:bg-[#2979ff]/20 text-[#2979ff] border border-[#2979ff]/40 px-3 py-1.5 rounded flex items-center gap-2 transition-all font-bold uppercase tracking-wider shadow-[0_0_10px_rgba(41,121,255,0.2)]">📍 Auto-Detect Location</button>
              </div>
              <div className="grid grid-cols-2 gap-4 text-xs font-mono">
                <label className="space-y-1"><span className="text-gray-500 uppercase">Phone</span><input value={phone} onChange={e=>setPhone(e.target.value)} className="input-field" /></label>
                <label className="space-y-1"><span className="text-gray-500 uppercase">Victim Name</span><input value={victimName} onChange={e=>setVictimName(e.target.value)} className="input-field" placeholder="Optional" /></label>
                <label className="space-y-1"><span className="text-gray-500 uppercase">Latitude</span><input value={lat} onChange={e=>setLat(e.target.value)} className="input-field" /></label>
                <label className="space-y-1"><span className="text-gray-500 uppercase">Longitude</span><input value={lon} onChange={e=>setLon(e.target.value)} className="input-field" /></label>
                <label className="space-y-1"><span className="text-gray-500 uppercase">Severity</span>
                  <select value={severity} onChange={e=>setSeverity(e.target.value)} className="input-field text-white"><option>Critical</option><option>High</option><option>Medium</option><option>Low</option></select>
                </label>
                <label className="space-y-1"><span className="text-[#ff2d2d] uppercase">🔥 Fire Hazard</span><select value={fireHzd} onChange={e=>setFireHzd(e.target.value)} className="input-field"><option value={0}>No</option><option value={1}>Yes</option></select></label>
              </div>
              <button onClick={handleDispatch} className="relative w-full mt-6 py-4 px-6 font-bold tracking-[0.3em] text-xs uppercase text-white overflow-hidden rounded-xl bg-gradient-to-r from-[#ff2d2d]/20 to-[#ff8c00]/10 border border-[#ff2d2d]/40 shadow-[0_0_20px_rgba(255,45,45,0.15)] hover:from-[#ff2d2d]/40 hover:to-[#ff8c00]/30 hover:shadow-[0_0_30px_rgba(255,45,45,0.5)] hover:border-[#ff2d2d]/80 transition-all duration-500 ease-out group active:scale-[0.98]">
                <div className="absolute top-0 left-0 w-full h-[1px] bg-gradient-to-r from-transparent via-[#ff2d2d] to-transparent opacity-50 group-hover:opacity-100 transition-opacity"></div>
                <div className="absolute bottom-0 right-0 w-full h-[1px] bg-gradient-to-r from-transparent via-[#ff8c00] to-transparent opacity-50 group-hover:opacity-100 transition-opacity"></div>
                <span className="relative z-10 flex items-center justify-center gap-3 drop-shadow-[0_2px_10px_rgba(255,45,45,0.8)]">
                  <span className="text-xl group-hover:scale-125 transition-transform duration-300 drop-shadow-lg">🚨</span> 
                  EXECUTE MULTI-AGENT DISPATCH
                </span>
                <div className="absolute inset-0 w-full h-full bg-gradient-to-r from-transparent via-white/5 to-transparent -translate-x-[150%] skew-x-[-45deg] group-hover:translate-x-[150%] transition-transform duration-700 ease-in-out"></div>
              </button>
            </div>
            
            <div className="glass-panel p-6">
              <h2 className="text-sm font-bold text-gray-400 tracking-widest uppercase mb-4 font-mono border-b border-[#1e3050] pb-2">Recent Incidents</h2>
              <div className="overflow-x-auto">
                <table className="w-full text-left font-mono text-xs">
                  <thead className="text-gray-500 border-b border-[#1e3050]">
                    <tr><th className="pb-2">ID</th><th className="pb-2">Severity</th><th className="pb-2">Status</th></tr>
                  </thead>
                  <tbody>
                    {incidents.slice(0,10).map(inc => (
                      <tr key={inc.id} className="border-b border-[rgba(30,48,80,0.3)] hover:bg-[#1e3050]/20 transition-colors">
                        <td className="py-3 text-gray-400">#{inc.id}</td>
                        <td className="py-3"><span className={`px-2 py-0.5 rounded border text-[10px] uppercase tracking-wider ${SEVERITY_COLOR[inc.severity]}`}>{inc.severity}</span></td>
                        <td className="py-3 text-gray-300">{inc.status}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {tab === "audit" && (
          <div className="glass-panel p-6">
            <h2 className="text-sm font-bold text-gray-400 tracking-widest uppercase mb-4 font-mono border-b border-[#1e3050] pb-2">Transparency Ledger</h2>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs font-sans">
                <thead className="text-gray-500 border-b border-[#1e3050] font-mono uppercase tracking-wider text-[10px]">
                  <tr><th className="p-3 whitespace-nowrap">Incident</th><th className="p-3">Agent</th><th className="p-3">Decision</th><th className="p-3">Reasoning</th><th className="p-3 hidden md:table-cell">Citation</th></tr>
                </thead>
                <tbody className="divide-y divide-[rgba(30,48,80,0.3)]">
                  {audit.map(log => (
                    <tr key={log.id} className="hover:bg-white/5 transition duration-150">
                      <td className="p-3 font-mono text-[#2979ff] font-bold">#{log.incident_id}</td>
                      <td className="p-3 font-bold text-gray-300">{log.agent}</td>
                      <td className="p-3"><span className={`px-2 py-1 rounded text-[10px] font-bold border ${DECISION_COLOR[log.decision]}`}>{log.decision}</span></td>
                      <td className="p-3 text-gray-400 max-w-sm leading-relaxed">{log.reasoning}</td>
                      <td className="p-3 text-[#607080] hidden md:table-cell text-[10px] italic">📜 {log.citation || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {tab === "trace" && (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 h-[500px]">
             <div className="lg:col-span-2 glass-panel p-6 flex flex-col">
              <h2 className="text-sm font-bold text-gray-400 tracking-widest uppercase mb-4 font-mono border-b border-[#1e3050] pb-2">Agent Thought Stream</h2>
              <div className="flex items-center gap-4 mb-4">
                <span className="text-xs text-gray-500 font-mono">INCIDENT ID:</span>
                <input type="number" value={streamId} onChange={e => setStreamId(+e.target.value)} className="input-field w-24" />
              </div>
              <div className="flex-1 min-h-0">
                <ThoughtTrace incidentId={streamId} />
              </div>
             </div>
             
             <div className="glass-panel p-6 flex flex-col h-[500px]">
              <h2 className="text-sm font-bold text-gray-400 tracking-widest uppercase mb-4 font-mono border-b border-[#1e3050] pb-2">Dispatch Feed</h2>
              <div className="flex-1 overflow-y-auto space-y-3 pr-2 custom-scrollbar">
                {[
                  { agency: "General Hospital TVM", dist: 0.72, eta: 6.4, type: "🏥", color: "#00e676" },
                  { agency: "Fire HQ Chengalchoola", dist: 1.10, eta: 7.2, type: "🚒", color: "#2979ff" },
                  { agency: "Police Control Room", dist: 0.95, eta: 6.9, type: "🚔", color: "#2979ff" },
                ].map((d, i) => (
                  <div key={i} className="bg-[#06101c] border border-[#1e3050] rounded-lg p-3 flex items-center gap-3 hover:border-[#2979ff]/50 transition-colors cursor-pointer">
                    <div className="text-2xl">{d.type}</div>
                    <div className="flex-1 min-w-0">
                      <div className="text-gray-200 text-xs font-bold truncate">{d.agency}</div>
                      <div className="text-gray-500 text-[10px] font-mono">{d.dist} km radius</div>
                    </div>
                    <div className={`px-2 py-1 rounded text-[10px] font-bold border shadow-[0_0_10px_${d.color}33]`} style={{color: d.color, borderColor: `${d.color}66`, backgroundColor: `${d.color}11`}}>
                      {d.eta} min
                    </div>
                  </div>
                ))}
              </div>
             </div>
          </div>
        )}
        
        {tab === "resources" && (
          <div className="glass-panel p-6">
            <h2 className="text-sm font-bold text-gray-400 tracking-widest uppercase mb-4 font-mono border-b border-[#1e3050] pb-2">Resource Capacity Network</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
              {resources.map(r => (
                <div key={r.id} className="bg-[#06101c] border border-[#1e3050] rounded-xl p-4 shadow-lg hover:shadow-[0_0_15px_rgba(41,121,255,0.15)] transition-all">
                  <div className="flex justify-between items-start mb-2">
                    <div className="font-bold text-sm text-gray-200">{r.name}</div>
                    <div className={`text-[10px] px-2 py-0.5 rounded border uppercase font-bold tracking-widest ${r.status === "Active" ? "text-[#00e676] border-[#00e676]/40 bg-[#00e676]/10" : "text-[#ff2d2d] border-[#ff2d2d]/40 bg-[#ff2d2d]/10"}`}>
                      {r.status}
                    </div>
                  </div>
                  <div className="text-xs text-gray-500 font-mono mb-3">{r.type} · LAT {r.lat.toFixed(4)}</div>
                  <CapBar avail={r.cap_avail} total={r.cap_total} inclusive={r.inclusive} />
                </div>
              ))}
            </div>
          </div>
        )}
      </main>
    </div>
  );
}