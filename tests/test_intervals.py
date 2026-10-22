from test_model import *
from datetime import datetime, timedelta
from solar_yield_forecast.model import TZ, forecast_summary, merge_quarter_hourly, hourly_power_profile, combine_weather

def test_quarter_energy_and_remaining():
    start = datetime(2026, 10, 22, 12, tzinfo=TZ)
    rows = [{'end': start.timestamp()+900*(i+1), 'kw': 4, 'interval_seconds':900} for i in range(4)]
    result = forecast_summary(rows, 1, 10, start+timedelta(minutes=7, seconds=30))
    assert result['remaining_today'] == 3.5
    assert result['today'] == 13.5
    assert result['current_kw'] == 4
    assert sum(p['energy_kwh'] for p in result['power_profile_today']) == 4

def test_fallback_no_double_counting():
    hourly = [{'end':3600,'kw':4},{'end':7200,'kw':4}]
    quarters = [{'end':900*i,'kw':4,'interval_seconds':900} for i in range(1,8)]
    rows = merge_quarter_hourly(hourly,quarters)
    assert len(rows) == 5
    assert sum(r['kw']*r.get('interval_seconds',3600)/3600 for r in rows)==8

def test_midnight_belongs_to_preceding_day():
    midnight = datetime(2026,10,23,tzinfo=TZ)
    rows = [{'end':midnight.timestamp(),'kw':4,'interval_seconds':900}]
    result = forecast_summary(rows,1,None,midnight-timedelta(minutes=15))
    assert result['today']==1
    assert result['tomorrow']==0

def test_dst_profile_uses_elapsed_time():
    start=datetime(2026,10,25,0,tzinfo=TZ)
    end=datetime(2026,10,26,0,tzinfo=TZ)
    rows=[{'start':datetime.fromtimestamp(t,TZ).isoformat(),'kw':4} for t in range(int(start.timestamp()),int(end.timestamp()),3600)]
    points=hourly_power_profile(rows)
    assert len(points)==100
    assert len({datetime.fromisoformat(p['time']).timestamp() for p in points})==100
    assert sum(p['energy_kwh'] for p in points)==100

def test_null_weather_is_not_zero_sunshine():
    group={'id':'a','count':1}
    response={'minutely_15':{'time':[900], 'global_tilted_irradiance':[None]}}
    assert combine_weather([response],[group], 'minutely_15',900)==[]
