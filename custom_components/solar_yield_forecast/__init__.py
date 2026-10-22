"""Integration entry point."""
from __future__ import annotations
from .const import DOMAIN
from .coordinator import SolarYieldCoordinator
PLATFORMS = ["sensor"]

async def async_setup_entry(hass, entry):
    coordinator = SolarYieldCoordinator(hass, entry)
    await coordinator.async_initialize()
    await coordinator.async_config_entry_first_refresh()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    coordinator.async_start_tracking()
    entry.async_on_unload(coordinator.async_stop_tracking)
    return True

async def async_unload_entry(hass, entry):
    success = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if success:
        hass.data[DOMAIN][entry.entry_id].async_stop_tracking()
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return success
