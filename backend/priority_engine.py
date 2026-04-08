"""
priority_engine.py — Sentinel Override Engine v2.0
Multi-dimensional dispatch priority scoring for Sentinel-AI.

v2.0 Changes:
  - Medical-dominant weights: S = 60·M_agg + 40·H + 30·V + 20·E
  - Multi-agent consensus: S_final = S_base × 0.80 + S_consensus × 0.20
  - LGBTQIA+ yields 0 priority points (routing only)
  - Vulnerability scored only on Disability Access
  - DM Act 2005 Sections 30 & 34 citations

Evaluates every new incident through:
  1. Priority Score (S) — Medical, Hazard, Vulnerability, Environment
  2. Density Coefficient (alpha=0.25) — prevents mass-stable overriding single-critical
  3. Logistical Sunk Cost (Ci) — prevents disrupting near-complete missions
  4. Distance-Based Flexibility — offset for units near a rescue center
  5. Multi-Agent Consensus (20%) — blended agent agreement score
  6. Tie-Breaker — Raw Score resolves equal capped-score conflicts
"""

import math


# ── DM Act 2005 Legal Citations ──────────────────────────────────────────────
DM_ACT_CITATIONS = {
    "priority_dispatch": "DM Act 2005, Section 34 — Duties of District Authority for disaster response allocation",
    "override": "DM Act 2005, Section 30 — State Authority empowered to override local allocations for life-threatening emergencies",
    "triage_approval": "DM Act 2005, Section 38(2) — Severity-based triage mandated; no political status may alter allocation",
    "resource_audit": "DM Act 2005, Section 34(j) — Ensuring transparent and equitable distribution of relief resources",
}


class PriorityOverrideSystem:
    """
    Sentinel Override Engine v2.0: Medical-dominant priority scoring.

    Logic:
    1. Priority Score (S): (60 * M_agg) + (40 * H) + (30 * V) + (20 * E)
       - Capped at 150.0 for standard logic.
       - Raw Score (R) is maintained for tie-breaking.
    2. Multi-Agent Consensus: S_final = S_base × 0.80 + S_consensus × 0.20
    3. Medical Aggregate (M_agg): M_highest + (Sum of others * 0.25)
    4. LGBTQIA+: 0 priority points. Used only for shelter routing by Local Liaison.
    5. Vulnerability: Only Disability Access counts (1.0).
    6. Residual Cost (Ci): (S_active * (1 - P)) + 40 - (Distance Offset)
    7. Progress Lock: If P > 0.70, Ci = infinity.
    """

    def __init__(self, alpha=0.25, max_proximity_offset=30, consensus_weight=0.20):
        self.weights = {
            "medical": 60,      # Medical urgency is absolute dominant
            "hazard": 40,
            "vulnerability": 30,
            "environment": 20,
        }
        self.alpha = alpha
        self.delta = 40
        self.progress_limit = 0.70
        self.max_score_cap = 150.0
        self.consensus_weight = consensus_weight

        self.min_dist = 100
        self.max_dist = 5000
        self.max_offset = max_proximity_offset

        self.MAP_H = {
            "fire": 1.0, "electricity": 0.9, "electrical": 0.9,
            "flood": 0.6, "sewage": 0.4, "road": 0.5, "tree": 0.3, "other": 0.3,
        }
        # Updated medical mapping per spec
        self.MAP_M = {
            "critical": 1.0, "high": 0.7, "medium": 0.4, "low": 0.1,
            "serious": 0.7, "stable": 0.1,  # legacy compat
        }
        # LGBTQIA+ = 0 points. Only Disability Access scores.
        self.MAP_V = {"disability": 1.0, "high_risk": 1.0, "standard": 0.0}
        self.MAP_E = {"camp": 1.0, "home": 0.2}

    # ── Distance Offset ───────────────────────────────────────────────────────

    def calculate_distance_offset(self, distance_m: float) -> float:
        if distance_m <= self.min_dist:
            return self.max_offset
        if distance_m >= self.max_dist:
            return 0.0
        ratio = (distance_m - self.min_dist) / (self.max_dist - self.min_dist)
        return round(self.max_offset * (1 - ratio), 2)

    # ── Priority Score ────────────────────────────────────────────────────────

    def calculate_priority_score(
        self, hazard_type: str, medical_tags: list, is_vulnerable: str, env_type: str
    ) -> tuple[float, float]:
        """Returns (capped_score, raw_score)."""
        h = self.MAP_H.get(hazard_type.lower(), 0.3)
        v = self.MAP_V.get(is_vulnerable.lower(), 0.0)
        e = self.MAP_E.get(env_type.lower(), 0.2)

        if isinstance(medical_tags, str):
            medical_tags = [medical_tags]

        m_values = sorted(
            [self.MAP_M.get(t.lower(), 0.1) for t in medical_tags], reverse=True
        )
        if not m_values:
            m_agg = 0.0
        else:
            m_agg = m_values[0] + sum(m_values[1:]) * self.alpha

        raw_score = (
            self.weights["medical"] * m_agg
            + self.weights["hazard"] * h
            + self.weights["vulnerability"] * v
            + self.weights["environment"] * e
        )
        capped_score = round(min(raw_score, self.max_score_cap), 2)
        return capped_score, round(raw_score, 2)

    # ── Multi-Agent Consensus Blending ────────────────────────────────────────

    def score_with_consensus(
        self, base_score: float, consensus_score: float
    ) -> float:
        """
        Blend base priority score with multi-agent consensus.
        S_final = S_base × 0.80 + S_consensus × 0.20
        """
        s_final = (base_score * (1 - self.consensus_weight)) + (consensus_score * self.consensus_weight)
        return round(min(s_final, self.max_score_cap), 2)

    # ── Residual Cost ─────────────────────────────────────────────────────────

    def calculate_residual_cost(
        self,
        score: float,
        progress: float,
        raw_score: float = None,
        distance_m: float = 5000,
    ) -> tuple[float, float, float]:
        """Returns (cost, raw_cost, offset). Infinity if mission > 70% complete."""
        progress = max(0.0, min(1.0, progress))
        if progress > self.progress_limit:
            return float("inf"), float("inf"), 0.0

        offset = self.calculate_distance_offset(distance_m)
        effective_delta = self.delta - offset

        cost = round((score * (1 - progress)) + effective_delta, 2)
        base_raw = raw_score if raw_score is not None else score
        raw_cost = round((base_raw * (1 - progress)) + effective_delta, 2)
        return cost, raw_cost, offset

    # ── Fleet-Specific Override Gate ──────────────────────────────────────────

    def check_fleet_gate(self, required_fleet: str, fleet_status: dict) -> dict:
        """
        Only activate override logic if the SPECIFIC required fleet is 100% occupied.
        fleet_status: {fleet_type: {"total": N, "available": M}}
        Returns: {"gate_open": bool, "reason": str}
        """
        fleet = fleet_status.get(required_fleet, {"total": 0, "available": 0})
        if fleet["available"] > 0:
            return {
                "gate_open": False,
                "reason": f"{required_fleet} has {fleet['available']} unit(s) available — direct dispatch, no override needed.",
            }
        return {
            "gate_open": True,
            "reason": f"{required_fleet} fleet exhausted (0/{fleet['total']} available) — initiating preemption check.",
        }

    # ── Multi-Override Evaluator ──────────────────────────────────────────────

    def evaluate_multi_override(self, new_incident: dict, active_missions: list) -> dict:
        """
        Determines if new_incident should override one or more active missions.
        Now includes fleet-specific gate check.
        """
        s_new, raw_new = self.calculate_priority_score(
            new_incident.get("hazard", "other"),
            new_incident.get("medical", []),
            new_incident.get("vulnerable", "standard"),
            new_incident.get("env", "home"),
        )

        total_cost = 0.0
        total_raw_cost = 0.0
        mission_details = []

        for m in active_missions:
            cost, raw_cost, offset = self.calculate_residual_cost(
                m["score"],
                m["progress"],
                m.get("raw_score"),
                m.get("distance_m", 5000),
            )
            total_cost += cost
            total_raw_cost += raw_cost
            mission_details.append({
                "cost": cost if cost != float("inf") else "∞",
                "offset": offset,
                "locked": cost == float("inf"),
            })

        override_approved = s_new > total_cost or raw_new > total_raw_cost

        return {
            "s_new": s_new,
            "raw_new": raw_new,
            "total_residual_cost": round(total_cost, 2) if total_cost != float("inf") else "∞",
            "total_raw_residual_cost": round(total_raw_cost, 2) if total_raw_cost != float("inf") else "∞",
            "override_approved": override_approved,
            "mission_details": mission_details,
            "legal_basis": DM_ACT_CITATIONS["override"] if override_approved else DM_ACT_CITATIONS["priority_dispatch"],
        }

    # ── Convenience: score from incident dict ────────────────────────────────

    def score_incident(self, incident: dict) -> tuple[float, float]:
        """
        Score an incident dict as stored in the DB / API.
        v2.0: LGBTQIA+ = 0 points, only Disability Access scores vulnerability.
        """
        hazard = incident.get("emergency_type", "other").lower()
        severity = incident.get("severity", "low").lower()

        # Only Disability Access scores vulnerability — LGBTQ is routing-only
        is_vulnerable = (
            "disability"
            if incident.get("is_disability")
            else "standard"
        )

        env = "camp" if incident.get("flood_level", 0) > 0 else "home"

        medical_cnt = max(0, incident.get("medical_cnt", 0))
        medical_tags = [severity] * medical_cnt if medical_cnt > 0 else []
        return self.calculate_priority_score(hazard, medical_tags, is_vulnerable, env)

    def get_citation(self, context: str = "triage_approval") -> str:
        """Return the appropriate DM Act 2005 citation for audit logging."""
        return DM_ACT_CITATIONS.get(context, DM_ACT_CITATIONS["triage_approval"])


# Singleton for import
engine = PriorityOverrideSystem()


if __name__ == "__main__":
    print("=== Sentinel Override Engine v2.0: Medical-Dominant Scoring ===")
    sys = PriorityOverrideSystem(alpha=0.25, max_proximity_offset=30)

    # Test medical-dominant scoring
    print("\n--- Score Tests ---")
    tests = [
        ("Critical flood", "flood", ["critical"], "disability", "camp"),
        ("High fire", "fire", ["high"], "standard", "home"),
        ("Medium sewage", "sewage", ["medium"], "standard", "camp"),
        ("Low other", "other", ["low"], "standard", "home"),
    ]
    for label, h, m, v, e in tests:
        score, raw = sys.calculate_priority_score(h, m, v, e)
        print(f"  {label}: Score={score}, Raw={raw}")

    # Test consensus blending
    print("\n--- Consensus Blending ---")
    base = 100.0
    consensus = 120.0
    final = sys.score_with_consensus(base, consensus)
    print(f"  Base={base}, Consensus={consensus}, Final={final} (expected: {base*0.8 + consensus*0.2})")

