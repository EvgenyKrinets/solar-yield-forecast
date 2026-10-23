"""Defaults and configuration keys for Solar Yield Forecast."""
DOMAIN = "solar_yield_forecast"
DEFAULT_LAT = 31.07079
DEFAULT_LON = 35.03269
DEFAULT_DAILY_SENSOR = "sensor.daily_pv_generation"
DEFAULT_DC_SENSOR = "sensor.total_dc_power"
PANEL_KWP = 0.670
# These defaults preserve existing Dimona installations created before the
# panel-group wizard was added. New installations store their own groups in
# the config entry and never depend on these values.
PANEL_GROUPS = [
    {"id":"G1","name":"G1","count":21,"panel_power_w":670,"kwp":14.07,"tilt":10,"azimuth":290},
    {"id":"G2","name":"G2","count":10,"panel_power_w":670,"kwp":6.70,"tilt":30,"azimuth":290},
    {"id":"G3","name":"G3","count":10,"panel_power_w":670,"kwp":6.70,"tilt":15,"azimuth":30},
    {"id":"G4","name":"G4","count":5,"panel_power_w":670,"kwp":3.35,"tilt":30,"azimuth":30},
    {"id":"G5","name":"G5","count":2,"panel_power_w":670,"kwp":1.34,"tilt":30,"azimuth":130},
]
TIMEZONE = "Asia/Jerusalem"
CONF_SITE_NAME = "site_name"
CONF_TIME_ZONE = "time_zone"
CONF_PANEL_GROUPS = "panel_groups"
CONF_GROUP_NAME = "group_name"
CONF_PANEL_COUNT = "panel_count"
CONF_PANEL_POWER_W = "panel_power_w"
CONF_TILT = "tilt"
CONF_AZIMUTH = "azimuth"
CONF_ADD_ANOTHER = "add_another"
CONF_INCLUDE_GROUP = "include_group"
MAX_PANEL_GROUPS = 12
API_FORECAST = "https://api.open-meteo.com/v1/forecast"
API_ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"
API_ENSEMBLE = "https://ensemble-api.open-meteo.com/v1/ensemble"
