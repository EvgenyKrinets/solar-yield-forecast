"""Hourly Open-Meteo polling + robust learning from real HA energy readings."""
from __future__ import annotations
import asyncio
from functools import partial
from .shape import interval_shape, power_hours, learn_site_profile
import logging
import math
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from aiohttp import ClientError, ClientTimeout
from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from .const import (CONF_PANEL_GROUPS, CONF_TIME_ZONE, DOMAIN, PANEL_GROUPS, API_ARCHIVE, API_ENSEMBLE, API_FORECAST, DEFAULT_DAILY_SENSOR, DEFAULT_DC_SENSOR, TIMEZONE)
from .model import (combine_weather, calibration, daily_shape_normalizers, day_of_hour,
                    forecast_summary, open_meteo_azimuth, merge_quarter_hourly,
                    recent_live_scale, quarter_weather_rows)
from .history import daily_energy_maxima
_LOGGER = logging.getLogger(__name__)

class SolarYieldCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, entry):
        super().__init__(hass, _LOGGER, name="Solar Yield Forecast", update_interval=timedelta(minutes=15))
        self.entry = entry
        self.config = {**entry.data, **entry.options}
        self.groups = self.config.get(CONF_PANEL_GROUPS) or PANEL_GROUPS
        time_zone = self.config.get(CONF_TIME_ZONE) or getattr(hass.config, "time_zone", TIMEZONE)
        try:
            self.tz = ZoneInfo(time_zone)
            self.time_zone = time_zone
        except ZoneInfoNotFoundError:
            _LOGGER.warning("Unknown timezone %s; using %s", time_zone, TIMEZONE)
            self.tz = ZoneInfo(TIMEZONE)
            self.time_zone = TIMEZONE
        self.session = async_get_clientsession(hass)
        self.store = Store(hass, 1, f"{DOMAIN}_{entry.entry_id}")
        self.actuals: dict[str, float] = {}
        self.forecast_rows = []
        self.ensemble_rows = []
        self.shape_factors = {}
        self.shape_report = {"status": "not_loaded"}
        self.shape_profile_updated_at = None
        self._shape_day = None
        self._hourly_weather = []
        self.archive_rows = []
        self.factor = 1.0
        self.cal_days = 0
        self.training_error = None
        self.daily_baselines = {}
        self.daily_errors = {}
        self.live_comparisons = []
        self._unsub_power = None
        self.archive_last_attempt: datetime | None = None
        self.ensemble_last_attempt: datetime | None = None
        self._unsub_energy = None
        self.history_import = {"status": "not_started", "days": 0}
        self._recalculate_lock = asyncio.Lock()
        self._model_update_lock = asyncio.Lock()
        self.recalculation = {'status':'idle','stage':None}
        self._archive_error = None

    async def async_initialize(self):
        seed_path = Path(__file__).with_name("daily_seed.json")
        try:
            self.actuals = {k: float(v) for k, v in json.loads(await self.hass.async_add_executor_job(seed_path.read_text, "utf-8")).items()}
        except (FileNotFoundError, ValueError, OSError) as exc:
            _LOGGER.debug("No bundled history: %s", exc)
        data = await self.store.async_load() or {}
        daily_sensor = self.config.get("daily_sensor", DEFAULT_DAILY_SENSOR)
        stored_sensor = data.get("actuals_sensor")
        same_energy_source = stored_sensor in (None, daily_sensor)
        for day, value in (data.get("actuals", {}) if same_energy_source else {}).items():
            try:
                val = float(value)
                if math.isfinite(val):
                    self.actuals[day] = val
            except (TypeError, ValueError):
                pass
        self.daily_baselines = data.get("daily_baselines", {}) if same_energy_source else {}
        self.daily_errors = data.get("daily_errors", {}) if same_energy_source else {}
        self.history_import = (
            data.get("history_import", self.history_import)
            if same_energy_source else {"status": "not_started", "days": 0}
        )
        try:
            old_system = json.loads(data.get('shape_signature') or '{}')
        except (ValueError, TypeError):
            old_system = {}
        self.live_comparisons = (
            data.get("live_comparisons", [])[-5000:]
            if old_system.get('power_sensor') == self.config.get('dc_power_sensor',DEFAULT_DC_SENSOR)
            and old_system.get('groups') == self.groups else []
        )
        if data.get("shape_signature") == self._shape_signature():
            try:
                stored_shape = {
                    str(hour): float(value)
                    for hour, value in data.get("shape_factors", {}).items()
                    if ((str(hour).startswith('q') and 0 <= int(str(hour)[1:]) < 96)
                        or (str(hour).isdigit() and 0 <= int(hour) < 24))
                    and 0.3 <= float(value) <= 1.8
                }
            except (TypeError, ValueError):
                stored_shape = {}
            if stored_shape:
                self.shape_factors = stored_shape
                self.shape_report = data.get("shape_report", {"status": "persisted_active"})
                self.shape_profile_updated_at = data.get("shape_profile_updated_at")
        self._ingest_state(self.hass.states.get(self.config.get("daily_sensor", DEFAULT_DAILY_SENSOR)))
        await self.async_import_daily_history()

    async def async_import_daily_history(self, force=False):
        """Bootstrap completed daily yields from Recorder on a new installation."""
        now = datetime.now(timezone.utc)
        previous = self.history_import.get("updated_at")
        if not force and previous:
            try:
                if now - datetime.fromisoformat(previous) < timedelta(hours=20):
                    return self.history_import
            except (TypeError, ValueError):
                pass
        if "recorder" not in self.hass.config.components:
            self.history_import = {"status": "recorder_unavailable", "days": len(self.actuals)}
            return self.history_import
        entity = self.config.get("daily_sensor", DEFAULT_DAILY_SENSOR)
        try:
            from homeassistant.components.recorder import get_instance
            from homeassistant.components.recorder.history import get_significant_states
            history = await get_instance(self.hass).async_add_executor_job(partial(
                get_significant_states, self.hass, now-timedelta(days=46), now,
                entity_ids=[entity], significant_changes_only=False,
                minimal_response=False, no_attributes=False))
            samples = []
            for state in history.get(entity, []):
                samples.append((
                    state.last_updated.timestamp(), state.state,
                    state.attributes.get("unit_of_measurement", "kWh"),
                ))
            imported = daily_energy_maxima(samples, self.tz)
            for day, value in imported.items():
                self.actuals[day] = max(value, self.actuals.get(day, -1.0))
            self.history_import = {
                "status": "imported" if imported else "no_history",
                "days": len(imported),
                "total_days": len(self.actuals),
                "entity_id": entity,
                "updated_at": now.isoformat(),
            }
            self._persist()
        except Exception as exc:
            _LOGGER.warning("Could not import daily production history: %s", exc)
            self.history_import = {
                "status": "error", "days": len(self.actuals),
                "entity_id": entity, "updated_at": now.isoformat(),
            }
        return self.history_import

    async def async_recalculate(self):
        """Manually re-import history and rebuild every adaptive layer."""
        if self._recalculate_lock.locked():
            raise HomeAssistantError('Model recalculation is already running')
        async with self._recalculate_lock:
            started = time.monotonic()
            self.recalculation = {'status':'running','stage':'history',
                'started_at':datetime.now(timezone.utc).isoformat()}
            self._publish_recalculation()
            try:
                self.archive_last_attempt = None
                self.ensemble_last_attempt = None
                self._shape_day = None
                await self.async_import_daily_history(force=True)
                # async_request_refresh may return while a debounce timer is
                # pending. Manual completion must await an actual refresh.
                await self.async_refresh()
                if not self.last_update_success:
                    raise HomeAssistantError(str(self.last_exception or 'Forecast refresh failed'))
                warnings = []
                if self.history_import.get('status') in ('error','recorder_unavailable'):
                    warnings.append('production_history_unavailable')
                if self._archive_error:
                    warnings.append('archive_weather_unavailable')
                if (self.shape_report.get('status') in ('history_error','recorder_unavailable')
                    or self.shape_report.get('latest_candidate_status')=='history_error'):
                    warnings.append('power_history_unavailable')
                self.recalculation.update(status='completed_with_warnings' if warnings else 'completed',
                    stage='finished',warnings=warnings,shape_status=self.shape_report.get('status'),
                    eligible_profile_days=self.shape_report.get('available_days',0))
            except asyncio.CancelledError:
                self.recalculation.update(status='failed',stage='cancelled',error='Recalculation cancelled')
                raise
            except Exception as exc:
                self.recalculation.update(status='failed',error=str(exc))
                raise HomeAssistantError(f'Model recalculation failed: {exc}') from exc
            finally:
                self.recalculation.update(finished_at=datetime.now(timezone.utc).isoformat(),
                    duration_seconds=round(time.monotonic()-started,2))
                self._publish_recalculation()

    def _publish_recalculation(self, stage=None):
        if stage is not None and self.recalculation.get('status')!='running':
            return
        if stage is not None and self.recalculation.get('status')=='running':
            self.recalculation['stage']=stage
        if self.data is not None:
            # Progress is not new forecast data: do not reset the refresh timer,
            # cancel debounce work or hide last_update_success=False on failure.
            self.data = {**self.data, 'recalculation':dict(self.recalculation),
                'recalculation_status':self.recalculation['status'],
                'model_status':self._model_status()}
            self.async_update_listeners()
        if 'persistent_notification' in self.hass.config.components:
            from homeassistant.components import persistent_notification
            status=self.recalculation['status']
            message=(f"Status: {status}\n\nStage: {self.recalculation.get('stage')}"
                     f"\n\nDuration: {self.recalculation.get('duration_seconds','…')} s")
            if status!='running':
                message += (f"\n\nProfile: {self.shape_report.get('status')}"
                            f"\n\nEligible profile days: {self.shape_report.get('available_days',0)}")
            if self.recalculation.get('error'):
                message += f"\n\n{self.recalculation['error']}"
            persistent_notification.async_create(self.hass,message,
                title='Solar Yield Forecast — model recalculation',
                notification_id=f'solar_yield_forecast_recalculate_{self.entry.entry_id}')

    def _model_status(self):
        if self.recalculation.get('status')=='running':
            return 'recalculating'
        if self.cal_days>=3:
            return 'ready' if self.shape_factors else 'calibration_only'
        if len(self.actuals)>=3:
            return 'history_loaded'
        return 'collecting_history' if self.actuals else 'no_history'

    def _shape_signature(self):
        """Invalidate a learned profile only when the physical system changes."""
        return json.dumps({
            "profile_version": 2,
            "power_sensor": self.config.get("dc_power_sensor", DEFAULT_DC_SENSOR),
            "latitude": self.config.get(CONF_LATITUDE),
            "longitude": self.config.get(CONF_LONGITUDE),
            "groups": self.groups,
            "time_zone": self.time_zone,
        }, sort_keys=True, separators=(",", ":"))

    async def _one_group(self, base, group, extras):
        params = {
            "latitude": self.config[CONF_LATITUDE],
            "longitude": self.config[CONF_LONGITUDE],
            "hourly": "global_tilted_irradiance,temperature_2m,wind_speed_10m,cloud_cover,direct_radiation,diffuse_radiation,shortwave_radiation",
            "tilt": group["tilt"],
            "azimuth": open_meteo_azimuth(group["azimuth"]),
            "timezone": self.time_zone,
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
        responses = await asyncio.gather(*(get(g) for g in self.groups))
        hourly = combine_weather(responses, self.groups)
        if base == API_FORECAST:
            self._hourly_weather = hourly
        if base == API_FORECAST:
            try:
                quarters = combine_weather(responses, self.groups, section="minutely_15", interval_seconds=900)
                return quarter_weather_rows(merge_quarter_hourly(hourly, quarters))
            except ValueError:
                _LOGGER.warning("Incomplete 15-minute forecast; using hourly means")
        return quarter_weather_rows(hourly) if base == API_FORECAST else hourly

    @staticmethod
    def _ensemble_mean(response):
        """Collapse individual ensemble members into the provider mean."""
        hourly = response.get("hourly") or {}
        times = hourly.get("time") or []
        result = {"time": times}
        for variable in ("global_tilted_irradiance", "temperature_2m", "wind_speed_10m"):
            member_keys = sorted(key for key in hourly if key.startswith(f"{variable}_member"))
            if member_keys and variable in hourly:
                member_keys.insert(0, variable)  # un-suffixed control member
            elif not member_keys and variable in hourly:
                result[variable] = hourly[variable]
                continue
            values = []
            for index in range(len(times)):
                members = []
                for key in member_keys:
                    row = hourly.get(key) or []
                    if index < len(row):
                        try:
                            value = float(row[index])
                            if math.isfinite(value):
                                members.append(value)
                        except (TypeError, ValueError):
                            pass
                values.append(sum(members)/len(members) if members else None)
            result[variable] = values
        return {**response, "hourly": result}

    async def _maybe_refresh_ensemble(self, now):
        """Refresh the lower-resolution 30-day ensemble at most every 6 h."""
        if self.ensemble_last_attempt is not None and now-self.ensemble_last_attempt < timedelta(hours=6):
            return
        self.ensemble_last_attempt = now
        try:
            semaphore = asyncio.Semaphore(3)
            async def get(group):
                async with semaphore:
                    response = await self._one_group(API_ENSEMBLE, group, {
                        "models": "ncep_gefs05", "forecast_days": 31,
                    })
                    return self._ensemble_mean(response)
            responses = await asyncio.gather(*(get(group) for group in self.groups))
            self.ensemble_rows = combine_weather(responses, self.groups)
            for row in self.ensemble_rows:
                row["forecast_source"] = "ensemble"
        except (ClientError, asyncio.TimeoutError, ValueError, KeyError) as exc:
            # The accurate 16-day forecast remains usable when the optional
            # long-range ensemble is temporarily unavailable.
            _LOGGER.warning("Long-range ensemble unavailable; keeping previous data: %s", exc)

    def _combined_forecast_rows(self):
        """Prefer the regular high-resolution forecast over ensemble overlap."""
        combined = {int(row["end"]): row for row in self.forecast_rows}
        for row in self.ensemble_rows:
            combined.setdefault(int(row["end"]), row)
        return [combined[key] for key in sorted(combined)]

    async def _maybe_refresh_archive(self, now):
        if self.archive_last_attempt is not None and (now - self.archive_last_attempt < timedelta(hours=20)):
            return
        self.archive_last_attempt = now
        if not self.actuals:
            return
        today = now.astimezone(self.tz).date()
        archive_end = today - timedelta(days=5)
        archive_start = max(today - timedelta(days=45), datetime.fromisoformat(min(self.actuals)).date())
        if archive_start > archive_end:
            return
        try:
            self._archive_error = None
            self.archive_rows = await self._get_groups(API_ARCHIVE, {
                "start_date": archive_start.isoformat(),
                "end_date": archive_end.isoformat(),
            })
            self.factor, self.cal_days, self.training_error = calibration(
                self.actuals, self.archive_rows, today.isoformat(), self.tz
            )
        except (ClientError, asyncio.TimeoutError, ValueError, KeyError) as exc:
            self._archive_error = str(exc) or type(exc).__name__
            _LOGGER.warning("Historical Open-Meteo unavailable; keeping calibration: %s", exc)

    def _actual_today(self, now):
        today = now.astimezone(self.tz).date().isoformat()
        return float(self.actuals[today]) if today in self.actuals else None

    def _persist(self):
        self.store.async_delay_save(lambda: {
            "actuals": self.actuals,
            "actuals_sensor": self.config.get("daily_sensor", DEFAULT_DAILY_SENSOR),
            "history_import": self.history_import,
            "daily_baselines": self.daily_baselines,
            "daily_errors": self.daily_errors,
            # Keep a private rolling power archive even when Recorder has a
            # short purge window. About 5,000 five-minute daylight samples
            # cover more than a month without touching ESP32/inverter storage.
            "live_comparisons": self.live_comparisons[-5000:],
            # The installation's validated intraday geometry is stable across
            # Home Assistant restarts.  A configuration signature prevents a
            # profile learned for an old array layout from being reused.
            "shape_factors": self.shape_factors,
            "shape_report": self.shape_report,
            "shape_profile_updated_at": self.shape_profile_updated_at,
            "shape_signature": self._shape_signature(),
        }, 180)

    def _update_scorecard(self, now, result):
        local = now.astimezone(self.tz)
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
        live_scale, live_samples = recent_live_scale(self.live_comparisons, now, self.tz)
        result = forecast_summary(
            self._combined_forecast_rows(), self.factor, self._actual_today(now), now,
            self.shape_factors, tz=self.tz, today_scale=live_scale,
        )
        result.update({
            'recalculation':dict(self.recalculation),
            'recalculation_status':self.recalculation['status'],
            "factor_percent": round(self.factor * 100, 1),
            "calibration_days": self.cal_days,
            "training_error": self.training_error,
            "updated_at": now.isoformat(),
            "actual_today": self._actual_today(now),
            "shape_calibration": self.shape_report,
            "shape_factors_utc": self.shape_factors,
            "shape_profile_updated_at": self.shape_profile_updated_at,
            "live_correction_samples": live_samples,
            "history_import": self.history_import,
            'model_status':self._model_status(),
            "site": {
                "name": self.config.get("site_name", self.entry.title),
                "latitude": self.config.get(CONF_LATITUDE),
                "longitude": self.config.get(CONF_LONGITUDE),
                "time_zone": self.time_zone,
                "panel_groups": self.groups,
                "capacity_kwp": round(sum(float(group.get("kwp", 0)) for group in self.groups), 3),
            },
        })
        self._update_scorecard(now, result)
        result["forward_status"] = (
            "validated" if result.get("forward_error_days") else "awaiting_completed_day"
        )
        return result

    async def _async_update_data(self):
        async with self._model_update_lock:
            return await self._async_fetch_model()

    async def _async_fetch_model(self):
        try:
            now = datetime.now(timezone.utc)
            self._publish_recalculation('archive_weather')
            await self._maybe_refresh_archive(now)
            # Thirty retrospective days feed robust shape learning. The regular
            # API supplies the accurate first 16 days; GFS ensemble extends the
            # daily estimate to one month.
            self._publish_recalculation('forecast_weather')
            self.forecast_rows = await self._get_groups(API_FORECAST, {"forecast_days": 16, "past_days": 30, "minutely_15": "global_tilted_irradiance,temperature_2m,wind_speed_10m"})
            self._publish_recalculation('long_range_weather')
            await self._maybe_refresh_ensemble(now)
            self._publish_recalculation('profile_training')
            await self._learn_shape(now)
            return self._build_data()
        except (ClientError, asyncio.TimeoutError, ValueError, KeyError) as exc:
            raise UpdateFailed(f"Open-Meteo forecast failed: {exc}") from exc

    async def _learn_shape(self, now):
        today = now.astimezone(self.tz).date().isoformat()
        if self._shape_day == today:
            return
        self._shape_day = today
        if "recorder" not in self.hass.config.components:
            self.shape_report = {"status": "recorder_unavailable"}
            return
        try:
            from homeassistant.components.recorder import get_instance
            from homeassistant.components.recorder.history import get_significant_states
            entity = self.config.get("dc_power_sensor", DEFAULT_DC_SENSOR)
            history = await get_instance(self.hass).async_add_executor_job(partial(
                get_significant_states, self.hass, now-timedelta(days=30), now,
                entity_ids=[entity], significant_changes_only=False,
                minimal_response=False, no_attributes=False))
            states = []
            for state in history.get(entity, []):
                try:
                    value = float(state.state)
                    unit = state.attributes.get("unit_of_measurement", "").lower()
                    value = value/1000 if unit == "w" else value if unit == "kw" else None
                except (ValueError, TypeError):
                    value = None
                states.append((state.last_updated.timestamp(), value))
            # Older self-recorded samples extend a short Recorder retention.
            # Recorder values win when timestamps happen to match exactly.
            known = {round(stamp, 3) for stamp, _ in states}
            cutoff = (now-timedelta(days=30)).timestamp()
            for sample in self.live_comparisons:
                try:
                    stamp = datetime.fromisoformat(sample["time"]).timestamp()
                    value = float(sample["actual_kw"])
                    if cutoff <= stamp <= now.timestamp() and round(stamp, 3) not in known and math.isfinite(value) and value >= 0:
                        states.append((stamp, value))
                except (KeyError, TypeError, ValueError):
                    continue
            hours = await self.hass.async_add_executor_job(power_hours, states, now.timestamp(), 900)
            candidate, report = learn_site_profile(hours, self.forecast_rows, self.factor, today, self.tz)
            if candidate:
                self.shape_factors = candidate
                self.shape_profile_updated_at = now.isoformat()
                self.shape_report = {**report, "profile_source": "newly_validated"}
                # Today's stored comparisons were made against the previous
                # model. Reusing them would immediately counteract the newly
                # learned profile with an obsolete live scale.
                retained = []
                for sample in self.live_comparisons:
                    try:
                        sample_day = datetime.fromisoformat(sample["time"]).astimezone(self.tz).date().isoformat()
                    except (KeyError, TypeError, ValueError):
                        continue
                    if sample_day != today:
                        retained.append(sample)
                self.live_comparisons = retained
            elif self.shape_factors:
                # A short Recorder window or one unusual validation day must
                # not erase a profile already validated for the same physical
                # array.  It remains active until a new profile passes.
                self.shape_report = {
                    **report,
                    "latest_candidate_status": report.get("status"),
                    "status": "persisted_active",
                    "profile_source": "stored_validated_profile",
                    "profile_updated_at": self.shape_profile_updated_at,
                }
            else:
                self.shape_report = report
        except Exception:
            # Optional calibration must never make the main forecast unavailable.
            _LOGGER.exception("Could not learn intraday power profile")
            if self.shape_factors:
                self.shape_report = {
                    "status": "persisted_active",
                    "latest_candidate_status": "history_error",
                    "profile_source": "stored_validated_profile",
                    "profile_updated_at": self.shape_profile_updated_at,
                }
            else:
                self.shape_report = {"status": "history_error"}

    def _ingest_state(self, state):
        if state is None or state.state in ("unknown", "unavailable", "none"):
            return False
        try:
            value = float(state.state)
            if not math.isfinite(value) or not 0 <= value <= 1000:
                return False
        except (TypeError, ValueError):
            return False
        stamp = state.last_updated.astimezone(self.tz)
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
            normalizers = daily_shape_normalizers(self.forecast_rows, self.shape_factors, self.tz)
            predicted = None
            for row in self.forecast_rows:
                seconds = row.get("interval_seconds", 3600)
                start = row["end"] - seconds
                if start <= now.timestamp() < row["end"]:
                    day = day_of_hour(row["end"], seconds, self.tz)
                    shape = interval_shape(start, seconds, self.shape_factors)
                    predicted = row["kw"] * self.factor * shape / normalizers.get(day, 1.0)
                    break
            if predicted is None or predicted < 0.2:
                return
            self.live_comparisons.append({
                "time": now.isoformat(),
                "actual_kw": round(power_kw,2),
                "forecast_interval_mean_kw": round(predicted,2),
            })
            self.live_comparisons = self.live_comparisons[-5000:]
            self._persist()
        except (ValueError, TypeError, OverflowError):
            return

    @callback
    def async_start_tracking(self):
        if self._unsub_energy is None:
            self._unsub_energy = async_track_state_change_event(
                self.hass, [self.config.get("daily_sensor", DEFAULT_DAILY_SENSOR)], self._energy_changed
            )
        if self._unsub_power is None:
            self._unsub_power = async_track_state_change_event(
                self.hass, [self.config.get("dc_power_sensor", DEFAULT_DC_SENSOR)], self._power_changed
            )

    @callback
    def async_stop_tracking(self):
        if self._unsub_power:
            self._unsub_power()
            self._unsub_power = None
        if self._unsub_energy:
            self._unsub_energy()
            self._unsub_energy = None
