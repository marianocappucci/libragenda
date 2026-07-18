from datetime import date, datetime, time

import pytest

from libragenda.recurrence import RecurrenceRule, generate_occurrences


def test_weekly_rule_generates_one_occurrence_per_matching_weekday():
    # 2026-07-20 is a Monday.
    rule = RecurrenceRule(
        weekdays=frozenset({0, 2}), start_time=time(9, 0),
        starts_on=date(2026, 7, 20), count=4,
    )
    occurrences = generate_occurrences(rule)
    assert occurrences == [
        datetime(2026, 7, 20, 9, 0),  # Mon week 1
        datetime(2026, 7, 22, 9, 0),  # Wed week 1
        datetime(2026, 7, 27, 9, 0),  # Mon week 2
        datetime(2026, 7, 29, 9, 0),  # Wed week 2
    ]


def test_starts_on_mid_week_skips_earlier_weekday_in_first_week():
    # starts_on is a Wednesday; Monday of that same week must not appear.
    rule = RecurrenceRule(
        weekdays=frozenset({0, 2}), start_time=time(9, 0),
        starts_on=date(2026, 7, 22), count=2,
    )
    occurrences = generate_occurrences(rule)
    assert occurrences == [
        datetime(2026, 7, 22, 9, 0),  # Wed week 1 (Mon already passed)
        datetime(2026, 7, 27, 9, 0),  # Mon week 2
    ]


def test_interval_weeks_skips_the_weeks_in_between():
    rule = RecurrenceRule(
        weekdays=frozenset({0}), start_time=time(9, 0),
        starts_on=date(2026, 7, 20), interval_weeks=2, count=3,
    )
    occurrences = generate_occurrences(rule)
    assert [occ.date() for occ in occurrences] == [
        date(2026, 7, 20), date(2026, 8, 3), date(2026, 8, 17),
    ]


def test_until_stops_generation_at_the_boundary_inclusive():
    rule = RecurrenceRule(
        weekdays=frozenset({0}), start_time=time(9, 0),
        starts_on=date(2026, 7, 20), until=date(2026, 8, 3),
    )
    occurrences = generate_occurrences(rule)
    assert [occ.date() for occ in occurrences] == [
        date(2026, 7, 20), date(2026, 7, 27), date(2026, 8, 3),
    ]


def test_until_and_count_both_bound_the_series_whichever_hits_first():
    rule = RecurrenceRule(
        weekdays=frozenset({0}), start_time=time(9, 0),
        starts_on=date(2026, 7, 20), until=date(2026, 12, 31), count=2,
    )
    assert len(generate_occurrences(rule)) == 2


@pytest.mark.parametrize("factory", [
    lambda: RecurrenceRule(frozenset(), time(9), date(2026, 7, 20), count=1),
    lambda: RecurrenceRule(frozenset({7}), time(9), date(2026, 7, 20), count=1),
    lambda: RecurrenceRule(frozenset({0}), time(9), date(2026, 7, 20), interval_weeks=0, count=1),
    lambda: RecurrenceRule(frozenset({0}), time(9), date(2026, 7, 20)),
    lambda: RecurrenceRule(frozenset({0}), time(9), date(2026, 7, 20), count=0),
    lambda: RecurrenceRule(frozenset({0}), time(9), date(2026, 7, 20), until=date(2026, 1, 1)),
])
def test_recurrence_rule_rejects_invalid_values(factory):
    with pytest.raises(ValueError):
        factory()
