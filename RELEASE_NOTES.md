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
