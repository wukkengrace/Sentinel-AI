"""
priority_engine.py — Sentinel Override Engine
Multi-dimensional dispatch priority scoring for Sentinel-AI.

Evaluates every new incident through:
  1. Priority Score (S) — Hazard, Medical Density, Vulnerability, Environment
  2. Density Coefficient (alpha=0.25) — prevents mass-stable overriding single-critical
  3. Logistical Sunk Cost (Ci) — prevents disrupting near-complete missions
  4. Distance-Based Flexibility — offset for units near a rescue center
  5. Tie-Breaker — Raw Score resolves equal capped-score conflicts
"""

import math


class PriorityOverrideSystem:
    """
    Sentinel Override Engine: A priority scoring system for emergency dispatch.

    Logic:
    1. Priority Score (S): (50 * H) + (40 * M_agg) + (30 * V) + (30 * E)
       - Capped at 150.0 for standard logic.
       - Raw Score (R) is maintained for tie-breaking.
    2. Medical Aggregate (M_agg): M_highest + (Sum of others * 0.25)
    3. Residual Cost (Ci): (S_active * (1 - P)) + 40 - (Distance Offset)
       - Distance Offset: Linear scale from 100m (Max Offset) to 5km (0 Offset).
    4. Progress Lock: If P > 0.70, Ci = infinity.
    5. Tie-Breaker: If capped scores are equal, Raw Score determines priority.
    """

    def __init__(self, alpha=0.25, max_proximity_offset=30):
        self.weights = {
            "hazard": 50,
            "medical": 40,
            "vulnerability": 30,
            "environment": 30,
        }
        self.alpha = alpha
        self.delta = 40
        self.progress_limit = 0.70
        self.max_score_cap = 150.0

        self.min_dist = 100
        self.max_dist = 5000
        self.max_offset = max_proximity_offset

        self.MAP_H = {"fire": 1.0, "electricity": 0.9, "flood": 0.6, "sewage": 0.2, "road": 0.5, "tree": 0.3, "other": 0.3}
        self.MAP_M = {"critical": 1.0, "serious": 0.5, "high": 0.5, "medium": 0.3, "stable": 0.1, "low": 0.1}
        self.MAP_V = {"high_risk": 1.0, "standard": 0.0}
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
            self.weights["hazard"] * h
            + self.weights["medical"] * m_agg
            + self.weights["vulnerability"] * v
            + self.weights["environment"] * e
        )
        capped_score = round(min(raw_score, self.max_score_cap), 2)
        return capped_score, round(raw_score, 2)

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

    # ── Multi-Override Evaluator ──────────────────────────────────────────────

    def evaluate_multi_override(self, new_incident: dict, active_missions: list) -> dict:
        """
        Determines if new_incident should override one or more active missions.

        new_incident keys: hazard, medical (list), vulnerable, env
        active_missions keys: score, progress, raw_score (opt), distance_m (opt)
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
        }

    # ── Convenience: score from incident dict ────────────────────────────────

    def score_incident(self, incident: dict) -> tuple[float, float]:
        """
        Score an incident dict as stored in the DB / API.
        Maps: emergency_type → hazard, severity → medical, is_lgbtq/is_disability → vulnerable
        """
        hazard = incident.get("emergency_type", "other").lower()
        severity = incident.get("severity", "low").lower()
        is_vulnerable = (
            "high_risk"
            if incident.get("is_lgbtq") or incident.get("is_disability") or incident.get("child_cnt", 0) > 0
            else "standard"
        )
        # Use flood_level as environment proxy: flood → displaced camp, else home
        # (shelter_cnt counts people needing shelter, NOT whether they are at a camp)
        env = "camp" if incident.get("flood_level", 0) > 0 else "home"
        # medical_cnt=0 → no medical weight; max(0,...) prevents spurious single-tag
        medical_cnt = max(0, incident.get("medical_cnt", 0))
        medical_tags = [severity] * medical_cnt if medical_cnt > 0 else []
        return self.calculate_priority_score(hazard, medical_tags, is_vulnerable, env)


# Singleton for import
engine = PriorityOverrideSystem()


if __name__ == "__main__":
    print("=== Sentinel Override Engine: Distance-Based Logic Test ===")
    sys = PriorityOverrideSystem(alpha=0.25, max_proximity_offset=30)
    inc = {"hazard": "electricity", "medical": ["serious"], "vulnerable": "standard", "env": "home"}
    s_new, r_new = sys.calculate_priority_score(inc["hazard"], inc["medical"], inc["vulnerable"], inc["env"])
    print(f"\nNew Incident Score: {s_new}  (raw: {r_new})")
    active = {"score": 100, "progress": 0.5}
    print(f"\n{'Distance (m)':<15} | {'Offset':<10} | {'Resid. Cost':<12} | {'Override?':<10}")
    print("-" * 55)
    for d in [100, 1000, 2500, 5000]:
        active["distance_m"] = d
        res = sys.evaluate_multi_override(inc, [active])
        offset = res["mission_details"][0]["offset"]
        cost = res["total_residual_cost"]
        approved = "YES" if res["override_approved"] else "NO"
        print(f"{d:<15} | {offset:<10} | {cost:<12} | {approved:<10}")
