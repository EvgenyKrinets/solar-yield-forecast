from datetime import datetime
from zoneinfo import ZoneInfo
import importlib.util
from pathlib import Path

BASE = Path(__file__).resolve().parents[1] / "custom_components" / "solar_yield_forecast"
spec = importlib.util.spec_from_file_location("solar_history", BASE / "history.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
daily_energy_maxima = module.daily_energy_maxima


TZ = ZoneInfo("Asia/Jerusalem")


def stamp(value):
    return datetime.fromisoformat(value).timestamp()


def test_daily_history_uses_maximum_and_converts_wh():
    samples = [
        (stamp("2026-10-20T08:00:00+03:00"), 12000, "Wh"),
        (stamp("2026-10-20T12:00:00+03:00"), 48.5, "kWh"),
        (stamp("2026-10-20T18:00:00+03:00"), 91.2, "kWh"),
    ]
    assert daily_energy_maxima(samples, TZ) == {"2026-10-20": 91.2}


def test_late_midnight_reset_is_assigned_to_previous_day():
    samples = [
        (stamp("2026-10-21T00:05:00+03:00"), 92.0, "kWh"),
        (stamp("2026-10-21T00:10:00+03:00"), 0.0, "kWh"),
        (stamp("2026-10-21T14:00:00+03:00"), 70.0, "kWh"),
    ]
    assert daily_energy_maxima(samples, TZ) == {
        "2026-10-20": 92.0,
        "2026-10-21": 70.0,
    }


def test_invalid_unknown_and_wrong_units_are_ignored():
    samples = [
        (stamp("2026-10-20T12:00:00+03:00"), "unknown", "kWh"),
        (stamp("2026-10-20T13:00:00+03:00"), 5, "kW"),
        (stamp("2026-10-20T14:00:00+03:00"), 5000, "kWh"),
    ]
    assert daily_energy_maxima(samples, TZ) == {}
