import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import pytest
from datetime import datetime, timedelta
from homeassistant.exceptions import HomeAssistantError


def coordinator(hass):
    from custom_components.solar_yield_forecast.coordinator import SolarYieldCoordinator
    entry=SimpleNamespace(data={'latitude':1,'longitude':2},options={},entry_id='test',title='Roof')
    with patch('custom_components.solar_yield_forecast.coordinator.async_get_clientsession',return_value=SimpleNamespace()):
        obj=SolarYieldCoordinator(hass,entry)
    obj.data={}
    return obj


async def test_pending_evening_retries_after_failure_and_returns_to_normal(hass,enable_custom_integrations):
    obj=coordinator(hass)
    evening=datetime(2026,10,30,23,30,tzinfo=obj.tz)
    obj._async_fetch_model=AsyncMock(side_effect=ValueError('weather missing'))
    with patch('custom_components.solar_yield_forecast.coordinator.datetime') as clock:
        clock.now.return_value=evening
        with pytest.raises(ValueError):
            await obj._async_update_data()
    assert obj.update_interval==timedelta(minutes=5)
    obj.forecast_ledger={'2026-10-31':{'day_ahead':{'kwh':100}}}
    obj._async_fetch_model=AsyncMock(return_value={})
    with patch('custom_components.solar_yield_forecast.coordinator.datetime') as clock:
        clock.now.return_value=evening
        await obj._async_update_data()
    assert obj.update_interval==timedelta(minutes=15)
    obj.forecast_ledger={}
    with patch('custom_components.solar_yield_forecast.coordinator.datetime') as clock:
        clock.now.return_value=evening+timedelta(minutes=30)
        await obj._async_update_data()
    assert obj.update_interval==timedelta(minutes=15)


async def test_recalculation_waits_for_real_refresh_and_reports_completion(hass,enable_custom_integrations):
    obj=coordinator(hass)
    started=asyncio.Event(); finish=asyncio.Event()
    async def refresh():
        started.set()
        await finish.wait()
        obj.last_update_success=True
        obj.shape_report={'status':'insufficient_history','available_days':4}
    obj.async_refresh=AsyncMock(side_effect=refresh)
    obj.async_request_refresh=AsyncMock()
    obj.async_import_daily_history=AsyncMock()
    task=asyncio.create_task(obj.async_recalculate())
    await started.wait()
    assert not task.done()
    assert obj.data['recalculation_status']=='running'
    with pytest.raises(HomeAssistantError,match='already running'):
        await obj.async_recalculate()
    finish.set(); await task
    obj.async_request_refresh.assert_not_called()
    obj.async_import_daily_history.assert_awaited_once_with(force=True)
    assert obj.data['recalculation_status']=='completed'
    assert obj.data['recalculation']['shape_status']=='insufficient_history'
    assert 'duration_seconds' in obj.data['recalculation']


async def test_failed_refresh_never_reports_success(hass,enable_custom_integrations):
    obj=coordinator(hass)
    async def fail():
        obj.last_update_success=False
        obj.last_exception=ValueError('Weather failed')
    obj.async_refresh=AsyncMock(side_effect=fail)
    obj.async_import_daily_history=AsyncMock()
    with pytest.raises(HomeAssistantError,match='Weather failed'):
        await obj.async_recalculate()
    assert obj.data['recalculation_status']=='failed'
    assert obj.last_update_success is False
    assert 'Weather failed' in obj.data['recalculation']['error']


async def test_model_status_separates_daily_calibration_from_shape(hass,enable_custom_integrations):
    obj=coordinator(hass);obj.cal_days=16
    assert obj._model_status()=='calibration_only'
    obj.shape_factors={'q40':1.1}
    assert obj._model_status()=='ready'
    obj.recalculation={'status':'running'}
    assert obj._model_status()=='recalculating'


async def test_timeout_keeps_last_forecast_and_diagnostics_available(hass,enable_custom_integrations):
    from datetime import datetime,timezone,timedelta
    from custom_components.solar_yield_forecast.sensor import SolarYieldEntity
    from homeassistant.helpers.update_coordinator import UpdateFailed
    obj=coordinator(hass)
    now=datetime.now(timezone.utc)
    stamp=(now-timedelta(minutes=2)).isoformat()
    obj.weather_updated_at=stamp
    obj.data={'today':90,'daily':[{'date':now.astimezone(obj.tz).date().isoformat(),'kwh':90}],
        'forecast_date_today':now.astimezone(obj.tz).date().isoformat(),'weather_updated_at':stamp}
    obj._maybe_refresh_archive=AsyncMock()
    obj._get_groups=AsyncMock(side_effect=asyncio.TimeoutError())
    with pytest.raises(UpdateFailed,match='timed out'):
        await obj._async_fetch_model()
    obj.last_update_success=False
    entity=SolarYieldEntity(obj,obj.entry,'today','Today','today','kWh',None)
    assert entity.available and entity.native_value==90
    assert entity.extra_state_attributes['weather_status']=='stale'
    assert entity.extra_state_attributes['forecast_updated_at']==stamp
    diagnostic=SolarYieldEntity(obj,obj.entry,'recalculation_status','Status','recalculation_status',None,None)
    assert diagnostic.available
    assert obj._model_status()=='weather_stale'
    obj.weather_updated_at=(now-timedelta(hours=7)).isoformat()
    obj.data['weather_updated_at']=obj.weather_updated_at
    assert not entity.available and diagnostic.available


async def test_request_timeout_is_retried_once_and_message_is_not_blank(hass,enable_custom_integrations):
    from aiohttp import ClientError
    from unittest.mock import MagicMock
    obj=coordinator(hass)
    obj.session=MagicMock()
    obj.session.get.return_value.__aenter__=AsyncMock(side_effect=asyncio.TimeoutError())
    with patch('custom_components.solar_yield_forecast.coordinator.asyncio.sleep',AsyncMock()):
        with pytest.raises(ClientError,match='timed out after 30 seconds'):
            await obj._one_group('https://example.invalid',obj.groups[0],{})
    assert obj.session.get.call_count==2


async def test_http_rate_limit_preserves_status_group_and_retry_after(hass,enable_custom_integrations):
    from aiohttp import ClientResponseError
    from unittest.mock import MagicMock
    from custom_components.solar_yield_forecast.coordinator import WeatherRequestError
    obj=coordinator(hass);obj.session=MagicMock()
    request=SimpleNamespace(real_url='https://api.open-meteo.com/v1/forecast')
    failure=ClientResponseError(request,(),status=429,message='Too Many Requests',headers={'Retry-After':'60'})
    obj.session.get.return_value.__aenter__=AsyncMock(side_effect=failure)
    with pytest.raises(WeatherRequestError) as caught:
        await obj._one_group(str(request.real_url),obj.groups[0],{})
    details=caught.value.details[0]
    assert details['http_status']==429 and details['attempts']==1
    assert details['retry_after']=='60' and details['group_id']==obj.groups[0]['id']
    assert '429' in str(caught.value)


async def test_power_recording_does_not_require_weather(hass,enable_custom_integrations):
    from unittest.mock import MagicMock
    obj=coordinator(hass);obj._persist=MagicMock()
    obj._power_changed(SimpleNamespace(data={'new_state':SimpleNamespace(
        state='4000',attributes={'unit_of_measurement':'W'})}))
    assert obj.power_archive.pending[-1][1]==4
    obj._power_changed(SimpleNamespace(data={'new_state':SimpleNamespace(
        state='unavailable',attributes={'unit_of_measurement':'W'})}))
    assert obj.power_archive.pending[-1][1] is None


async def test_own_archive_can_train_without_recorder(hass,enable_custom_integrations):
    from datetime import datetime,timezone,timedelta
    from unittest.mock import MagicMock
    import math
    obj=coordinator(hass);obj._persist=MagicMock()
    start=datetime(2026,10,1,tzinfo=timezone.utc)
    for day in range(10):
        for q in range(96):
            stamp=(start+timedelta(days=day,minutes=15*q)).timestamp()
            p=16*max(0,math.sin(math.pi*(q-24)/48)) if 24<=q<=72 else 0
            obj.forecast_rows.append(dict(end=stamp+900,interval_seconds=900,kw=p,cloud_cover=4))
            obj.power_archive.bins[int(stamp)]=[p*(1.25 if q<46 else .7)*.25,900]
    await obj._learn_shape(datetime(2026,10,20,tzinfo=timezone.utc))
    assert obj.shape_report['training_days']==7 and obj.shape_report['validation_days']==3
    assert obj.shape_report['status']=='active'
    assert obj.shape_report['active_profile']['confidence_percent']==50
