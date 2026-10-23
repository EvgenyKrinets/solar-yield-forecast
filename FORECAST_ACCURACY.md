# Forecast accuracy and diagnosis

The October 22 screenshots show a lower predicted midday peak and higher
morning/evening power than the measurements. A uniform multiplier cannot
correct both signs of error. The screenshots alone cannot establish whether
the cause is shading, geometry, weather, DC/AC conversion or interpolation.

## Confirmed implementation issues addressed in 0.6.0

- Recorder samples were averaged by count, biasing results toward times with
  more state changes. They are now integrated as held states over elapsed time.
- Hourly interpolation could change the displayed energy and blur sunrise and
  sunset. Forecast intervals now use the provider's 15-minute means when
  present and energy-conserving hourly means otherwise.
- Interval duration is explicitly included in energy and remaining-day sums.
- Daily calibration is a single scalar based on historical daily energy. It
  cannot learn a morning/evening shading profile. Version 0.7.0 learns time-of-day
  corrections from recorder data, with separate held-out validation days.

## Measurements needed before changing the production model

Use 7–14 complete days of recorder power and energy, including sensor units,
unavailable intervals and the integration's calibration attributes. Confirm
that daily PV energy and DC power describe the same energy boundary. Compare
energy-integrated quarter hours, not instantaneous peaks. Separate morning,
midday and evening bias. Check array orientations, shading and inverter limits.
Select parameters on earlier days and score them on untouched later days.
Forecasts fetched retrospectively are not proof of day-ahead forecast accuracy.

## Alternative sources evaluated

- [Open-Meteo forecast](https://open-meteo.com/en/docs): GTI, temperature and
  wind for all five panel groups without an account. In Israel, 15-minute
  weather is interpolated from hourly data. Retained pending measured comparison.
- [Open-Meteo satellite radiation](https://open-meteo.com/en/docs/satellite-radiation-api):
  useful independent radiation evidence for past intervals, with acquisition
  delays; it is not tomorrow's forecast. It can help distinguish weather error
  from PV conversion/shading error.
- [Solcast](https://www.solcast.io/free-rooftop-solar-forecasting): an alternative
  PV forecast requiring an account/site configuration; hobbyist API quotas
  apply. No account created, key requested, or accuracy advantage assumed.
- [Forecast.Solar in Home Assistant](https://www.home-assistant.io/integrations/forecast_solar/):
  the free offering supports one plane; paid multi-plane support in the HA
  integration is limited to four, while this installation has five groups.

Private recorder exports and home credentials must not be committed to GitHub.

## 0.7.0 calibration safeguards

Seven days of local recorder history are integrated by elapsed time. Older
days train UTC-hour factors; the newest two completed days validate them.
At least six days, four training samples per hour, 12 validation samples and
30 kWh of validation energy are required. Factors are bounded to 0.2–1.5.
They activate only with a 10% relative improvement in retrospective WAPE.
Invalid states and partial hours are excluded. Recorder failure retains the
base forecast. No household history is published. A new Model Today sensor
distinguishes model energy from Today (actual plus remaining).

## 0.9.0 calibration and horizon safeguards

Shape learning reads 30 days and needs at least 19 complete days. Daily
amplitude is removed before hourly ratios are calculated. Ten samples per UTC
hour, five validation days, five-hour smoothing, a 3.5% adjacent-factor limit
and an independent peak-period WAPE check prevent isolated cloudy intervals
from becoming a permanent midday notch. Failure of any gate uses the base
physical model.

The regular forecast API supplies the first 16 days. Days 17–30 use the mean
of the 31-member NCEP GEFS 0.5-degree ensemble. Those long-range values are
marked `source: ensemble` and rendered as striped bars because their local
day-to-day accuracy is inherently lower.
