"""UI installation with user-editable site coordinates and entities."""
from __future__ import annotations
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE
from .const import DOMAIN, DEFAULT_LAT, DEFAULT_LON, DEFAULT_DAILY_SENSOR, DEFAULT_DC_SENSOR

class SolarYieldConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        if user_input is not None:
            await self.async_set_unique_id("solar_yield_forecast_main")
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title="Solar Yield Forecast", data=user_input)
        schema = vol.Schema({
            vol.Required(CONF_LATITUDE, default=DEFAULT_LAT): vol.All(vol.Coerce(float), vol.Range(min=-90, max=90)),
            vol.Required(CONF_LONGITUDE, default=DEFAULT_LON): vol.All(vol.Coerce(float), vol.Range(min=-180, max=180)),
            vol.Required("daily_sensor", default=DEFAULT_DAILY_SENSOR): str,
            vol.Required("dc_power_sensor", default=DEFAULT_DC_SENSOR): str,
        })
        return self.async_show_form(step_id="user", data_schema=schema)
