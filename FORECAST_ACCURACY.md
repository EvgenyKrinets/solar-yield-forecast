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
  cannot learn a morning/evening shading profile. No unverified time-of-day
  correction has been fitted to two screenshot curves.

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
