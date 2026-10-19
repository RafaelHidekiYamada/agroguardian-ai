"""Display helpers: the API stores and returns UTC, the dashboard shows UTC-3."""
from __future__ import annotations

from datetime import timedelta, timezone
from typing import Any

import pandas as pd

LOCAL_TZ = timezone(timedelta(hours=-3))  # UTC-3 (horario de Brasilia)
LOCAL_TZ_LABEL = "UTC-3"

_TIME_COLUMNS = {"timestamp", "recorded_at", "received_at", "created_at", "updated_at", "last_seen_at"}
_HAS_CLOCK_TIME = r"\d{2}:\d{2}"


def to_local_time(value: Any) -> pd.Timestamp | None:
    """Convert an API timestamp (ISO string; a naive value means UTC) to UTC-3."""
    if value is None or value == "":
        return None
    parsed = pd.to_datetime(value, utc=True, errors="coerce", format="ISO8601")
    if pd.isna(parsed):
        return None
    return parsed.tz_convert(LOCAL_TZ)


def format_local_time(value: Any, fmt: str = "%Y-%m-%d %H:%M:%S", default: str = "-") -> str:
    local = to_local_time(value)
    return local.strftime(fmt) if local is not None else default


def localize_time_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Return df with its timestamp columns converted from UTC to UTC-3 (naive datetimes)."""
    if df.empty:
        return df
    result = df.copy()
    for column in result.columns:
        name = str(column)
        if name not in _TIME_COLUMNS and not name.endswith("_at"):
            continue
        series = result[column]
        if series.dtype != object:
            continue
        text = series.dropna().astype(str)
        # Skip date-only values (e.g. daily trends): shifting them would change the day.
        if text.empty or not text.str.contains(_HAS_CLOCK_TIME).all():
            continue
        parsed = pd.to_datetime(series, utc=True, errors="coerce", format="ISO8601")
        if parsed.notna().sum() == 0:
            continue
        result[column] = parsed.dt.tz_convert(LOCAL_TZ).dt.tz_localize(None)
    return result
