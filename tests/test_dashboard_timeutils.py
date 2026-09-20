from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd

_MODULE_PATH = Path(__file__).resolve().parents[1] / "dashboard" / "timeutils.py"
_spec = importlib.util.spec_from_file_location("dashboard_timeutils", _MODULE_PATH)
timeutils = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(timeutils)


def test_utc_timestamps_are_shown_three_hours_earlier():
    assert timeutils.format_local_time("2026-09-20T17:24:09") == "2026-09-20 14:24:09"
    assert timeutils.format_local_time("2026-09-20T17:24:09Z") == "2026-09-20 14:24:09"
    assert timeutils.format_local_time("2026-09-20T17:24:09.123456+00:00") == "2026-09-20 14:24:09"


def test_conversion_crosses_midnight_backwards():
    assert timeutils.format_local_time("2026-09-21T01:30:00Z") == "2026-09-20 22:30:00"
    assert timeutils.format_local_time("2026-09-21T02:59:00Z", "%d/%m %H:%M") == "20/09 23:59"


def test_missing_or_invalid_values_fall_back_to_default():
    assert timeutils.format_local_time(None) == "-"
    assert timeutils.format_local_time("") == "-"
    assert timeutils.format_local_time("not-a-date", default="?") == "?"


def test_dataframe_time_columns_are_converted_and_other_columns_untouched():
    df = pd.DataFrame(
        {
            "id": [1, 2],
            "recorded_at": ["2026-09-20T17:00:00Z", "2026-09-20T17:00:15.500000+00:00"],
            "received_at": ["2026-09-20T17:00:01", "2026-09-20T17:00:16"],
            "temperature_c": [23.5, 23.6],
            "device_id": ["ESP32-TRATOR-001", "ESP32-TRATOR-001"],
        }
    )

    result = timeutils.localize_time_columns(df)

    assert list(result["recorded_at"].dt.strftime("%H:%M:%S")) == ["14:00:00", "14:00:15"]
    assert list(result["received_at"].dt.strftime("%H:%M:%S")) == ["14:00:01", "14:00:16"]
    assert list(result["temperature_c"]) == [23.5, 23.6]
    assert list(result["device_id"]) == ["ESP32-TRATOR-001"] * 2
    assert df["recorded_at"].iloc[0] == "2026-09-20T17:00:00Z"  # input is not mutated


def test_date_only_columns_are_not_shifted_to_the_previous_day():
    df = pd.DataFrame({"timestamp": ["2026-09-20", "2026-09-21"], "avg_risk": [30.0, 40.0]})

    result = timeutils.localize_time_columns(df)

    assert list(result["timestamp"]) == ["2026-09-20", "2026-09-21"]


def test_empty_dataframe_and_null_values_are_handled():
    assert timeutils.localize_time_columns(pd.DataFrame()).empty

    df = pd.DataFrame({"created_at": ["2026-09-20T17:00:00Z", None]})
    result = timeutils.localize_time_columns(df)

    assert result["created_at"].iloc[0] == pd.Timestamp("2026-09-20 14:00:00")
    assert pd.isna(result["created_at"].iloc[1])
