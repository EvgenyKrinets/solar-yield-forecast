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
