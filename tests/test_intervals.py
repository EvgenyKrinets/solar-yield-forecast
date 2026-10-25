from test_model import *
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from solar_yield_forecast.model import TZ, day_of_hour, forecast_summary, merge_quarter_hourly, hourly_power_profile, combine_weather, recent_live_scale

def test_quarter_energy_and_remaining():
    start = datetime(2026, 10, 22, 12, tzinfo=TZ)
    rows = [{'end': start.timestamp()+900*(i+1), 'kw': 4, 'interval_seconds':900} for i in range(4)]
    result = forecast_summary(rows, 1, 10, start+timedelta(minutes=7, seconds=30))
    assert result['remaining_today'] == 3.5
    assert result['today'] == 13.5
    assert result['current_kw'] == 4
    assert sum(p['energy_kwh'] for p in result['power_profile_today']) == 4

def test_site_timezone_controls_local_forecast_day():
    stamp=datetime(2026,1,2,0,30,tzinfo=timezone.utc).timestamp()
    assert day_of_hour(stamp, 3600, ZoneInfo("Europe/London")) == "2026-01-02"
    assert day_of_hour(stamp, 3600, ZoneInfo("America/Los_Angeles")) == "2026-01-01"

def test_thirty_day_summary_keeps_eight_day_total_separate():
    now=datetime(2026,10,22,tzinfo=TZ)
    rows=[]
    for day in range(30):
        rows.append({'end':(now+timedelta(days=day,hours=1)).timestamp(),'kw':day+1,
                     'forecast_source':'ensemble' if day>=16 else 'weather'})
    result=forecast_summary(rows,1,None,now)
    assert len(result['daily'])==30
    assert result['next_7_days']==sum(range(2,9))
    assert result['next_30_days']==sum(range(1,31))
    assert result['daily'][15]['source']=='weather'
    assert result['daily'][16]['source']=='ensemble'

def test_fallback_no_double_counting():
    hourly = [{'end':3600,'kw':4,'cloud_cover':18},{'end':7200,'kw':4}]
    quarters = [{'end':900*i,'kw':4,'interval_seconds':900} for i in range(1,8)]
    rows = merge_quarter_hourly(hourly,quarters)
    assert len(rows) == 5
    assert sum(r['kw']*r.get('interval_seconds',3600)/3600 for r in rows)==8
    assert all(row['cloud_cover']==18 for row in rows[:4])

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


def test_isolated_null_hour_does_not_reject_valid_forecast():
    group={'id':'a','count':1,'kwp':1}
    response={'hourly':{'time':[3600,7200,10800],
                        'global_tilted_irradiance':[0,None,500]}}
    rows=combine_weather([response],[group])
    assert [row['end'] for row in rows]==[3600,10800]
    assert rows[0]['kw']==0
    assert rows[1]['kw']>0


def test_profiles_are_available_for_past_and_future_selected_days():
    now=datetime(2026,10,24,8,tzinfo=TZ)
    rows=[]
    for offset in (-2,0,3):
        rows.append({'end':(now+timedelta(days=offset,hours=1)).timestamp(),
                     'kw':5,'interval_seconds':3600})
    result=forecast_summary(rows,1,None,now)
    profiles=result['power_profiles_by_date']
    assert (now-timedelta(days=2)).date().isoformat() in profiles
    assert now.date().isoformat() in profiles
    assert (now+timedelta(days=3)).date().isoformat() in profiles
    assert all(len(points)==4 for points in profiles.values())


def test_weather_metadata_survives_group_combination():
    group={'id':'a','count':1,'kwp':1}
    response={'hourly':{'time':[3600], 'global_tilted_irradiance':[500],
                        'cloud_cover':[12], 'direct_radiation':[420],
                        'diffuse_radiation':[80], 'shortwave_radiation':[500]}}
    row=combine_weather([response],[group])[0]
    assert row['cloud_cover']==12
    assert row['direct_radiation']==420
    assert row['diffuse_radiation']==80


def test_recent_live_scale_is_bounded_and_requires_four_samples():
    now=datetime(2026,10,24,9,tzinfo=TZ)
    samples=[{'time':(now-timedelta(minutes=10*i)).isoformat(),
              'actual_kw':12, 'forecast_interval_mean_kw':10} for i in range(5)]
    assert recent_live_scale(samples[:3],now,TZ)==(1.0,3)
    scale,count=recent_live_scale(samples,now,TZ)
    assert count==5
    assert scale==1.08
    confident=samples+[{'time':(now-timedelta(minutes=5*i+2)).isoformat(),
                        'actual_kw':12,'forecast_interval_mean_kw':10} for i in range(3)]
    assert recent_live_scale(confident,now,TZ)==(1.2,8)


def test_today_live_scale_does_not_change_tomorrow():
    now=datetime(2026,10,24,8,tzinfo=TZ)
    rows=[{'end':(now+timedelta(hours=1)).timestamp(),'kw':10,'cloud_cover':10},
          {'end':(now+timedelta(days=1,hours=1)).timestamp(),'kw':10,'cloud_cover':80}]
    result=forecast_summary(rows,1,None,now,today_scale=1.08)
    # With no measured daily-energy state, Today remains the complete baseline
    # model. The live correction is visible in current power and, once actual
    # energy exists, only in the remaining part of Today.
    assert result['today']==10
    assert result['tomorrow']==10
    assert result['model_today']==10
    assert result['power_profile_today'][0]['power_w']==10000
    assert result['current_kw']==10.8
    assert result['live_scale_scope']=='remaining_today_only'
    assert result['daily'][0]['weather_mode']=='clear'
    assert result['daily'][1]['weather_mode']=='cloudy'


def test_today_live_scale_changes_only_remaining_energy_when_actual_exists():
    now=datetime(2026,10,24,8,tzinfo=TZ)
    rows=[{'end':(now+timedelta(hours=1)).timestamp(),'kw':10}]
    result=forecast_summary(rows,1,4,now,today_scale=.86)
    assert result['model_today']==10
    assert result['remaining_today']==8.6
    assert result['today']==12.6
    assert result['power_profile_today'][0]['power_w']==10000
    assert result['current_kw']==8.6
