/**
 * api.js — Shared API utility for Sentinel-AI v2.0
 * Used by both /sos and /admin pages.
 */

export const API = "http://localhost:8000/api";

export async function apiFetch(path, opts = {}) {
  try {
    const r = await fetch(API + path, {
      ...opts,
      headers: { "Content-Type": "application/json", ...opts.headers },
    });
    if (!r.ok) {
      let err;
      try {
        err = await r.json();
      } catch {
        err = null;
      }
      return { error: true, status: r.status, data: err };
    }
    return { error: false, data: await r.json() };
  } catch (e) {
    return { error: true, message: e.message };
  }
}

/**
 * Mask Aadhaar for display: XXXX-XXXX-1234
 */
export function maskAadhaar(aadhaar) {
  if (!aadhaar) return "—";
  const digits = aadhaar.replace(/\D/g, "");
  if (digits.length !== 12) return aadhaar;
  return `XXXX-XXXX-${digits.slice(-4)}`;
}

/**
 * Flood level layman labels (matches backend)
 */
export const FLOOD_LABELS = {
  0: "No Flood",
  1: "Level 1: Ankle — Water is low; watch for hidden drains",
  2: "Level 2: Waist — Deep/strong water; dangerous to move",
  3: "Level 3: Overhead — Ground floor submerged; roof/upper floor",
};

export const SEVERITY_COLOR = {
  Critical: "text-[#ff2d2d] border-[#ff2d2d]/60 bg-[#ff2d2d]/10 font-bold",
  High: "text-[#ff8c00] border-[#ff8c00]/60 bg-[#ff8c00]/10",
  Medium: "text-[#f5c518] border-[#f5c518]/60 bg-[#f5c518]/10",
  Low: "text-[#00e676] border-[#00e676]/60 bg-[#00e676]/10",
};

export const DECISION_COLOR = {
  APPROVED: "text-[#00e676] border-[#00e676]/60 bg-[#00e676]/10",
  REJECTED: "text-[#ff2d2d] border-[#ff2d2d]/60 bg-[#ff2d2d]/10",
  REDIRECTED: "text-[#f5c518] border-[#f5c518]/60 bg-[#f5c518]/10",
  VIP_BLOCKED: "text-[#bf00ff] border-[#bf00ff]/60 bg-[#bf00ff]/10",
  FRAUD_ALERT: "text-[#ff2d2d] border-[#ff2d2d]/60 bg-[#ff2d2d]/10",
  OVERRIDE: "text-[#ff8c00] border-[#ff8c00]/60 bg-[#ff8c00]/10",
  CONSENSUS: "text-[#2979ff] border-[#2979ff]/60 bg-[#2979ff]/10",
};
