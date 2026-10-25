from test_model import BASE
import importlib.util
from datetime import datetime,timedelta,timezone
from zoneinfo import ZoneInfo

spec=importlib.util.spec_from_file_location('freshness',BASE/'freshness.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def test_cache_is_bounded_and_never_claims_yesterdays_forecast_is_today():
    now=datetime(2026,10,25,12,tzinfo=timezone.utc)
    data={'daily':[{'date':'2026-10-25','kwh':90}], 'forecast_date_today':'2026-10-25',
          'weather_updated_at':(now-timedelta(hours=1)).isoformat()}
    assert module.usable_forecast(data,now,timezone.utc)
    assert not module.usable_forecast(data,now+timedelta(hours=6),timezone.utc)
    assert not module.usable_forecast({**data,'forecast_date_today':'2026-10-24'},now,timezone.utc)
    assert not module.usable_forecast({**data,'daily':[]},now,timezone.utc)
    assert not module.usable_forecast({**data,'weather_updated_at':'bad'},now,timezone.utc)
    assert not module.usable_forecast({},now,timezone.utc)
