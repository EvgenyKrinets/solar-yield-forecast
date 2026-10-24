# Contributing

Thank you for helping improve Solar Yield Forecast.

## Before opening an issue

1. Update to the latest release.
2. Restart Home Assistant and reproduce the problem.
3. Check the Home Assistant log for `custom_components.solar_yield_forecast`.
4. Review the known limitations in [README.md](README.md) and [FORECAST_ACCURACY.md](FORECAST_ACCURACY.md).

Never post passwords, tokens, precise residential coordinates or an unredacted Recorder export in a public issue.

## Bug reports

Include:

- Home Assistant version;
- Solar Yield Forecast version;
- installation method;
- source sensor units;
- expected and actual behaviour;
- relevant sanitized log entries;
- sanitized `shape_calibration` attributes when the issue concerns forecast learning.

## Pull requests

Keep changes focused. Explain the problem, the chosen behaviour and how it was tested. User-facing changes should update the README or release notes where appropriate.

Run:

```bash
python -m pytest -q tests
node --test tests/test_card.cjs
python -m compileall -q custom_components/solar_yield_forecast
```

Do not commit private production history, Home Assistant storage files or household coordinates.
