"""Solar Yield Forecast: prediction sensors and automatically loaded dashboard card."""
from __future__ import annotations

from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig

from .const import DOMAIN
from .coordinator import SolarYieldCoordinator

PLATFORMS = ["sensor"]
FRONTEND_URL = f"/api/{DOMAIN}/solar-comparison-card.js"
FRONTEND_VERSION = "1.0.0"


async def _async_reload_entry(hass, entry):
    """Apply UI option changes immediately by rebuilding the coordinator."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_setup(hass, config):
    """Register the frontend file once for all dashboards, without manual resources."""
    filepath = Path(__file__).parent / "frontend" / "solar-comparison-card.js"
    await hass.http.async_register_static_paths(
        [StaticPathConfig(FRONTEND_URL, str(filepath), cache_headers=False)]
    )
    add_extra_js_url(hass, f"{FRONTEND_URL}?v={FRONTEND_VERSION}")
    return True


async def async_setup_entry(hass, entry):
    coordinator = SolarYieldCoordinator(hass, entry)
    await coordinator.async_initialize()
    await coordinator.async_config_entry_first_refresh()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    coordinator.async_start_tracking()
    entry.async_on_unload(coordinator.async_stop_tracking)
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    return True


async def async_unload_entry(hass, entry):
    success = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if success:
        hass.data[DOMAIN][entry.entry_id].async_stop_tracking()
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return success
