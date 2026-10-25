"""UI setup and options for arbitrary PV sites and panel orientations."""
from __future__ import annotations

from copy import deepcopy
from aiohttp import ClientError, ClientTimeout
import asyncio
from zipfile import BadZipFile
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from .geocoding import normalized_locations, location_label
from .const import API_GEOCODING
from .city_catalog import async_city_catalog

from .const import (
    CONF_ADD_ANOTHER,
    CONF_AZIMUTH,
    CONF_GROUP_NAME,
    CONF_INCLUDE_GROUP,
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
    MAX_PANEL_GROUPS,
    PANEL_GROUPS,
    TIMEZONE,
)


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


def _location_schema(values):
    """Choose HA's configured home location or the explicit manual fallback."""
    return vol.Schema({
        vol.Required('location_method', default=values.get('location_method',
            'manual' if values.get(CONF_MANUAL_COORDINATES) else 'home')):
            selector.SelectSelector(selector.SelectSelectorConfig(
                options=['home', 'city', 'manual'], translation_key='location_method',
                mode=selector.SelectSelectorMode.DROPDOWN)),
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
        vol.Required(
            CONF_SITE_NAME,
            default=values.get(
                CONF_SITE_NAME, getattr(hass.config, "location_name", "Home")
            ),
        ): selector.TextSelector(),
        vol.Required(CONF_LATITUDE, default=latitude): _number(-90, 90, "any", "°"),
        vol.Required(CONF_LONGITUDE, default=longitude): _number(-180, 180, "any", "°"),
        vol.Required(CONF_TIME_ZONE, default=time_zone): selector.TextSelector(),
    })


def _site_from_home(hass, values):
    """Use the authoritative location already configured in Home Assistant."""
    return {
        'location_method':'home',
        CONF_MANUAL_COORDINATES:False,
        CONF_SITE_NAME: str(getattr(hass.config, "location_name", "Home") or "Home"),
        CONF_LATITUDE: float(hass.config.latitude),
        CONF_LONGITUDE: float(hass.config.longitude),
        CONF_TIME_ZONE: str(getattr(hass.config, "time_zone", TIMEZONE) or TIMEZONE),
        "daily_sensor": values["daily_sensor"],
        "dc_power_sensor": values["dc_power_sensor"],
    }


def _home_placeholders(hass):
    """Show the HA home location without making its coordinates editable."""
    return {
        "home_name": str(getattr(hass.config, "location_name", "Home") or "Home"),
        "latitude": f"{float(hass.config.latitude):.5f}",
        "longitude": f"{float(hass.config.longitude):.5f}",
        "time_zone": str(getattr(hass.config, "time_zone", TIMEZONE) or TIMEZONE),
    }


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


class CityLocationFlow:
    """Shared country + city search for installation and options, never country centroids."""

    async def async_step_place(self, user_input=None):
        errors = {}
        if user_input is not None:
            self._place_query = user_input
            if 'city_query' not in user_input:
                self._catalog_error = False
                try:
                    catalog = await async_city_catalog(self.hass)
                    self._catalog_places = {p['key']:p for p in catalog.get(user_input['country'].upper(),[])}
                except (ClientError, asyncio.TimeoutError, ValueError, BadZipFile, KeyError, UnicodeError):
                    self._catalog_places = {}
                    self._catalog_error = True
                return await self.async_step_city_picker()
            try:
                params = {'name':user_input['city_query'].strip(), 'count':100,
                          'countryCode':user_input['country'].upper(),
                          'language':str(getattr(self.hass.config,'language','en') or 'en').split('-')[0]}
                async with async_get_clientsession(self.hass).get(
                    API_GEOCODING, params=params, timeout=ClientTimeout(total=20)
                ) as response:
                    response.raise_for_status()
                    payload = await response.json()
                self._places = {p['key']:p for p in normalized_locations(payload)
                                if p['country_code']==params['countryCode']}
                if self._places:
                    return await self.async_step_city_result()
                errors['base'] = 'city_not_found'
            except (ClientError, asyncio.TimeoutError, ValueError):
                errors['base'] = 'city_search_failed'
        previous = getattr(self, '_place_query', {})
        return self.async_show_form(step_id='place', errors=errors, data_schema=vol.Schema({
            vol.Required('country', default=previous.get('country', '')):selector.CountrySelector(),
        }))

    async def async_step_city_picker(self, user_input=None):
        if user_input is not None:
            if user_input.get('search_again'):
                return await self.async_step_place()
            place = (getattr(self,'_catalog_choices',{}).get(user_input['city'])
                     or self._catalog_places.get(user_input['city']))
            if place is not None:
                self._places = {place['key']:place}
                return await self.async_step_city_result({'city':place['key']})
            # Custom values cover villages or localized spellings not included
            # in the major-city catalogue. Never guess their coordinates.
            return await self.async_step_place({
                'country':self._place_query['country'],'city_query':user_input['city']})
        options=[]
        self._catalog_choices={}
        for place in self._catalog_places.values():
            aliases=' / '.join(place.get('aliases',[]))
            label=location_label(place)+(f' · {aliases}' if aliases else '')
            # HA's custom-value combobox can display the raw value rather than
            # the option label. Use a readable, unambiguous value, never an ID.
            options.append({'value':label,'label':label})
            self._catalog_choices[label]=place
        return self.async_show_form(step_id='city_picker',
            description_placeholders={'catalog_status':
                'GeoNames unavailable — Open-Meteo name search remains available.' if self._catalog_error
                else 'GeoNames cities15000 · CC BY 4.0 · https://www.geonames.org/'},
            data_schema=vol.Schema({
                vol.Required('city'):selector.SelectSelector(selector.SelectSelectorConfig(
                    options=options,custom_value=True,mode=selector.SelectSelectorMode.DROPDOWN)),
                vol.Optional('search_again',default=False):selector.BooleanSelector(),
            }))

    async def async_step_city_result(self, user_input=None):
        if user_input is not None:
            if user_input.get('search_again'):
                return await self.async_step_place()
            place = self._places.get(user_input['city'])
            if place is None:
                return await self.async_step_place()
            self._site.update({CONF_SITE_NAME:place['name'],
                CONF_LATITUDE:place['latitude'], CONF_LONGITUDE:place['longitude'],
                CONF_TIME_ZONE:place['time_zone'], 'country':place['country_code'],
                'location_method':'city', CONF_MANUAL_COORDINATES:True})
            return await self.async_step_city_confirm()
        return self.async_show_form(step_id='city_result', data_schema=vol.Schema({
            vol.Required('city'):selector.SelectSelector(selector.SelectSelectorConfig(
                options=[{'value':p['key'],'label':location_label(p)} for p in self._places.values()],
                mode=selector.SelectSelectorMode.DROPDOWN)),
            vol.Optional('search_again', default=False):selector.BooleanSelector(),
        }))

    async def async_step_city_confirm(self, user_input=None):
        if user_input is not None:
            if user_input.get('search_again'):
                return await self.async_step_place()
            return await self.async_step_group()
        return self.async_show_form(step_id='city_confirm',
            description_placeholders={key:str(self._site[key]) for key in
                (CONF_SITE_NAME, CONF_LATITUDE, CONF_LONGITUDE, CONF_TIME_ZONE)},
            data_schema=vol.Schema({vol.Optional('search_again',default=False):selector.BooleanSelector()}))


class SolarYieldConfigFlow(CityLocationFlow, config_entries.ConfigFlow, domain=DOMAIN):
    """Configure a solar site without editing YAML or source files."""

    VERSION = 1

    def __init__(self):
        self._site = {}
        self._groups = []

    async def async_step_user(self, user_input=None):
        if user_input is not None:
            if user_input.get('location_method') == 'city':
                self._site = {key:user_input[key] for key in ('daily_sensor','dc_power_sensor')}
                self._groups = []
                return await self.async_step_place()
            if user_input.get(CONF_MANUAL_COORDINATES) or user_input.get('location_method') == 'manual':
                self._site = {
                    "daily_sensor": user_input["daily_sensor"],
                    "dc_power_sensor": user_input["dc_power_sensor"],
                }
                return await self.async_step_manual()
            self._site = _site_from_home(self.hass, user_input)
            self._groups = []
            return await self.async_step_group()
        return self.async_show_form(
            step_id="user",
            data_schema=_location_schema({}),
            description_placeholders=_home_placeholders(self.hass),
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
            self._site.update(location_method='manual', manual_coordinates=True)
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


class SolarYieldOptionsFlow(CityLocationFlow, config_entries.OptionsFlow):
    """Edit the site and rebuild its panel groups from the UI."""

    def __init__(self):
        self._site = {}
        self._current = {}
        self._existing = []
        self._groups = []
        self._index = 0

    async def async_step_init(self, user_input=None):
        current = {**self.config_entry.data, **self.config_entry.options}
        self._current = current
        if user_input is not None:
            self._existing = deepcopy(current.get(CONF_PANEL_GROUPS) or PANEL_GROUPS)
            self._groups = []
            self._index = 0
            if user_input.get('location_method') == 'city':
                self._site = {key:user_input[key] for key in ('daily_sensor','dc_power_sensor')}
                return await self.async_step_place()
            if user_input.get(CONF_MANUAL_COORDINATES) or user_input.get('location_method') == 'manual':
                self._site = {
                    "daily_sensor": user_input["daily_sensor"],
                    "dc_power_sensor": user_input["dc_power_sensor"],
                }
                return await self.async_step_manual()
            self._site = _site_from_home(self.hass, user_input)
            return await self.async_step_group()
        return self.async_show_form(
            step_id="init",
            data_schema=_location_schema(current),
            description_placeholders=_home_placeholders(self.hass),
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
            self._site.update(location_method='manual', manual_coordinates=True)
            return await self.async_step_group()
        return self.async_show_form(
            step_id="manual",
            data_schema=_manual_location_schema(
                self.hass, {**self._current, **self._site}
            ),
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
