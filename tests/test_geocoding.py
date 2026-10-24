"""Dependency-free tests for safe geocoding result handling."""
from __future__ import annotations

import importlib.util
from pathlib import Path


PATH = (
    Path(__file__).parents[1]
    / "custom_components"
    / "solar_yield_forecast"
    / "geocoding.py"
)
SPEC = importlib.util.spec_from_file_location("solar_geocoding", PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_complete_location_is_normalized_and_labelled() -> None:
    payload = {"results": [{
        "id": 295277,
        "name": "Dimona",
        "latitude": 31.07079,
        "longitude": 35.03269,
        "timezone": "Asia/Jerusalem",
        "country_code": "il",
        "country": "Israel",
        "admin1": "Southern District",
    }]}
    result = MODULE.normalized_locations(payload)[0]
    assert result["country_code"] == "IL"
    assert result["time_zone"] == "Asia/Jerusalem"
    assert result["latitude"] == 31.07079
    label = MODULE.location_label(result)
    assert "Dimona" in label
    assert "Southern District, Israel" in label
    assert "31.07079, 35.03269" in label
    assert "Asia/Jerusalem" in label


def test_incomplete_or_out_of_range_results_are_rejected() -> None:
    payload = {"results": [
        {"name": "Missing coordinates", "timezone": "UTC", "country_code": "IL"},
        {"name": "Bad latitude", "latitude": 190, "longitude": 1,
         "timezone": "UTC", "country_code": "IL"},
        None,
    ]}
    assert MODULE.normalized_locations(payload) == []
    assert MODULE.normalized_locations(None) == []
    assert MODULE.normalized_locations([]) == []
