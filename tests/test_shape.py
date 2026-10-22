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

def fixture(correction):
    weather=[];actual={}
    for day in range(6):
        for hour in range(7,18):
            t=datetime(2026,10,10+day,hour,tzinfo=timezone.utc).timestamp()
            weather.append({'end':t+3600,'kw':10})
            actual[t]=[10*correction(day,hour),3600]
    return actual,weather

def test_holdout_approves_repeatable_bias():
    actual,weather=fixture(lambda d,h:.5 if h>=15 else 1.1)
    factors,report=learn_shape(actual,weather,1,'2026-10-16',TZ)
    assert report['status']=='active'
    assert report['after_wape_percent']==0
    assert factors['15']==.5

def test_holdout_rejects_changed_pattern():
    actual,weather=fixture(lambda d,h:.5 if d<4 else 1)
    factors,report=learn_shape(actual,weather,1,'2026-10-16',TZ)
    assert factors=={}
    assert report['status']=='no_validated_improvement'

def test_insufficient_and_partial_history():
    actual,weather=fixture(lambda d,h:.5)
    assert learn_shape(actual,weather[:44],1,'2026-10-16',TZ)[0]=={}
    assert learn_shape({k:[v[0],1000] for k,v in actual.items()},weather,1,'2026-10-16',TZ)[0]=={}

def test_shape_and_model_total_separate_from_actual():
    start=datetime(2026,10,22,12,tzinfo=TZ)
    row={'end':start.timestamp()+900,'kw':4,'interval_seconds':900}
    result=forecast_summary([row],1,90,start+timedelta(hours=2),{str(start.astimezone(timezone.utc).hour):.5})
    assert result['today']==90
    assert result['model_today']==.5
    assert result['power_profile_today'][0]['power_w']==2000
