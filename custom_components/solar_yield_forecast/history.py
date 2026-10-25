"""Small dependency-free helpers for importing existing Home Assistant history."""
from __future__ import annotations

from datetime import datetime, timedelta
import math


def daily_energy_maxima(samples, tz, maximum_kwh=1000.0):
    """Return the largest valid daily-energy reading for each local day.

    ``samples`` contains ``(unix_timestamp, value, unit)`` tuples.  A daily
    utility meter sometimes resets a few minutes late; a still-large reading
    before 04:00 therefore belongs to the preceding production day.
    """
    result = {}
    for stamp, raw_value, raw_unit in samples:
        try:
            value = float(raw_value)
            if not math.isfinite(value):
                continue
            unit = str(raw_unit or "kWh").lower().replace(" ", "")
            if unit == "wh":
                value /= 1000.0
            elif unit == "mwh":
                value *= 1000.0
            elif unit not in ("kwh", "kw·h", "kw h"):
                continue
            if not 0 <= value <= maximum_kwh:
                continue
            local = datetime.fromtimestamp(float(stamp), tz)
        except (TypeError, ValueError, OverflowError, OSError):
            continue
        day = local.date()
        if local.hour < 4 and value > 3:
            day -= timedelta(days=1)
        key = day.isoformat()
        result[key] = max(value, result.get(key, -1.0))
    return result
