"""UI setup and options for arbitrary PV sites and panel orientations."""
from __future__ import annotations

from copy import deepcopy
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_ADD_ANOTHER,
    CONF_AZIMUTH,
    CONF_GROUP_NAME,
    CONF_INCLUDE_GROUP,
    CONF_PANEL_COUNT,
    CONF_PANEL_GROUPS,
    CONF_PANEL_POWER_W,
    CONF_SITE_NAME,
    CONF_TILT,
    CONF_TIME_ZONE,
    DEFAULT_DAILY_SENSOR,
    DEFAULT_DC_SENSOR,
    DOMAIN,
    MAX_PANEL_GROUPS,
    PANEL_GROUPS,
    TIMEZONE,
)


def _number(minimum, maximum, step=1, unit=None):
    return selector.NumberSelector(selector.NumberSelectorConfig(
        min=minimum,
        max=maximum,
        step=step,
        mode=selector.NumberSelectorMode.BOX,
        unit_of_measurement=unit,
    ))


def _site_schema(hass, values):
    """Build the site form with Home Assistant location as first-install default."""
    latitude = values.get(CONF_LATITUDE, getattr(hass.config, "latitude", 0.0))
    longitude = values.get(CONF_LONGITUDE, getattr(hass.config, "longitude", 0.0))
    location_name = values.get(CONF_SITE_NAME, getattr(hass.config, "location_name", "Home"))
    time_zone = values.get(CONF_TIME_ZONE, getattr(hass.config, "time_zone", TIMEZONE))
    return vol.Schema({
        vol.Required(CONF_SITE_NAME, default=location_name): selector.TextSelector(),
        vol.Required(CONF_LATITUDE, default=latitude): _number(-90, 90, 0.00001, "°"),
        vol.Required(CONF_LONGITUDE, default=longitude): _number(-180, 180, 0.00001, "°"),
        vol.Required(CONF_TIME_ZONE, default=time_zone): selector.TextSelector(),
        vol.Required("daily_sensor", default=values.get("daily_sensor", DEFAULT_DAILY_SENSOR)):
            selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
        vol.Required("dc_power_sensor", default=values.get("dc_power_sensor", DEFAULT_DC_SENSOR)):
            selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
    })


def _group_schema(number, group=None, editing=False, has_more=False):
    """Build one repeatable panel-group form."""
    group = group or {}
    schema = {
        vol.Required(CONF_GROUP_NAME, default=group.get("name", f"G{number}")):
            selector.TextSelector(),
        vol.Required(CONF_PANEL_COUNT, default=int(group.get("count", 1))): _number(1, 1000, 1),
        vol.Required(CONF_PANEL_POWER_W, default=int(group.get("panel_power_w", 670))):
            _number(50, 1500, 1, "W"),
        vol.Required(CONF_TILT, default=float(group.get("tilt", 20))): _number(0, 90, 0.1, "°"),
        vol.Required(CONF_AZIMUTH, default=float(group.get("azimuth", 180))): _number(0, 359.9, 0.1, "°"),
    }
    if editing:
        schema[vol.Required(CONF_INCLUDE_GROUP, default=True)] = selector.BooleanSelector()
    schema[vol.Required(CONF_ADD_ANOTHER, default=has_more)] = selector.BooleanSelector()
    return vol.Schema(schema)


def _stored_group(values, number):
    count = int(values[CONF_PANEL_COUNT])
    panel_power = int(values[CONF_PANEL_POWER_W])
    return {
        "id": f"G{number}",
        "name": str(values[CONF_GROUP_NAME]).strip() or f"G{number}",
        "count": count,
        "panel_power_w": panel_power,
        "kwp": round(count * panel_power / 1000.0, 6),
        "tilt": round(float(values[CONF_TILT]), 1),
        "azimuth": round(float(values[CONF_AZIMUTH]) % 360, 1),
    }


def _summary_placeholders(groups):
    """Return a readable per-group capacity list and the system total."""
    lines = []
    for index, group in enumerate(groups, 1):
        capacity = float(group["kwp"])
        lines.append(
            f"- **{index}. {group['name']}:** {group['count']} × "
            f"{group['panel_power_w']} W = **{capacity:.3f} kWp** · "
            f"↗ {group['tilt']:.1f}° · 🧭 {group['azimuth']:.1f}°"
        )
    return {
        "groups": "\n".join(lines),
        "total_kwp": f"{sum(float(group['kwp']) for group in groups):.3f}",
        "panel_count": str(sum(int(group["count"]) for group in groups)),
    }


class SolarYieldConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Configure a solar site without editing YAML or source files."""

    VERSION = 1

    def __init__(self):
        self._site = {}
        self._groups = []

    async def async_step_user(self, user_input=None):
        if user_input is not None:
            try:
                ZoneInfo(user_input[CONF_TIME_ZONE])
            except (ZoneInfoNotFoundError, ValueError, TypeError):
                return self.async_show_form(
                    step_id="user",
                    data_schema=_site_schema(self.hass, user_input),
                    errors={CONF_TIME_ZONE: "invalid_time_zone"},
                )
            self._site = dict(user_input)
            self._groups = []
            return await self.async_step_group()
        return self.async_show_form(step_id="user", data_schema=_site_schema(self.hass, {}))

    async def async_step_group(self, user_input=None):
        number = len(self._groups) + 1
        if user_input is not None:
            self._groups.append(_stored_group(user_input, number))
            if user_input.get(CONF_ADD_ANOTHER) and len(self._groups) < MAX_PANEL_GROUPS:
                return await self.async_step_group()
            return await self.async_step_summary()
        return self.async_show_form(
            step_id="group",
            data_schema=_group_schema(number),
            description_placeholders={"number": str(number)},
        )

    async def async_step_summary(self, user_input=None):
        if user_input is not None:
            await self.async_set_unique_id("solar_yield_forecast_main")
            self._abort_if_unique_id_configured()
            data = {**self._site, CONF_PANEL_GROUPS: self._groups}
            title = self._site.get(CONF_SITE_NAME) or "Solar Yield Forecast"
            return self.async_create_entry(title=title, data=data)
        return self.async_show_form(
            step_id="summary",
            data_schema=vol.Schema({}),
            description_placeholders=_summary_placeholders(self._groups),
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return SolarYieldOptionsFlow(config_entry)


class SolarYieldOptionsFlow(config_entries.OptionsFlow):
    """Edit the site and rebuild its panel groups from the UI."""

    def __init__(self, config_entry):
        self._entry = config_entry
        self._site = {}
        self._existing = []
        self._groups = []
        self._index = 0

    async def async_step_init(self, user_input=None):
        current = {**self._entry.data, **self._entry.options}
        if user_input is not None:
            try:
                ZoneInfo(user_input[CONF_TIME_ZONE])
            except (ZoneInfoNotFoundError, ValueError, TypeError):
                return self.async_show_form(
                    step_id="init",
                    data_schema=_site_schema(self.hass, user_input),
                    errors={CONF_TIME_ZONE: "invalid_time_zone"},
                )
            self._site = dict(user_input)
            self._existing = deepcopy(current.get(CONF_PANEL_GROUPS) or PANEL_GROUPS)
            self._groups = []
            self._index = 0
            return await self.async_step_group()
        return self.async_show_form(step_id="init", data_schema=_site_schema(self.hass, current))

    async def async_step_group(self, user_input=None):
        current = self._existing[self._index] if self._index < len(self._existing) else None
        errors = {}
        if user_input is not None:
            if user_input.get(CONF_INCLUDE_GROUP, True):
                self._groups.append(_stored_group(user_input, len(self._groups) + 1))
            self._index += 1
            has_existing = self._index < len(self._existing)
            wants_more = bool(user_input.get(CONF_ADD_ANOTHER))
            if (has_existing or wants_more) and self._index < MAX_PANEL_GROUPS:
                return await self.async_step_group()
            if not self._groups:
                self._index -= 1
                errors["base"] = "at_least_one_group"
                current = self._existing[self._index] if self._index < len(self._existing) else None
            else:
                return await self.async_step_summary()
        number = self._index + 1
        return self.async_show_form(
            step_id="group",
            data_schema=_group_schema(
                number,
                current,
                editing=True,
                has_more=self._index < len(self._existing) - 1,
            ),
            errors=errors,
            description_placeholders={"number": str(number)},
        )

    async def async_step_summary(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(
                title="",
                data={**self._site, CONF_PANEL_GROUPS: self._groups},
            )
        return self.async_show_form(
            step_id="summary",
            data_schema=vol.Schema({}),
            description_placeholders=_summary_placeholders(self._groups),
        )
