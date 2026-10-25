## 1.5.0 — Robust all-weather learning and independent 90-day power archive

- Use **all eligible completed days**, rather than selecting only three clear days. Clear-day weights are modestly higher (1.25 versus 0.75–1.0); weather remains an input at every interval.
- Require at least seven eligible days and at least three chronological holdout days. Ten eligible days now yield **seven training + three validation days**. The current incomplete day is never used.
- Normalize per-day energy, reject interval outliers with median/MAD, fit bounded weighted medians and smooth broad bias. Shrink corrections by `min(1, training_days / 14)` confidence, which is a correction-strength limit, **not a probability or guaranteed accuracy**.
- Require overall held-out improvement, non-worsening behavior on at least two thirds of validation days, and guarded morning/peak/evening errors. A new compatible candidate must also improve on the previously active profile.
- Report exact training/validation dates, per-date and per-phase validation errors, confidence, maximum day weight, and a separate `active_profile` summary when an older validated V3 profile is retained.
- Invalidate V2 learned factors on this model upgrade; measured production history is preserved. With insufficient support or failed validation, fall back to the weather model rather than force an unverified shape.
- Store measured 15-minute energy and coverage for a rolling **90 days** in Home Assistant integration storage, separately from Recorder. Record power/unknown states even when forecasts are unavailable; preserve short-gap rules and conservatively handle restarts.
- Bootstrap existing detailed Recorder history in bounded three-day chunks, preserve complete archived intervals across Recorder purges, and combine historical weather with the recent forecast history. Archived power alone cannot recover deleted measurements or replace missing weather.
- Bound storage write frequency, save completed manual recalculation explicitly, and avoid false empty warning blocks. Notifications now include active training/validation counts and confidence.

Update through HACS, restart HA, then press **Recalculate model** on the integration device. Inspect `shape_calibration.active_profile`, `training_dates`, `validation_dates`, `validation_by_phase` and `power_archive`. Daily energy calibration and forward day-ahead accuracy remain distinct; this release's shape acceptance is a retrospective held-out check, not a promise of future accuracy.

## 1.4.6 — Actionable provider errors and readable city selections

- Preserve request context on weather errors: provider endpoint, panel-group ID, exception type, HTTP status, attempts, timeout and Retry-After. Aggregate failed orientations and drain in-flight batches before reporting failure.
- Retry transient connection/time-out/5xx failures once. Do not immediately retry HTTP 429 or other 4xx errors. Empty exception messages now produce an explicit type/time-out explanation rather than a blank failure toast.
- Show the failure in the manual-recalculation notification and diagnostics, not just a stale-data message. Keep status entities and the retry button available even when forecast updates fail.
- Keep previously loaded forecasts visible only within a bounded six-hour, same-local-day cache, clearly marked stale with the concrete error and original weather timestamp. Expired or absent forecast data is unavailable; cached values are never labeled fresh. The cache is in memory, not a guarantee of offline startup after restarting HA.
- Show a visible warning on the main chart with the actual update error.
- Fix the city autocomplete showing a numeric GeoNames ID after selection. Its displayed value is now the readable city label with coordinates/time zone; backend coordinates still come from the selected catalogue record.

Update via HACS and restart Home Assistant. A new recalculation will either complete or report its concrete provider failure. The empty error emitted by older versions cannot retrospectively prove which provider/network failure occurred.

## 1.4.5 — Reliable history, visible recalculation and city autocomplete

- Learning now linearly bridges bracketed unavailable gaps up to **10 minutes**, consistently with the chart. Longer, leading and trailing gaps remain missing. Quality thresholds are not relaxed.
- Report per-day exclusion reasons and coverage; insufficient history no longer claims that fitting or validation took place.
- Manual recalculation awaits an actual forecast refresh, publishes stages and duration, rejects concurrent requests and distinguishes success, warnings and failure. A persistent HA notification reports progress when the notification component is enabled.
- Add a recalculation diagnostic sensor and distinguish daily-only calibration from a trained power profile. Keep the button exclusively on the integration device configuration page, with retry available after weather failures.
- Country selection uses HA's searchable country picker. After choosing a country, the native city autocomplete filters a preloaded GeoNames major-city catalogue from the first typed character. Results include exact city-centre coordinates, IANA time zone, and selected transliterations/aliases.
- Download/cache the GeoNames catalogue once per HA session, with bounded archive sizes. If it is unavailable or a small place is not listed, typed full-name search through Open-Meteo remains available. No country-centroid coordinate fallback.
- Add weather-only power, daily factor, profile multiplier and cloud cover to intraday forecast diagnostics, allowing weather features to be distinguished from learned profile corrections.

Update through HACS and restart HA. On the integration device press **Recalculate model**, then inspect **Recalculation status**, **Model status** and `shape_calibration.day_diagnostics`. Completion does not guarantee that the available history passed profile validation.

City data: [GeoNames](https://www.geonames.org/), [cities15000](https://download.geonames.org/export/dump/), [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). The catalogue covers major towns/capitals rather than every village; it is an online dependency for initial suggestions, not for existing configured forecasts.

## 1.4.4 — Installation-specific power shape, city selection and settings controls

- Learn smooth 15-minute actual/model residual profiles from each installation's own power history. Prefer at least three provider-confirmed clear days; retain a conservative all-weather fallback only with sufficient history.
- Always apply current weather. No Dimona-specific curve, fixed time shift, orientation override or shared learned factors.
- Validate the same interpolated, daily-energy-normalized profile used by the chart on held-out completed days. Reject incomplete history, changed patterns and corrections that do not improve validation error.
- Reconstruct hourly weather at interval centres while preserving every hourly energy total. Native 15-minute weather takes precedence.
- Invalidate obsolete learned factors when the model, coordinates, source power sensor or panel configuration changes. Preserve compatible measured power history for retraining.
- Keep **Recalculate model** as a configuration button on the integration device; remove it from the main sidebar application header.
- Add English entity translations and readable fallback entity descriptions so unsupported server languages cannot collapse sensor names to just the city.
- Restore explicit Home Assistant home / country-and-city search / manual-coordinate modes for both installation and options. City results show coordinates and time zone; the selected city's exact coordinates are confirmed before panel setup. No country-centre fallback.

Update via HACS, restart Home Assistant, then open Settings → Devices & services → Solar Yield Forecast → device → **Recalculate model**. The new profile activates only after validation succeeds; inspect `shape_calibration` for status and held-out errors. Improved accuracy on an individual installation still requires verification against its own data. Historical curves are retrospective model reconstructions, not immutable day-ahead forecast snapshots.

## 1.4.3 — Existing-history bootstrap and manual recalculation

- Import up to 46 days of the selected daily-yield sensor from Home Assistant
  Recorder on first setup, using the maximum valid value for each local solar
  day and handling a delayed midnight reset.
- Start installation-specific energy calibration immediately when at least
  three suitable completed days already exist instead of waiting weeks after
  installation.
- Remove the former large-system-only 35/15 kWh calibration floor so smaller
  residential arrays can learn from valid days as well.
- Add a translated Model Status diagnostic showing whether the model is ready,
  has loaded history, is still collecting data or has no production history.
- Translate every integration sensor in Russian and English and group model
  metrics as diagnostics.
- Add a **Recalculate model** button both as a Home Assistant button entity and
  in the sidebar application. It re-imports Recorder history, refreshes archive
  weather, relearns the power-curve shape and rebuilds the forecast.
- Keep stored production history isolated from a newly selected energy sensor,
  preventing data from the previous source from contaminating calibration.

## 1.4.2 — Resilient weather data and profiles for every day

- Keep the integration available when Open-Meteo returns isolated null GTI
  intervals; skip only incomplete timestamps instead of rejecting the complete
  forecast response with `Missing hourly irradiance`.
- Provide the calculated green power curve for each available date: up to 30
  previous days, today and all future days supplied by the regular and
  long-range weather models.
- Load only the selected day's profile through an authenticated endpoint, so
  the Home Assistant state and Recorder database are not inflated with all
  profiles at once.

## 1.4.1 — Home Assistant location and in-app settings

- Use Home Assistant's configured home name, latitude, longitude and time zone
  as the default forecast site; remove country and city search from setup.
- Show the active Home Assistant location as read-only information and offer
  one explicit switch for a different manually entered site.
- Keep daily-energy and live-power sensor selection on the same first step.
- Add an administrator-only Settings button to the Solar Forecast sidebar app,
  linking directly to the integration page where the same site, sensor and
  panel-group options can be changed.

## 1.4.0 — One-page city selection and coordinate confirmation

- Keep country, city search, exact-city selection and production sensors on
  the same native Home Assistant setup page.
- After the place search, replace ambiguity with a city dropdown on that same
  page instead of opening a separate location step.
- Show region, country, latitude, longitude and IANA time zone directly in
  every dropdown option, so changing the selected city also changes the
  visible coordinate pair before it is saved.
- Apply the same workflow to both initial setup and Configure, while retaining
  the explicit manual-coordinate fallback.

## 1.3.2 — Validated profile activation and scoped live correction

- Accept a short-history installation profile when two held-out days show at
  least a 5% whole-day WAPE improvement and the independently measured peak
  error does not worsen. This activates useful borderline candidates such as
  12.90% → 11.67% WAPE instead of silently retaining the generic curve.
- Keep the complete daily power curve as the weather-and-history forecast.
  A live correction derived from the latest 90 minutes now affects only the
  remaining energy and current-power estimate; it can no longer lower an
  already elapsed midday peak from an evening measurement.
- Calculate live comparison samples with the same daily shape normalization
  used by the displayed forecast and discard today's obsolete comparisons
  when a newly validated profile is activated.
- Add diagnostics describing the validation thresholds and the live
  correction scope.

## 1.3.0 — Country and city location search

- Replace mandatory coordinate entry during initial setup with a translated
  Home Assistant country selector and city/place-name search.
- Query the Open-Meteo Geocoding API and present up to ten unambiguous matches
  including administrative area, country and WGS84 coordinates.
- Fill latitude, longitude and the IANA time zone automatically from the
  selected result.
- Keep an explicit manual-coordinate fallback for remote roofs and places not
  present in the geocoding database.
- Use the same workflow in Configure; leaving the existing city unchanged
  preserves its coordinates without performing another search.

No API key is required. Place search follows the Home Assistant interface
language where Open-Meteo provides localized names.

## 1.2.1 — Stable real-profile height calibration

- Separate the daily energy forecast from the intraday curve shape. Historical
  shape factors now redistribute the predicted kWh across the day without
  lowering or raising the independently calibrated daily total.
- Preserve the validated real production profile in Home Assistant storage so
  a restart or one failed validation day cannot replace it with the broad,
  low physical fallback curve.
- Invalidate the stored profile automatically when the power sensor, time zone
  or physical panel-group configuration changes.
- Let consistent live measurements strengthen today's correction gradually:
  four samples start gently, while eight or more samples can correct a
  systematic height error by up to 20%.
- Publish the stored profile timestamp and per-day energy normalizers as sensor
  diagnostics.

Update through HACS and restart Home Assistant. The first refresh validates the
Recorder history; subsequent restarts retain the last successful site profile.

## 1.2.0 — One-click dashboard and sidebar application

- Register a dedicated **Solar Forecast** application in the Home Assistant
  sidebar after the integration setup wizard finishes.
- Open the complete interactive forecast interface without manually creating a
  Lovelace card or editing YAML.
- Automatically create a valid managed Lovelace dashboard, including its
  required `views` array, the first time an administrator opens the sidebar
  application. The dashboard is available under Home Assistant Dashboards but
  is hidden from the sidebar to avoid a duplicate menu item.
- Use the exact production and energy sensors selected during setup, plus the
  actual entity IDs created for this config entry.
- Repair an empty or invalid previously managed dashboard instead of showing
  `Expected an array value at views`.
- Preserve manual card support for users who also want the forecast on another
  dashboard.

## 1.1.1 — Short Recorder gap recovery

- Linearly interpolate brief `unknown` or `unavailable` PV power gaps lasting
  up to 10 minutes, using the measured values immediately before and after the
  interruption.
- Prevent a short Home Assistant restart from discarding entire 15-minute
  chart intervals and making a few minutes of downtime look like an hour.
- Preserve honest missing-data semantics: interruptions longer than 10 minutes
  remain visible gaps and are not included as measured history.
- Keep the forecast model, weather correction, configuration and learned
  production history unchanged.

## 1.1.0 — Real-profile forecast with continuous weather correction

- Learn the installation's real intraday shape only from provider-confirmed clear, complete historical days.
- Continue applying Open-Meteo GTI, cloud cover, direct/diffuse radiation, temperature and wind to every forecast interval; there is no weather on/off switch.
- Exclude cloudy days from the stable installation profile while retaining their normal weather losses in forecasts.
- Replace the former ±18%, five-hour profile restriction with a validated three-hour clear-profile smoother and an 8% per-hour slope guard, allowing broad orientation and shading differences without narrow artificial notches.
- Correct today's remaining forecast from the latest 90 minutes of measured PV power, bounded to ±8% so brief clouds and sensor transients cannot cause large jumps.
- Publish clear-day counts, weather classification, energy-weighted cloud cover and live-correction diagnostics in sensor attributes.
- Preserve all configuration, learned storage, daily observations and dashboard behaviour.

Update through HACS, restart Home Assistant and allow the first refresh to analyse Recorder history. No reconfiguration is required.

## 1.0.4 — HACS download compatibility

- Use the standard HACS tagged-source installation path instead of a custom ZIP release asset.
- Avoid the GitHub release-asset redirect whose oversized security header can be rejected by Home Assistant's `aiohttp` client.
- Keep the 1.0.3 settings-selector fix unchanged; existing configuration, learned calibration and production history are preserved.

Update through HACS and restart Home Assistant. No integration reconfiguration is required.

## 1.0.1 — Installed-capacity review

- Add a final review step to both initial setup and Configure flows.
- Show each group as panel count × panel wattage = group kWp, together with its tilt and azimuth.
- Show total panel count and total installed system capacity at the bottom before saving.

## 1.0.0 — Configurable sites and panel groups

- Replace the fixed Dimona array with a multi-step Home Assistant setup wizard. Use the HA home location as the default, while allowing a custom site/city name, latitude, longitude and IANA time zone.
- Select the daily energy and live PV power entities from the UI.
- Add up to 12 panel groups with independent names, panel counts, panel wattages, tilts and north-clockwise azimuths.
- Add an Options flow so all site and array settings can be changed later without deleting the integration. Saving options reloads the entry automatically and preserves its private history.
- Keep the former 48 × 670 W five-group configuration as a compatibility fallback for existing entries. New installations store their own array definition.
- Calculate local days, profiles, calibration and Recorder ingestion in the configured site time zone.

Update through HACS and restart Home Assistant. Existing users can open **Configure** to review or change the original groups; no reinstallation is required.

## 0.9.1 — Adaptive fallback for short Recorder history

- Fix the practical reason a stable real production curve could still show the uncorrected broad physical forecast: 0.9.0 required 19 complete **power-history** days, while Home Assistant Recorder often retains fewer even when daily energy totals exist for months.
- Keep the full 30-day learner when at least 19 complete days are available. With 7–18 complete days, use two held-out validation days and a stricter 10% overall plus 3% peak-region improvement gate. The same daily normalisation, five-hour smoothing and 3.5% adjacent-factor limit remain active, so the fallback cannot restore the old unstable one-hour notch behaviour.
- Retain up to 5,000 private five-minute actual/forecast samples in the integration's Home Assistant storage. These gradually extend shape learning beyond Recorder's purge window; no measurements are uploaded or committed to GitHub.
- Publish `history_mode`, `available_days` and `minimum_hour_support` in `shape_calibration` for diagnosis.

Update through HACS and restart Home Assistant. The adaptive shape is recalculated on the first successful update after restart.

## 0.9.0 — Robust 30-day learning and monthly forecast

- Learn the intraday correction from 30 days of Recorder history. Normalise each training day by its daily energy before learning shape, require at least 19 complete days, use five held-out validation days and at least ten observations per corrected UTC hour.
- Smooth the learned shape over five hours, limit adjacent correction changes to 3.5%, and require the peak-period WAPE not to worsen. A weak or unvalidated correction falls back to the physical forecast instead of drawing an artificial midday notch.
- Use the regular Open-Meteo forecast for the first 16 days and extend daily estimates to 30 days with the mean of the 31-member, 0.5-degree GFS ensemble. Long-range striped bars are intentionally marked as lower confidence.
- Add an **8 days / Month** switch below the power chart and a `Solar Yield Forecast Next 30 Days` sensor. The existing 7-day sensor remains compatible.
- Keep 15-minute touch zoom, calendar navigation, missing-history semantics and stored daily observations unchanged.

Update through HACS, restart Home Assistant and refresh the dashboard. The first start can take longer while the 30-day ensemble and Recorder history are loaded.

## 0.8.2 — Touch gesture continuity

Keep the SVG and touch targets mounted during pinch updates. Use two-dimensional finger distance and rebase panning when one finger is lifted. Hide tooltips during gestures. Short missing history intervals are shown with explicitly labelled dashed guides; measured curves/fills and energy remain unchanged, and tooltips no longer borrow a neighbour's value inside a missing interval.

## 0.8.1 — Mobile chart fixes

Preserve card/controls and scroll position during updates, including expanded view. Format fractional zoom ticks as HH:mm. Interpolate learned hourly shape corrections continuously and integrate them consistently for power/energy; held-out validation now evaluates that same correction. Weather-driven changes remain visible.

## 0.8.0 — Interactive history chart

- Day / Week / Month / Year / All-time tabs, calendar and previous/next period navigation.
- Two-finger horizontal zoom, drag while zoomed, reset, Ctrl+wheel, expanded view.
- Orange PV fill, blue previous-day curve, green forecast and series switches.
- Historical daily curves load the selected day and preceding day from Recorder; unavailable history remains empty. Today/tomorrow profiles are shown only where available.
- Energy views use the integration's saved daily totals. Missing days are not zero-filled; month/year totals can be partial. Click bars to drill down.
- Israel calendar navigation respects DST. Fast navigation ignores stale history responses.

Update through HACS after release, then restart Home Assistant. Recorder retention limits older power curves. Saved daily totals begin with the integration's available history; this update does not recover deleted Recorder data.

# 0.7.2

- Match the requested upper chart colors: yesterday blue, today's measured power golden yellow with a translucent area, and forecast green. Apply matching colors to the legend and tooltip.
- Fill only today's observed intervals; leave future time and missing intervals unfilled. Keep the separate eight-day bar forecast.
- Includes the smooth curves and larger typography from 0.7.1. Forecast calculations and interval values are unchanged.

# 0.7.1

- Draw shape-preserving smooth curves through the original 15-minute points. Curves do not overshoot the neighboring values or bridge missing intervals. Tooltip values, forecast calculations and energy totals are unchanged. Set `smooth: false` for straight segments.
- Use the Home Assistant/system font, larger headings, 13px axis labels, 14px legends and tooltips, and tabular numbers. Keep all labels readable in narrow cards: fewer time ticks and two rows of daily bars.
- Improve chart spacing, display power/energy units, and keep the 24:00 label inside the card.
- Preserve already-loaded history on a temporary refresh error and show a readable error message.
- Refresh the automatically loaded frontend cache version and repair the integration display name.

Update in HACS, restart Home Assistant, then refresh the dashboard. Remove any old manually registered `/local/solar-comparison-card.js` resource if it overrides the automatically loaded card.

# 0.7.0

- Learn intraday power bias from the local recorder's previous seven days, using time-weighted energy and UTC hour buckets.
- Train on older days and enable corrections only when the newest two completed days improve retrospective hourly WAPE by at least 10%. Require at least six days overall, four samples per corrected hour, and adequate valid coverage. Missing data or recorder errors retain the base model.
- Add Model Today: the complete modeled daily yield stays separate from Today (actual energy plus the remaining forecast).
- Publish calibration status, UTC-hour multipliers, training/validation counts and retrospective errors as attributes. These are model-fit diagnostics, not measured future forecast accuracy.
- Retain Open-Meteo pending a prospective source comparison; do not embed household measurements in the integration.

## Earlier 0.6.0 fixes

- Time-weighted recorder power analysis for completed 15-minute intervals. Unknown and unavailable readings break coverage. No sample-count averaging.
- Open-Meteo 15-minute GTI, temperature and wind; incomplete hours retain hourly forecast coverage. Power is integrated using each interval's duration, including remaining energy and DST.
- Hover/touch interval values, responsive plot dimensions, gaps, invalid timestamps and unrelated Home Assistant updates handled correctly.
- Wide/compact card picker defaults and automatic frontend loading with versioned cache URL.
- HACS install link and automatically packaged GitHub releases.

Open-Meteo interpolates weather to 15 minutes in Israel. This release improves temporal accounting, not guaranteed weather accuracy. Recorder states are treated as held until the next state; this is an estimate from sensor history, not a revenue-grade energy measurement. Only completed, fully covered intervals are plotted.

Update through HACS, restart Home Assistant and refresh the browser. The card is installed automatically. Choose the target dashboard/section using Home Assistant's card editor. Remove any old manually registered `/local/solar-comparison-card.js` resource.
