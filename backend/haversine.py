"""
haversine.py — Distance & ETA calculations for TVM dispatch.
Formula: Haversine (great-circle distance).
ETA = (distance_km / 30 kmh) * 60 minutes + 5 minutes preparation buffer.
"""

import math
from typing import Tuple, List, Dict, Any


# ── Core Haversine ─────────────────────────────────────────────────────────────

def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Return great-circle distance in kilometres between two GPS points.
    Uses Haversine formula.
    """
    R = 6371.0  # Earth's radius in km

    phi1, phi2   = math.radians(lat1), math.radians(lat2)
    dphi         = math.radians(lat2 - lat1)
    dlambda      = math.radians(lon2 - lon1)

    a = (math.sin(dphi / 2) ** 2
         + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2)

    return R * 2 * math.asin(math.sqrt(a))


def calc_eta(distance_km: float, speed_kmh: float = 30.0, buffer_min: float = 5.0) -> float:
    """
    ETA in minutes.
    Default speed = 30 km/h (urban TVM roads during disaster).
    Buffer = 5 min preparation / gear-up time.
    """
    travel_min = (distance_km / speed_kmh) * 60
    return round(travel_min + buffer_min, 1)


# ── Nearest Resource Finder ────────────────────────────────────────────────────

def nearest_resource(
    incident_lat: float,
    incident_lon: float,
    resources: List[Dict[str, Any]],
    resource_type: str = None,
    require_inclusive: bool = False,
    require_available: bool = True
) -> Dict[str, Any] | None:
    """
    Return the nearest resource (Hospital/Shelter/Fire) with available capacity.

    Args:
        incident_lat/lon:  Victim's GPS coordinates.
        resources:         List of resource dicts from SQLite (cap_avail, lat, lon …).
        resource_type:     Filter by 'Hospital', 'Shelter', or 'Fire'.
        require_inclusive: If True, only return inclusive=1 resources.
        require_available: If True, skip resources with cap_avail == 0.

    Returns:
        Resource dict enriched with 'distance_km' and 'eta_min', or None.
    """
    candidates = []

    for r in resources:
        # ── Apply filters ──────────────────────────────────────────────────
        if resource_type and r.get("type") != resource_type:
            continue
        if require_available and r.get("cap_avail", 0) <= 0:
            continue
        if require_inclusive and not r.get("inclusive", 0):
            continue
        if r.get("status", "Active") == "Cut-off":
            continue

        dist = haversine(incident_lat, incident_lon, r["lat"], r["lon"])
        eta  = calc_eta(dist)

        candidates.append({
            **r,
            "distance_km": round(dist, 2),
            "eta_min":     eta
        })

    if not candidates:
        return None

    # Sort by distance (closest first)
    candidates.sort(key=lambda x: x["distance_km"])
    return candidates[0]


def nearest_agency(
    incident_lat: float,
    incident_lon: float,
    agencies: List[Dict[str, Any]],
    category: str = None
) -> Dict[str, Any] | None:
    """
    Return the nearest agency of a given category (e.g., 'Fire', 'Police').
    Agencies must have 'latitude' and 'longitude' fields.
    """
    candidates = []

    for a in agencies:
        if category and a.get("category") != category:
            continue
        lat = a.get("latitude")
        lon = a.get("longitude")
        if lat is None or lon is None:
            continue

        dist = haversine(incident_lat, incident_lon, lat, lon)
        eta  = calc_eta(dist)

        candidates.append({
            **a,
            "distance_km": round(dist, 2),
            "eta_min":     eta
        })

    if not candidates:
        return None

    candidates.sort(key=lambda x: x["distance_km"])
    return candidates[0]


def rank_resources(
    incident_lat: float,
    incident_lon: float,
    resources: List[Dict[str, Any]],
    resource_type: str = None,
    top_n: int = 3
) -> List[Dict[str, Any]]:
    """
    Return top-N nearest resources sorted by distance, enriched with ETA.
    """
    ranked = []
    for r in resources:
        if resource_type and r.get("type") != resource_type:
            continue
        if r.get("status", "Active") == "Cut-off":
            continue
        dist = haversine(incident_lat, incident_lon, r["lat"], r["lon"])
        ranked.append({**r, "distance_km": round(dist, 2), "eta_min": calc_eta(dist)})

    ranked.sort(key=lambda x: x["distance_km"])
    return ranked[:top_n]


# ── Quick self-test ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # Test: Distance from Secretariat (8.4982, 76.9502) to General Hospital TVM
    d = haversine(8.4982, 76.9502, 8.4977, 76.9415)
    print(f"Secretariat → General Hospital: {d:.2f} km, ETA: {calc_eta(d)} min")

    # Test: Distance to Fire HQ
    d2 = haversine(8.4982, 76.9502, 8.4938, 76.9535)
    print(f"Secretariat → Fire HQ: {d2:.2f} km, ETA: {calc_eta(d2)} min")