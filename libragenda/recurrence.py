"""Pure recurrence-rule expansion, decoupled from Appointment.

Per MODULES.md, occurrence generation lives on its own: this module only
turns a weekly pattern into a chronological list of candidate start
datetimes. Turning each candidate into an actual Appointment (and deciding
how to group them, e.g. via Appointment.series_id) is the caller's job —
typically one InMemoryScheduler.create() call per occurrence.
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta


@dataclass(frozen=True, slots=True)
class RecurrenceRule:
    """A weekly-on-fixed-days recurrence, optionally every N weeks."""

    weekdays: frozenset[int]
    start_time: time
    starts_on: date
    interval_weeks: int = 1
    until: date | None = None
    count: int | None = None

    def __post_init__(self) -> None:
        if not self.weekdays:
            raise ValueError("weekdays cannot be empty")
        if any(not 0 <= day <= 6 for day in self.weekdays):
            raise ValueError("weekdays must be between 0 (Monday) and 6 (Sunday)")
        if self.interval_weeks < 1:
            raise ValueError("interval_weeks must be at least 1")
        if self.until is None and self.count is None:
            raise ValueError("a recurrence rule needs an until date, a count, or both")
        if self.count is not None and self.count < 1:
            raise ValueError("count must be at least 1")
        if self.until is not None and self.until < self.starts_on:
            raise ValueError("until cannot be before starts_on")


def generate_occurrences(rule: RecurrenceRule) -> list[datetime]:
    """Expand a RecurrenceRule into chronologically ordered start datetimes."""
    week_start = rule.starts_on - timedelta(days=rule.starts_on.weekday())
    ordered_weekdays = sorted(rule.weekdays)
    occurrences: list[datetime] = []
    cycle = 0
    while rule.count is None or len(occurrences) < rule.count:
        cycle_start = week_start + timedelta(weeks=cycle * rule.interval_weeks)
        stop = False
        for weekday in ordered_weekdays:
            occurrence_date = cycle_start + timedelta(days=weekday)
            if occurrence_date < rule.starts_on:
                continue
            if rule.until is not None and occurrence_date > rule.until:
                stop = True
                break
            occurrences.append(datetime.combine(occurrence_date, rule.start_time))
            if rule.count is not None and len(occurrences) == rule.count:
                break
        if stop:
            break
        cycle += 1
        if cycle > 100_000:
            raise RuntimeError("recurrence expansion exceeded a sane iteration limit")
    return occurrences
