"""Time-weighted recorder analysis and held-out intraday bias calibration."""
from datetime import datetime, timezone
from collections import defaultdict
from statistics import median
from math import isfinite

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
    """Train on older days; require improvement on the newest two complete days.

    Weather is retrospective, so these scores describe model fit, not forecast
    skill. UTC hour avoids introducing a one-hour shift at a DST transition.
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
    report = {'status':'insufficient_history', 'training_days':max(0,len(days)-2), 'validation_days':min(2,len(days)),
              'metric':'Retrospective hourly energy WAPE, not day-ahead accuracy'}
    if len(days)<6:
        return {}, report
    train = [s for s in samples if s[0] < days[-2]]
    factors = {}
    for hour in range(24):
        ratios = [s[2]/s[3] for s in train if s[1]==hour]
        if len(ratios)>=4:
            factors[str(hour)] = max(.2,min(1.5,median(ratios)))
    test = [s for s in samples if s[0]>=days[-2] and str(s[1]) in factors]
    total = sum(s[2] for s in test)
    if len(test)<12 or total<30:
        return {}, report
    before = sum(abs(s[2]-s[3]) for s in test)/total
    after = sum(abs(s[2]-s[3]*factors[str(s[1])]) for s in test)/total
    accepted = after < before*.9
    report.update(status='active' if accepted else 'no_validated_improvement',
                  before_wape_percent=round(before*100,2), after_wape_percent=round(after*100,2))
    return (factors if accepted else {}), report
