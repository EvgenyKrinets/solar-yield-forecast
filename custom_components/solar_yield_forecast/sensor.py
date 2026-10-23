"""Lovelace and HA energy estimate sensors."""
from __future__ import annotations
from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from homeassistant.const import UnitOfEnergy, UnitOfPower, PERCENTAGE
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN

SENSORS = (
    ("model_today", "Model Today", "model_today", UnitOfEnergy.KILO_WATT_HOUR, None),
    ("today", "Today", "today", UnitOfEnergy.KILO_WATT_HOUR, None),
    ("tomorrow", "Tomorrow", "tomorrow", UnitOfEnergy.KILO_WATT_HOUR, None),
    ("next_7_days", "Next 7 Days", "next_7_days", UnitOfEnergy.KILO_WATT_HOUR, None),
    ("next_30_days", "Next 30 Days", "next_30_days", UnitOfEnergy.KILO_WATT_HOUR, None),
    ("remaining_today", "Remaining Today", "remaining_today", UnitOfEnergy.KILO_WATT_HOUR, None),
    ("power_now", "Power Now", "current_kw", UnitOfPower.KILO_WATT, SensorDeviceClass.POWER),
    ("power_profile_today", "Power Profile Today", "peak_today_kw", UnitOfPower.KILO_WATT, SensorDeviceClass.POWER),
    ("power_profile_tomorrow", "Power Profile Tomorrow", "peak_tomorrow_kw", UnitOfPower.KILO_WATT, SensorDeviceClass.POWER),
    ("calibration_factor", "Calibration Factor", "factor_percent", PERCENTAGE, None),
    ("calibration_samples", "Calibration Samples", "calibration_days", None, None),
    ("training_error", "Training Error", "training_error", PERCENTAGE, None),
    ("forward_error", "Forward Forecast Error", "forward_error_percent", PERCENTAGE, None),
    ("forward_samples", "Forward Forecast Samples", "forward_error_days", None, None),
)

async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([SolarYieldEntity(coordinator, entry, *row) for row in SENSORS])

class SolarYieldEntity(CoordinatorEntity, SensorEntity):
    def __init__(self, coordinator, entry, key, label, field, unit, dev_class):
        super().__init__(coordinator)
        self.key = key
        self.field = field
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_name = f"Solar Yield Forecast {label}"
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = dev_class
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": "Solar Yield Forecast",
            "manufacturer": "Local custom integration / Open-Meteo",
            "model": "32.16 kWp / 5 orientations",
        }
    @property
    def native_value(self):
        return (self.coordinator.data or {}).get(self.field)

    @property
    def extra_state_attributes(self):
        values = self.coordinator.data or {}
        attrs = {"forecast_updated_at": values.get("updated_at")}
        if self.key == "today":
            attrs.update({
                "daily_forecast": values.get("daily", []),
                "daily_actuals": dict(self.coordinator.actuals),
                "hourly_forecast": values.get("hourly_today", []),
                "actual_today_kwh": values.get("actual_today"),
                "calibration_days": values.get("calibration_days"),
                "model_today_kwh": values.get("model_today"),
                "shape_calibration": values.get("shape_calibration", {}),
                "shape_factors_utc": values.get("shape_factors_utc", {}),
                "forecast_baselines": values.get("forecast_baselines", {}),
                "power_comparisons": values.get("comparison_history", []),
            })
        elif self.key == "tomorrow":
            attrs["hourly_forecast"] = values.get("hourly_tomorrow", [])
        elif self.key in ("power_profile_today", "power_profile_tomorrow"):
            which = "today" if self.key.endswith("today") else "tomorrow"
            attrs.update({
                "date": values.get(f"forecast_date_{which}"),
                "points": values.get(f"power_profile_{which}", []),
                "point_semantics": "15-minute interval means in watts; source per point; Open-Meteo may interpolate weather regionally",
            })
        elif self.key == "forward_error":
            attrs["daily_errors"] = values.get("forecast_accuracy_history", [])
            attrs["metric"] = "MAE percentage of one-or-more-day-ahead forecast snapshots"
        elif self.key == "training_error":
            attrs["error_description"] = "In-sample median error; not forward forecast accuracy"
        return attrs
