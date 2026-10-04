"""
Date parsing and the 7-day window. `as_of` is always a caller-supplied
date (string or date) - nothing here calls datetime.now()/date.today(),
per data-model.md's Snapshot contract and Constitution Principle I
(deterministic domain, reproducible against fixtures).
"""
from datetime import date, datetime, timedelta
from typing import List, Optional, Union

WEEKDAY_FIELDS = (
    "monday_hours", "tuesday_hours", "wednesday_hours", "thursday_hours",
    "friday_hours", "saturday_hours", "sunday_hours",
)


def parse_date(value: Optional[Union[str, date, datetime]]) -> Optional[date]:
    """
    Parse a platform date/datetime string into a date. Accepts bare
    'YYYY-MM-DD' and full ISO datetimes ('YYYY-MM-DDTHH:MM:SS[Z]').
    Returns None for None/empty/unparsable input rather than raising,
    so a missing due_date becomes "no date" instead of crashing a run.
    """
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        pass
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def to_iso(d: Optional[date]) -> Optional[str]:
    return d.isoformat() if d else None


def next_seven_days(as_of: Union[str, date]) -> List[date]:
    """Tomorrow through +7 days inclusive (clarified spec: window excludes
    today itself), i.e. 7 dates starting at as_of + 1 day."""
    base = parse_date(as_of) if not isinstance(as_of, date) else as_of
    if base is None:
        raise ValueError(f"Cannot parse as_of date: {as_of!r}")
    return [base + timedelta(days=i) for i in range(1, 8)]


def weekday_field_for(d: date) -> str:
    """Map a date's weekday to the ProjectResourceProfile capacity field
    name (monday_hours ... sunday_hours)."""
    return WEEKDAY_FIELDS[d.weekday()]


def days_between(earlier: Optional[date], later: Optional[date]) -> Optional[int]:
    if earlier is None or later is None:
        return None
    return (later - earlier).days
