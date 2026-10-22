"""Dependency-free solar calculation and forecast calibration utilities."""
from __future__ import annotations
from datetime import datetime, timedelta
from statistics import median
from zoneinfo import ZoneInfo
import math
from .const import PANEL_KWP, PANEL_GROUPS, TIMEZONE
TZ = ZoneInfo(TIMEZONE)

def open_meteo_azimuth(north_clockwise: int | float) -> float:
    return (float(north_clockwise) % 360 - 180 + 180) % 360 - 180

def _number(value, fallback=0.0):
    try:
        result = float(value)
        return result if math.isfinite(result) else fallback
    except (TypeError, ValueError):
        return fallback

def estimate_kw(irradiance_w_m2, air_temp_c, wind_kmh, group):
    gti = max(0.0, _number(irradiance_w_m2))
    temp = _number(air_temp_c, 25.0)
    wind = max(0, _number(wind_kmh)) / 3.6
    temp_increase = gti / 800.0 * max(10.0, 20.0 - min(1.5 * wind, 8.0))
    cell_temp = temp + temp_increase
    temp_factor = max(0.60, min(1.12, 1.0 - 0.0035 * (cell_temp - 25.0)))
    return group["count"] * PANEL_KWP * gti / 1000.0 * 0.92 * temp_factor

def combine_weather(group_responses, groups=PANEL_GROUPS):
    results = {}
    if len(group_responses) != len(groups):
        raise ValueError("Missing panel group weather response")
    for group, response in zip(groups, group_responses):
        hourly = response.get("hourly") or {}
        times = hourly.get("time") or []
        irradiances = hourly.get("global_tilted_irradiance") or []
        temps = hourly.get("temperature_2m") or []
        winds = hourly.get("wind_speed_10m") or []
        if not times or len(times) != len(irradiances):
            raise ValueError(f"Missing radiation from Open-Meteo for {group['id']}")
        for i, stamp in enumerate(times):
            stamp = int(stamp)
            entry = results.setdefault(stamp, {"end": stamp, "group_kw": {}, "kw": 0.0})
            kw = estimate_kw(irradiances[i], temps[i] if i < len(temps) else 25, winds[i] if i < len(winds) else 0, group)
            entry["group_kw"][group["id"]] = kw
            entry["kw"] += kw
    return [results[k] for k in sorted(results) if len(results[k]["group_kw"]) == len(groups)]

def day_of_hour(hour_end_unix):
    return datetime.fromtimestamp(hour_end_unix - 1800, TZ).date().isoformat()

def daily_raw_totals(rows):
    totals = {}
    for row in rows:
        day = day_of_hour(row["end"])
        totals[day] = totals.get(day, 0.0) + row["kw"]
    return totals

def calibration(actual_by_day, archive_rows, current_day):
    raw = daily_raw_totals(archive_rows)
    ratios = []
    for day in sorted(actual_by_day, reverse=True):
        if day >= current_day or day not in raw:
            continue
        actual = _number(actual_by_day[day], -1)
        theoretical = raw[day]
        if theoretical >= 35 and actual >= 15:
            r = actual / theoretical
            if 0.45 <= r <= 1.35:
                ratios.append((day, r, actual, theoretical))
        if len(ratios) >= 30:
            break
    if len(ratios) < 3:
        return 1.0, 0, None
    factor = max(0.5, min(1.25, median(r for _, r, _, _ in ratios)))
    fitting_error = 100.0 * median(abs(a - factor * e) / a for _, _, a, e in ratios if a > 0)
    return factor, len(ratios), round(fitting_error, 1)

def hourly_power_profile(hourly):
    """Interpolate hourly mean PV power into 15-minute DISPLAY points.

    This is interpolation, not independent quarter-hour weather prediction.
    Daily energy remains calculated from original hourly mean estimates.
    """
    midpoints = []
    for hour in hourly:
        start = datetime.fromisoformat(hour["start"])
        midpoints.append((start + timedelta(minutes=30), max(0.0, _number(hour.get("kw"))) * 1000))
    if not midpoints:
        return []
    profile = []
    for index, (mid, watts) in enumerate(midpoints):
        for quarter in range(4):
            when = mid - timedelta(minutes=22, seconds=30) + timedelta(minutes=15 * quarter)
            if index == 0:
                interpolated = watts
            elif index == len(midpoints)-1:
                previous = midpoints[index-1][1]
                fraction = max(0.0, min(1.0, (when - midpoints[index-1][0]).total_seconds()/3600))
                interpolated = previous + fraction*(watts - previous)
            else:
                nxt = midpoints[index+1]
                if when <= mid:
                    prev = midpoints[index-1]
                    fraction = (when-prev[0]).total_seconds()/3600
                    interpolated = prev[1] + fraction*(watts-prev[1])
                else:
                    fraction = (when-mid).total_seconds()/3600
                    interpolated = watts + fraction*(nxt[1]-watts)
            profile.append({"time": when.isoformat(), "power_w": round(max(0,interpolated))})
    return profile


def peak_kw_of_profile(profile):
    return round(max((p["power_w"] for p in profile), default=0) / 1000.0, 2)

def forecast_summary(forecast_rows, factor, actual_today, now):
    today = now.astimezone(TZ).date()
    today_iso = today.isoformat()
    days = [(today + timedelta(days=i)).isoformat() for i in range(8)]
    sums = {d: 0.0 for d in days}
    remaining = 0.0
    live_kw = 0.0
    by_day = {d: [] for d in days}
    raw_by_day = {d: 0.0 for d in days}
    now_ts = now.timestamp()
    current_interval_found = False
    for row in forecast_rows:
        date = day_of_hour(row["end"])
        if date not in sums:
            continue
        end = int(row["end"])
        start = end - 3600
        calibrated_kw = max(0, row["kw"] * factor)
        raw_by_day[date] += calibrated_kw
        if start <= now_ts < end:
            live_kw = calibrated_kw
            current_interval_found = True
        by_day[date].append({"start": datetime.fromtimestamp(start, TZ).isoformat(), "kw": round(calibrated_kw, 2)})
        if date == today_iso:
            fraction_left = max(0.0, min(1.0, (end - now_ts) / 3600.0))
            remaining += calibrated_kw * fraction_left
        else:
            sums[date] += calibrated_kw
    if not current_interval_found:
        live_kw = 0.0
    if actual_today is None:
        sums[today_iso] = raw_by_day[today_iso]
        remaining = max(0.0, sum(row["kw"] * factor * max(0, min(1, (int(row["end"]) - now_ts) / 3600)) for row in forecast_rows if day_of_hour(row["end"]) == today_iso))
    else:
        sums[today_iso] = actual_today + remaining
    daily = [{"date": d, "kwh": round(sums[d], 1)} for d in days]
    power_profile_today = hourly_power_profile(by_day[today_iso])
    power_profile_tomorrow = hourly_power_profile(by_day[days[1]])
    return {
        "today": round(sums[today_iso], 1),
        "tomorrow": round(sums[days[1]], 1),
        "next_7_days": round(sum(sums[d] for d in days[1:]), 1),
        "remaining_today": round(remaining, 1),
        "current_kw": round(live_kw, 2),
        "daily": daily,
        "hourly_today": by_day[today_iso],
        "hourly_tomorrow": by_day[days[1]],
        "power_profile_today": power_profile_today,
        "power_profile_tomorrow": power_profile_tomorrow,
        "peak_today_kw": peak_kw_of_profile(power_profile_today),
        "peak_tomorrow_kw": peak_kw_of_profile(power_profile_tomorrow),
        "forecast_date_today": today_iso,
        "forecast_date_tomorrow": days[1],
    }
