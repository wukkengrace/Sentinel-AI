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
  FRAUD_ALERT: "text-[#ff2d2d] border-[#ff2d2d]/60 bg-[#ff2d2d]/10",
};

const FLOOD_COLORS = {
  1: "#2979ff", // Light Blue
  2: "#f5c518", // Yellow
  3: "#ff8c00", // Orange
  4: "#ff2d2d", // Red
  5: "#8b0000", // Dark Red
  0: "#00e676", // Green - No Flood
};

async function apiFetch(path, opts = {}) {
  try {
    const r = await fetch(API + path, { ...opts, headers: { "Content-Type": "application/json", ...opts.headers } });
    if (!r.ok) {
        let err;
        try { err = await r.json(); } catch { err = null; }
        return { error: true, status: r.status, data: err };
    }
    return { error: false, data: await r.json() };
  } catch (e) { return { error: true, message: e.message }; }
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
        {inclusive ? <span className="text-[#bf00ff]">♿ INCL</span> : null}
      </div>
      <div className="h-1.5 bg-[#1a2535] rounded-full overflow-hidden">
        <div className={`h-full ${color} transition-all duration-700`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

function LeafletMap({ incidents, resources, rescueUnits }) {
  const mapRef = useRef(null);
  const mapInstance = useRef(null);
  const markersRef = useRef([]);

  useEffect(() => {
    if (mapInstance.current || !mapRef.current) return;
    if (!window.L) return;

    const L = window.L;
    const map = L.map(mapRef.current, { center: [8.5150, 76.9300], zoom: 12 });
    mapInstance.current = map;

    L.tileLayer("https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png", {
      attribution: "© OpenStreetMap © CARTO", maxZoom: 18
    }).addTo(map);

  }, []);

  useEffect(() => {
      const map = mapInstance.current;
      if (!map || !window.L) return;
      
      markersRef.current.forEach(m => map.removeLayer(m));
      markersRef.current = [];

      const mkIcon = (color, symbol, pulse=false) => window.L.divIcon({
        className: "", iconSize: [28, 28], iconAnchor: [14, 14],
        html: `<div class="${pulse ? 'animate-pulse':''}" style="width:28px;height:28px;border-radius:50%;background:${color}22;
              border:1.5px solid ${color};display:flex;align-items:center;justify-content:center;
              font-size:14px;box-shadow:0 0 10px ${color}88 backdrop-filter:blur(4px);">${symbol}</div>`
      });

      const severityIcon = (inc) => {
        const c = inc.flood_level > 0 ? FLOOD_COLORS[inc.flood_level] : (inc.severity === 'Critical' ? '#ff2d2d' : inc.severity === 'High' ? '#ff8c00' : inc.severity === 'Medium' ? '#f5c518' : '#00e676');
        return window.L.divIcon({
          className: "", iconSize: [24, 24], iconAnchor: [12, 12],
          html: `<div class="${inc.priority === 'ULTRA_PRIORITY' ? 'animate-bounce' : inc.severity === 'Critical' ? 'animate-pulse' : ''}" style="width:20px;height:20px;border-radius:50%;background:${c};
                border:2px solid #fff;box-shadow:0 0 12px ${c};">&nbsp;</div>`
        });
      };

      incidents.forEach(inc => {
        if (!inc.lat || !inc.lon || inc.status === 'Resolved') return;
        const m = window.L.marker([inc.lat, inc.lon], { icon: severityIcon(inc) })
          .addTo(map)
          .bindPopup(`<b>INC #${inc.id}</b><br>${inc.victim_name || inc.phone}<br>Emergency: ${inc.emergency_type}<br>Severity: ${inc.severity}<br>Victims: ${inc.total_victims}`);
        markersRef.current.push(m);
      });

      resources.forEach(r => {
        if (!r.lat || !r.lon) return;
        const symbol = r.type === "Hospital" ? "🏥" : r.type === "Shelter" ? "⛺" : "🚒";
        const color = r.status === "Full" ? "#ff2d2d" : "#00e676";
        const m = window.L.marker([r.lat, r.lon], { icon: mkIcon(color, symbol) })
          .addTo(map)
          .bindPopup(`<b>${r.name}</b><br>Beds: ${r.cap_avail}/${r.cap_total}`);
        markersRef.current.push(m);
      });

      rescueUnits.forEach(u => {
        if (!u.base_lat || !u.base_lon) return;
        const symbol = u.unit_type.includes("Fire") ? "🚒" : u.unit_type.includes("Fishermen") ? "🚤" : u.unit_type.includes("Helicopter") ? "🚁" : "🛟";
        const color = u.status === "Deployed" ? "#ff8c00" : u.status === "Returning" ? "#f5c518" : "#2979ff";
        const m = window.L.marker([u.base_lat, u.base_lon], { icon: mkIcon(color, symbol, u.status !== 'Available') })
          .addTo(map).bindPopup(`<b>${u.name}</b><br>Status: ${u.status}`);
        markersRef.current.push(m);
      });
  }, [incidents, resources, rescueUnits]);

  return (
    <div className="relative">
      <div ref={mapRef} className="h-[420px] rounded-xl border border-[rgba(30,48,80,0.5)] shadow-[0_0_20px_rgba(41,121,255,0.1)] z-10" />
      <div className="absolute top-3 right-3 bg-[rgba(5,12,24,0.85)] backdrop-blur border border-[rgba(30,48,80,0.5)] rounded-lg p-2 z-[1000] text-[10px] space-y-1 text-gray-300 shadow-lg">
        <div className="text-[#ff2d2d] font-bold">● Incident</div>
        <div className="text-[#00e676]">🏥 Hospital / ⛺ Shelter</div>
        <div className="text-[#2979ff]">🚒 Rescue Unit (Avail)</div>
        <div className="text-[#ff8c00]">🚒 Rescue Unit (Deployed)</div>
      </div>
    </div>
  );
}

function ThoughtTrace({ incidentId, events, autoStart }) {
  const [lines, setLines] = useState([]);
  const [active, setActive] = useState(false);
  const termRef = useRef(null);
  const esRef = useRef(null);

  const startStream = useCallback(() => {
    if (!incidentId) return;
    if (esRef.current) { esRef.current.close(); }
    setLines([]);
    setActive(true);
    const es = new EventSource(`${API}/stream/${incidentId}`);
    esRef.current = es;
    es.onmessage = (e) => {
      const data = JSON.parse(e.data);
      setLines(prev => [...prev, data.message]);
      if (data.message === "[STREAM_END]") { es.close(); esRef.current = null; setActive(false); }
    };
    es.onerror = () => { es.close(); esRef.current = null; setActive(false); };
  }, [incidentId]);

  // Auto-start stream when incidentId changes and autoStart is requested
  useEffect(() => {
    if (autoStart && incidentId) {
      startStream();
    }
    return () => { if (esRef.current) { esRef.current.close(); esRef.current = null; } };
  }, [autoStart, incidentId]);

  useEffect(() => {
    if (termRef.current) termRef.current.scrollTop = termRef.current.scrollHeight;
  }, [lines, events]);

  const getLogColor = (l) => {
    if(l.startsWith("[Comm")) return "text-[#2979ff]";
    if(l.startsWith("[Stra")) return "text-[#bf00ff]";
    if(l.startsWith("[Loca")) return "text-[#00e676]";
    if(l.startsWith("[Oper")) return "text-[#f5c518]";
    if(l.startsWith("[Logi")) return "text-[#ff8c00]";
    if(l.startsWith("[Priority Engine]")) return "text-[#ff2d2d] font-bold";
    if(l.startsWith("[DONE]") || l.startsWith("[Rescue Complete]")) return "text-[#00e676] bg-[#00e676]/10 inline p-1 rounded font-bold";
    if(l.startsWith("[ERROR]") || l.startsWith("[WARNING]")) return "text-[#ff2d2d] bg-[#ff2d2d]/10 inline p-1 rounded font-bold";
    return "text-gray-400";
  };

  return (
    <div className="flex flex-col h-full">
      <div className="flex gap-3 mb-3">
        <button onClick={startStream} disabled={!incidentId} className="btn-success">
          ⚡ Live Stream #{incidentId || "?"}
        </button>
        {active && <span className="text-[#00e676] text-xs self-center font-bold animate-pulse tracking-widest uppercase">● Streaming Model Thoughts</span>}
      </div>
      <div ref={termRef} className="bg-[#020813] border border-[#0d2535] rounded-xl p-4 flex-1 min-h-[300px] overflow-y-auto font-mono text-xs shadow-inner relative space-y-4">
        <div>
            <div className="text-gray-500 uppercase mb-2 border-b border-[#1e3050] pb-1">AI Execution Trace</div>
            {lines.length === 0 ? <span className="text-gray-600 italic">» Awaiting multi-agent consensus...</span> : 
            lines.map((l, i) => (
                <div key={i} className={`mb-1.5 leading-relaxed tracking-wide ${getLogColor(l)}`}>
                <span className="text-gray-600 mr-2">{String(i + 1).padStart(2, "0")}</span>{l}
                </div>
            ))}
        </div>
        <div>
            <div className="text-gray-500 uppercase mb-2 border-b border-[#1e3050] pb-1 mt-4">System Event Log</div>
            {events.length === 0 ? <span className="text-gray-600 italic">» No events yet...</span> :
            events.map((e, i) => (
                <div key={i} className={`mb-1.5 leading-relaxed tracking-wide text-gray-300`}>
                 <span className="text-gray-500 mr-2">[{new Date(e.timestamp).toLocaleTimeString()}]</span>
                 <span className="text-[#ff8c00] mr-2">[{e.event_type}]</span>
                 {e.message}
                </div>
            ))}
        </div>
      </div>
    </div>
  );
}

export default function SentinelDashboard() {
  const [tab, setTab] = useState("map");
  const [incidents, setIncidents] = useState([]);
  const [resources, setResources] = useState([]);
  const [audit, setAudit] = useState([]);
  const [rescueUnits, setRescueUnits] = useState([]);
  const [victims, setVictims] = useState([]);
  const [events, setEvents] = useState([]);
  
  const [streamId, setStreamId] = useState("");
  const [online, setOnline] = useState(false);

  // Form State
  const [phone, setPhone] = useState("919876543210");
  const [victimName, setVictimName] = useState("");
  const [aadhar, setAadhar] = useState("");
  const [maleCnt, setMaleCnt] = useState(0);
  const [femaleCnt, setFemaleCnt] = useState(0);
  const [childCnt, setChildCnt] = useState(0);
  const [severity, setSeverity] = useState("Critical");
  const [medCnt, setMedCnt] = useState(1);
  const [emergencyType, setEmergencyType] = useState("Flood");
  const [floodLevel, setFloodLevel] = useState(2);
  const [isLgbtq, setIsLgbtq] = useState(0);
  const [isDisability, setIsDisability] = useState(0);
  const [extraComments, setExtraComments] = useState("");
  const [lat, setLat] = useState("8.5000");
  const [lon, setLon] = useState("76.9500");

  const totalVictims = parseInt(maleCnt) + parseInt(femaleCnt) + parseInt(childCnt);

  const fetchEvents = async (id) => {
    if (!id) return;
    const { error, data } = await apiFetch(`/dispatch-events/${id}`);
    if (!error) setEvents(data);
  };

  useEffect(() => {
      if(tab === "trace" && streamId) {
          fetchEvents(streamId);
          const i = setInterval(() => fetchEvents(streamId), 3000);
          return () => clearInterval(i);
      }
  }, [tab, streamId]);

  const [autoStartStream, setAutoStartStream] = useState(false);

  const handleDispatch = async () => {
    if (totalVictims === 0) {
        alert("Total victims must be greater than 0");
        return;
    }
    const payload = {
      phone, victim_name: victimName, aadhar_id: aadhar,
      male_cnt: parseInt(maleCnt), female_cnt: parseInt(femaleCnt), child_cnt: parseInt(childCnt),
      lat: parseFloat(lat), lon: parseFloat(lon),
      severity, emergency_type: emergencyType, flood_level: parseInt(floodLevel),
      medical_cnt: parseInt(medCnt), shelter_cnt: totalVictims - parseInt(medCnt),
      is_lgbtq: parseInt(isLgbtq), is_disability: parseInt(isDisability),
      extra_comments: extraComments
    };
    
    const res = await apiFetch("/incident", { method: "POST", body: JSON.stringify(payload) });
    
    if (res.error) {
      if (res.data?.detail?.status === "FRAUD_ALERT") {
          alert(`🚫 FRAUD ALERT: ${res.data.detail.message}`);
      } else {
          alert(`Error: ${JSON.stringify(res.data?.detail || res.message || "Unknown error")}`);
      }
    } else {
      const newId = res.data.incident_id;
      setStreamId(newId);
      setAutoStartStream(true);
      setTab("trace");
      // Rapid-poll for 10 seconds so the new incident appears immediately
      let count = 0;
      const rapidPoll = setInterval(() => {
        refreshData();
        count++;
        if (count >= 20) clearInterval(rapidPoll);
      }, 500);
    }
  };

  const handleGetLocation = () => {
    if ("geolocation" in navigator) {
      navigator.geolocation.getCurrentPosition(
        (position) => { setLat(position.coords.latitude.toFixed(6)); setLon(position.coords.longitude.toFixed(6)); },
        (error) => { console.error(error); alert("Could not detect location."); }
      );
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

  const refreshData = async () => {
    const h = await apiFetch("/health");
    if (!h.error) {
      setOnline(true);
      const [inc, res, aud, un, vic] = await Promise.all([
          apiFetch("/incidents"), apiFetch("/resources"), apiFetch("/audit"),
          apiFetch("/rescue-units"), apiFetch("/victims")
      ]);
      if (!inc.error) setIncidents(inc.data);
      if (!res.error) setResources(res.data);
      if (!aud.error) setAudit(aud.data);
      if (!un.error) setRescueUnits(un.data);
      if (!vic.error) setVictims(vic.data);
    } else {
      setOnline(false);
    }
  };

  useEffect(() => {
    refreshData();
    const iv = setInterval(refreshData, 5000);
    return () => clearInterval(iv);
  }, []);

  const TABS = [
    { id: "map", label: "🗺 Live Map" },
    { id: "triage", label: "🚨 SOS Triage" },
    { id: "fleet", label: "🚒 Rescue Fleet" },
    { id: "victims", label: "👥 Victim Tracker" },
    { id: "resources", label: "🏥 Resources" },
    { id: "audit", label: "📋 AI Ledger" },
    { id: "trace", label: "🧠 Incident Trace" },
  ];

  return (
    <div className="min-h-screen relative text-gray-200">
      <div className="fixed inset-0 pointer-events-none z-[9999] scanline" />
      
      {/* Header */}
      <header className="bg-[rgba(2,12,24,0.95)] border-b border-[#0d2535] py-4 px-6 flex items-center gap-4 sticky top-0 z-[5000] backdrop-blur-lg">
        <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-[#ff2d2d] to-[#2979ff] flex items-center justify-center text-xl shadow-[0_0_15px_rgba(41,121,255,0.5)] border border-white/20">⚡</div>
        <div>
          <h1 className="text-xl font-bold tracking-[0.2em] text-[#e8f0f8] drop-shadow-md">SENTINEL-AI 2.0</h1>
          <div className="text-[10px] text-[#607080] tracking-[0.3em] font-mono mt-0.5">INCORRUPTIBLE TVM DISPATCH & FLEET MANAGER</div>
        </div>
        <div className="ml-auto flex items-center gap-6">
          <div className={`text-[10px] uppercase font-bold tracking-widest flex items-center gap-2 ${online ? "text-[#00e676]" : "text-[#ff2d2d]"}`}>
            <span className={`w-2 h-2 rounded-full ${online ? "bg-[#00e676] animate-pulse" : "bg-[#ff2d2d]"}`}></span>
            {online ? "BACKEND LIVE" : "DISCONNECTED"}
          </div>
        </div>
      </header>

      <main className="p-6 max-w-[1600px] mx-auto">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
          <StatCard label="Active Incidents" value={incidents.filter(i=>i.status!=="Resolved").length} borderColorCls="border-[#ff2d2d]" textCls="text-[#ff2d2d]" />
          <StatCard label="Fleet Deployment" value={`${rescueUnits.filter(u=>u.status==='Deployed').length}/${rescueUnits.length}`} sub="Units active in field" borderColorCls="border-[#ff8c00]" textCls="text-[#ff8c00]" />
          <StatCard label="Victims Managed" value={victims.length} sub="Evacuated / Placed" borderColorCls="border-[#2979ff]" textCls="text-[#2979ff]" />
          <StatCard label="Available Beds" value={resources.reduce((s, r)=>s+r.cap_avail, 0)} sub="All resources" borderColorCls="border-[#00e676]" textCls="text-[#00e676]" />
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
            <LeafletMap incidents={incidents} resources={resources} rescueUnits={rescueUnits} />
          </div>
        )}

        {tab === "triage" && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div className="glass-panel p-6">
              <div className="flex justify-between items-center mb-4 border-b border-[#1e3050] pb-2">
                <h2 className="text-sm font-bold text-gray-400 tracking-widest uppercase font-mono">New SOS Triage</h2>
                <div className="flex gap-2">
                 <button onClick={handleGetLocation} className="text-[10px] bg-[#2979ff]/10 hover:bg-[#2979ff]/20 text-[#2979ff] border border-[#2979ff]/40 px-3 py-1.5 rounded flex items-center gap-2 transition-all font-bold uppercase tracking-wider shadow-[0_0_10px_rgba(41,121,255,0.2)]">📍 Auto Location</button>
                 {totalVictims > 20 && <span className="bg-[#ff2d2d] text-white text-[10px] px-3 py-1.5 rounded font-bold uppercase tracking-wider animate-pulse flex items-center">🚨 ULTRA PRIORITY</span>}
                </div>
              </div>
              
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs font-mono">
                <div className="col-span-full border-b border-[#1e3050] pb-2 mb-2 text-[#2979ff] font-bold">1. Caller Identity</div>
                <label className="space-y-1"><span className="text-gray-500 uppercase">Phone</span><input value={phone} onChange={e=>setPhone(e.target.value)} className="input-field" /></label>
                <label className="space-y-1"><span className="text-gray-500 uppercase">Victim Name</span><input value={victimName} onChange={e=>setVictimName(e.target.value)} className="input-field" placeholder="Optional" /></label>
                <label className="space-y-1 md:col-span-2"><span className="text-gray-500 uppercase">Aadhar ID (Fraud Check)</span><input value={aadhar} onChange={e=>setAadhar(e.target.value)} className="input-field" placeholder="1234-5678-9012" /></label>
                
                <div className="col-span-full border-b border-[#1e3050] pb-2 mt-2 mb-2 text-[#2979ff] font-bold">2. Demographics & Context</div>
                <label className="space-y-1"><span className="text-gray-500 uppercase">Male Count</span><input type="number" min="0" value={maleCnt} onChange={e=>setMaleCnt(e.target.value)} className="input-field" /></label>
                <label className="space-y-1"><span className="text-gray-500 uppercase">Female Count</span><input type="number" min="0" value={femaleCnt} onChange={e=>setFemaleCnt(e.target.value)} className="input-field" /></label>
                <label className="space-y-1"><span className="text-gray-500 uppercase">Child Count</span><input type="number" min="0" value={childCnt} onChange={e=>setChildCnt(e.target.value)} className="input-field" /></label>
                <div className="flex items-center gap-4">
                  <label className="flex items-center gap-2 cursor-pointer"><input type="checkbox" checked={!!isLgbtq} onChange={e=>setIsLgbtq(e.target.checked?1:0)} className="rounded bg-[#1a2535] border-[#2979ff] text-[#2979ff] focus:ring-[#2979ff]" /> <span className="text-gray-400 uppercase">LGBTQIA+ Shelter Need</span></label>
                </div>
                 <div className="flex items-center gap-4">
                  <label className="flex items-center gap-2 cursor-pointer"><input type="checkbox" checked={!!isDisability} onChange={e=>setIsDisability(e.target.checked?1:0)} className="rounded bg-[#1a2535] border-[#2979ff] text-[#2979ff] focus:ring-[#2979ff]" /> <span className="text-gray-400 uppercase">Disability Access Req.</span></label>
                </div>

                <div className="col-span-full border-b border-[#1e3050] pb-2 mt-2 mb-2 text-[#2979ff] font-bold">3. Emergency Assessment</div>
                <label className="space-y-1"><span className="text-[#ff2d2d] uppercase">Severity</span>
                  <select value={severity} onChange={e=>setSeverity(e.target.value)} className="input-field text-white"><option>Critical</option><option>High</option><option>Medium</option><option>Low</option></select>
                </label>
                <label className="space-y-1"><span className="text-gray-500 uppercase">Requires Med Evac</span><input type="number" min="0" max={totalVictims} value={medCnt} onChange={e=>setMedCnt(e.target.value)} className="input-field" /></label>
                
                <label className="space-y-1"><span className="text-gray-500 uppercase">Emergency Type</span>
                  <select value={emergencyType} onChange={e=>setEmergencyType(e.target.value)} className="input-field text-white">
                      <option>Flood</option><option>Fire</option><option>Electrical</option><option>Sewage</option><option>Road</option><option>Tree</option><option>Other</option>
                  </select>
                </label>
                {emergencyType === "Flood" && (
                    <label className="space-y-1"><span className="text-[#2979ff] uppercase font-bold">Flood Level (1-5)</span>
                       <div className="flex items-center gap-2">
                        <input type="range" min="1" max="5" value={floodLevel} onChange={e=>setFloodLevel(e.target.value)} className="w-full accent-[#2979ff]" />
                        <span className="text-lg font-bold w-6 text-center text-[#2979ff]">{floodLevel}</span>
                       </div>
                       <div className="text-[10px] text-gray-500">
                         {floodLevel==1 && "1: Water < 3ft (Fire Dinghy)"}
                         {floodLevel==2 && "2: Rapid Inundation (Fishermen)"}
                         {floodLevel==3 && "3: Deep Water (NDRF Power Boat)"}
                         {floodLevel==4 && "4: Total Isolation (Air Rescue)"}
                         {floodLevel==5 && "5: Collapse/Washout (Army/Navy)"}
                       </div>
                    </label>
                )}

                <div className="col-span-full border-b border-[#1e3050] pb-2 mt-2 mb-2 text-[#2979ff] font-bold">4. Location & Security</div>
                <label className="space-y-1 md:col-span-2"><span className="text-[#f5c518] uppercase">Extra Comments (VIP Filter active)</span><input value={extraComments} onChange={e=>setExtraComments(e.target.value)} className="input-field" placeholder="Any mentions of VIPs will flag the system..." /></label>
                <label className="space-y-1"><span className="text-gray-500 uppercase">Latitude</span><input value={lat} onChange={e=>setLat(e.target.value)} className="input-field" /></label>
                <label className="space-y-1"><span className="text-gray-500 uppercase">Longitude</span><input value={lon} onChange={e=>setLon(e.target.value)} className="input-field" /></label>
              </div>

              <button onClick={handleDispatch} className="relative w-full mt-6 py-4 px-6 font-bold tracking-[0.3em] text-xs uppercase text-white overflow-hidden rounded-xl bg-gradient-to-r from-[#ff2d2d]/20 to-[#ff8c00]/10 border border-[#ff2d2d]/40 shadow-[0_0_20px_rgba(255,45,45,0.15)] hover:from-[#ff2d2d]/40 hover:to-[#ff8c00]/30 hover:shadow-[0_0_30px_rgba(255,45,45,0.5)] hover:border-[#ff2d2d]/80 transition-all duration-500 ease-out group active:scale-[0.98]">
                <span className="relative z-10 flex items-center justify-center gap-3 drop-shadow-[0_2px_10px_rgba(255,45,45,0.8)]">
                  <span className="text-xl group-hover:scale-125 transition-transform duration-300 drop-shadow-lg">🚨</span> 
                  EXECUTE MULTI-AGENT DISPATCH
                </span>
              </button>
            </div>
            
            <div className="glass-panel p-6">
              <h2 className="text-sm font-bold text-gray-400 tracking-widest uppercase mb-4 font-mono border-b border-[#1e3050] pb-2">Recent Incidents</h2>
              <div className="overflow-x-auto">
                <table className="w-full text-left font-mono text-xs">
                  <thead className="text-gray-500 border-b border-[#1e3050]">
                    <tr><th className="pb-2">ID</th><th className="pb-2">Priority</th><th className="pb-2">Severity</th><th className="pb-2">Status</th></tr>
                  </thead>
                  <tbody>
                    {incidents.slice(0,12).map(inc => (
                      <tr key={inc.id} className="border-b border-[rgba(30,48,80,0.3)] hover:bg-[#1e3050]/20 transition-colors cursor-pointer" onClick={() => {setStreamId(inc.id); setTab("trace");}}>
                        <td className="py-2 text-gray-400">#{inc.id}</td>
                        <td className="py-2"><span className={`px-2 py-0.5 rounded border text-[9px] uppercase tracking-wider ${inc.priority==='ULTRA_PRIORITY'?'text-white bg-[#ff2d2d] border-[#ff2d2d] animate-pulse':'text-gray-400 border-gray-600'}`}>{inc.priority==='ULTRA_PRIORITY'?'ULTRA':'STD'}</span></td>
                        <td className="py-2"><span className={`px-2 py-0.5 rounded border text-[9px] uppercase tracking-wider ${SEVERITY_COLOR[inc.severity]}`}>{inc.severity}</span></td>
                        <td className="py-2 text-gray-300">{inc.status}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {tab === "fleet" && (
          <div className="glass-panel p-6">
            <h2 className="text-sm font-bold text-gray-400 tracking-widest uppercase mb-4 font-mono border-b border-[#1e3050] pb-2">Live Rescue Fleet Status</h2>
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
               {["Fire_Rescue", "Fishermen", "NDRF", "IAF_Navy", "Army"].map(type => (
                 <div key={type} className="bg-[#06101c] border border-[#1e3050] rounded-xl p-4">
                    <h3 className="text-[#2979ff] font-bold uppercase tracking-widest text-xs mb-3 border-b border-[#1e3050]/50 pb-2">{type.replace('_',' ')}</h3>
                    <div className="space-y-2">
                        {rescueUnits.filter(u=>u.unit_type===type).map(u => (
                            <div key={u.id} className="flex items-center justify-between p-2 rounded bg-[#1a2535]/50 border border-transparent hover:border-[#1e3050] transition-colors">
                                <div>
                                    <div className="text-sm text-gray-200 font-bold">{u.name} <span className="text-[10px] text-gray-500 font-mono font-normal ml-2">({u.boat_type})</span></div>
                                    <div className="text-[10px] text-gray-400 font-mono mt-0.5">Sorties: {u.sorties_completed} | Cap: {u.victim_capacity} victims</div>
                                </div>
                                <div className="text-right">
                                    <div className={`text-[10px] uppercase font-bold tracking-widest ${u.status==='Available'?'text-[#00e676]':u.status==='Deployed'?'text-[#ff8c00]':'text-[#f5c518]'}`}>
                                        {u.status}
                                    </div>
                                    {u.current_incident_id && <div className="text-[10px] text-gray-500 font-mono mt-0.5">INC #{u.current_incident_id}</div>}
                                </div>
                            </div>
                        ))}
                    </div>
                 </div>
               ))}
            </div>
          </div>
        )}
        
        {tab === "victims" && (
          <div className="glass-panel p-6">
            <h2 className="text-sm font-bold text-gray-400 tracking-widest uppercase mb-4 font-mono border-b border-[#1e3050] pb-2">Victim Manifest & Placement</h2>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs font-sans">
                <thead className="text-gray-500 border-b border-[#1e3050] font-mono uppercase tracking-wider text-[10px]">
                  <tr>
                      <th className="p-3">Incident</th>
                      <th className="p-3">Victim Label</th>
                      <th className="p-3">Gender</th>
                      <th className="p-3">Severity</th>
                      <th className="p-3">Needs</th>
                      <th className="p-3">Status</th>
                      <th className="p-3">Placement</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[rgba(30,48,80,0.3)]">
                  {victims.slice(0, 50).map(v => (
                    <tr key={v.id} className="hover:bg-[#1e3050]/20 transition-colors">
                      <td className="p-3 text-[#2979ff] font-mono font-bold">#{v.incident_id}</td>
                      <td className="p-3 text-gray-300">{v.name}</td>
                      <td className="p-3 text-gray-400">{v.gender}</td>
                      <td className="p-3"><span className={`px-2 py-0.5 rounded text-[9px] uppercase tracking-wider border ${SEVERITY_COLOR[v.severity]}`}>{v.severity}</span></td>
                      <td className="p-3 text-gray-400 text-[10px]">
                          {v.needs_medical ? <span className="mr-2 border border-[#ff2d2d] text-[#ff2d2d] px-1 rounded">Medical</span> : ''}
                          {v.is_lgbtq ? <span className="mr-2 border border-[#bf00ff] text-[#bf00ff] px-1 rounded">LGBTQ+</span> : ''}
                          {v.is_disability ? <span className="border border-[#f5c518] text-[#f5c518] px-1 rounded">Disability</span> : ''}
                      </td>
                      <td className="p-3">
                          <span className={`${v.status==='Reported'?'text-[#ff2d2d]':v.status==='Evacuated'?'text-[#ff8c00]':'text-[#00e676]'} font-bold text-[10px] uppercase`}>{v.status}</span>
                      </td>
                      <td className="p-3 text-[#00e676] font-mono">
                          {v.placed_at_name ? <>{v.placed_at_type==='Hospital'?'🏥':'⛺'} {v.placed_at_name}</> : <span className="text-gray-600">—</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
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
                    <tr key={log.id} className="hover:bg-[#1e3050]/20 transition duration-150">
                      <td className="p-3 font-mono text-[#2979ff] font-bold cursor-pointer hover:underline" onClick={() => {setStreamId(log.incident_id); setTab("trace");}}>#{log.incident_id}</td>
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
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 h-[600px]">
             <div className="lg:col-span-3 glass-panel p-6 flex flex-col h-full">
              <div className="flex items-center justify-between mb-4 border-b border-[#1e3050] pb-2">
                 <h2 className="text-sm font-bold text-gray-400 tracking-widest uppercase font-mono">Agent Thought Stream & System Timeline</h2>
                 <div className="flex items-center gap-4">
                   <span className="text-xs text-gray-500 font-mono">INCIDENT ID:</span>
                   <input type="number" value={streamId} onChange={e => setStreamId(e.target.value)} className="input-field w-24 text-center" placeholder="ID" />
                 </div>
              </div>
              <div className="flex-1 min-h-0">
                <ThoughtTrace incidentId={streamId} events={events} autoStart={autoStartStream} />
              </div>
             </div>
          </div>
        )}
        
        {tab === "resources" && (
          <div className="glass-panel p-6">
            <h2 className="text-sm font-bold text-gray-400 tracking-widest uppercase mb-4 font-mono border-b border-[#1e3050] pb-2">Resource Capacity Network</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
              {resources.map(r => (
                <div key={r.id} className="bg-[#06101c] border border-[#1e3050] rounded-xl p-4 shadow-lg hover:border-[#2979ff]/40 transition-all">
                  <div className="flex justify-between items-start mb-2">
                     <div>
                        <div className="font-bold text-xs text-gray-200">{r.name}</div>
                        <div className="text-[10px] text-gray-500 font-mono mt-1">{r.type} {r.type==='Shelter' ? `[${r.shelter_type}]` : ''}</div>
                     </div>
                    <div className={`text-[9px] px-2 py-0.5 rounded border uppercase font-bold tracking-widest flex-shrink-0 ${r.status === "Active" ? "text-[#00e676] border-[#00e676]/40 bg-[#00e676]/10" : "text-[#ff2d2d] border-[#ff2d2d]/40 bg-[#ff2d2d]/10"}`}>
                      {r.status}
                    </div>
                  </div>
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