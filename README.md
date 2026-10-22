# Solar Yield Forecast — Home Assistant

## 0.7.0 — intraday calibration / обучение формы

The integration now learns the intraday profile from seven days of local DC
power history. Corrections are enabled only after improving a separate
two-day retrospective validation by at least 10%; insufficient data leaves
the base forecast active. The hourly correction uses UTC to avoid DST shifts.
It is combined with the existing daily calibration, and applied to interval
energy as well as the power curve. Model Today exposes the modeled whole-day
energy separately from Today (actual plus remaining).

Поправки формы обучаются по истории DC-мощности автоматически. Статус,
ошибки проверки и коэффициенты доступны в свойствах Today. Это проверка
модели на прошлой погоде, а не обещание такой же точности на завтра.
Для обновления установите 0.7.0 через HACS и перезапустите Home Assistant.


[![Open in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=EvgenyKrinets&repository=solar-yield-forecast&category=integration)

## 0.6.0

15-minute time-weighted analysis replaces sample-count averaging. Only fully covered, completed intervals are shown. Open-Meteo 15-minute forecasts are integrated as kW × 0.25 h, with hourly fallback for the remaining horizon. In Israel, the provider interpolates weather from hourly data; this is not a guarantee of 15-minute weather accuracy. See [release notes](RELEASE_NOTES.md).

Установка: нажмите **Open in HACS**, подтвердите добавление репозитория и скачайте интеграцию. Перезапустите Home Assistant и добавьте Solar Yield Forecast в Devices & services. Карточки устанавливаются автоматически: выберите широкую или компактную в редакторе нужного Dashboard. Первую установку и перезапуск подтверждает пользователь; интеграция не устанавливает HACS самостоятельно.

В 0.6.0 фактическая мощность учитывает длительность показаний, пропуски не соединяются линией. Показываются завершённые 15-минутные интервалы. Новые данные прогноза используют длительность интервала при расчёте энергии. Погодная точность для Израиля ограничена интерполяцией Open-Meteo. Раздел о 0.5.0 ниже описывает предыдущую версию.


Custom integration for 48 × 670 W PV panels (five orientations) using Open-Meteo irradiance.

## Installation from HACS (custom repository)

1. Add `https://github.com/EvgenyKrinets/solar-yield-forecast` as a **Custom repository → Integration**.
2. Download Solar Yield Forecast, restart Home Assistant.
3. Settings → Devices & services → Add integration → Solar Yield Forecast.
4. Supply approximate latitude/longitude, `sensor.daily_pv_generation` and `sensor.total_dc_power`.

### Dashboard

The card is bundled and loaded automatically after restarting Home Assistant.
Add **Solar Comparison — широкий** or **Solar Comparison — компактный** in
the target dashboard's card picker. Remove any old manually registered
`/local/solar-comparison-card.js` resource to prevent duplicate old code.

### Accuracy

See [diagnosis and alternative sources](FORECAST_ACCURACY.md). Forecast weather
accuracy has not been validated against a private recorder export yet.

### Historical release notes

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

## v0.5.0 interactive plot and quarter-hour analysis

Hover or touch the time plot for the previous-day, current-day, and forecast power values. Actual history is binned into 15-minute averages. The weather profile is interpolated to 15-minute display points from hourly radiation (not independent 15-minute weather predictions in Israel). Forecast refresh is scheduled every 15 minutes; raw daily energy is still integrated from the original hourly means. Restart HA after updating in HACS.
