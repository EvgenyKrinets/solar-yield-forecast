"""Time-weighted recorder analysis and held-out intraday bias calibration."""
from datetime import datetime, timezone
from collections import defaultdict
from statistics import median
from math import isfinite

def shape_at(stamp, factors):
    """Interpolate UTC hourly corrections between hour centres, without steps."""
    hour = (stamp / 3600 - .5) % 24
    left = int(hour)
    fraction = hour - left
    a = factors.get(str(left), 1.0)
    b = factors.get(str((left + 1) % 24), 1.0)
    return a + (b - a) * fraction


def interval_shape(start, seconds, factors):
    """Integrate the piecewise-linear correction exactly over the interval."""
    if not factors:
        return 1.0
    end = start + seconds
    cursor, total = start, 0.0
    while cursor < end:
        boundary = (int((cursor - 1800) // 3600) + 1) * 3600 + 1800
        stop = min(end, boundary)
        total += shape_at((cursor + stop) / 2, factors) * (stop - cursor)
        cursor = stop
    return total / seconds

def power_hours(states, end):
    """Integrate held states in UTC; missing/invalid states break coverage."""
    rows = sorted(states, key=lambda x: x[0])
    bins = defaultdict(lambda: [0.0, 0.0])
    for i, (stamp, value) in enumerate(rows):
        stop = min(rows[i+1][0] if i+1<len(rows) else end, end)
        if value is None or not isfinite(value) or value < 0:
            continue
        while stamp < stop:
            bucket = int(stamp // 3600) * 3600
            until = min(stop, bucket + 3600)
            bins[bucket][0] += value * (until-stamp) / 3600
            bins[bucket][1] += until-stamp
            stamp = until
    return dict(bins)

def learn_shape(hours, weather, factor, today, tz):
    """Learn a conservative, smooth intraday correction from 30-day history.

    Each day is normalised by its daily actual/model ratio before its shape is
    used.  This prevents a generally cloudy or weak day from carving a dip into
    one hour.  The newest five complete days are held out and peak hours must
    improve independently of the whole-day score.
    """
    samples = []
    for row in weather:
        start = row['end'] - 3600
        local = datetime.fromtimestamp(start, tz)
        actual, coverage = hours.get(start, (0, 0))
        predicted = row['kw'] * factor
        if local.date().isoformat() < today and coverage >= 3550 and predicted >= .5:
            samples.append((local.date().isoformat(), datetime.fromtimestamp(start, timezone.utc).hour, actual, predicted))
    days = sorted({s[0] for s in samples})
    validation_count = min(5, max(0, len(days) - 14))
    report = {'status':'insufficient_history', 'training_days':max(0,len(days)-validation_count), 'validation_days':validation_count,
              'metric':'Retrospective hourly energy WAPE, not day-ahead accuracy'}
    if len(days)<19 or validation_count < 5:
        return {}, report
    validation_days = set(days[-validation_count:])
    train = [s for s in samples if s[0] not in validation_days]

    # Remove daily amplitude before learning the intraday shape. Daily
    # amplitude is already handled by the independent energy calibration.
    daily = defaultdict(lambda: [0.0, 0.0])
    for day, _, actual, predicted in train:
        daily[day][0] += actual
        daily[day][1] += predicted
    daily_scale = {day: actual/predicted for day, (actual, predicted) in daily.items()
                   if actual >= 15 and predicted >= 15 and .45 <= actual/predicted <= 1.55}
    raw = {}
    support = {}
    for hour in range(24):
        ratios = [actual/(predicted*daily_scale[day]) for day, h, actual, predicted in train
                  if h == hour and day in daily_scale and predicted >= .5]
        if len(ratios) >= 10:
            # Shape is deliberately conservative. Larger amplitude errors are
            # the job of the daily calibration, not the hourly correction.
            raw[hour] = max(.82, min(1.18, median(ratios)))
            support[hour] = len(ratios)
    if len(raw) < 8:
        return {}, report

    # Five-hour triangular smoothing suppresses one-hour notches. Missing
    # night-time factors do not pull sunrise/sunset towards an invented value.
    weights = (1, 2, 3, 2, 1)
    smooth = {}
    for hour in raw:
        values = [(raw[h], weights[offset+2]) for offset in range(-2, 3)
                  if (h := hour+offset) in raw]
        smooth[hour] = sum(value*weight for value, weight in values) / sum(weight for _, weight in values)

    # Limit the slope of the learned correction. This still permits broad
    # orientation/shading bias, but cannot create a narrow V-shaped peak.
    ordered = sorted(smooth)
    for _ in range(3):
        for left, right in zip(ordered, ordered[1:]):
            if right != left + 1:
                continue
            smooth[right] = max(smooth[left]-.035, min(smooth[left]+.035, smooth[right]))
        for right, left in zip(reversed(ordered[1:]), reversed(ordered[:-1])):
            if right != left + 1:
                continue
            smooth[left] = max(smooth[right]-.035, min(smooth[right]+.035, smooth[left]))
    factors = {str(hour): round(value, 5) for hour, value in smooth.items()}

    test = [s for s in samples if s[0] in validation_days and str(s[1]) in factors]
    total = sum(s[2] for s in test)
    if len(test)<30 or total<60:
        return {}, report
    before = sum(abs(s[2]-s[3]) for s in test)/total
    after = sum(abs(s[2]-s[3]*interval_shape(s[1]*3600,3600,factors)) for s in test)/total
    peak_limit = max(s[3] for s in test) * .72
    peak = [s for s in test if s[3] >= peak_limit]
    peak_total = sum(s[2] for s in peak)
    peak_before = sum(abs(s[2]-s[3]) for s in peak)/peak_total if peak_total else 0
    peak_after = sum(abs(s[2]-s[3]*interval_shape(s[1]*3600,3600,factors)) for s in peak)/peak_total if peak_total else 0
    accepted = after < before*.95 and peak_after <= peak_before
    report.update(status='active' if accepted else 'no_validated_improvement',
                  before_wape_percent=round(before*100,2), after_wape_percent=round(after*100,2),
                  peak_before_wape_percent=round(peak_before*100,2), peak_after_wape_percent=round(peak_after*100,2),
                  factor_support_utc={str(hour): count for hour, count in support.items()})
    return (factors if accepted else {}), report
