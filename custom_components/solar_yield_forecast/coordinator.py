"""Hourly Open-Meteo polling + robust learning from real HA energy readings."""
from __future__ import annotations
import asyncio
import logging
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
from aiohttp import ClientError, ClientTimeout
from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.core import callback
from .const import (DOMAIN, PANEL_GROUPS, API_ARCHIVE, API_FORECAST, DEFAULT_DAILY_SENSOR, TIMEZONE)
from .model import (TZ, combine_weather, calibration, forecast_summary, open_meteo_azimuth, merge_quarter_hourly)
_LOGGER = logging.getLogger(__name__)

class SolarYieldCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, entry):
        super().__init__(hass, _LOGGER, name="Solar Yield Forecast", update_interval=timedelta(minutes=15))
        self.entry = entry
        self.session = async_get_clientsession(hass)
        self.store = Store(hass, 1, f"{DOMAIN}_{entry.entry_id}")
        self.actuals: dict[str, float] = {}
        self.forecast_rows = []
        self.archive_rows = []
        self.factor = 1.0
        self.cal_days = 0
        self.training_error = None
        self.daily_baselines = {}
        self.daily_errors = {}
        self.live_comparisons = []
        self._unsub_power = None
        self.archive_last_attempt: datetime | None = None
        self._unsub_energy = None

    async def async_initialize(self):
        seed_path = Path(__file__).with_name("daily_seed.json")
        try:
            self.actuals = {k: float(v) for k, v in json.loads(await self.hass.async_add_executor_job(seed_path.read_text, "utf-8")).items()}
        except (FileNotFoundError, ValueError, OSError) as exc:
            _LOGGER.debug("No bundled history: %s", exc)
        data = await self.store.async_load() or {}
        for day, value in data.get("actuals", {}).items():
            try:
                val = float(value)
                if math.isfinite(val):
                    self.actuals[day] = val
            except (TypeError, ValueError):
                pass
        self.daily_baselines = data.get("daily_baselines", {})
        self.daily_errors = data.get("daily_errors", {})
        self.live_comparisons = data.get("live_comparisons", [])[-300:]
        self._ingest_state(self.hass.states.get(self.entry.data.get("daily_sensor", DEFAULT_DAILY_SENSOR)))

    async def _one_group(self, base, group, extras):
        params = {
            "latitude": self.entry.data[CONF_LATITUDE],
            "longitude": self.entry.data[CONF_LONGITUDE],
            "hourly": "global_tilted_irradiance,temperature_2m,wind_speed_10m",
            "tilt": group["tilt"],
            "azimuth": open_meteo_azimuth(group["azimuth"]),
            "timezone": TIMEZONE,
            "timeformat": "unixtime",
            **extras,
        }
        async with self.session.get(base, params=params, timeout=ClientTimeout(total=30)) as response:
            response.raise_for_status()
            data = await response.json(content_type=None)
            if data.get("error"):
                raise ValueError(data.get("reason", "Open-Meteo API error"))
            return data

    async def _get_groups(self, base, extras):
        semaphore = asyncio.Semaphore(3)
        async def get(group):
            async with semaphore:
                return await self._one_group(base, group, extras)
        responses = await asyncio.gather(*(get(g) for g in PANEL_GROUPS))
        hourly = combine_weather(responses)
        if base == API_FORECAST:
            try:
                quarters = combine_weather(responses, section="minutely_15", interval_seconds=900)
                return merge_quarter_hourly(hourly, quarters)
            except ValueError:
                _LOGGER.warning("Incomplete 15-minute forecast; using hourly means")
        return hourly

    async def _maybe_refresh_archive(self, now):
        if self.archive_last_attempt is not None and (now - self.archive_last_attempt < timedelta(hours=20)):
            return
        self.archive_last_attempt = now
        if not self.actuals:
            return
        today = now.astimezone(TZ).date()
        archive_end = today - timedelta(days=5)
        archive_start = max(today - timedelta(days=45), datetime.fromisoformat(min(self.actuals)).date())
        if archive_start > archive_end:
            return
        try:
            self.archive_rows = await self._get_groups(API_ARCHIVE, {
                "start_date": archive_start.isoformat(),
                "end_date": archive_end.isoformat(),
            })
            self.factor, self.cal_days, self.training_error = calibration(
                self.actuals, self.archive_rows, today.isoformat()
            )
        except (ClientError, asyncio.TimeoutError, ValueError, KeyError) as exc:
            _LOGGER.warning("Historical Open-Meteo unavailable; keeping calibration: %s", exc)

    def _actual_today(self, now):
        today = now.astimezone(TZ).date().isoformat()
        return float(self.actuals[today]) if today in self.actuals else None

    def _persist(self):
        self.store.async_delay_save(lambda: {
            "actuals": self.actuals,
            "daily_baselines": self.daily_baselines,
            "daily_errors": self.daily_errors,
            "live_comparisons": self.live_comparisons[-300:],
        }, 180)

    def _update_scorecard(self, now, result):
        local = now.astimezone(TZ)
        today = local.date().isoformat()
        for row in result.get("daily", []):
            day = row["date"]
            if day not in self.daily_baselines:
                self.daily_baselines[day] = {
                    "kwh": row["kwh"], "recorded_at": now.isoformat(),
                    "lead_days": (datetime.fromisoformat(day).date() - local.date()).days,
                    "late": day == today and local.hour >= 11,
                }
        for day, snapshot in list(self.daily_baselines.items()):
            if day >= today or day in self.daily_errors or day not in self.actuals:
                continue
            actual = self.actuals[day]
            if actual > 1:
                self.daily_errors[day] = {
                    "forecast_kwh": snapshot["kwh"], "actual_kwh": round(actual, 2),
                    "error_percent": round(100 * (snapshot["kwh"] - actual) / actual, 1),
                    "abs_error_percent": round(100 * abs(snapshot["kwh"] - actual) / actual, 1),
                    "late": snapshot.get("late", False),
                    "lead_days": snapshot.get("lead_days"),
                }
        cutoff = (local.date()-timedelta(days=90)).isoformat()
        self.daily_baselines = {k:v for k,v in self.daily_baselines.items() if k >= cutoff}
        self.daily_errors = {k:v for k,v in self.daily_errors.items() if k >= cutoff}
        errors = [v["abs_error_percent"] for k,v in sorted(self.daily_errors.items())[-30:] if v.get("lead_days",0) >= 1]
        result["forward_error_percent"] = round(sum(errors)/len(errors),1) if errors else None
        result["forward_error_days"] = len(errors)
        result["forecast_baselines"] = {k:v for k,v in sorted(self.daily_baselines.items())[-8:]}
        result["forecast_accuracy_history"] = [{"date":k, **v} for k,v in sorted(self.daily_errors.items())[-30:]]
        result["comparison_history"] = self.live_comparisons[-96:]
        self._persist()

    def _build_data(self):
        now = datetime.now(timezone.utc)
        result = forecast_summary(self.forecast_rows, self.factor, self._actual_today(now), now)
        result.update({
            "factor_percent": round(self.factor * 100, 1),
            "calibration_days": self.cal_days,
            "training_error": self.training_error,
            "updated_at": now.isoformat(),
            "actual_today": self._actual_today(now),
        })
        self._update_scorecard(now, result)
        return result

    async def _async_update_data(self):
        try:
            now = datetime.now(timezone.utc)
            await self._maybe_refresh_archive(now)
            self.forecast_rows = await self._get_groups(API_FORECAST, {"forecast_days": 8, "past_days": 0, "minutely_15": "global_tilted_irradiance,temperature_2m,wind_speed_10m"})
            return self._build_data()
        except (ClientError, asyncio.TimeoutError, ValueError, KeyError) as exc:
            raise UpdateFailed(f"Open-Meteo forecast failed: {exc}") from exc

    def _ingest_state(self, state):
        if state is None or state.state in ("unknown", "unavailable", "none"):
            return False
        try:
            value = float(state.state)
            if not math.isfinite(value) or not 0 <= value <= 1000:
                return False
        except (TypeError, ValueError):
            return False
        stamp = state.last_updated.astimezone(TZ)
        day = stamp.date()
        if stamp.hour < 4 and value > 3:
            day -= timedelta(days=1)
        key = day.isoformat()
        old = self.actuals.get(key, -1)
        if value <= old:
            return False
        self.actuals[key] = value
        self._persist()
        return True

    @callback
    def _energy_changed(self, event):
        if self._ingest_state(event.data.get("new_state")) and self.forecast_rows:
            self.async_set_updated_data(self._build_data())

    @callback
    def _power_changed(self, event):
        state = event.data.get("new_state")
        if state is None or not self.forecast_rows:
            return
        try:
            value = float(state.state)
            if not math.isfinite(value) or value < 0:
                return
            unit = str(state.attributes.get("unit_of_measurement", "W")).lower()
            power_kw = value if unit == "kw" else value / 1000.0
            if unit not in ("kw", "w"):
                return
            now = datetime.now(timezone.utc)
            if self.live_comparisons and (now - datetime.fromisoformat(self.live_comparisons[-1]["time"]) < timedelta(minutes=5)):
                return
            predicted = next((r["kw"] * self.factor for r in self.forecast_rows if r["end"] - r.get("interval_seconds", 3600) <= now.timestamp() < r["end"]), None)
            if predicted is None or predicted < 0.2:
                return
            self.live_comparisons.append({
                "time": now.isoformat(),
                "actual_kw": round(power_kw,2),
                "forecast_interval_mean_kw": round(predicted,2),
            })
            self.live_comparisons = self.live_comparisons[-300:]
            self._persist()
        except (ValueError, TypeError, OverflowError):
            return

    @callback
    def async_start_tracking(self):
        if self._unsub_energy is None:
            self._unsub_energy = async_track_state_change_event(
                self.hass, [self.entry.data.get("daily_sensor", DEFAULT_DAILY_SENSOR)], self._energy_changed
            )
        if self._unsub_power is None:
            self._unsub_power = async_track_state_change_event(
                self.hass, [self.entry.data.get("dc_power_sensor", "sensor.total_dc_power")], self._power_changed
            )

    @callback
    def async_stop_tracking(self):
        if self._unsub_power:
            self._unsub_power()
            self._unsub_power = None
        if self._unsub_energy:
            self._unsub_energy()
            self._unsub_energy = None
