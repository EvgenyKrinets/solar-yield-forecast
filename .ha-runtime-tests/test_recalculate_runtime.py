import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import pytest
from homeassistant.exceptions import HomeAssistantError


def coordinator(hass):
    from custom_components.solar_yield_forecast.coordinator import SolarYieldCoordinator
    entry=SimpleNamespace(data={'latitude':1,'longitude':2},options={},entry_id='test',title='Roof')
    with patch('custom_components.solar_yield_forecast.coordinator.async_get_clientsession',return_value=SimpleNamespace()):
        obj=SolarYieldCoordinator(hass,entry)
    obj.data={}
    return obj


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
