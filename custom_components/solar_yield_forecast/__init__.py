"""Solar Yield Forecast: sensors, dashboard card and managed sidebar panel."""
from __future__ import annotations

from pathlib import Path

from homeassistant.components import frontend, panel_custom
from homeassistant.components.http import StaticPathConfig
from homeassistant.components.http import HomeAssistantView
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN
from .coordinator import SolarYieldCoordinator

PLATFORMS = ["sensor", "button"]
FRONTEND_URL = f"/api/{DOMAIN}/solar-comparison-card.js"
FRONTEND_VERSION = "1.6.1"
PANEL_URL = "solar-yield-forecast"
PANEL_TAG = "solar-yield-forecast-panel-v1-6-1"


class SolarForecastProfileView(HomeAssistantView):
    """Serve one requested profile without publishing every day as an entity attribute."""

    url = f"/api/{DOMAIN}/profile/{{date}}"
    name = f"api:{DOMAIN}:profile"
    requires_auth = True

    async def get(self, request, date):
        hass = request.app["hass"]
        coordinators = list((hass.data.get(DOMAIN) or {}).values())
        if not coordinators:
            return self.json({"date": date, "points": []}, status_code=404)
        profiles = (coordinators[0].data or {}).get("power_profiles_by_date", {})
        slots = coordinators[0].forecast_ledger.get(date, {})
        original = slots.get('day_ahead') or slots.get('morning') or slots.get('late_start')
        return self.json({"date": date, "points": profiles.get(date, []), 'original': original})


async def _async_reload_entry(hass, entry):
    """Apply UI option changes immediately by rebuilding the coordinator."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_setup(hass, config):
    """Register the frontend file once for all dashboards, without manual resources."""
    filepath = Path(__file__).parent / "frontend" / "solar-comparison-card.js"
    await hass.http.async_register_static_paths(
        [StaticPathConfig(FRONTEND_URL, str(filepath), cache_headers=False)]
    )
    frontend.add_extra_js_url(hass, f"{FRONTEND_URL}?v={FRONTEND_VERSION}")
    hass.http.register_view(SolarForecastProfileView)
    return True


def _panel_config(hass, entry):
    """Return exact entity IDs and source sensors for the managed frontend."""
    values = {**entry.data, **entry.options}
    registry = er.async_get(hass)
    entities = {}
    prefix = f"{entry.entry_id}_"
    for entity in er.async_entries_for_config_entry(registry, entry.entry_id):
        if entity.unique_id.startswith(prefix):
            entities[entity.unique_id[len(prefix):]] = entity.entity_id
    return {
        "title": f"Solar Yield Forecast — {values.get('site_name', entry.title)}",
        "pv_entity": values.get("dc_power_sensor", "sensor.total_dc_power"),
        "energy_entity": values.get("daily_sensor", "sensor.daily_pv_generation"),
        "forecast_entity": entities.get(
            "power_profile_today", "sensor.solar_yield_forecast_power_profile_today"
        ),
        "day_forecast_entity": entities.get(
            "today", "sensor.solar_yield_forecast_today"
        ),
        "recalculate_entity": entities.get(
            "recalculate_model", "button.solar_yield_forecast_recalculate_model"
        ),
        "time_zone": values.get("time_zone", hass.config.time_zone),
    }


async def _async_register_panel(hass, entry):
    """Create the dedicated application entry in the Home Assistant sidebar."""
    await panel_custom.async_register_panel(
        hass,
        webcomponent_name=PANEL_TAG,
        frontend_url_path=PANEL_URL,
        module_url=f"{FRONTEND_URL}?v={FRONTEND_VERSION}",
        sidebar_title="Solar Forecast",
        sidebar_icon="mdi:solar-power-variant",
        require_admin=False,
        config=_panel_config(hass, entry),
    )


async def async_setup_entry(hass, entry):
    coordinator = SolarYieldCoordinator(hass, entry)
    await coordinator.async_initialize()
    await coordinator.async_config_entry_first_refresh()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await _async_register_panel(hass, entry)
    coordinator.async_start_tracking()
    entry.async_on_unload(coordinator.async_stop_tracking)
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    return True


async def async_unload_entry(hass, entry):
    success = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if success:
        frontend.async_remove_panel(hass, PANEL_URL)
        hass.data[DOMAIN][entry.entry_id].async_stop_tracking()
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return success
