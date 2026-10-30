import json
import re
from pathlib import Path

BASE=Path(__file__).resolve().parents[1]/'custom_components/solar_yield_forecast/translations'


def flatten(value, prefix=''):
    result={}
    for key, child in value.items():
        path=prefix+'.'+key
        if isinstance(child,dict):
            result.update(flatten(child,path))
        else:
            result[path]=child
    return result


def test_setup_catalogs_cover_every_key_and_preserve_placeholders():
    original=flatten(json.loads((BASE/'en.json').read_text()))
    for lang in ('ru','he'):
        target=flatten(json.loads((BASE/f'{lang}.json').read_text()))
        assert target.keys()==original.keys()
        for key,text in original.items():
            assert re.findall(r'\{[^}]+\}',text)==re.findall(r'\{[^}]+\}',target[key]),key
