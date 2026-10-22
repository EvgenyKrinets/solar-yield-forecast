# Solar Yield Forecast — Home Assistant

Custom integration for 48 × 670 W PV panels (five orientations) using Open-Meteo irradiance.

## Installation from HACS (custom repository)

1. Add `https://github.com/EvgenyKrinets/solar-yield-forecast` as a **Custom repository → Integration**.
2. Download Solar Yield Forecast, restart Home Assistant.
3. Settings → Devices & services → Add integration → Solar Yield Forecast.
4. Supply approximate latitude/longitude, `sensor.daily_pv_generation` and `sensor.total_dc_power`.

### Dashboard (manual frontend resource)

Download [solar-comparison-card.js](https://raw.githubusercontent.com/EvgenyKrinets/solar-yield-forecast/main/solar-comparison-card.js) to `/config/www/` and add Dashboard resource `/local/solar-comparison-card.js?v=1.1.0` of type JavaScript module. Use `dashboard.yaml` to add the card. **HACS installs the integration, not this JavaScript card automatically.** This is not yet a fully one-click dashboard installation.

### New in 0.3.0

- Saved day-ahead baseline predictions, never rewritten as the day progresses.
- Separate forward forecast error metric once eligible full-day observations arrive; historical fit error remains separate.
- Samples of actual instant Sungrow power versus forecast *hourly mean*. These are contextual diagnostics, **not** valid direct point-by-point errors.
- A two-panel dashboard: yesterday/today/forecast and 8 daily yield bars.
- Existing entity IDs and .storage persisted energy/calibration retained.

**Important**: the built-in `daily_seed.json` is optional; do not publish private home energy histories. When upgrading from 0.2.0, leave this file in place on the local HA if you still need the old observations. Removing it may temporarily reduce calibration history. Do not delete your existing integration entry.

### Known limitations

- No built-in weather-based 15-minute nowcast yet. Open-Meteo hourly irradiation and instantaneous inverter output naturally differ.
- Forward accuracy requires future completed days and will initially be `unknown`.
- Past daily values are recorded only if Home Assistant sensors update correctly. Continuous daylight clipping is not detected automatically.
- Automated HACS installation requires a public GitHub repository; project files alone do not publish it.
## Automatic card installation (v0.4.0)

The integration now bundles and automatically loads `solar-comparison-card` after Home Assistant restart. No manual JavaScript copy or Lovelace Resource registration is necessary. HACS installs the integration, then the user adds the card to the desired dashboard using [`dashboard.yaml`](./dashboard.yaml). Remove any older `/local/solar-comparison-card.js` resource to prevent an outdated duplicate from loading.

For a card three standard columns wide, use a **Sections** dashboard: configure a 3-column section span, place the card in that section, and choose **Full width card**. The YAML sets `grid_options.columns: full`. Masonry dashboards cannot natively span a single card across three columns.

## Two card sizes (v0.4.1)

The **Wide** card uses `custom:solar-comparison-card` and requests the whole available section width. The **Compact** card uses `custom:solar-comparison-compact` and requests six grid columns. In Sections dashboards, choose where to place each card and drag it to a desired section. A three-column section span allows the wide card to cover three standard columns. Both card types are auto-loaded by the integration; no separate frontend installation.
