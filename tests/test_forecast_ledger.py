import importlib.util
from pathlib import Path
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

spec = importlib.util.spec_from_file_location('ledger', Path(__file__).resolve().parents[1]/'custom_components/solar_yield_forecast/forecast_ledger.py')
ledger = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ledger)


def fixture(now, tz):
    local = now.astimezone(tz)
    profiles = {}
    for offset in (0, 1):
        d = local.date()+timedelta(days=offset)
        start = datetime.combine(d, datetime.min.time(), tz)
        end = datetime.combine(d+timedelta(days=1), datetime.min.time(), tz)
        points = []
        for i in range(int((end.timestamp()-start.timestamp())/900)):
            t = datetime.fromtimestamp(start.timestamp()+i*900+450, tz)
            w = 1000 if 7 <= t.hour < 17 else 0
            points.append(dict(time=t.isoformat(), power_w=w, energy_kwh=w/4000))
        profiles[d.isoformat()] = points
    return dict(weather_status='fresh', power_profiles_by_date=profiles)


def test_frozen_day_ahead_survives_refresh_and_restart():
    import json
    tz=ZoneInfo('Asia/Jerusalem'); now=datetime(2026,10,24,20,10,tzinfo=tz)
    data={}; result=fixture(now,tz)
    ledger.capture(data,result,now,tz,'1.6.0','site',now.isoformat())
    snap=data['2026-10-25']['day_ahead']
    assert snap['kwh']==10
    restored=json.loads(json.dumps(data))
    result['power_profiles_by_date']['2026-10-25'][40]['energy_kwh']=999
    ledger.capture(restored,result,now+timedelta(minutes=10),tz,'new','site',now.isoformat())
    assert restored['2026-10-25']['day_ahead']==snap
    # Israel DST fall-back day is 25 hours, without duplicate UTC intervals.
    assert len(snap['points'])==100


def test_morning_and_late_start_and_no_backfill():
    tz=timezone.utc; now=datetime(2026,10,26,6,tzinfo=tz); data={}
    ledger.capture(data,fixture(now,tz),now,tz,'v','s',now.isoformat())
    assert set(data['2026-10-26'])=={'morning'}
    late=now+timedelta(hours=6)
    ledger.capture(data,fixture(late,tz),late,tz,'v','s',late.isoformat())
    assert set(data['2026-10-26'])=={'morning'}
    first={}
    ledger.capture(first,fixture(late,tz),late,tz,'v','s',late.isoformat())
    rows,scores=ledger.score(first,{'2026-10-26':8},'2026-10-27')
    assert rows[0]['kind']=='late_start' and scores['morning_7']['samples']==0
    assert '2026-10-25' not in first


def test_fixed_cohorts_and_calendar_metrics():
    tz=timezone.utc; now=datetime(2026,10,25,20,tzinfo=tz); data={}
    ledger.capture(data,fixture(now,tz),now,tz,'v','s',now.isoformat())
    rows,scores=ledger.score(data,{'2026-10-26':8},'2026-10-27')
    assert scores['day_ahead_7']==dict(samples=1,wape_percent=25,bias_percent=25)
    row=next(r for r in rows if r['kind']=='day_ahead')
    assert row['deviation_kwh']==-2
    assert ledger.score(data,{'2026-10-26':0},'2026-10-27')[1]['day_ahead_7']['samples']==0
    assert ledger.score(data,{'2026-10-26':8},'2026-10-26')[1]['day_ahead_7']['samples']==0


def test_stale_partial_and_wrong_evening_do_not_capture():
    tz=timezone.utc; now=datetime(2026,10,25,20,tzinfo=tz)
    for status,age in [('stale',0),('fresh',7)]:
        data={}; result=fixture(now,tz); result['weather_status']=status
        ledger.capture(data,result,now,tz,'v','s',(now-timedelta(hours=age)).isoformat())
        assert data=={}
    data={}; result=fixture(now,tz)
    ledger.capture(data,result,now,tz,'v','s',(now-timedelta(hours=1)).isoformat())
    assert '2026-10-26' not in data
    now=now.replace(hour=6);result=fixture(now,tz)
    result['power_profiles_by_date']['2026-10-25'].pop()
    data={};ledger.capture(data,result,now,tz,'v','s',now.isoformat())
    assert data=={}


def test_originals_survive_for_yearly_review_but_expire_after_two_years():
    tz=timezone.utc; now=datetime(2026,10,25,20,tzinfo=tz)
    data={'2025-01-01': {'day_ahead': {'kwh': 10}}, '2023-01-01': {'day_ahead': {'kwh': 10}}}
    ledger.capture(data,fixture(now,tz),now,tz,'v','s',now.isoformat())
    assert '2025-01-01' in data
    assert '2023-01-01' not in data


def test_evening_retries_until_midnight_and_stops_after_success():
    tz=ZoneInfo('Asia/Jerusalem');data={}
    assert not ledger.evening_pending(data,datetime(2026,10,30,19,59,tzinfo=tz),tz)
    for hour in (20,21,22,23):
        now=datetime(2026,10,30,hour,59,tzinfo=tz)
        assert ledger.evening_pending(data,now,tz)
        failed=fixture(now,tz);failed['weather_status']='stale'
        ledger.capture(data,failed,now,tz,'v','s',now.isoformat())
        assert ledger.evening_pending(data,now,tz)
    ledger.capture(data,fixture(now,tz),now,tz,'v','s',now.isoformat())
    assert not ledger.evening_pending(data,now,tz)
    assert not ledger.evening_pending({},datetime(2026,10,31,0,0,tzinfo=tz),tz)


def test_provider_retry_after_is_respected():
    now=datetime(2026,10,30,20,tzinfo=timezone.utc)
    assert ledger.retry_delay(None,now)==300
    assert ledger.retry_delay({'requests':[{'retry_after':'1200'}]},now)==1200
    assert ledger.retry_delay({'requests':[{'retry_after':'Fri, 30 Oct 2026 21:00:00 GMT'}]},now)==3600
