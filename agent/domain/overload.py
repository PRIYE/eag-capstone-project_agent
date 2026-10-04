"""
Resource overload next week (spec FR-002/5/6, US2 - **graded predicate**).
Pure function over a Snapshot.
"""
from typing import Dict, List

from . import dates as _dates
from .types import EmployeeLoad, OverloadResult, Snapshot


def _parse_dt(value):
    """Full datetime for duration math; falls back to date-only parsing."""
    from datetime import datetime
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        pass
    day = _dates.parse_date(text)
    return datetime(day.year, day.month, day.day) if day else None


def _event_hours_by_day(event: dict) -> Dict:
    """
    Split a calendar event's duration into per-day hours. Most events
    fall within one day; an event crossing midnight contributes hours
    to each day it touches, proportional to the time spent that day.

    Live schema uses `start_at`/`end_at` (no `hours` field); offline
    fixtures use `start`/`end`/`hours`. Accept both (T009). When `hours`
    is absent, derive the duration from the datetimes themselves.
    """
    start = _dates.parse_date(event.get("start", event.get("start_at")))
    end = _dates.parse_date(event.get("end", event.get("end_at")))
    hours = event.get("hours")

    if hours is None and (event.get("start_at") or event.get("end_at")):
        # Live shape: compute duration from the actual timestamps.
        s_dt = _parse_dt(event.get("start_at"))
        e_dt = _parse_dt(event.get("end_at"))
        if s_dt and e_dt and e_dt > s_dt:
            hours = (e_dt - s_dt).total_seconds() / 3600.0

    if hours is not None and (start is None or start == end):
        return {start: float(hours)} if start else {}

    if start is None:
        return {}
    if end is None or end == start:
        return {start: float(hours) if hours is not None else 0.0}

    # Multi-day block: split hours evenly across the days it spans.
    span_days = (end - start).days + 1
    per_day = (float(hours) if hours is not None else 0.0) / span_days
    result = {}
    cur = start
    for _ in range(span_days):
        result[cur] = result.get(cur, 0.0) + per_day
        from datetime import timedelta
        cur = cur + timedelta(days=1)
    return result


def overloaded(snapshot: Snapshot, as_of: str) -> OverloadResult:
    """
    Sums allocated hours per employee per day across ALL projects for
    the 7-day window (tomorrow through +7), compares against each
    employee's declared daily capacity (ProjectResourceProfile), and
    returns the employees over capacity on at least one day.

    Employees with allocations but no capacity profile are excluded
    from `overloaded` and reported separately in `capacity_unknown`
    (clarified spec). The two sets are always disjoint.
    """
    window = _dates.next_seven_days(as_of)
    window_set = set(window)

    # task_id -> project_id, for crediting hours to the right project list
    task_to_project = {t.get("id"): t.get("project_id") for t in snapshot.tasks}

    # allocation_id -> employee_id, task_id (allocations link an
    # employee/resource to a task via a calendar event)
    employee_day_hours: Dict[str, Dict] = {}
    employee_projects: Dict[str, set] = {}

    events_by_id = {e.get("id"): e for e in snapshot.events}

    for alloc in snapshot.allocations:
        employee_id = alloc.get("employee_id") or alloc.get("resource_id")
        if not employee_id:
            continue
        event = events_by_id.get(alloc.get("calendar_event_id"))
        if event is None:
            event = alloc  # some fixtures may inline start/end/hours on the allocation itself

        day_hours = _event_hours_by_day(event)
        for day, hours in day_hours.items():
            if day not in window_set:
                continue
            employee_day_hours.setdefault(employee_id, {}).setdefault(day, 0.0)
            employee_day_hours[employee_id][day] += hours

        task_id = alloc.get("task_id")
        project_id = task_to_project.get(task_id)
        if project_id:
            employee_projects.setdefault(employee_id, set()).add(project_id)

    profiles_by_employee = {}
    for profile in snapshot.profiles:
        emp_id = profile.get("employee_id") or profile.get("id")
        profiles_by_employee[emp_id] = profile

    overloaded_list: List[EmployeeLoad] = []
    capacity_unknown: List[str] = []
    within_capacity_count = 0

    all_employee_ids = set(employee_day_hours.keys())

    for employee_id in sorted(all_employee_ids):
        profile = profiles_by_employee.get(employee_id)
        if profile is None:
            capacity_unknown.append(employee_id)
            continue

        days_detail = []
        week_excess = 0.0
        any_excess = False
        for day in window:
            allocated = employee_day_hours.get(employee_id, {}).get(day, 0.0)
            capacity = float(profile.get(_dates.weekday_field_for(day), 0.0) or 0.0)
            excess = max(0.0, allocated - capacity)
            if excess > 0:
                any_excess = True
                week_excess += excess
            days_detail.append({
                "date": _dates.to_iso(day),
                "allocated_h": round(allocated, 2),
                "capacity_h": round(capacity, 2),
                "excess_h": round(excess, 2),
            })

        if any_excess:
            overloaded_list.append(EmployeeLoad(
                employee_id=employee_id,
                days=[d for d in days_detail if d["excess_h"] > 0],
                week_excess_h=week_excess,
                projects=sorted(employee_projects.get(employee_id, set())),
            ))
        else:
            within_capacity_count += 1

    return OverloadResult(
        window=[_dates.to_iso(d) for d in window],
        overloaded=overloaded_list,
        capacity_unknown=capacity_unknown,
        within_capacity_count=within_capacity_count,
    )
