<div align="center">

![Solar Yield Forecast hero](assets/solar-yield-forecast-hero.webp)

# Solar Yield Forecast

## 1.6.0 — Первоначальный прогноз и честная история точности

Карточка разделяет **зафиксированный прогноз**, **уточнённый итог дня** (факт + ожидаемый остаток) и **фактическую выработку**. Фиолетовая пунктирная линия показывает сохранённый исходный профиль; зелёная — текущую модель. При выборе прошлого дня пунктир не пересчитывается задним числом.

- **Накануне:** первый успешный свежий прогноз после 20:00 местного времени на следующий день. Это окно, а не гарантия запуска ровно в 20:00: используются обычные обновления интеграции.
- **Утром:** первый доступный полный профиль до первого ненулевого интервала генерации. Если HA включён позже, сохраняется «Поздний запуск», исключённый из оценки точности.
- Снимки неизменяемы при обновлении погоды, калибровке, ручном пересчёте и перезагрузке HA. Записываются время, версия, конфигурация, погодная отметка, кВт·ч и 15-минутная линия.
- В таблице «Точность первоначального прогноза» выберите **7 / 30 дней**, **Накануне / Утром**. Истории с разной заблаговременностью не смешиваются. Хранение — 90 дней; линии загружаются по выбранной дате, а не огромным атрибутом сенсора.
- Отклонение в таблице = **факт − прогноз**; положительное означает, что произведено больше. Смещение в сводке = **прогноз − факт**, положительное означает систематическое завышение. WAPE = сумма абсолютных ошибок / сумма фактической энергии. Только завершённые дни с положительным конечным суточным счётчиком входят в оценку; нулевые/неизвестные итоги исключаются. Отсутствие пропусков в самом суточном счётчике независимо не подтверждается.
- `sensor … Today` публикует `forecast_ledger_history` и `forecast_ledger_summary`. Сводки используют последние 7/30 **календарных дней**, не последние 7/30 доступных измерений; всегда показывается число образцов.

**Ограничения:** история начинается после установки этой версии. Старые первые прогнозы прежних выпусков остаются в прежней диагностике, но не выдаются за новые стандартизированные снимки. Отсутствующие исходные прогнозы за прошлый месяц восстановить честно невозможно. Текущая линия прошлых дней — ретроспективный расчёт, не доказательство точности предсказания. WAPE таблицы оценивает суточную энергию, не ошибку формы кривой. Погода и состав выборки влияют на метрики: уменьшение ошибки само по себе не доказывает обучение. Для строгого сравнения версий потребуется параллельное перспективное тестирование; оно не включено в этот выпуск.

Обновите интеграцию в HACS и перезапустите Home Assistant. Подождите первого подходящего окна фиксации; после завершения этого дня появится первое сравнение. Recalculate не создаёт фиктивную историю и не переписывает исходные снимки. Текущая погодная и адаптивная модель продолжает работать без изменений.

### Adaptive, weather-aware PV production forecasting for Home Assistant

[![Latest release](https://img.shields.io/github/v/release/EvgenyKrinets/solar-yield-forecast?style=for-the-badge&color=16a085)](https://github.com/EvgenyKrinets/solar-yield-forecast/releases/latest)
[![Home Assistant 2025.1+](https://img.shields.io/badge/Home%20Assistant-2025.1%2B-18BCF2?style=for-the-badge&logo=home-assistant&logoColor=white)](https://www.home-assistant.io/)
[![HACS custom](https://img.shields.io/badge/HACS-Custom-41BDF5?style=for-the-badge&logo=home-assistant-community-store&logoColor=white)](https://hacs.xyz/)
[![License MIT](https://img.shields.io/github/license/EvgenyKrinets/solar-yield-forecast?style=for-the-badge&color=6f42c1)](LICENSE)

[![Validate integration](https://github.com/EvgenyKrinets/solar-yield-forecast/actions/workflows/validate.yml/badge.svg)](https://github.com/EvgenyKrinets/solar-yield-forecast/actions/workflows/validate.yml)
[![GitHub stars](https://img.shields.io/github/stars/EvgenyKrinets/solar-yield-forecast?style=flat)](https://github.com/EvgenyKrinets/solar-yield-forecast/stargazers)
[![Open issues](https://img.shields.io/github/issues/EvgenyKrinets/solar-yield-forecast)](https://github.com/EvgenyKrinets/solar-yield-forecast/issues)

**English** · [Русский](README_RU.md) · [Releases](RELEASE_NOTES.md) · [Forecast accuracy](FORECAST_ACCURACY.md)

[![Open in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=EvgenyKrinets&repository=solar-yield-forecast&category=integration)

</div>

Solar Yield Forecast turns weather data and your own production history into an installation-specific solar forecast. It supports arbitrary locations, multiple panel orientations, local learning, interactive history and forecasts up to 30 days.

The setup wizard can resolve a country and city through the Open-Meteo
Geocoding API (location data based on GeoNames), automatically filling WGS84
coordinates and the IANA time zone. Manual coordinates remain available.

The learning layer runs inside Home Assistant. It is adaptive statistical intelligence rather than a remote black-box AI service: your measured production history remains local, while only site coordinates and panel geometry are sent to Open-Meteo for weather and irradiance forecasts.

## Why this integration?

Generic PV calculators know panel capacity and sunlight, but they do not know your roof. Solar Yield Forecast learns the repeatable shape of the real installation—including orientation mix, broad shading, clipping and systematic morning/evening bias—then continuously applies forecast irradiance, cloud cover, temperature and wind.

<table>
<tr>
<td width="33%" valign="top"><strong>☀️ Installation-specific</strong><br><br>Learns a validated power shape from complete, provider-confirmed clear days.</td>
<td width="33%" valign="top"><strong>🌦️ Weather always active</strong><br><br>Open-Meteo GTI and atmospheric conditions modify every forecast interval.</td>
<td width="33%" valign="top"><strong>🧠 Local adaptation</strong><br><br>Calibration, production history and learning samples stay in Home Assistant.</td>
</tr>
<tr>
<td valign="top"><strong>🧭 Multi-orientation arrays</strong><br><br>Configure up to 12 panel groups with independent count, wattage, tilt and azimuth.</td>
<td valign="top"><strong>📈 Interactive analytics</strong><br><br>Day, week, month, year and lifetime views with touch zoom and navigation.</td>
<td valign="top"><strong>🔭 30-day outlook</strong><br><br>High-resolution near-term weather plus a lower-confidence ensemble extension.</td>
</tr>
</table>

## Dashboard preview

<div align="center">
<img src="assets/dashboard-mobile.webp" alt="Solar Yield Forecast Home Assistant dashboard" width="420">
</div>

The bundled Lovelace card compares the previous day, measured PV production and the forecast profile. It also provides 8-day and 30-day energy bars, calendar navigation, history drill-down, pinch zoom, pan and expanded view.

## How it works

```mermaid
flowchart TD
    A[Open-Meteo weather and irradiance] --> C[Hybrid forecast engine]
    B[Local Recorder production history] --> C
    C --> D[Validated installation profile × continuous weather]
    D --> E[HA sensors and interactive dashboard]
```

For each interval, the integration combines:

```text
forecast power = physical PV estimate × daily calibration × learned shape × bounded live correction
```

- **Physical estimate:** tilted irradiance for every configured panel group, temperature and wind.
- **Daily calibration:** robust median comparison between historical modeled and measured energy; it controls total kWh, not peak height by itself.
- **Learned shape:** a persisted, validated profile from clear, complete production days redistributes those kWh across the day; cloudy days cannot carve false dips into it.
- **Live correction:** today's remaining forecast adapts gradually from the latest 90 minutes of measured PV power and may reach ±20% after eight consistent samples.
- **Weather continuity:** cloud and irradiance effects are never switched off.

## Features

- UI setup and reconfiguration—no YAML required for the integration itself.
- Custom site name, latitude, longitude and IANA time zone.
- Country/city search with automatic coordinates and time zone.
- Selectable daily-energy and live-PV-power sensors.
- Up to 12 independent panel groups.
- Automatic installed-capacity summary before saving.
- 15-minute forecast profile where provider data is available, with safe hourly fallback.
- Previous-day, current-day and forecast power curves.
- Saved daily energy history without filling missing dates with fake zeros.
- Today, tomorrow, 7-day and 30-day energy sensors.
- Retrospective training diagnostics and separately tracked forward forecast error.
- Automatic frontend registration of wide and compact Lovelace cards.
- English and Russian setup translations.
- DST-safe local calendar navigation.

## Requirements

| Requirement | Minimum / notes |
|---|---|
| Home Assistant | `2025.1.0` or newer |
| HACS | Recommended for installation and updates |
| Internet | Required for Open-Meteo forecast requests |
| Recorder | Strongly recommended for profile learning and historical charts |
| Daily energy sensor | A monotonically increasing daily PV value in `kWh` |
| Live PV power sensor | PV power in `W` or `kW` |

## Installation

### HACS custom repository

1. Open **HACS → Integrations**.
2. Open the menu and choose **Custom repositories**.
3. Add:

   ```text
   https://github.com/EvgenyKrinets/solar-yield-forecast
   ```

4. Select category **Integration**.
5. Install **Solar Yield Forecast**.
6. Restart Home Assistant.
7. Open **Settings → Devices & services → Add integration → Solar Yield Forecast**.
8. Select a country, enter a city, choose the correct search result, and
   complete the panel-group wizard. Coordinates and the IANA time zone are
   filled automatically. Then open **Solar Forecast** from
   the Home Assistant sidebar. No manual dashboard YAML is required.

Or use the **Open in HACS** button at the top of this page.

### Manual installation

Copy the directory:

```text
custom_components/solar_yield_forecast
```

to:

```text
/config/custom_components/solar_yield_forecast
```

Restart Home Assistant, then add the integration from **Devices & services**.

## Configuration

The setup wizard asks for:

| Setting | Description |
|---|---|
| Site name | Friendly installation or city name |
| Latitude / longitude | Defaults to the Home Assistant home location |
| Time zone | IANA zone such as `Asia/Jerusalem` |
| Daily production | Sensor that reports today's generated energy |
| Live PV power | Sensor that reports current PV power |
| Panel groups | Name, panel count, panel wattage, tilt and azimuth |

Azimuth is clockwise from geographic north:

| Direction | Azimuth |
|---|---:|
| North | `0°` |
| East | `90°` |
| South | `180°` |
| West | `270°` |

Panels with the same wattage, tilt and azimuth belong in one group. Open **Settings → Devices & services → Solar Yield Forecast → Configure** to change the site, sensors or array later. The entry reloads automatically and preserves its stored history.

## Dashboard

The integration automatically registers **Solar Forecast** as a dedicated
sidebar application. It uses the production and energy entities selected in the
setup wizard, so a new user does not need to find or configure the card.

When an administrator opens the sidebar application for the first time, the
integration also creates a valid managed **Solar Yield Forecast** dashboard in
Home Assistant's dashboard registry. That dashboard is hidden from the sidebar
because the dedicated application already occupies one sidebar entry.

The frontend card remains bundled for optional use on other dashboards. Add either:

- **Solar Comparison — Wide** (`custom:solar-comparison-card`)
- **Solar Comparison — Compact** (`custom:solar-comparison-compact`)

Minimal YAML:

```yaml
type: custom:solar-comparison-card
forecast_entity: sensor.solar_yield_forecast_power_profile_today
day_forecast_entity: sensor.solar_yield_forecast_today
```

See [`dashboard.yaml`](dashboard.yaml) for the complete example. For a three-column layout, use a **Sections** dashboard and place the wide card in a section spanning three columns.

If an older version was installed manually, remove `/local/solar-comparison-card.js` from Dashboard Resources to avoid loading duplicate frontend code.

## Entities

| Entity suffix | Unit | Purpose |
|---|---:|---|
| `model_today` | kWh | Whole-day modeled energy, independent of measured progress |
| `today` | kWh | Measured energy so far plus forecast remaining today |
| `tomorrow` | kWh | Tomorrow's forecast energy |
| `next_7_days` | kWh | Forecast total for the next seven complete days |
| `next_30_days` | kWh | Forecast total across the 30-day horizon |
| `remaining_today` | kWh | Estimated energy still available today |
| `power_now` | kW | Forecast mean power for the current interval |
| `power_profile_today` | kW | Today's forecast curve and 15-minute display points |
| `power_profile_tomorrow` | kW | Tomorrow's forecast curve |
| `calibration_factor` | % | Historical daily-energy scale factor |
| `calibration_samples` | days | Days used for daily calibration |
| `training_error` | % | Retrospective in-sample model error |
| `forward_error` | % | Error of saved day-ahead forecasts |
| `forward_samples` | days | Completed forward-forecast samples |

The `Today` sensor attributes also expose clear-day selection, learned shape factors, weather classification, live correction, saved baselines and site configuration.

## Forecast horizon and confidence

| Horizon | Source | Interpretation |
|---|---|---|
| Today–16 days | Open-Meteo regular forecast | Primary weather-aware estimate |
| Days 17–30 | GFS ensemble mean | Lower-confidence planning estimate |
| Historical profile | Local Recorder + stored samples | Installation-specific shape learning |

Striped long-range bars intentionally indicate lower confidence. Forecasts are estimates, not revenue-grade guarantees.

## Accuracy and limitations

- Weather timing is the largest unavoidable uncertainty, especially for local or fast-moving clouds.
- In regions without native 15-minute weather output, the provider may interpolate hourly data.
- Recorder retention limits how far detailed power curves can be reconstructed.
- Missing measurements remain missing; the integration does not invent zero production.
- Export limiting, battery charging policy, inverter clipping, curtailment, snow, dirt and temporary shading can affect measured production.
- The clear-day learner activates only after enough complete, validated history is available.
- `Training Error` describes retrospective fit. `Forward Forecast Error` is the relevant day-ahead metric after enough future days complete.

Read [FORECAST_ACCURACY.md](FORECAST_ACCURACY.md) for diagnostic details.

## Privacy

- Production measurements and learned samples stay in Home Assistant storage.
- No private production history is committed to this repository.
- Open-Meteo receives the configured coordinates and panel geometry needed to calculate irradiance.
- No API key or separate cloud account is required.

## Troubleshooting

| Symptom | Check |
|---|---|
| Integration is not listed | Restart Home Assistant after installation and clear the integration search |
| Card is missing | Restart Home Assistant and hard-refresh the browser/app |
| Dashboard reports that `views` is undefined | Update to the latest release, restart HA and open **Solar Forecast** once as an administrator |
| Old card still appears | Remove the manually registered `/local/solar-comparison-card.js` resource |
| Historical curve has gaps | Check Recorder retention and source sensor availability |
| Learned profile is inactive | Inspect `shape_calibration` on the `Today` sensor |
| Forecast is unavailable | Verify internet access and check the integration log for Open-Meteo errors |

When reporting a problem, include the Home Assistant version, integration version, relevant log entry and sanitized `Today` sensor diagnostics. Do not publish precise home coordinates or private energy history unless you deliberately choose to do so.

## Development

```bash
python -m pytest -q tests
node --test tests/test_card.cjs
python -m compileall -q custom_components/solar_yield_forecast
```

GitHub Actions also runs HACS validation, Python tests, frontend tests, browser rendering and compile checks for every pull request.

## Project status

- Public GitHub repository
- Semantic releases published through GitHub Releases
- HACS custom-repository installation supported
- Repository layout and metadata prepared for a future HACS default-catalog submission
- MIT licensed

See [RELEASE_NOTES.md](RELEASE_NOTES.md) for the complete version history.

## Contributing

Issues and focused pull requests are welcome. Please describe the installation layout, sensor units, expected behaviour and actual behaviour. Keep private recorder exports and exact residential coordinates out of public issues.

Read [CONTRIBUTING.md](CONTRIBUTING.md), [SECURITY.md](SECURITY.md) and the [Code of Conduct](CODE_OF_CONDUCT.md) before contributing.

## License

Released under the [MIT License](LICENSE).

---

<div align="center">

Built for real roofs, real weather and transparent Home Assistant automation.

</div>

# Model update — 1.5.0

The adaptive profile is learned independently for each installation from all its
eligible completed days of 15-minute PV power history, with modest extra weight
for clear days. At least seven eligible days and three chronological holdout days
are required. Ten eligible days mean seven training days and three validation
days, not a profile fitted on only two clear days. Outlier-resistant residuals,
small-sample confidence shrinkage, and morning/peak/evening holdout checks guard
against learning a single passing cloud as a permanent dip. Confidence limits
correction strength; it does not express a probability of forecast correctness.
A continuous measured/model residual corrects the
morning and afternoon shape; weather is always applied, and the daily energy
calibration remains separate. Held-out completed days must show an improvement
before a correction activates. Small roofs and large arrays use the same
relative thresholds. With insufficient or unreliable history the weather model
remains the safe fallback; no accuracy level is guaranteed.

**Пересчитать модель / Recalculate model** is on the integration's device page
under configuration controls, not on the main chart. The Settings button opens
the integration. Existing entity IDs and user-assigned names remain unchanged.

Location setup offers **Home Assistant home**, **Search country and city**, and
**Manual coordinates**. Type a country name in HA's searchable country picker,
confirm the country, then type in the city picker: matching catalogue entries
appear from the first character. Each entry shows its coordinates and time zone,
so the selected field immediately identifies the chosen point. A final wizard
step confirms it. This is not a map or a single combined reactive country/city form.
GeoNames major-city suggestions are downloaded once per HA session; for villages
not listed or a catalogue outage, enter the full city name and confirm an
Open-Meteo search. Coordinates never come from a country centroid. For a remote
roof, use manual coordinates if the city centre is not precise enough.

The learning path and chart both bridge bounded unavailable gaps up to ten
minutes. `shape_calibration.day_diagnostics` explains excluded days.
`training_dates` and `validation_dates` list the exact candidate sample;
`active_profile` describes the correction actually in use, including when the
latest candidate was rejected and a previously validated V3 correction remains.
The integration keeps its own rolling 90-day measured quarter-hour power archive
in Home Assistant storage, independent of Recorder purge settings. Existing
available Recorder power history is backfilled; already deleted detailed data
cannot be reconstructed from daily kWh totals. Restart and changed-source gaps
are not silently turned into full measurement coverage.
**Recalculation status** reports real completion, stages, duration and errors;
**Model status** distinguishes daily-only calibration from a learned profile.
An optional persistent HA notification also shows the manual operation's outcome.
История графиков за прошлые дни — пересчёт модели по доступной
погоде, а не сохранённый прогноз, выпущенный до наступления этого дня.

City suggestions contain information from [GeoNames](https://www.geonames.org/),
available under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/), using
the [cities15000 dataset](https://download.geonames.org/export/dump/).
