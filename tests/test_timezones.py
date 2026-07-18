from datetime import datetime

import pytest

from libragenda.timezones import to_branch_local, to_utc, validate_timezone


def test_validate_timezone_accepts_known_iana_name():
    validate_timezone("America/Argentina/Buenos_Aires")


def test_validate_timezone_rejects_unknown_name():
    with pytest.raises(ValueError):
        validate_timezone("Not/A_Zone")


def test_to_utc_converts_naive_branch_local_time():
    local = datetime(2026, 7, 20, 9, 0)
    converted = to_utc(local, "America/Argentina/Buenos_Aires")
    assert converted == datetime(2026, 7, 20, 12, 0, tzinfo=converted.tzinfo)
    assert converted.utcoffset().total_seconds() == 0


def test_to_utc_rejects_already_aware_datetime():
    aware = to_utc(datetime(2026, 7, 20, 9, 0), "UTC")
    with pytest.raises(ValueError):
        to_utc(aware, "UTC")


def test_to_branch_local_round_trips_with_to_utc():
    local = datetime(2026, 7, 20, 9, 0)
    instant = to_utc(local, "America/Argentina/Buenos_Aires")
    back = to_branch_local(instant, "America/Argentina/Buenos_Aires")
    assert back.replace(tzinfo=None) == local


def test_to_branch_local_assumes_naive_instant_is_utc():
    naive_utc = datetime(2026, 7, 20, 12, 0)
    local = to_branch_local(naive_utc, "America/Argentina/Buenos_Aires")
    assert local.hour == 9
