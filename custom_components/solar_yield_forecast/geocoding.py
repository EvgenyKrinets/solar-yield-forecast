"""Validation and presentation helpers for Open-Meteo place search."""
from __future__ import annotations

from math import isfinite


def normalized_locations(payload):
    """Return only complete, safe WGS84/IANA location results."""
    if not isinstance(payload, dict):
        return []
    results = []
    for index, item in enumerate((payload or {}).get("results") or []):
        try:
            latitude = float(item["latitude"])
            longitude = float(item["longitude"])
            name = str(item["name"]).strip()
            timezone = str(item["timezone"]).strip()
            country_code = str(item["country_code"]).strip().upper()
        except (KeyError, TypeError, ValueError):
            continue
        if (
            not name
            or not timezone
            or len(country_code) != 2
            or not isfinite(latitude)
            or not isfinite(longitude)
            or not -90 <= latitude <= 90
            or not -180 <= longitude <= 180
        ):
            continue
        key = str(item.get("id") or f"result-{index}")
        results.append({
            "key": key,
            "name": name,
            "latitude": latitude,
            "longitude": longitude,
            "time_zone": timezone,
            "country_code": country_code,
            "country": str(item.get("country") or country_code).strip(),
            "admin1": str(item.get("admin1") or "").strip(),
        })
    return results


def location_label(location):
    """Build an unambiguous label for the Home Assistant result selector."""
    area = ", ".join(
        part for part in (location.get("admin1"), location.get("country")) if part
    )
    suffix = f" — {area}" if area else ""
    return (
        f"{location['name']}{suffix} · "
        f"{location['latitude']:.5f}, {location['longitude']:.5f} · "
        f"{location['time_zone']}"
    )
