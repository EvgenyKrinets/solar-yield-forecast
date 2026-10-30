"""Immutable prospective forecasts, separate from live and retrospective models."""
from copy import deepcopy
from datetime import datetime, timedelta, time
import math
from email.utils import parsedate_to_datetime


def retry_delay(error, now):
    """Respect a provider's longer Retry-After, if one was reported."""
    delay=300
    for request in (error or {}).get('requests', []):
        value=request.get('retry_after')
        if not value:
            continue
        try:
            seconds=float(value)
        except (ValueError,TypeError):
            try:
                seconds=(parsedate_to_datetime(value)-now).total_seconds()
            except (ValueError,TypeError,OverflowError):
                continue
        if math.isfinite(seconds):
            delay=max(delay,seconds)
    return delay


def evening_pending(ledger, now, tz):
    """Retry only within the local evening window, until a snapshot exists."""
    local = now.astimezone(tz)
    tomorrow = (local.date()+timedelta(days=1)).isoformat()
    return local.hour >= 20 and 'day_ahead' not in ledger.get(tomorrow, {})


def capture(ledger, result, now, tz, version, signature, weather_at):
    """First successful refresh after 20:00 / before generation; never backfill."""
    local = now.astimezone(tz)
    today = local.date().isoformat()
    cutoff = (local.date() - timedelta(days=730)).isoformat()
    for day in list(ledger):
        if day < cutoff:
            del ledger[day]
    if not weather_at or result.get('weather_status') != 'fresh':
        return
    weather = datetime.fromisoformat(weather_at).astimezone(tz)
    if not 0 <= (now - weather).total_seconds() <= 21600:
        return
    tomorrow = (local.date() + timedelta(days=1)).isoformat()
    for day in (today, tomorrow):
        points = result.get('power_profiles_by_date', {}).get(day, [])
        start = datetime.combine(datetime.fromisoformat(day).date(), time(), tz)
        stop = datetime.combine(start.date()+timedelta(days=1), time(), tz)
        expected = int((stop.timestamp()-start.timestamp())/900)
        stamps = sorted(datetime.fromisoformat(p['time']).timestamp() for p in points)
        if (len(points) != expected or stamps != [start.timestamp()+450+900*i for i in range(expected)]
                or not all(math.isfinite(p.get('power_w', float('nan'))) and p['power_w'] >= 0 for p in points)):
            continue
        daylight = [datetime.fromisoformat(p['time']).timestamp()-450 for p in points if p['power_w'] > 0]
        if not daylight:
            continue
        if day == tomorrow:
            if local.hour < 20 or weather.date() != local.date() or weather.hour < 20:
                continue
            kind = 'day_ahead'
        else:
            kind = 'morning' if now.timestamp() <= min(daylight) else 'late_start'
        slots = ledger.setdefault(day, {})
        if kind == 'late_start' and ('morning' in slots or 'day_ahead' in slots):
            continue
        # A late installation snapshot is informative, never an accuracy sample.
        if kind in slots:
            continue
        slots[kind] = {'kind': kind, 'recorded_at': now.isoformat(),
            'weather_updated_at': weather_at, 'version': version,
            'configuration': signature, 'points': deepcopy(points),
            'kwh': round(sum(p['energy_kwh'] for p in points), 2)}


def score(ledger, actuals, today):
    """Separate cohorts; WAPE and signed bias use completed positive daily totals."""
    rows = []
    for day, slots in sorted(ledger.items()):
        for kind, snapshot in slots.items():
            actual = actuals.get(day)
            completed = day < today and actual is not None and math.isfinite(actual) and actual > 0
            row = {k: v for k, v in snapshot.items() if k not in ('points', 'configuration')}
            row.update(date=day, actual_kwh=actual, completed=completed)
            if completed:
                delta = actual - snapshot['kwh']
                row.update(deviation_kwh=round(delta, 2), deviation_percent=round(100*delta/actual, 2))
            rows.append(row)
    summaries = {}
    end = datetime.fromisoformat(today).date()
    for days in (7, 30):
        start = (end-timedelta(days=days)).isoformat()
        for kind in ('day_ahead', 'morning'):
            selected = [r for r in rows if r['completed'] and r['kind'] == kind and start <= r['date'] < today]
            total = sum(r['actual_kwh'] for r in selected)
            summaries[f'{kind}_{days}'] = {'samples': len(selected),
                'wape_percent': round(100*sum(abs(r['actual_kwh']-r['kwh']) for r in selected)/total, 2) if total else None,
                'bias_percent': round(100*sum(r['kwh']-r['actual_kwh'] for r in selected)/total, 2) if total else None}
    return rows, summaries
