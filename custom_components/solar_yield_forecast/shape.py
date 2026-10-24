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


def clear_weather_days(weather, today, tz):
    """Select recent days whose daylight forecast is consistently clear.

    Cloud cover is energy-weighted, so harmless dawn/dusk cloud does not
    disqualify an otherwise clear production curve. Direct/diffuse radiation
    is an additional guard when the provider supplies it.
    """
    rows_by_day = defaultdict(list)
    days_with_cloud = set()
    for row in weather:
        start = row['end'] - row.get('interval_seconds', 3600)
        day = datetime.fromtimestamp(start, tz).date().isoformat()
        if day >= today or row.get('kw', 0) <= 0:
            continue
        rows_by_day[day].append(row)
        if row.get('cloud_cover') is not None:
            days_with_cloud.add(day)
    clear, scores = set(), {}
    for day, rows in rows_by_day.items():
        peak = max((row.get('kw', 0) for row in rows), default=0)
        daylight = [row for row in rows if row.get('kw', 0) >= peak * .15]
        cloud_rows = [row for row in daylight if row.get('cloud_cover') is not None]
        if not daylight or len(cloud_rows) < max(4, len(daylight) // 2):
            continue
        weight = sum(row['kw'] for row in cloud_rows)
        cloud = sum(float(row['cloud_cover']) * row['kw'] for row in cloud_rows) / weight
        radiation = [row for row in daylight
                     if row.get('direct_radiation') is not None and row.get('diffuse_radiation') is not None]
        direct = sum(max(0.0, float(row['direct_radiation'])) for row in radiation)
        diffuse = sum(max(0.0, float(row['diffuse_radiation'])) for row in radiation)
        diffuse_share = diffuse / (direct + diffuse) if direct + diffuse > 0 else None
        scores[day] = {'cloud_cover_percent': round(cloud, 1),
                       'diffuse_share_percent': round(diffuse_share * 100, 1) if diffuse_share is not None else None}
        if cloud <= 25 and (diffuse_share is None or diffuse_share <= .48):
            clear.add(day)
    return clear, scores, len(days_with_cloud)

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
    all_days = sorted({s[0] for s in samples})
    clear_days, clear_scores, weather_days = clear_weather_days(weather, today, tz)
    selected_clear_days = [day for day in all_days if day in clear_days]
    use_clear_profile = weather_days >= 5 and len(selected_clear_days) >= 5
    days = selected_clear_days if use_clear_profile else all_days
    if use_clear_profile:
        validation_count = 2 if len(days) >= 8 else 1
        training_count = len(days) - validation_count
        min_support = max(3, min(8, (training_count * 3 + 4) // 5))
        min_test, min_test_energy = 6, 20
        improvement, peak_improvement = .98, 1.02
        history_mode = 'clear_weather_profile'
    elif len(days) >= 19:
        validation_count, min_support = 5, 10
        min_test, min_test_energy = 30, 60
        improvement, peak_improvement = .95, 1.0
        history_mode = 'full_30_day'
    elif len(days) >= 7:
        # Home Assistant commonly keeps only about ten Recorder days. Use a
        # stricter acceptance gate instead of disabling adaptation entirely.
        validation_count = 2
        training_count = len(days) - validation_count
        min_support = max(4, min(10, (training_count*3+4)//5))
        min_test, min_test_energy = 12, 30
        # Two held-out days are noisy enough that demanding a full 10% WAPE
        # gain rejects useful, repeatable profiles on a boundary (for example
        # 12.90% -> 11.67%).  Still require a material 5% whole-day gain and
        # an independently non-worsening peak before activating the profile.
        improvement, peak_improvement = .95, 1.0
        history_mode = 'short_history'
    else:
        validation_count, history_mode = min(2, len(days)), 'insufficient'
    report = {'status':'insufficient_history', 'history_mode':history_mode,
              'available_days':len(all_days), 'selected_profile_days':len(days),
              'clear_weather_days':len(selected_clear_days),
              'training_days':max(0,len(days)-validation_count),
              'validation_days':validation_count,
              'metric':'Retrospective hourly energy WAPE, not day-ahead accuracy'}
    if clear_scores:
        report['clear_day_weather'] = {day: clear_scores[day] for day in selected_clear_days[-10:]}
    if len(days) < 7:
        # Five or six provider-confirmed clear days are sufficient for the
        # installation-specific profile, even though generic learning still
        # requires seven days.
        if not use_clear_profile:
            return {}, report
    validation_days = set(days[-validation_count:])
    selected_days = set(days)
    train = [s for s in samples if s[0] in selected_days and s[0] not in validation_days]

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
        if len(ratios) >= min_support:
            # Shape is deliberately conservative. Larger amplitude errors are
            # the job of the daily calibration, not the hourly correction.
            lower, upper = (.65, 1.35) if use_clear_profile else (.82, 1.18)
            raw[hour] = max(lower, min(upper, median(ratios)))
            support[hour] = len(ratios)
    if len(raw) < 8:
        return {}, report

    # The validated clear profile uses a three-hour triangular smoother so it
    # can reproduce broad orientation bias. Generic fallback keeps the former
    # five-hour protection. Neither mode lets missing night-time factors pull
    # sunrise/sunset towards an invented value.
    weights = (1, 2, 1) if use_clear_profile else (1, 2, 3, 2, 1)
    radius = len(weights) // 2
    smooth = {}
    for hour in raw:
        values = [(raw[h], weights[offset+radius]) for offset in range(-radius, radius + 1)
                  if (h := hour+offset) in raw]
        smooth[hour] = sum(value*weight for value, weight in values) / sum(weight for _, weight in values)

    # Limit the slope of the learned correction. This still permits broad
    # orientation/shading bias, but cannot create a narrow V-shaped peak.
    ordered = sorted(smooth)
    max_hourly_change = .08 if use_clear_profile else .035
    for _ in range(3):
        for left, right in zip(ordered, ordered[1:]):
            if right != left + 1:
                continue
            smooth[right] = max(smooth[left]-max_hourly_change, min(smooth[left]+max_hourly_change, smooth[right]))
        for right, left in zip(reversed(ordered[1:]), reversed(ordered[:-1])):
            if right != left + 1:
                continue
            smooth[left] = max(smooth[right]-max_hourly_change, min(smooth[right]+max_hourly_change, smooth[left]))
    factors = {str(hour): round(value, 5) for hour, value in smooth.items()}

    test = [s for s in samples if s[0] in validation_days and str(s[1]) in factors]
    total = sum(s[2] for s in test)
    if len(test) < min_test or total < min_test_energy:
        return {}, report
    before = sum(abs(s[2]-s[3]) for s in test)/total
    after = sum(abs(s[2]-s[3]*interval_shape(s[1]*3600,3600,factors)) for s in test)/total
    peak_limit = max(s[3] for s in test) * .72
    peak = [s for s in test if s[3] >= peak_limit]
    peak_total = sum(s[2] for s in peak)
    peak_before = sum(abs(s[2]-s[3]) for s in peak)/peak_total if peak_total else 0
    peak_after = sum(abs(s[2]-s[3]*interval_shape(s[1]*3600,3600,factors)) for s in peak)/peak_total if peak_total else 0
    accepted = after < before*improvement and peak_after <= peak_before*peak_improvement
    report.update(status='active' if accepted else 'no_validated_improvement',
                  before_wape_percent=round(before*100,2), after_wape_percent=round(after*100,2),
                  peak_before_wape_percent=round(peak_before*100,2), peak_after_wape_percent=round(peak_after*100,2),
                  minimum_hour_support=min_support,
                  weather_always_applied=True,
                  required_overall_improvement_percent=round((1-improvement)*100,1),
                  allowed_peak_regression_percent=round((peak_improvement-1)*100,1),
                  maximum_hourly_factor_change=max_hourly_change,
                  factor_support_utc={str(hour): count for hour, count in support.items()})
    return (factors if accepted else {}), report
