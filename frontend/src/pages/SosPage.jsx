import { useState, useEffect, useRef, useCallback } from "react";
import { apiFetch, FLOOD_LABELS, maskAadhaar } from "../api";

// ── Chatbot Phases ───────────────────────────────────────────────────────────
const PHASE = {
  VICTIM_COUNT: 0,
  LOCATION: 1,
  FLOOD_LEVEL: 2,
  HAZARDS: 3,
  COMMENTS: 4,
  VICTIM_LOOP: 5,
  SIMPLIFIED_LOOP: 6,
  SUBMITTING: 7,
  RESULT: 8,
};

const HAZARDS_OPTIONS = [
  "Fire Hazards",
  "Electrical Shortages",
  "Sewage Contamination",
  "None",
];

function ChatBubble({ from, children, animate }) {
  const isBot = from === "bot";
  return (
    <div className={`flex ${isBot ? "justify-start" : "justify-end"} mb-4 ${animate ? "chat-bubble-enter" : ""}`}>
      <div
        className={`max-w-[85%] px-4 py-3 rounded-2xl text-sm leading-relaxed ${
          isBot
            ? "bg-[#0d1f35] border border-[#1e3050] text-gray-200 rounded-bl-md"
            : "bg-[#2979ff]/20 border border-[#2979ff]/40 text-[#c8d8e8] rounded-br-md"
        }`}
      >
        {isBot && <div className="text-[9px] text-[#2979ff] font-bold uppercase tracking-widest mb-1">🤖 sentinel</div>}
        {children}
      </div>
    </div>
  );
}

function TypingIndicator() {
  return (
    <div className="flex justify-start mb-4">
      <div className="bg-[#0d1f35] border border-[#1e3050] px-4 py-3 rounded-2xl rounded-bl-md">
        <div className="flex gap-1.5">
          <span className="typing-dot w-2 h-2 rounded-full bg-[#2979ff]" style={{ animationDelay: "0s" }}></span>
          <span className="typing-dot w-2 h-2 rounded-full bg-[#2979ff]" style={{ animationDelay: "0.2s" }}></span>
          <span className="typing-dot w-2 h-2 rounded-full bg-[#2979ff]" style={{ animationDelay: "0.4s" }}></span>
        </div>
      </div>
    </div>
  );
}

export default function SosPage() {
  const [phase, setPhase] = useState(PHASE.VICTIM_COUNT);
  const [messages, setMessages] = useState([]);
  const [typing, setTyping] = useState(false);
  const chatRef = useRef(null);

  // ── Collected Data ───────────────────────────────────────────────────────
  const [victimCount, setVictimCount] = useState("");
  const [lat, setLat] = useState("");
  const [lon, setLon] = useState("");
  const [locationReady, setLocationReady] = useState(false);
  const [floodLevel, setFloodLevel] = useState(null);
  const [hazards, setHazards] = useState([]);
  const [comments, setComments] = useState("");

  // Victim loop state
  const [currentVictimIdx, setCurrentVictimIdx] = useState(0);
  const [victimDetails, setVictimDetails] = useState([]);
  const [simplifiedVictims, setSimplifiedVictims] = useState([]);

  // Current victim form
  const [vName, setVName] = useState("");
  const [vPhone, setVPhone] = useState("");
  const [vAadhaar, setVAadhaar] = useState("");
  const [vCategory, setVCategory] = useState("Male");
  const [vLgbtq, setVLgbtq] = useState(false);
  const [vDisability, setVDisability] = useState(false);
  const [vMedical, setVMedical] = useState(false);
  const [vSeverity, setVSeverity] = useState("Low");
  const [vPhoneError, setVPhoneError] = useState("");
  const [vAadhaarError, setVAadhaarError] = useState("");

  // Simplified victim form
  const [svCategory, setSvCategory] = useState("Male");
  const [svMedical, setSvMedical] = useState(false);
  const [svSeverity, setSvSeverity] = useState("Low");

  // Result
  const [sosResult, setSosResult] = useState(null);

  // How many full-detail victims to collect
  const fullDetailCount = victimCount > 10 ? 2 : parseInt(victimCount) || 0;
  const simplifiedCount = victimCount > 10 ? parseInt(victimCount) - 2 : 0;

  // ── Auto-scroll chat ─────────────────────────────────────────────────────
  useEffect(() => {
    if (chatRef.current) chatRef.current.scrollTop = chatRef.current.scrollHeight;
  }, [messages, typing, phase]);

  // ── Bot message helper ────────────────────────────────────────────────────
  const addBot = useCallback((text, delay = 600) => {
    setTyping(true);
    setTimeout(() => {
      setMessages((prev) => [...prev, { from: "bot", text }]);
      setTyping(false);
    }, delay);
  }, []);

  const addUser = useCallback((text) => {
    setMessages((prev) => [...prev, { from: "user", text }]);
  }, []);

  // ── Initial message ──────────────────────────────────────────────────────
  useEffect(() => {
    addBot("🚨 Emergency SOS — Sentinel-AI v2.0\n\nI'll guide you through the rescue request process. Your location will be auto-detected.\n\nQ1: How many victims require rescue?", 300);
    // Auto-detect GPS
    if ("geolocation" in navigator) {
      navigator.geolocation.getCurrentPosition(
        (pos) => {
          setLat(pos.coords.latitude.toFixed(6));
          setLon(pos.coords.longitude.toFixed(6));
          setLocationReady(true);
        },
        () => {
          setLat("8.5150");
          setLon("76.9300");
          setLocationReady(true);
        },
        { enableHighAccuracy: true, timeout: 10000 }
      );
    } else {
      setLat("8.5150");
      setLon("76.9300");
      setLocationReady(true);
    }
  }, []);

  // ── Phase Handlers ────────────────────────────────────────────────────────
  const handleVictimCount = () => {
    const n = parseInt(victimCount);
    if (!n || n < 1) return;
    addUser(`${n} victim${n > 1 ? "s" : ""}`);
    setPhase(PHASE.LOCATION);
    setTimeout(() => {
      if (locationReady) {
        addBot(`📍 Location auto-detected!\nLatitude: ${lat}\nLongitude: ${lon}\n\nPlease verify these coordinates are correct, then click "Confirm Location".\n\n⚠️ In poor connectivity, read these numbers over phone/radio to a dispatcher.`);
      } else {
        addBot("📍 Detecting your location... Please wait or enter coordinates manually.");
      }
    }, 700);
  };

  const handleLocationConfirm = () => {
    if (!lat || !lon) return;
    addUser(`📍 Location confirmed: ${lat}, ${lon}`);
    setPhase(PHASE.FLOOD_LEVEL);
    setTimeout(() => {
      addBot("Q3: Select current Flood Level:\n\n🟢 Level 1 (Ankle): Water is low; you can stand. Watch for hidden drains.\n🟡 Level 2 (Waist): Water is deep/strong; dangerous to move.\n🔴 Level 3 (Overhead): Ground floor submerged; you are on a roof or upper floor.");
    }, 700);
  };

  const handleFloodLevel = (level) => {
    setFloodLevel(level);
    addUser(FLOOD_LABELS[level]);
    setPhase(PHASE.HAZARDS);
    setTimeout(() => {
      addBot("Q4: Are there any specific hazards? (Select all that apply)");
    }, 700);
  };

  const handleHazards = () => {
    const selected = hazards.length === 0 || hazards.includes("None") ? ["None"] : hazards;
    addUser(`Hazards: ${selected.join(", ")}`);
    setPhase(PHASE.COMMENTS);
    setTimeout(() => {
      addBot('Q5: Any extra comments? (e.g., elderly persons, structural damage, urgency notes)\n\nType your comment or click "Skip" to proceed.');
    }, 700);
  };

  const handleComments = (skip = false) => {
    const text = skip ? "—" : comments;
    addUser(text);
    setPhase(PHASE.VICTIM_LOOP);
    setCurrentVictimIdx(0);
    const n = parseInt(victimCount);
    const detailCount = n > 10 ? 2 : n;
    setTimeout(() => {
      if (n > 10) {
        addBot(`You have ${n} victims. I'll collect full details for 2 primary contacts, then simplified info for the remaining ${n - 2}.`);
      }
      setTimeout(() => {
        addBot(`📋 Please provide details for Victim #1 of ${detailCount}:`);
      }, n > 10 ? 1200 : 700);
    }, 700);
  };

  const handleVictimSubmit = () => {
    // Validate phone
    const cleanPhone = vPhone.replace(/\D/g, "");
    if (cleanPhone.length !== 10) {
      setVPhoneError("Phone number must be exactly 10 digits");
      return;
    }
    setVPhoneError("");
    // Validate Aadhaar
    const cleanAadhaar = vAadhaar.replace(/\D/g, "");
    if (cleanAadhaar.length !== 12) {
      setVAadhaarError("Aadhaar ID must be exactly 12 digits");
      return;
    }
    setVAadhaarError("");

    const detail = {
      name: vName,
      phone: cleanPhone,
      aadhaar: cleanAadhaar,
      category: vCategory,
      lgbtq_shelter: vLgbtq,
      disability_access: vDisability,
      medical_need: vMedical,
      severity: vMedical ? vSeverity : "Low",
    };

    const updated = [...victimDetails, detail];
    setVictimDetails(updated);
    addUser(`✅ Victim #${currentVictimIdx + 1}: ${vName} (${vCategory}) — ${vMedical ? `Medical: ${vSeverity}` : "No medical need"}`);

    // Reset form
    setVName("");
    setVPhone("");
    setVAadhaar("");
    setVCategory("Male");
    setVLgbtq(false);
    setVDisability(false);
    setVMedical(false);
    setVSeverity("Low");

    const nextIdx = currentVictimIdx + 1;
    if (nextIdx < fullDetailCount) {
      setCurrentVictimIdx(nextIdx);
      setTimeout(() => {
        addBot(`📋 Please provide details for Victim #${nextIdx + 1} of ${fullDetailCount}:`);
      }, 700);
    } else if (simplifiedCount > 0) {
      setPhase(PHASE.SIMPLIFIED_LOOP);
      setCurrentVictimIdx(0);
      setTimeout(() => {
        addBot(`Now provide simplified info for the remaining ${simplifiedCount} victims.\n\nVictim #${fullDetailCount + 1} of ${parseInt(victimCount)}:`);
      }, 700);
    } else {
      submitSOS(updated, []);
    }
  };

  const handleSimplifiedSubmit = () => {
    const sv = {
      category: svCategory,
      medical_need: svMedical,
      severity: svMedical ? svSeverity : "Low",
    };
    const updated = [...simplifiedVictims, sv];
    setSimplifiedVictims(updated);
    addUser(`Victim #${fullDetailCount + currentVictimIdx + 1}: ${svCategory} — ${svMedical ? svSeverity : "No medical"}`);

    setSvCategory("Male");
    setSvMedical(false);
    setSvSeverity("Low");

    const nextIdx = currentVictimIdx + 1;
    if (nextIdx < simplifiedCount) {
      setCurrentVictimIdx(nextIdx);
      setTimeout(() => {
        addBot(`Victim #${fullDetailCount + nextIdx + 1} of ${parseInt(victimCount)}:`);
      }, 500);
    } else {
      submitSOS(victimDetails, updated);
    }
  };

  // ── Submit SOS ────────────────────────────────────────────────────────────
  const submitSOS = async (details, simplified) => {
    setPhase(PHASE.SUBMITTING);
    addBot("🔄 Submitting your SOS to Sentinel-AI multi-agent dispatchers...");

    const payload = {
      victim_count: parseInt(victimCount),
      lat: parseFloat(lat),
      lon: parseFloat(lon),
      flood_level: floodLevel,
      hazards: hazards.filter((h) => h !== "None"),
      extra_comments: comments || null,
      victims: details,
      simplified_victims: simplified,
    };

    const res = await apiFetch("/sos", {
      method: "POST",
      body: JSON.stringify(payload),
    });

    if (res.error) {
      if (res.data?.detail?.status === "FRAUD_ALERT") {
        addBot(`🚫 FRAUD ALERT: ${res.data.detail.message}`);
      } else {
        addBot(`❌ Error: ${JSON.stringify(res.data?.detail || res.message || "Submission failed")}`);
      }
      setPhase(PHASE.VICTIM_COUNT);
    } else {
      setSosResult(res.data);
      setPhase(PHASE.RESULT);
    }
  };

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <div className="min-h-screen bg-[#020813] text-gray-200 flex flex-col">
      {/* Header */}
      <header className="bg-[rgba(2,12,24,0.95)] border-b border-[#0d2535] py-4 px-6 flex items-center gap-4 sticky top-0 z-50 backdrop-blur-lg">
        <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-[#ff2d2d] to-[#2979ff] flex items-center justify-center text-xl shadow-[0_0_15px_rgba(255,45,45,0.5)] border border-white/20">
          🆘
        </div>
        <div>
          <h1 className="text-lg font-bold tracking-[0.15em] text-[#e8f0f8]">SENTINEL-AI SOS</h1>
          <div className="text-[9px] text-[#607080] tracking-[0.3em] font-mono mt-0.5">
            EMERGENCY TRIAGE CHATBOT
          </div>
        </div>
        <a href="/admin" className="ml-auto text-[10px] text-[#607080] hover:text-[#2979ff] uppercase tracking-widest transition-colors">
          Admin →
        </a>
      </header>

      {/* Chat Area */}
      <div ref={chatRef} className="flex-1 overflow-y-auto p-4 md:p-6 max-w-3xl w-full mx-auto space-y-1">
        {messages.map((msg, i) => (
          <ChatBubble key={i} from={msg.from} animate={i === messages.length - 1}>
            <div className="whitespace-pre-wrap">{msg.text}</div>
          </ChatBubble>
        ))}
        {typing && <TypingIndicator />}

        {/* ── Phase 0: Victim Count ──────────────────────────────────────── */}
        {phase === PHASE.VICTIM_COUNT && (
          <div className="sos-input-area">
            <input
              type="number"
              min="1"
              value={victimCount}
              onChange={(e) => setVictimCount(e.target.value)}
              placeholder="Number of victims..."
              className="sos-input"
              autoFocus
              onKeyDown={(e) => e.key === "Enter" && handleVictimCount()}
            />
            <button onClick={handleVictimCount} className="sos-btn">Send</button>
          </div>
        )}

        {/* ── Phase 1: Location ──────────────────────────────────────────── */}
        {phase === PHASE.LOCATION && (
          <div className="sos-input-area flex-col gap-3">
            <div className="coord-display">
              <div className="text-[10px] text-[#607080] uppercase tracking-widest mb-2">GPS Coordinates (for manual verification)</div>
              <div className="grid grid-cols-2 gap-3">
                <label className="space-y-1">
                  <span className="text-[10px] text-gray-500">Latitude</span>
                  <input value={lat} onChange={(e) => setLat(e.target.value)} className="sos-input text-center font-mono text-lg" />
                </label>
                <label className="space-y-1">
                  <span className="text-[10px] text-gray-500">Longitude</span>
                  <input value={lon} onChange={(e) => setLon(e.target.value)} className="sos-input text-center font-mono text-lg" />
                </label>
              </div>
            </div>
            <button onClick={handleLocationConfirm} className="sos-btn w-full">
              ✅ Confirm Location
            </button>
          </div>
        )}

        {/* ── Phase 2: Flood Level ───────────────────────────────────────── */}
        {phase === PHASE.FLOOD_LEVEL && (
          <div className="sos-input-area flex-col gap-2">
            {[1, 2, 3].map((level) => (
              <button
                key={level}
                onClick={() => handleFloodLevel(level)}
                className={`w-full text-left px-4 py-3 rounded-xl border text-sm transition-all ${
                  level === 1
                    ? "border-[#00e676]/40 hover:bg-[#00e676]/10 text-[#00e676]"
                    : level === 2
                    ? "border-[#f5c518]/40 hover:bg-[#f5c518]/10 text-[#f5c518]"
                    : "border-[#ff2d2d]/40 hover:bg-[#ff2d2d]/10 text-[#ff2d2d]"
                }`}
              >
                {FLOOD_LABELS[level]}
              </button>
            ))}
          </div>
        )}

        {/* ── Phase 3: Hazards ───────────────────────────────────────────── */}
        {phase === PHASE.HAZARDS && (
          <div className="sos-input-area flex-col gap-2">
            {HAZARDS_OPTIONS.map((h) => (
              <label
                key={h}
                className={`flex items-center gap-3 px-4 py-3 rounded-xl border cursor-pointer transition-all ${
                  hazards.includes(h)
                    ? "border-[#2979ff]/60 bg-[#2979ff]/10"
                    : "border-[#1e3050] hover:border-[#2979ff]/30"
                }`}
              >
                <input
                  type="checkbox"
                  checked={hazards.includes(h)}
                  onChange={(e) => {
                    if (h === "None") {
                      setHazards(e.target.checked ? ["None"] : []);
                    } else {
                      setHazards((prev) =>
                        e.target.checked
                          ? [...prev.filter((x) => x !== "None"), h]
                          : prev.filter((x) => x !== h)
                      );
                    }
                  }}
                  className="rounded bg-[#1a2535] border-[#2979ff] text-[#2979ff]"
                />
                <span className="text-sm text-gray-300">{h}</span>
              </label>
            ))}
            <button onClick={handleHazards} className="sos-btn w-full mt-2">
              Confirm Hazards
            </button>
          </div>
        )}

        {/* ── Phase 4: Comments ──────────────────────────────────────────── */}
        {phase === PHASE.COMMENTS && (
          <div className="sos-input-area flex-col gap-2">
            <textarea
              value={comments}
              onChange={(e) => setComments(e.target.value)}
              placeholder="Elderly persons, structural damage, urgency..."
              className="sos-input min-h-[80px] resize-none"
              rows={3}
            />
            <div className="flex gap-2">
              <button onClick={() => handleComments(true)} className="sos-btn-secondary flex-1">
                Skip
              </button>
              <button onClick={() => handleComments(false)} className="sos-btn flex-1">
                Submit Comment
              </button>
            </div>
          </div>
        )}

        {/* ── Phase 5: Full Victim Details Loop ──────────────────────────── */}
        {phase === PHASE.VICTIM_LOOP && (
          <div className="sos-input-area flex-col gap-3">
            <div className="text-[10px] text-[#2979ff] font-bold uppercase tracking-widest">
              Victim #{currentVictimIdx + 1} of {fullDetailCount}
            </div>
            <input value={vName} onChange={(e) => setVName(e.target.value)} placeholder="Victim Name" className="sos-input" />
            <div>
              <input
                value={vPhone}
                onChange={(e) => { setVPhone(e.target.value); setVPhoneError(""); }}
                placeholder="Phone (10 digits)"
                className={`sos-input ${vPhoneError ? "border-[#ff2d2d]!" : ""}`}
                maxLength={10}
              />
              {vPhoneError && <div className="text-[#ff2d2d] text-[11px] mt-1 font-bold">{vPhoneError}</div>}
            </div>
            <div>
              <input
                value={vAadhaar}
                onChange={(e) => { setVAadhaar(e.target.value); setVAadhaarError(""); }}
                placeholder="Aadhaar ID (12 digits)"
                className={`sos-input ${vAadhaarError ? "border-[#ff2d2d]!" : ""}`}
                maxLength={12}
              />
              {vAadhaarError && <div className="text-[#ff2d2d] text-[11px] mt-1 font-bold">{vAadhaarError}</div>}
            </div>
            <div className="grid grid-cols-3 gap-2">
              {["Male", "Female", "Child"].map((c) => (
                <button
                  key={c}
                  onClick={() => setVCategory(c)}
                  className={`px-3 py-2 rounded-lg text-xs font-bold border transition-all ${
                    vCategory === c
                      ? "bg-[#2979ff]/20 border-[#2979ff]/60 text-[#2979ff]"
                      : "border-[#1e3050] text-gray-500 hover:border-[#2979ff]/30"
                  }`}
                >
                  {c}
                </button>
              ))}
            </div>
            <div className="flex gap-4">
              <label className="flex items-center gap-2 cursor-pointer text-[11px] text-gray-400 uppercase">
                <input
                  type="checkbox"
                  checked={vLgbtq}
                  onChange={(e) => setVLgbtq(e.target.checked)}
                  className="rounded bg-[#1a2535] border-[#bf00ff] text-[#bf00ff]"
                />
                LGBTQIA+ Shelter
              </label>
              <label className="flex items-center gap-2 cursor-pointer text-[11px] text-gray-400 uppercase">
                <input
                  type="checkbox"
                  checked={vDisability}
                  onChange={(e) => setVDisability(e.target.checked)}
                  className="rounded bg-[#1a2535] border-[#f5c518] text-[#f5c518]"
                />
                Disability Access
              </label>
            </div>
            <div className="flex items-center gap-4">
              <label className="flex items-center gap-2 cursor-pointer text-[11px] text-gray-400 uppercase">
                <input
                  type="checkbox"
                  checked={vMedical}
                  onChange={(e) => setVMedical(e.target.checked)}
                  className="rounded bg-[#1a2535] border-[#ff2d2d] text-[#ff2d2d]"
                />
                Medical Need
              </label>
              {vMedical && (
                <select
                  value={vSeverity}
                  onChange={(e) => setVSeverity(e.target.value)}
                  className="sos-input w-auto text-white"
                >
                  <option>Critical</option>
                  <option>High</option>
                  <option>Medium</option>
                  <option>Low</option>
                </select>
              )}
            </div>
            <button
              onClick={handleVictimSubmit}
              disabled={!vName || !vPhone || !vAadhaar}
              className="sos-btn w-full disabled:opacity-40 disabled:cursor-not-allowed"
            >
              ✅ Submit Victim #{currentVictimIdx + 1}
            </button>
          </div>
        )}

        {/* ── Phase 6: Simplified Victim Loop ────────────────────────────── */}
        {phase === PHASE.SIMPLIFIED_LOOP && (
          <div className="sos-input-area flex-col gap-3">
            <div className="text-[10px] text-[#f5c518] font-bold uppercase tracking-widest">
              Simplified — Victim #{fullDetailCount + currentVictimIdx + 1} of {victimCount}
            </div>
            <div className="grid grid-cols-3 gap-2">
              {["Male", "Female", "Child"].map((c) => (
                <button
                  key={c}
                  onClick={() => setSvCategory(c)}
                  className={`px-3 py-2 rounded-lg text-xs font-bold border transition-all ${
                    svCategory === c
                      ? "bg-[#2979ff]/20 border-[#2979ff]/60 text-[#2979ff]"
                      : "border-[#1e3050] text-gray-500 hover:border-[#2979ff]/30"
                  }`}
                >
                  {c}
                </button>
              ))}
            </div>
            <div className="flex items-center gap-4">
              <label className="flex items-center gap-2 cursor-pointer text-[11px] text-gray-400 uppercase">
                <input
                  type="checkbox"
                  checked={svMedical}
                  onChange={(e) => setSvMedical(e.target.checked)}
                  className="rounded bg-[#1a2535] border-[#ff2d2d] text-[#ff2d2d]"
                />
                Medical Need
              </label>
              {svMedical && (
                <select
                  value={svSeverity}
                  onChange={(e) => setSvSeverity(e.target.value)}
                  className="sos-input w-auto text-white"
                >
                  <option>Critical</option>
                  <option>High</option>
                  <option>Medium</option>
                  <option>Low</option>
                </select>
              )}
            </div>
            <button onClick={handleSimplifiedSubmit} className="sos-btn w-full">
              ✅ Submit
            </button>
          </div>
        )}

        {/* ── Phase 7: Submitting ────────────────────────────────────────── */}
        {phase === PHASE.SUBMITTING && <TypingIndicator />}

        {/* ── Phase 8: Result ────────────────────────────────────────────── */}
        {phase === PHASE.RESULT && sosResult && (
          <div className="space-y-4">
            <ChatBubble from="bot">
              <div className="space-y-3">
                <div className="text-[#00e676] font-bold text-sm">✅ SOS Received — Incident #{sosResult.incident_id}</div>
                <div className="text-xs text-gray-400">
                  Priority: <span className={`font-bold ${sosResult.priority === "ULTRA_PRIORITY" ? "text-[#ff2d2d]" : "text-[#2979ff]"}`}>{sosResult.priority}</span>
                  {" • "}Score: <span className="text-white font-bold">{sosResult.priority_score}</span>
                  {" • "}{sosResult.total_victims} victims
                </div>
                <div className="text-xs text-gray-400">{sosResult.flood_level_label}</div>
              </div>
            </ChatBubble>

            {/* Coordinate display box — high contrast for radio readout */}
            <div className="coord-readout">
              <div className="text-[10px] uppercase tracking-widest text-[#f5c518] font-bold mb-2">
                📻 GPS Coordinates — Read Over Radio
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <div className="text-[10px] text-gray-500 uppercase">Latitude</div>
                  <div className="text-xl font-mono font-bold text-white tracking-wider">
                    {sosResult.coordinates.lat}
                  </div>
                </div>
                <div>
                  <div className="text-[10px] text-gray-500 uppercase">Longitude</div>
                  <div className="text-xl font-mono font-bold text-white tracking-wider">
                    {sosResult.coordinates.lon}
                  </div>
                </div>
              </div>
            </div>

            {/* Per-victim allotments */}
            {sosResult.victim_allotments && sosResult.victim_allotments.length > 0 && (
              <div className="bg-[#0d1f35] border border-[#1e3050] rounded-xl p-4 space-y-3">
                <div className="text-[10px] uppercase tracking-widest text-[#2979ff] font-bold">
                  Victim Allotments
                </div>
                {sosResult.victim_allotments.map((va, i) => (
                  <div key={i} className="flex justify-between items-center p-3 bg-[#06101c] rounded-lg border border-[#1e3050]/50">
                    <div>
                      <div className="text-sm font-bold text-gray-200">{va.name}</div>
                      <div className="text-[10px] text-gray-500 font-mono">{va.aadhaar_masked}</div>
                    </div>
                    <div className="text-right">
                      <div className="text-xs text-[#00e676] font-bold">
                        {va.destination_type === "Hospital" ? "🏥" : "⛺"} {va.destination}
                      </div>
                      {va.eta_minutes && (
                        <div className="text-[10px] text-gray-400">
                          ETA: {va.eta_minutes} min | {va.distance_km} km
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}

            <button
              onClick={() => window.location.reload()}
              className="sos-btn-secondary w-full"
            >
              Submit Another SOS
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
