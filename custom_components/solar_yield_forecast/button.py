"""Manual controls for Solar Yield Forecast."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.entity import EntityCategory

from .const import DOMAIN


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([SolarYieldRecalculateButton(coordinator, entry)])


class SolarYieldRecalculateButton(CoordinatorEntity, ButtonEntity):
    """Re-import Recorder history and rebuild the adaptive forecast."""

    _attr_has_entity_name = True
    _attr_translation_key = "recalculate_model"
    _attr_icon = "mdi:calculator-variant-outline"
    _attr_entity_category = EntityCategory.CONFIG
    entity_description = ButtonEntityDescription(key='recalculate_model', name='Recalculate model')

    def __init__(self, coordinator, entry):
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_recalculate_model"
        capacity = sum(float(group.get("kwp", 0)) for group in coordinator.groups)
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": coordinator.config.get("site_name", entry.title),
            "manufacturer": "Local custom integration / Open-Meteo",
            "model": f"{capacity:.2f} kWp / {len(coordinator.groups)} orientations",
        }

    async def async_press(self):
        await self.coordinator.async_recalculate()

    @property
    def extra_state_attributes(self):
        values = self.coordinator.data or {}
        return {
            "history_import": values.get("history_import", {}),
            "model_status": values.get("model_status"),
            "calibration_days": values.get("calibration_days"),
            "shape_calibration": values.get("shape_calibration", {}),
        }
