from datetime import datetime
from zoneinfo import ZoneInfo
from custom_components.solar_yield_forecast.model import open_meteo_azimuth, estimate_kw, hourly_power_profile

def test_azimuth():
    assert open_meteo_azimuth(180) == 0
    assert open_meteo_azimuth(90) == -90
    assert open_meteo_azimuth(290) == 110

def test_power():
    group = {"count": 10}
    assert estimate_kw(0, 25, 0, group) == 0
    assert estimate_kw(800, 25, 5, group) > 0

def test_profile():
    data = [{"start":"2026-10-22T08:00:00+03:00","kw":1.5}]
    points = hourly_power_profile(data)
    assert points[0]["power_w"] == 1500
    assert "08:30" in points[0]["time"]
