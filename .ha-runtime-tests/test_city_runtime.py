from unittest.mock import MagicMock, AsyncMock, patch
from homeassistant.data_entry_flow import FlowResultType


async def test_city_coordinates_use_selected_city(hass, enable_custom_integrations):
    from custom_components.solar_yield_forecast.config_flow import SolarYieldConfigFlow
    flow=SolarYieldConfigFlow()
    flow.hass=hass
    flow._site={'daily_sensor':'sensor.energy','dc_power_sensor':'sensor.power'}
    response=MagicMock()
    response.raise_for_status=MagicMock()
    response.json=AsyncMock(return_value={'results':[
        {'id':1,'name':'Dimona','latitude':31.07079,'longitude':35.03269,'timezone':'Asia/Jerusalem','country_code':'IL'},
        {'id':2,'name':'Other','latitude':32.1,'longitude':34.9,'timezone':'Asia/Jerusalem','country_code':'IL'},
        {'id':3,'name':'Wrong country','latitude':1,'longitude':2,'timezone':'UTC','country_code':'US'},
    ]})
    session=MagicMock()
    session.get.return_value.__aenter__=AsyncMock(return_value=response)
    session.get.return_value.__aexit__=AsyncMock(return_value=False)
    with patch('custom_components.solar_yield_forecast.config_flow.async_get_clientsession',return_value=session):
        result=await flow.async_step_place({'country':'IL','city_query':'Dimona'})
    assert result['step_id']=='city_result'
    assert set(flow._places)=={'1','2'}
    result['data_schema']({'city':'2','search_again':False})
    confirmed=await flow.async_step_city_result({'city':'2'})
    assert confirmed['step_id']=='city_confirm'
    assert flow._site['latitude']==32.1
    assert flow._site['longitude']==34.9
    assert confirmed['description_placeholders']['site_name']=='Other'
    assert (await flow.async_step_city_confirm({'search_again':True}))['step_id']=='place'


async def test_home_city_manual_selector_and_options_start(hass, enable_custom_integrations):
    from custom_components.solar_yield_forecast.config_flow import _location_schema
    schema=_location_schema({})
    for method in ('home','city','manual'):
        values=schema({'location_method':method,'daily_sensor':'sensor.energy','dc_power_sensor':'sensor.power'})
        assert values['location_method']==method
    from pytest_homeassistant_custom_component.common import MockConfigEntry
    entry=MockConfigEntry(domain='solar_yield_forecast',data={},title='Roof')
    entry.add_to_hass(hass)
    result=await hass.config_entries.options.async_init(entry.entry_id)
    assert result['type']==FlowResultType.FORM
    result=await hass.config_entries.options.async_configure(result['flow_id'],
        {'location_method':'city','daily_sensor':'sensor.energy','dc_power_sensor':'sensor.power'})
    assert result['step_id']=='place'
