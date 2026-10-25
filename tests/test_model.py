import importlib.util, sys, types
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
BASE=Path(__file__).resolve().parents[1]/"custom_components"/"solar_yield_forecast"
pkg=types.ModuleType("solar_yield_forecast");pkg.__path__=[str(BASE)];sys.modules["solar_yield_forecast"]=pkg
for name in ("const","model"):
    spec=importlib.util.spec_from_file_location("solar_yield_forecast."+name,BASE/(name+".py"))
    module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
from solar_yield_forecast.model import open_meteo_azimuth, estimate_kw, calibration
from solar_yield_forecast.const import PANEL_GROUPS

def test_groups_and_azimuths():
    assert sum(x["count"] for x in PANEL_GROUPS)==48
    assert [open_meteo_azimuth(x["azimuth"]) for x in PANEL_GROUPS]==[110.0,110.0,-150.0,-150.0,-50.0]

def test_dc_power():
    assert 0 < estimate_kw(800,27,5,PANEL_GROUPS[0]) < 14.07

def test_custom_group_uses_its_own_capacity():
    small={"id":"roof","count":10,"panel_power_w":400,"kwp":4.0,"tilt":25,"azimuth":180}
    large={**small,"kwp":8.0}
    assert estimate_kw(800,27,5,large) == 2 * estimate_kw(800,27,5,small)

def test_empty_history():
    assert calibration({},[],"2026-10-22")== (1.0,0,None)


def test_small_residential_array_can_calibrate():
    rows=[]
    actuals={}
    for day,value in enumerate((4.0,4.4,3.6),start=1):
        date=f"2026-10-{day:02d}"
        actuals[date]=value
        end=datetime.fromisoformat(date+"T12:00:00+00:00").timestamp()
        rows.append({"end":end,"kw":4.0})
    factor,days,error=calibration(actuals,rows,"2026-10-22",ZoneInfo("UTC"))
    assert factor==1.0
    assert days==3
    assert error is not None
