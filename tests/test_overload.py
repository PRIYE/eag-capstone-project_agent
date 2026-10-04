"""(hand-written) agent/domain/overload.py, tasks.md T054."""
from agent.domain.overload import overloaded
from agent.domain.types import Snapshot
from agent.domain.dates import next_seven_days

AS_OF = "2026-10-04"
WINDOW = next_seven_days(AS_OF)
DAY1 = WINDOW[0].isoformat()  # 2026-10-05, a Monday
DAY2 = WINDOW[1].isoformat()


def _profile(employee_id, hours_per_day=8.0):
    return {"employee_id": employee_id,
            "monday_hours": hours_per_day, "tuesday_hours": hours_per_day,
            "wednesday_hours": hours_per_day, "thursday_hours": hours_per_day,
            "friday_hours": hours_per_day, "saturday_hours": 0, "sunday_hours": 0}


def _alloc(employee_id, task_id, event_id):
    return {"id": f"A-{employee_id}-{task_id}", "employee_id": employee_id,
            "task_id": task_id, "calendar_event_id": event_id}


def _event(event_id, day, hours):
    return {"id": event_id, "start": day, "end": day, "hours": hours}


def test_cross_project_sum_triggers_overload():
    snapshot = Snapshot(
        as_of=AS_OF,
        tasks=[{"id": "T1", "project_id": "P1"}, {"id": "T2", "project_id": "P2"}],
        allocations=[_alloc("E1", "T1", "EV1"), _alloc("E1", "T2", "EV2")],
        events=[_event("EV1", DAY1, 5), _event("EV2", DAY1, 5)],  # 10h total on one day
        profiles=[_profile("E1", 8)],
    )
    result = overloaded(snapshot, AS_OF)
    assert [e.employee_id for e in result.overloaded] == ["E1"]
    assert sorted(result.overloaded[0].projects) == ["P1", "P2"]


def test_within_capacity_all_week_is_not_overloaded():
    snapshot = Snapshot(
        as_of=AS_OF,
        tasks=[{"id": "T1", "project_id": "P1"}],
        allocations=[_alloc("E1", "T1", "EV1")],
        events=[_event("EV1", DAY1, 4)],
        profiles=[_profile("E1", 8)],
    )
    result = overloaded(snapshot, AS_OF)
    assert result.overloaded == []
    assert result.within_capacity_count == 1


def test_exactly_at_capacity_is_not_overloaded():
    snapshot = Snapshot(
        as_of=AS_OF,
        tasks=[{"id": "T1", "project_id": "P1"}],
        allocations=[_alloc("E1", "T1", "EV1")],
        events=[_event("EV1", DAY1, 8)],
        profiles=[_profile("E1", 8)],
    )
    result = overloaded(snapshot, AS_OF)
    assert result.overloaded == []


def test_over_on_one_day_only_still_counts():
    snapshot = Snapshot(
        as_of=AS_OF,
        tasks=[{"id": "T1", "project_id": "P1"}],
        allocations=[_alloc("E1", "T1", "EV1"), _alloc("E1", "T1b", "EV2")],
        events=[_event("EV1", DAY1, 12), _event("EV2", DAY2, 4)],
        profiles=[_profile("E1", 8)],
    )
    result = overloaded(snapshot, AS_OF)
    assert len(result.overloaded) == 1
    excess_days = [d for d in result.overloaded[0].days if d["excess_h"] > 0]
    assert len(excess_days) == 1
    assert excess_days[0]["date"] == DAY1


def test_capacity_unknown_excluded_from_overloaded_and_listed_separately():
    snapshot = Snapshot(
        as_of=AS_OF,
        tasks=[{"id": "T1", "project_id": "P1"}],
        allocations=[_alloc("E2", "T1", "EV1")],
        events=[_event("EV1", DAY1, 20)],  # would be overloaded if capacity were known
        profiles=[],  # no profile for E2
    )
    result = overloaded(snapshot, AS_OF)
    assert result.overloaded == []
    assert result.capacity_unknown == ["E2"]
    assert set(e.employee_id for e in result.overloaded).isdisjoint(result.capacity_unknown)


def test_multi_day_block_split_across_days():
    from datetime import timedelta
    day1 = WINDOW[0]
    day2 = WINDOW[1]
    snapshot = Snapshot(
        as_of=AS_OF,
        tasks=[{"id": "T1", "project_id": "P1"}],
        allocations=[_alloc("E1", "T1", "EV1")],
        events=[{"id": "EV1", "start": day1.isoformat(), "end": day2.isoformat(), "hours": 16}],
        profiles=[_profile("E1", 8)],
    )
    result = overloaded(snapshot, AS_OF)
    # 16h split across 2 days = 8h/day = exactly at capacity, not overloaded
    assert result.overloaded == []


def test_block_outside_window_is_ignored():
    far_future = "2027-01-01"
    snapshot = Snapshot(
        as_of=AS_OF,
        tasks=[{"id": "T1", "project_id": "P1"}],
        allocations=[_alloc("E1", "T1", "EV1")],
        events=[_event("EV1", far_future, 20)],
        profiles=[_profile("E1", 8)],
    )
    result = overloaded(snapshot, AS_OF)
    assert result.overloaded == []
    assert result.within_capacity_count == 0  # E1 never had an in-window allocation at all


def test_window_is_tomorrow_through_plus_seven():
    assert len(WINDOW) == 7
    from agent.domain.dates import parse_date
    assert WINDOW[0] == parse_date(AS_OF) + __import__("datetime").timedelta(days=1)
