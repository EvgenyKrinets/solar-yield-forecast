"""Bounded last-known forecast availability; never hide the stale marker."""
from datetime import datetime


def usable_forecast(data, now, tz, maximum_age_seconds=21600):
    if not data or not data.get('daily'):
        return False
    try:
        stamp=datetime.fromisoformat(data['weather_updated_at'])
        age=now.timestamp()-stamp.timestamp()
        return (stamp.tzinfo is not None and 0<=age<=maximum_age_seconds
                and data.get('forecast_date_today')==now.astimezone(tz).date().isoformat())
    except (KeyError,TypeError,ValueError,OverflowError):
        return False
