"""Dependency-free solar calculation and forecast calibration utilities."""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from statistics import median
from zoneinfo import ZoneInfo
import math
from .shape import interval_shape
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
    capacity_kwp = _number(
        group.get("kwp"),
        _number(group.get("count")) * _number(group.get("panel_power_w"), PANEL_KWP * 1000) / 1000,
    )
    return capacity_kwp * gti / 1000.0 * 0.92 * temp_factor

def combine_weather(group_responses, groups=PANEL_GROUPS, section="hourly", interval_seconds=3600):
    results = {}
    if len(group_responses) != len(groups):
        raise ValueError("Missing panel group weather response")
    for group_index, (group, response) in enumerate(zip(groups, group_responses)):
        hourly = response.get(section) or {}
        times = hourly.get("time") or []
        irradiances = hourly.get("global_tilted_irradiance") or []
        temps = hourly.get("temperature_2m") or []
        winds = hourly.get("wind_speed_10m") or []
        if not times or len(times) != len(irradiances):
            raise ValueError(f"Missing radiation from Open-Meteo for {group['id']}")
        for i, stamp in enumerate(times):
            if _number(irradiances[i], None) is None:
                if section == "minutely_15":
                    continue
                raise ValueError("Missing hourly irradiance")
            stamp = int(stamp)
            entry = results.setdefault(stamp, {"end": stamp, "interval_seconds": interval_seconds, "group_kw": {}, "kw": 0.0})
            kw = estimate_kw(irradiances[i], temps[i] if i < len(temps) else 25, winds[i] if i < len(winds) else 0, group)
            entry["group_kw"][group["id"]] = kw
            entry["kw"] += kw
            # These site-wide weather values are identical for every panel
            # orientation. Keep one copy so profile learning can select truly
            # clear historical days while GTI remains the power multiplier.
            if group_index == 0:
                for variable in ("cloud_cover", "direct_radiation", "diffuse_radiation", "shortwave_radiation"):
                    values = hourly.get(variable) or []
                    value = _number(values[i], None) if i < len(values) else None
                    if value is not None:
                        entry[variable] = value
    return [results[k] for k in sorted(results) if len(results[k]["group_kw"]) == len(groups)]

def day_of_hour(hour_end_unix, interval_seconds=3600, tz=TZ):
    return datetime.fromtimestamp(hour_end_unix - interval_seconds / 2, tz).date().isoformat()

def daily_raw_totals(rows, tz=TZ):
    totals = {}
    for row in rows:
        day = day_of_hour(row["end"], row.get("interval_seconds", 3600), tz)
        totals[day] = totals.get(day, 0.0) + row["kw"] * row.get("interval_seconds", 3600) / 3600
    return totals

def calibration(actual_by_day, archive_rows, current_day, tz=TZ):
    raw = daily_raw_totals(archive_rows, tz)
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

def hourly_power_profile(hourly, tz=TZ):
    """Produce interval midpoints, preserving energy for hourly fallback rows."""
    profile = []
    for hour in hourly:
        start = datetime.fromisoformat(hour["start"])
        seconds = hour.get("interval_seconds", 3600)
        for offset in range(0, seconds, 900):
            # Work on the UTC timeline, including DST transitions.
            when = datetime.fromtimestamp(start.timestamp() + offset + 450, tz)
            profile.append({"time": when.isoformat(), "power_w": round(hour["kw"] * 1000),
                            "energy_kwh": round(hour["kw"] / 4, 5),
                            "source": "open_meteo_15min" if seconds == 900 else "hourly_mean"})
    return profile



def peak_kw_of_profile(profile):
    return round(max((p["power_w"] for p in profile), default=0) / 1000.0, 2)

def forecast_summary(forecast_rows, factor, actual_today, now, shape=None, forecast_days=30, tz=TZ, today_scale=1.0):
    today = now.astimezone(tz).date()
    today_iso = today.isoformat()
    days = [(today + timedelta(days=i)).isoformat() for i in range(forecast_days)]
    sums = {d: 0.0 for d in days}
    remaining = 0.0
    live_kw = 0.0
    by_day = {d: [] for d in days}
    raw_by_day = {d: 0.0 for d in days}
    sources_by_day = {d: set() for d in days}
    cloud_by_day = {d: [0.0, 0.0] for d in days}
    now_ts = now.timestamp()
    current_interval_found = False
    for row in forecast_rows:
        date = day_of_hour(row["end"], row.get("interval_seconds", 3600), tz)
        if date not in sums:
            continue
        end = int(row["end"])
        seconds = row.get("interval_seconds", 3600)
        start = end - seconds
        duration_hours = seconds / 3600
        live_scale = today_scale if date == today_iso else 1.0
        calibrated_kw = max(0, row["kw"] * factor * interval_shape(start, seconds, shape or {}) * live_scale)
        sources_by_day[date].add(row.get("forecast_source", "weather"))
        cloud = _number(row.get("cloud_cover"), None)
        if cloud is not None and row["kw"] > 0.1:
            weight = row["kw"] * duration_hours
            cloud_by_day[date][0] += cloud * weight
            cloud_by_day[date][1] += weight
        raw_by_day[date] += calibrated_kw * duration_hours
        if start <= now_ts < end:
            live_kw = calibrated_kw
            current_interval_found = True
        by_day[date].append({"start": datetime.fromtimestamp(start, tz).isoformat(), "kw": calibrated_kw, "interval_seconds": seconds})
        if date == today_iso:
            fraction_left = max(0.0, min(1.0, (end - now_ts) / seconds))
            remaining += calibrated_kw * fraction_left * duration_hours
        else:
            sums[date] += calibrated_kw * duration_hours
    if not current_interval_found:
        live_kw = 0.0
    if actual_today is None:
        sums[today_iso] = raw_by_day[today_iso]

    else:
        sums[today_iso] = actual_today + remaining
    daily = []
    for d in days:
        if not sources_by_day[d]:
            continue
        cloud_sum, cloud_weight = cloud_by_day[d]
        cloud = round(cloud_sum / cloud_weight) if cloud_weight else None
        weather_mode = None if cloud is None else "clear" if cloud <= 25 else "mixed" if cloud <= 65 else "cloudy"
        daily.append({"date": d, "kwh": round(sums[d], 1),
                      "source": "ensemble" if "ensemble" in sources_by_day[d] else "weather",
                      "weather_mode": weather_mode, "cloud_cover_percent": cloud})
    power_profile_today = hourly_power_profile(by_day[today_iso], tz)
    power_profile_tomorrow = hourly_power_profile(by_day[days[1]], tz)
    return {
        "today": round(sums[today_iso], 1),
        "model_today": round(raw_by_day[today_iso], 1),
        "tomorrow": round(sums[days[1]], 1),
        "next_7_days": round(sum(sums[d] for d in days[1:8]), 1),
        "next_30_days": round(sum(sums[d] for d in days), 1),
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
        "live_scale_percent": round(today_scale * 100, 1),
    }


def recent_live_scale(comparisons, now, tz=TZ, minutes=90):
    """Return a conservative same-day nowcast correction from recent PV data."""
    cutoff = now.timestamp() - minutes * 60
    today = now.astimezone(tz).date()
    ratios = []
    for sample in comparisons:
        try:
            stamp = datetime.fromisoformat(sample["time"])
            actual = float(sample["actual_kw"])
            predicted = float(sample["forecast_interval_mean_kw"])
        except (KeyError, TypeError, ValueError):
            continue
        if stamp.timestamp() < cutoff or stamp.astimezone(tz).date() != today or predicted < 1.0:
            continue
        ratio = actual / predicted
        if 0.5 <= ratio <= 1.5:
            ratios.append(ratio)
    if len(ratios) < 4:
        return 1.0, len(ratios)
    # Live measurements refine the weather forecast but cannot make the
    # remaining day jump wildly after a short cloud or sensor transient.
    return max(0.92, min(1.08, median(ratios))), len(ratios)


def merge_quarter_hourly(hourly, quarters):
    """Replace only complete hours; retain hourly coverage for the full horizon."""
    by_end = {r["end"]: r for r in quarters}
    result = []
    for row in hourly:
        ends = [row["end"] - 2700 + i * 900 for i in range(4)]
        if all(e in by_end for e in ends):
            site_weather = {key: row[key] for key in
                            ("cloud_cover", "direct_radiation", "diffuse_radiation", "shortwave_radiation")
                            if key in row}
            result.extend([{**site_weather, **by_end[e]} for e in ends])
        else:
            result.append(row)
    return result
