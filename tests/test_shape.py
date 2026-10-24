from test_model import BASE
import importlib.util,sys
spec=importlib.util.spec_from_file_location('solar_yield_forecast.shape',BASE/'shape.py')
module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
from solar_yield_forecast.shape import power_hours,learn_shape
from solar_yield_forecast.model import forecast_summary,TZ
from datetime import datetime,timedelta,timezone

def test_weighted_hours_and_invalid_gap():
    assert power_hours([(0,1),(60,3)],3600)[0]==[178/60,3600]
    assert power_hours([(0,1),(1800,None)],3600)[0]==[.5,1800]

def fixture(correction, days=24):
    weather=[];actual={}
    for day in range(days):
        for hour in range(7,18):
            t=(datetime(2026,9,20,hour,tzinfo=timezone.utc)+timedelta(days=day)).timestamp()
            weather.append({'end':t+3600,'kw':10})
            actual[t]=[10*correction(day,hour),3600]
    return actual,weather

def test_holdout_approves_repeatable_bias():
    actual,weather=fixture(lambda d,h:.8 if h>=15 else 1.08)
    factors,report=learn_shape(actual,weather,1,'2026-10-20',TZ)
    assert report['status']=='active'
    assert report['after_wape_percent'] < report['before_wape_percent'] * .95
    assert factors['15'] < 1
    assert report['factor_support_utc']['15'] >= 10

def test_holdout_rejects_changed_pattern():
    actual,weather=fixture(lambda d,h:(.8 if h>=15 else 1.08) if d<19 else 1.0)
    factors,report=learn_shape(actual,weather,1,'2026-10-20',TZ)
    assert factors=={}
    assert report['status']=='no_validated_improvement'

def test_insufficient_and_partial_history():
    actual,weather=fixture(lambda d,h:.5)
    assert learn_shape(actual,weather[:6*11],1,'2026-10-20',TZ)[0]=={}
    assert learn_shape({k:[v[0],1000] for k,v in actual.items()},weather,1,'2026-10-20',TZ)[0]=={}

def test_short_recorder_history_uses_stricter_fallback():
    actual,weather=fixture(lambda d,h:.82 if h>=15 else 1.08, days=9)
    factors,report=learn_shape(actual,weather,1,'2026-10-20',TZ)
    assert report['history_mode']=='short_history'
    assert report['available_days']==9
    assert report['validation_days']==2
    assert report['minimum_hour_support']>=4
    assert factors and factors['15'] < 1

def test_short_history_rejects_pattern_missing_from_validation():
    actual,weather=fixture(lambda d,h:(.8 if h>=15 else 1.08) if d<7 else 1, days=9)
    factors,report=learn_shape(actual,weather,1,'2026-10-20',TZ)
    assert factors=={}
    assert report['status']=='no_validated_improvement'

def test_daily_amplitude_is_not_learned_as_hourly_shape():
    actual,weather=fixture(lambda d,h:.65 if d%3==0 else 1.15)
    factors,report=learn_shape(actual,weather,1,'2026-10-20',TZ)
    assert factors=={}
    assert report['status']=='no_validated_improvement'

def test_hourly_shape_is_smooth_and_cannot_form_a_narrow_notch():
    actual,weather=fixture(lambda d,h:.82 if h==12 else 1.02)
    factors,_=learn_shape(actual,weather,1,'2026-10-20',TZ)
    if factors:
        ordered=sorted((int(hour),value) for hour,value in factors.items())
        assert all(abs(a[1]-b[1]) <= .03501 for a,b in zip(ordered,ordered[1:]) if b[0]==a[0]+1)

def test_shape_and_model_total_separate_from_actual():
    start=datetime(2026,10,22,12,tzinfo=TZ)
    row={'end':start.timestamp()+900,'kw':4,'interval_seconds':900}
    result=forecast_summary([row],1,90,start+timedelta(hours=2),{str(h):.5 for h in range(24)})
    assert result['today']==90
    assert result['model_today']==1
    assert result['power_profile_today'][0]['power_w']==4000


def test_shape_redistributes_power_without_changing_daily_energy():
    start=datetime(2026,10,24,8,tzinfo=TZ)
    rows=[{'end':(start+timedelta(hours=i+1)).timestamp(),'kw':10}
          for i in range(6)]
    utc_hours=[datetime.fromtimestamp(row['end']-3600,timezone.utc).hour for row in rows]
    factors={str(hour):.6 for hour in range(24)}
    factors[str(utc_hours[2])]=1.6
    factors[str(utc_hours[3])]=1.6
    result=forecast_summary(rows,.82,None,start,shape=factors)
    powers=[point['power_w'] for point in result['power_profile_today']]
    assert result['model_today']==49.2
    assert abs(sum(point['energy_kwh'] for point in result['power_profile_today'])-49.2)<1e-4
    assert max(powers)>8200
    assert min(powers)<8200


def test_shape_continuity_and_interval_energy():
    from solar_yield_forecast.shape import shape_at, interval_shape
    factors = {'10':1.2, '11':.8, '12':1.1}
    assert abs(shape_at(11*3600-.001,factors)-shape_at(11*3600+.001,factors)) < 1e-6
    hourly=interval_shape(11*3600,3600,factors)
    quarters=sum(interval_shape(11*3600+i*900,900,factors) for i in range(4))/4
    assert abs(hourly-quarters)<1e-12
    assert interval_shape(0,3600,{})==1


def test_shape_is_continuous_at_missing_hour_boundaries():
    from solar_yield_forecast.shape import shape_at
    for hour in [9.5,10.5,11.5,23.5,24.5]:
        t=hour*3600
        assert abs(shape_at(t-.001,{'10':.5})-shape_at(t+.001,{'10':.5}))<1e-6


def test_clear_days_build_real_profile_while_cloudy_days_are_excluded():
    actual,weather=fixture(lambda d,h:(1.16 if h<14 else .72) if d<8 else (.55 if h in (11,12) else 1.0), days=11)
    for row in weather:
        day=(datetime.fromtimestamp(row['end']-3600, timezone.utc).date()-datetime(2026,9,20,tzinfo=timezone.utc).date()).days
        clear=day<8
        row.update(cloud_cover=8 if clear else 82,
                   direct_radiation=700 if clear else 120,
                   diffuse_radiation=100 if clear else 380,
                   shortwave_radiation=800 if clear else 500)
    factors,report=learn_shape(actual,weather,1,'2026-10-20',TZ)
    assert report['history_mode']=='clear_weather_profile'
    assert report['clear_weather_days']==8
    assert report['selected_profile_days']==8
    assert report['weather_always_applied'] is True
    assert factors['10'] > 1
    assert factors['15'] < 1


def test_constant_shape_cannot_multiply_weather_energy():
    now=datetime(2026,10,24,8,tzinfo=TZ)
    rows=[{'end':(now+timedelta(hours=1)).timestamp(),'kw':10},
          {'end':(now+timedelta(hours=2)).timestamp(),'kw':5}]
    shaped=forecast_summary(rows,1,None,now,{str(hour):1.2 for hour in range(24)})
    powers=[point['power_w'] for point in shaped['power_profile_today']]
    assert max(powers)==10000
    assert min(powers)==5000
    assert shaped['model_today']==15
