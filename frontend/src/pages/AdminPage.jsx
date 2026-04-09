import { useState, useEffect, useRef, useCallback } from "react";
import { apiFetch, maskAadhaar, SEVERITY_COLOR, DECISION_COLOR, FLOOD_LABELS, API } from "../api";

const FLOOD_COLORS = {
  1: "#2979ff", 2: "#f5c518", 3: "#ff8c00", 4: "#ff2d2d", 5: "#8b0000", 0: "#00e676",
};

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

    incidents.forEach(inc => {
      if (!inc.lat || !inc.lon || inc.status === 'Resolved') return;
      const isPaused = inc.status === 'PAUSED_BY_OVERRIDE';
      const c = inc.flood_level > 0 ? FLOOD_COLORS[inc.flood_level] : (inc.severity === 'Critical' ? '#ff2d2d' : inc.severity === 'High' ? '#ff8c00' : inc.severity === 'Medium' ? '#f5c518' : '#00e676');
      const markerColor = isPaused ? '#ff8c00' : c;
      const markerBorder = isPaused ? '#6b7280' : '#fff';
      const animClass = isPaused ? 'animate-pulse'
        : inc.priority === 'ULTRA_PRIORITY' ? 'animate-bounce'
        : inc.severity === 'Critical' ? 'animate-pulse' : '';
      const icon = window.L.divIcon({
        className: "", iconSize: [24, 24], iconAnchor: [12, 12],
        html: `<div class="${animClass}" style="width:20px;height:20px;border-radius:50%;background:${markerColor};
              border:2px solid ${markerBorder};box-shadow:0 0 12px ${markerColor};">&nbsp;</div>`
      });
      const m = window.L.marker([inc.lat, inc.lon], { icon })
        .addTo(map)
        .bindPopup(`<b>INC #${inc.id}</b>${isPaused ? ' ⏸ <b style="color:#ff8c00">PAUSED</b>' : ''}<br>${inc.victim_name || inc.phone}<br>Emergency: ${inc.emergency_type}<br>Severity: ${inc.severity}<br>Victims: ${inc.total_victims}<br>Status: ${inc.status}`);
      markersRef.current.push(m);
    });

    resources.forEach(r => {
      if (!r.lat || !r.lon) return;
      const symbol = r.type === "Hospital" ? "🏥" : r.type === "Shelter" ? "⛺" : "🚒";
      const color = r.status === "Full" ? "#ff2d2d" : "#00e676";
      const m = window.L.marker([r.lat, r.lon], { icon: mkIcon(color, symbol) })
        .addTo(map).bindPopup(`<b>${r.name}</b><br>Beds: ${r.cap_avail}/${r.cap_total}`);
      markersRef.current.push(m);
    });

    rescueUnits.forEach(u => {
      if (!u.base_lat || !u.base_lon) return;
      const symbol = u.unit_type.includes("Fire") ? "🚒" : u.unit_type.includes("Fishermen") ? "🚤" : "🛟";
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
        <div className="text-[#ff8c00]">⏸ Paused (Override)</div>
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

  useEffect(() => {
    if (autoStart && incidentId) startStream();
    return () => { if (esRef.current) { esRef.current.close(); esRef.current = null; } };
  }, [autoStart, incidentId]);

  useEffect(() => {
    if (termRef.current) termRef.current.scrollTop = termRef.current.scrollHeight;
  }, [lines, events]);

  const getLogColor = (l) => {
    if(l.startsWith("[Comm")) return "text-[#2979ff]";
    if(l.startsWith("[Stra")) return "text-[#bf00ff]";
    if(l.startsWith("[Loca") || l.startsWith("[Liaison]")) return "text-[#00e676]";
    if(l.startsWith("[Oper")) return "text-[#f5c518]";
    if(l.startsWith("[Priority Engine]")) return "text-[#ff2d2d] font-bold";
    if(l.startsWith("[Fleet Gate]")) return "text-[#ff8c00] font-bold";
    if(l.startsWith("[Override]")) return "text-[#ff8c00] bg-[#ff8c00]/10 inline p-1 rounded font-bold";
    if(l.includes("[OVERRIDE_PAUSE]")) return "text-[#ff8c00] bg-[#ff8c00]/10 inline p-1 rounded font-bold";
    if(l.includes("[OVERRIDE_RESUME]")) return "text-[#00e676] bg-[#00e676]/10 inline p-1 rounded font-bold";
    if(l.startsWith("[Admission Paused]")) return "text-[#ff8c00] bg-[#ff8c00]/10 inline p-1 rounded font-bold";
    if(l.startsWith("[Admission]")) return "text-[#bf00ff]";
    if(l.startsWith("[Shelter Fallback]")) return "text-[#f5c518] bg-[#f5c518]/10 inline p-1 rounded font-bold";
    if(l.startsWith("[DONE]") || l.startsWith("[Rescue Complete]") || l.startsWith("[Admission Complete]")) return "text-[#00e676] bg-[#00e676]/10 inline p-1 rounded font-bold";
    if(l.startsWith("[ERROR]") || l.startsWith("[WARNING]") || l.startsWith("[CRITICAL]")) return "text-[#ff2d2d] bg-[#ff2d2d]/10 inline p-1 rounded font-bold";
    if(l.startsWith("[Audit]")) return "text-[#607080] italic";
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
            <div key={i} className="mb-1.5 leading-relaxed tracking-wide text-gray-300">
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

// ── Notification Toast ────────────────────────────────────────────────────────
function NotificationToast({ notification, onDismiss }) {
  if (!notification) return null;
  return (
    <div className="notification-toast">
      <div className="flex items-start gap-3">
        <div className="text-2xl animate-pulse">🚨</div>
        <div className="flex-1">
          <div className="text-[10px] text-[#ff2d2d] uppercase tracking-widest font-bold mb-2">NEW SOS INCIDENT</div>
          <div className="text-sm text-gray-200 space-y-1">
            <div>Victims needing Shelter: <span className="text-[#2979ff] font-bold">{notification.shelter_needed}</span></div>
            <div>Victims requiring Medical Attention: <span className="text-[#ff2d2d] font-bold">{notification.medical_needed}</span></div>
          </div>
          <div className="text-[10px] text-gray-500 mt-2 font-mono">
            Incident #{notification.latest_incident_id} • {notification.latest_timestamp}
          </div>
        </div>
        <button onClick={onDismiss} className="text-gray-500 hover:text-white text-lg transition-colors">×</button>
      </div>
    </div>
  );
}

export default function AdminPage() {
  const [tab, setTab] = useState("map");
  const [incidents, setIncidents] = useState([]);
  const [resources, setResources] = useState([]);
  const [audit, setAudit] = useState([]);
  const [rescueUnits, setRescueUnits] = useState([]);
  const [victims, setVictims] = useState([]);
  const [events, setEvents] = useState([]);

  const [streamId, setStreamId] = useState("");
  const [online, setOnline] = useState(false);
  const [autoStartStream, setAutoStartStream] = useState(false);

  // Notification state
  const [notification, setNotification] = useState(null);
  const [lastSeenIncidentId, setLastSeenIncidentId] = useState(null);

  // Expanded audit rows (for model transparency)
  const [expandedAudit, setExpandedAudit] = useState(new Set());

  const fetchEvents = async (id) => {
    if (!id) return;
    const { error, data } = await apiFetch(`/dispatch-events/${id}`);
    if (!error) setEvents(data);
  };

  useEffect(() => {
    if (tab === "trace" && streamId) {
      fetchEvents(streamId);
      const i = setInterval(() => fetchEvents(streamId), 3000);
      return () => clearInterval(i);
    }
  }, [tab, streamId]);

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

  // Poll for notifications
  useEffect(() => {
    const checkNotifications = async () => {
      const { error, data } = await apiFetch("/notifications/latest");
      if (!error && data.latest_incident_id && data.latest_incident_id !== lastSeenIncidentId) {
        setNotification(data);
        setLastSeenIncidentId(data.latest_incident_id);
      }
    };
    checkNotifications();
    const iv = setInterval(checkNotifications, 3000);
    return () => clearInterval(iv);
  }, [lastSeenIncidentId]);

  useEffect(() => {
    if (!document.getElementById("leaflet-css")) {
      const link = document.createElement("link"); link.id = "leaflet-css"; link.rel = "stylesheet"; link.href = "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css"; document.head.appendChild(link);
    }
    if (!window.L) {
      const s = document.createElement("script"); s.src = "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js"; document.head.appendChild(s);
    }
  }, []);

  useEffect(() => {
    refreshData();
    const iv = setInterval(refreshData, 5000);
    return () => clearInterval(iv);
  }, []);

  const TABS = [
    { id: "map", label: "🗺 Live Map" },
    { id: "fleet", label: "🚒 Rescue Fleet" },
    { id: "victims", label: "👥 Victim Tracker" },
    { id: "resources", label: "🏥 Resources" },
    { id: "audit", label: "📋 AI Ledger" },
    { id: "trace", label: "🧠 Incident Trace" },
  ];

  const toggleAuditExpand = (id) => {
    setExpandedAudit(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  return (
    <div className="min-h-screen relative text-gray-200">
      <div className="fixed inset-0 pointer-events-none z-[9999] scanline" />

      {/* Notification Toast */}
      <NotificationToast
        notification={notification}
        onDismiss={() => setNotification(null)}
      />

      {/* Header */}
      <header className="bg-[rgba(2,12,24,0.95)] border-b border-[#0d2535] py-4 px-6 flex items-center gap-4 sticky top-0 z-[5000] backdrop-blur-lg">
        <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-[#ff2d2d] to-[#2979ff] flex items-center justify-center text-xl shadow-[0_0_15px_rgba(41,121,255,0.5)] border border-white/20">⚡</div>
        <div>
          <h1 className="text-xl font-bold tracking-[0.2em] text-[#e8f0f8] drop-shadow-md">SENTINEL-AI 2.0</h1>
          <div className="text-[10px] text-[#607080] tracking-[0.3em] font-mono mt-0.5">EMERGENCY SUPPORT CENTER — ADMIN DASHBOARD</div>
        </div>
        <div className="ml-auto flex items-center gap-6">
          <a href="/sos" className="text-[10px] text-[#607080] hover:text-[#ff2d2d] uppercase tracking-widest transition-colors font-bold">
            🆘 SOS Page
          </a>
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
            <h2 className="text-sm font-bold text-gray-400 tracking-widest uppercase mb-4 font-mono border-b border-[#1e3050] pb-2">Victim Manifest — Individual Tracking</h2>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs font-sans">
                <thead className="text-gray-500 border-b border-[#1e3050] font-mono uppercase tracking-wider text-[10px]">
                  <tr>
                    <th className="p-3">Incident</th>
                    <th className="p-3">Victim Name</th>
                    <th className="p-3">Aadhaar ID</th>
                    <th className="p-3">Gender</th>
                    <th className="p-3">Severity</th>
                    <th className="p-3">Needs</th>
                    <th className="p-3">Status</th>
                    <th className="p-3">Allotted Destination</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[rgba(30,48,80,0.3)]">
                  {victims.slice(0, 50).map(v => (
                    <tr key={v.id} className="hover:bg-[#1e3050]/20 transition-colors">
                      <td className="p-3 text-[#2979ff] font-mono font-bold">#{v.incident_id}</td>
                      <td className="p-3 text-gray-300">{v.name}</td>
                      <td className="p-3 text-gray-400 font-mono text-[10px]">{v.aadhar_id_masked || maskAadhaar(v.aadhar_id)}</td>
                      <td className="p-3 text-gray-400">{v.gender}</td>
                      <td className="p-3"><span className={`px-2 py-0.5 rounded text-[9px] uppercase tracking-wider border ${SEVERITY_COLOR[v.severity]}`}>{v.severity}</span></td>
                      <td className="p-3 text-gray-400 text-[10px]">
                        {v.needs_medical ? <span className="mr-2 border border-[#ff2d2d] text-[#ff2d2d] px-1 rounded">Medical</span> : ''}
                        {v.is_lgbtq ? <span className="mr-2 border border-[#bf00ff] text-[#bf00ff] px-1 rounded">LGBTQ+</span> : ''}
                        {v.is_disability ? <span className="border border-[#f5c518] text-[#f5c518] px-1 rounded">Disability</span> : ''}
                      </td>
                      <td className="p-3">
                        <span className={`font-bold text-[10px] uppercase ${
                          v.status==='Reported' ? 'text-[#ff2d2d]' :
                          v.status==='In_Transit' ? 'text-[#f5c518] animate-pulse' :
                          v.status==='Evacuated' ? 'text-[#ff8c00]' :
                          'text-[#00e676]'
                        }`}>{v.status}</span>
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
            <h2 className="text-sm font-bold text-gray-400 tracking-widest uppercase mb-4 font-mono border-b border-[#1e3050] pb-2">AI Transparency Ledger</h2>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs font-sans">
                <thead className="text-gray-500 border-b border-[#1e3050] font-mono uppercase tracking-wider text-[10px]">
                  <tr>
                    <th className="p-3 whitespace-nowrap">Incident</th>
                    <th className="p-3">Aadhaar</th>
                    <th className="p-3">Agent</th>
                    <th className="p-3">Decision</th>
                    <th className="p-3">Reasoning</th>
                    <th className="p-3 hidden md:table-cell">Legal Basis</th>
                    <th className="p-3 hidden lg:table-cell">Fleet Check</th>
                    <th className="p-3">Thought</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[rgba(30,48,80,0.3)]">
                  {audit.map(log => (
                    <>
                      <tr key={log.id} className="hover:bg-[#1e3050]/20 transition duration-150">
                        <td className="p-3 font-mono text-[#2979ff] font-bold cursor-pointer hover:underline" onClick={() => {setStreamId(log.incident_id); setTab("trace");}}>#{log.incident_id}</td>
                        <td className="p-3 text-gray-400 font-mono text-[10px]">{maskAadhaar(log.aadhar_id)}</td>
                        <td className="p-3 font-bold text-gray-300">{log.agent}</td>
                        <td className="p-3"><span className={`px-2 py-1 rounded text-[10px] font-bold border ${DECISION_COLOR[log.decision]}`}>{log.decision}</span></td>
                        <td className="p-3 text-gray-400 max-w-sm leading-relaxed">{log.reasoning?.slice(0, 120)}{log.reasoning?.length > 120 ? '...' : ''}</td>
                        <td className="p-3 text-[#607080] hidden md:table-cell text-[10px] italic">📜 {log.citation || "—"}</td>
                        <td className="p-3 text-[#ff8c00] hidden lg:table-cell text-[10px] font-mono">{log.fleet_check || "—"}</td>
                        <td className="p-3">
                          <button
                            onClick={() => toggleAuditExpand(log.id)}
                            className="text-[10px] text-[#2979ff] hover:text-white border border-[#2979ff]/30 px-2 py-1 rounded transition-colors"
                          >
                            {expandedAudit.has(log.id) ? "▼ Hide" : "▶ Show"}
                          </button>
                        </td>
                      </tr>
                      {expandedAudit.has(log.id) && (
                        <tr key={`${log.id}-detail`}>
                          <td colSpan={8} className="p-4 bg-[#06101c] border-l-2 border-[#2979ff]">
                            <div className="space-y-2 text-xs">
                              <div className="text-[10px] text-[#2979ff] uppercase tracking-widest font-bold mb-2">
                                🧠 Model Reasoning & Consensus
                              </div>
                              <div className="text-gray-300 leading-relaxed whitespace-pre-wrap">{log.reasoning}</div>
                              {log.consensus_score != null && (
                                <div className="mt-2 text-[#f5c518]">
                                  Consensus Score: <span className="font-bold">{log.consensus_score}</span>/150
                                </div>
                              )}
                              {log.fleet_check && (
                                <div className="mt-2 text-[#ff8c00]">
                                  Fleet Availability: <span className="font-mono">{log.fleet_check}</span>
                                </div>
                              )}
                              {log.citation && (
                                <div className="mt-2 text-[#607080] italic">
                                  📜 Legal: {log.citation}
                                </div>
                              )}
                            </div>
                          </td>
                        </tr>
                      )}
                    </>
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
