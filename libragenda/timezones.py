"""Timezone helpers shared by the domain layer and vertical consumers.

LibraGenda persists instants in UTC. Each branch declares its own IANA
timezone; verticals are expected to collect wall-clock times from staff or
clients in that branch's local time and convert at the boundary using this
module, rather than teaching the scheduling engine about civil time zones.
"""

from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def validate_timezone(name: str) -> None:
    """Raise ValueError if `name` is not a known IANA timezone."""
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError(f"unknown timezone: {name}") from exc


def to_utc(local_time: datetime, branch_timezone: str) -> datetime:
    """Interpret a naive datetime as branch-local time and convert to UTC.

    Raises ValueError if `local_time` is already timezone-aware, since the
    branch timezone would otherwise silently override whatever offset it
    already carries.
    """
    if local_time.tzinfo is not None:
        raise ValueError("local_time must be naive; it is interpreted as branch-local")
    return local_time.replace(tzinfo=ZoneInfo(branch_timezone)).astimezone(ZoneInfo("UTC"))


def to_branch_local(instant: datetime, branch_timezone: str) -> datetime:
    """Convert an aware (or UTC-assumed naive) instant to branch-local time."""
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=ZoneInfo("UTC"))
    return instant.astimezone(ZoneInfo(branch_timezone))
