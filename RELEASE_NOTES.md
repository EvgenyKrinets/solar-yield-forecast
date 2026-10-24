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
