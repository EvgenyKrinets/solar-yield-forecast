"""UI setup and options for arbitrary PV sites and panel orientations."""
from __future__ import annotations

import asyncio
from copy import deepcopy
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import voluptuous as vol
from aiohttp import ClientError, ClientTimeout
from homeassistant import config_entries
from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_ADD_ANOTHER,
    CONF_AZIMUTH,
    CONF_COUNTRY_CODE,
    CONF_GROUP_NAME,
    CONF_INCLUDE_GROUP,
    CONF_LOCATION_RESULT,
    CONF_MANUAL_COORDINATES,
    CONF_PANEL_COUNT,
    CONF_PANEL_GROUPS,
    CONF_PANEL_POWER_W,
    CONF_SITE_NAME,
    CONF_TILT,
    CONF_TIME_ZONE,
    DEFAULT_DAILY_SENSOR,
    DEFAULT_DC_SENSOR,
    DOMAIN,
    API_GEOCODING,
    MAX_PANEL_GROUPS,
    PANEL_GROUPS,
    TIMEZONE,
)
from .geocoding import location_label, normalized_locations


def _number(minimum, maximum, step=1, unit=None):
    config = selector.NumberSelectorConfig(
        min=minimum,
        max=maximum,
        step=step,
        mode=selector.NumberSelectorMode.BOX,
    )
    if unit is not None:
        config["unit_of_measurement"] = unit
    return selector.NumberSelector(config)


def _search_schema(hass, values):
    """Country/city lookup with the production sensors on the first page."""
    country = str(
        values.get(CONF_COUNTRY_CODE)
        or getattr(hass.config, "country", None)
        or "US"
    ).upper()
    location_name = values.get(
        CONF_SITE_NAME, getattr(hass.config, "location_name", "Home")
    )
    return vol.Schema({
        vol.Required(CONF_COUNTRY_CODE, default=country):
            selector.CountrySelector(selector.CountrySelectorConfig()),
        vol.Required(CONF_SITE_NAME, default=location_name): selector.TextSelector(),
        vol.Required(
            CONF_MANUAL_COORDINATES,
            default=bool(values.get(CONF_MANUAL_COORDINATES, False)),
        ): selector.BooleanSelector(),
        vol.Required("daily_sensor", default=values.get("daily_sensor", DEFAULT_DAILY_SENSOR)):
            selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
        vol.Required("dc_power_sensor", default=values.get("dc_power_sensor", DEFAULT_DC_SENSOR)):
            selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
    })


def _manual_location_schema(hass, values):
    """Fallback for roofs that cannot be resolved to a named place."""
    latitude = values.get(CONF_LATITUDE, getattr(hass.config, "latitude", 0.0))
    longitude = values.get(CONF_LONGITUDE, getattr(hass.config, "longitude", 0.0))
    time_zone = values.get(
        CONF_TIME_ZONE, getattr(hass.config, "time_zone", TIMEZONE)
    )
    return vol.Schema({
        vol.Required(CONF_LATITUDE, default=latitude): _number(-90, 90, "any", "°"),
        vol.Required(CONF_LONGITUDE, default=longitude): _number(-180, 180, "any", "°"),
        vol.Required(CONF_TIME_ZONE, default=time_zone): selector.TextSelector(),
    })


def _location_result_schema(locations):
    options = [
        {"value": location["key"], "label": location_label(location)}
        for location in locations
    ]
    return vol.Schema({
        vol.Required(CONF_LOCATION_RESULT, default=locations[0]["key"]):
            selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=options,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            )
    })


async def _async_find_locations(hass, name, country_code):
    """Resolve a city/place name through the Open-Meteo Geocoding API."""
    language = str(getattr(hass.config, "language", "en") or "en")
    language = language.replace("_", "-").split("-", 1)[0].lower()
    params = {
        "name": str(name).strip(),
        "count": 10,
        "language": language,
        "format": "json",
        "countryCode": str(country_code).upper(),
    }
    session = async_get_clientsession(hass)
    async with session.get(
        API_GEOCODING, params=params, timeout=ClientTimeout(total=15)
    ) as response:
        response.raise_for_status()
        payload = await response.json(content_type=None)
    if not isinstance(payload, dict):
        raise ValueError("Invalid geocoding response")
    if payload.get("error"):
        raise ValueError(payload.get("reason", "Geocoding API error"))
    return normalized_locations(payload)


def _site_from_search(values):
    """Keep only persistent values from the first lookup page."""
    return {
        CONF_SITE_NAME: str(values[CONF_SITE_NAME]).strip(),
        CONF_COUNTRY_CODE: str(values[CONF_COUNTRY_CODE]).upper(),
        "daily_sensor": values["daily_sensor"],
        "dc_power_sensor": values["dc_power_sensor"],
    }


def _apply_location(site, location):
    """Copy the selected WGS84 coordinates and IANA timezone into the entry."""
    site.update({
        CONF_SITE_NAME: location["name"],
        CONF_COUNTRY_CODE: location["country_code"],
        CONF_LATITUDE: location["latitude"],
        CONF_LONGITUDE: location["longitude"],
        CONF_TIME_ZONE: location["time_zone"],
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
        self._locations = {}

    async def async_step_user(self, user_input=None):
        if user_input is not None:
            self._site = _site_from_search(user_input)
            if user_input.get(CONF_MANUAL_COORDINATES):
                return await self.async_step_manual()
            try:
                locations = await _async_find_locations(
                    self.hass,
                    user_input[CONF_SITE_NAME],
                    user_input[CONF_COUNTRY_CODE],
                )
            except (ClientError, asyncio.TimeoutError, ValueError, KeyError):
                return self.async_show_form(
                    step_id="user",
                    data_schema=_search_schema(self.hass, user_input),
                    errors={"base": "geocoding_unavailable"},
                )
            if not locations:
                return self.async_show_form(
                    step_id="user",
                    data_schema=_search_schema(self.hass, user_input),
                    errors={CONF_SITE_NAME: "location_not_found"},
                )
            self._locations = {location["key"]: location for location in locations}
            return await self.async_step_location()
        return self.async_show_form(step_id="user", data_schema=_search_schema(self.hass, {}))

    async def async_step_location(self, user_input=None):
        locations = list(self._locations.values())
        if user_input is not None:
            location = self._locations.get(str(user_input[CONF_LOCATION_RESULT]))
            if location is None:
                return self.async_show_form(
                    step_id="location",
                    data_schema=_location_result_schema(locations),
                    errors={CONF_LOCATION_RESULT: "location_not_found"},
                )
            _apply_location(self._site, location)
            self._groups = []
            return await self.async_step_group()
        return self.async_show_form(
            step_id="location", data_schema=_location_result_schema(locations)
        )

    async def async_step_manual(self, user_input=None):
        if user_input is not None:
            try:
                ZoneInfo(user_input[CONF_TIME_ZONE])
            except (ZoneInfoNotFoundError, ValueError, TypeError):
                return self.async_show_form(
                    step_id="manual",
                    data_schema=_manual_location_schema(self.hass, user_input),
                    errors={CONF_TIME_ZONE: "invalid_time_zone"},
                )
            self._site.update(user_input)
            self._groups = []
            return await self.async_step_group()
        return self.async_show_form(
            step_id="manual",
            data_schema=_manual_location_schema(self.hass, self._site),
        )

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
        # Home Assistant attaches the config entry after constructing the flow.
        # Passing it into __init__ prevents the options flow from starting on
        # current HA releases and surfaces as a generic HTTP 400 in the UI.
        return SolarYieldOptionsFlow()


class SolarYieldOptionsFlow(config_entries.OptionsFlow):
    """Edit the site and rebuild its panel groups from the UI."""

    def __init__(self):
        self._site = {}
        self._current = {}
        self._locations = {}
        self._existing = []
        self._groups = []
        self._index = 0

    async def async_step_init(self, user_input=None):
        current = {**self.config_entry.data, **self.config_entry.options}
        self._current = current
        if user_input is not None:
            self._site = _site_from_search(user_input)
            self._existing = deepcopy(current.get(CONF_PANEL_GROUPS) or PANEL_GROUPS)
            self._groups = []
            self._index = 0
            if user_input.get(CONF_MANUAL_COORDINATES):
                return await self.async_step_manual()
            same_place = (
                str(user_input[CONF_SITE_NAME]).strip().casefold()
                == str(current.get(CONF_SITE_NAME, "")).strip().casefold()
                and str(user_input[CONF_COUNTRY_CODE]).upper()
                == str(current.get(CONF_COUNTRY_CODE) or user_input[CONF_COUNTRY_CODE]).upper()
                and CONF_LATITUDE in current
                and CONF_LONGITUDE in current
                and CONF_TIME_ZONE in current
            )
            if same_place:
                self._site.update({
                    CONF_LATITUDE: current[CONF_LATITUDE],
                    CONF_LONGITUDE: current[CONF_LONGITUDE],
                    CONF_TIME_ZONE: current[CONF_TIME_ZONE],
                })
                return await self.async_step_group()
            try:
                locations = await _async_find_locations(
                    self.hass,
                    user_input[CONF_SITE_NAME],
                    user_input[CONF_COUNTRY_CODE],
                )
            except (ClientError, asyncio.TimeoutError, ValueError, KeyError):
                return self.async_show_form(
                    step_id="init",
                    data_schema=_search_schema(self.hass, user_input),
                    errors={"base": "geocoding_unavailable"},
                )
            if not locations:
                return self.async_show_form(
                    step_id="init",
                    data_schema=_search_schema(self.hass, user_input),
                    errors={CONF_SITE_NAME: "location_not_found"},
                )
            self._locations = {location["key"]: location for location in locations}
            return await self.async_step_location()
        return self.async_show_form(step_id="init", data_schema=_search_schema(self.hass, current))

    async def async_step_location(self, user_input=None):
        locations = list(self._locations.values())
        if user_input is not None:
            location = self._locations.get(str(user_input[CONF_LOCATION_RESULT]))
            if location is None:
                return self.async_show_form(
                    step_id="location",
                    data_schema=_location_result_schema(locations),
                    errors={CONF_LOCATION_RESULT: "location_not_found"},
                )
            _apply_location(self._site, location)
            return await self.async_step_group()
        return self.async_show_form(
            step_id="location", data_schema=_location_result_schema(locations)
        )

    async def async_step_manual(self, user_input=None):
        if user_input is not None:
            try:
                ZoneInfo(user_input[CONF_TIME_ZONE])
            except (ZoneInfoNotFoundError, ValueError, TypeError):
                return self.async_show_form(
                    step_id="manual",
                    data_schema=_manual_location_schema(self.hass, user_input),
                    errors={CONF_TIME_ZONE: "invalid_time_zone"},
                )
            self._site.update(user_input)
            return await self.async_step_group()
        return self.async_show_form(
            step_id="manual",
            data_schema=_manual_location_schema(self.hass, self._current),
        )

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
