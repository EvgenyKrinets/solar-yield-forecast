"""Country-scoped city suggestions for HA's native searchable picker.

GeoNames cities15000 (CC BY 4.0) supplies names, coordinates and time zones.
Small places not present in this catalogue retain Open-Meteo search fallback.
"""
from __future__ import annotations
import asyncio
from io import BytesIO
from zipfile import ZipFile, BadZipFile
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

URL = 'https://download.geonames.org/export/dump/cities15000.zip'
CACHE_KEY = 'solar_yield_forecast_city_catalog'
MAX_ARCHIVE_BYTES = 12_000_000


def decode_catalog(data):
    with ZipFile(BytesIO(data)) as archive:
        info=archive.getinfo('cities15000.txt')
        if info.file_size > 40_000_000:
            raise ValueError('City catalogue exceeds safe size')
        text=archive.read(info).decode('utf-8')
    countries={}
    for line in text.splitlines():
        fields=line.split('\t')
        if len(fields)<19 or fields[6]!='P' or len(fields[8])!=2:
            continue
        try:
            latitude,longitude=float(fields[4]),float(fields[5])
            ZoneInfo(fields[17])
            if not -90<=latitude<=90 or not -180<=longitude<=180:
                continue
        except (ValueError,ZoneInfoNotFoundError):
            continue
        aliases=[]
        for name in [fields[2],*fields[3].split(',')]:
            if name and name!=fields[1] and name not in aliases and (
                name==fields[2] or any('\u0400'<=c<='\u05ff' for c in name)):
                aliases.append(name)
            if len(aliases)>=5:
                break
        place={'key':fields[0], 'name':fields[1], 'latitude':latitude,
            'longitude':longitude,'time_zone':fields[17], 'country_code':fields[8],
            'country':fields[8], 'admin1':fields[10], 'aliases':aliases}
        countries.setdefault(fields[8],[]).append(place)
    if not countries:
        raise ValueError('City catalogue is empty')
    for places in countries.values():
        places.sort(key=lambda p:p['name'].casefold())
    return countries


async def async_city_catalog(hass):
    """Download once per HA session, sharing in-flight work across flows."""
    from aiohttp import ClientTimeout
    from homeassistant.helpers.aiohttp_client import async_get_clientsession
    state=hass.data.setdefault(CACHE_KEY,{'lock':asyncio.Lock()})
    async with state['lock']:
        if 'countries' not in state:
            async with async_get_clientsession(hass).get(URL,timeout=ClientTimeout(total=30)) as response:
                response.raise_for_status()
                chunks=[]; size=0
                async for chunk in response.content.iter_chunked(65536):
                    size+=len(chunk)
                    if size>MAX_ARCHIVE_BYTES:
                        raise ValueError('City archive exceeds safe size')
                    chunks.append(chunk)
            state['countries']=await hass.async_add_executor_job(decode_catalog,b''.join(chunks))
        return state['countries']
