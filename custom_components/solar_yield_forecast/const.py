"""Defaults and the five measured PV installation orientations."""
DOMAIN = "solar_yield_forecast"
DEFAULT_LAT = 31.07079
DEFAULT_LON = 35.03269
DEFAULT_DAILY_SENSOR = "sensor.daily_pv_generation"
DEFAULT_DC_SENSOR = "sensor.total_dc_power"
PANEL_KWP = 0.670
PANEL_GROUPS = [
    {"id":"G1","count":21,"tilt":10,"azimuth":290},
    {"id":"G2","count":10,"tilt":30,"azimuth":290},
    {"id":"G3","count":10,"tilt":15,"azimuth":30},
    {"id":"G4","count":5,"tilt":30,"azimuth":30},
    {"id":"G5","count":2,"tilt":30,"azimuth":130},
]
TIMEZONE = "Asia/Jerusalem"
API_FORECAST = "https://api.open-meteo.com/v1/forecast"
API_ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"
API_ENSEMBLE = "https://ensemble-api.open-meteo.com/v1/ensemble"
