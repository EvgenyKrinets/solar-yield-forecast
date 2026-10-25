"""Site-independent residual profiles, exact runtime validation and safe fallbacks."""
from test_model import BASE
from solar_yield_forecast.shape import learn_site_profile, interval_shape, power_hours
from solar_yield_forecast.model import forecast_summary
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import math


def site_fixture(capacity=16, days=8, changed=False):
    weather, actual = [], {}
    start = datetime(2026, 10, 1, tzinfo=timezone.utc)
    for day in range(days):
        for q in range(96):
            t = (start+timedelta(days=day, minutes=q*15)).timestamp()
            p = capacity * max(0, math.sin(math.pi*(q-24)/48)) if 24 <= q <= 72 else 0
            correction = 1 if changed and day >= days-2 else 1.25 if q < 46 else .70
            weather.append(dict(end=t+900, interval_seconds=900, kw=p,
                                cloud_cover=4, direct_radiation=700, diffuse_radiation=100))
            actual[t] = (p*correction*.25, 900)
    return actual, weather


def test_site_profile_corrects_morning_and_afternoon_at_any_system_size():
    for capacity in (.5, 4, 16, 100):
        actual, weather = site_fixture(capacity)
        factors, report = learn_site_profile(actual,weather,1,'2026-10-20',ZoneInfo('Asia/Jerusalem'))
        assert report['status'] == 'active'
        assert report['resolution_minutes'] == 15
        assert factors['q36'] > factors['q60']
        assert report['after_wape_percent'] < report['before_wape_percent']*.95
        now = datetime(2026,10,8,tzinfo=timezone.utc)
        plain = forecast_summary(weather,1,None,now,tz=timezone.utc)
        shaped = forecast_summary(weather,1,None,now,shape=factors,tz=timezone.utc)
        assert shaped['model_today'] == plain['model_today']
        assert sum(p['energy_kwh'] for p in shaped['power_profile_today']) == __import__('pytest').approx(
            sum(p['energy_kwh'] for p in plain['power_profile_today']),abs=.001)


def test_site_profile_rejects_changed_pattern_and_missing_data():
    actual, weather = site_fixture(changed=True)
    assert learn_site_profile(actual,weather,1,'2026-10-20',timezone.utc)[0] == {}
    partial = {t:(a,100) for t,(a,_) in actual.items()}
    assert learn_site_profile(partial,weather,1,'2026-10-20',timezone.utc)[0] == {}
    assert learn_site_profile({},weather,1,'2026-10-20',timezone.utc)[0] == {}


def test_quarter_factors_integrate_exactly_and_recorder_bins_are_kwh():
    factors = {'q'+str(q):.7+q/100 for q in range(96)}
    for h in range(24):
        assert interval_shape(h*3600,3600,factors) == __import__('pytest').approx(
            sum(interval_shape(h*3600+i*900,900,factors) for i in range(4))/4)
    assert power_hours([(0,4)],900,900)[0] == [1,900]


def test_weather_is_not_replaced_by_the_learned_profile():
    actual, weather = site_fixture()
    factors,_ = learn_site_profile(actual,weather,1,'2026-10-20',timezone.utc)
    now = datetime(2026,10,8,tzinfo=timezone.utc)
    sunny = forecast_summary(weather,1,None,now,shape=factors,tz=timezone.utc)
    cloudy = forecast_summary([{**r,'kw':r['kw']*.5} for r in weather],1,None,now,shape=factors,tz=timezone.utc)
    assert cloudy['model_today'] == __import__('pytest').approx(sunny['model_today']/2,abs=.1)


def test_three_clear_days_can_validate_but_two_cannot():
    for days in (2,3):
        actual,weather=site_fixture(days=days)
        factors,report=learn_site_profile(actual,weather,1,'2026-10-20',timezone.utc)
        assert bool(factors) == (days==3)


def test_fallback_names_and_english_translations_exist_for_every_entity():
    import json
    strings=json.loads((BASE/'strings.json').read_text())
    english=json.loads((BASE/'translations/en.json').read_text())
    assert english['entity'] == strings['entity']
    assert 'SensorEntityDescription(key=key, name=label)' in (BASE/'sensor.py').read_text()


def test_hourly_reconstruction_preserves_each_hours_energy_and_native_quarters():
    from solar_yield_forecast.model import quarter_weather_rows
    rows=[dict(end=(h+1)*3600,kw=p) for h,p in enumerate([0,1,5,8,6,2,0])]
    quarters=quarter_weather_rows(rows)
    for i,row in enumerate(rows):
        assert sum(q['kw']*.25 for q in quarters[4*i:4*i+4]) == __import__('pytest').approx(row['kw'])
    assert quarters[8]['kw'] < quarters[11]['kw']
    native=[dict(end=900,kw=2,interval_seconds=900)]
    assert quarter_weather_rows(native)==native
