"""agent/domain/critical_path.py, tasks.md T067.
NOTE (T104): AI-drafted, needs team sign-off to claim hand-written credit.
"""
from agent.domain import critical_path as _cp
from agent.domain.types import Snapshot

AS_OF = "2026-10-04"


def _chain_snapshot():
    return Snapshot(
        as_of=AS_OF,
        projects=[{"id": "PC1", "name": "Chain"}],
        tasks=[
            {"id": "T-A", "project_id": "PC1", "status": "todo", "due_date": "2026-10-10"},
            {"id": "T-B", "project_id": "PC1", "status": "todo", "due_date": "2026-10-12",
             "depends_on_task_id": "T-A"},
            {"id": "T-C", "project_id": "PC1", "status": "todo", "due_date": "2026-10-15",
             "depends_on_task_id": "T-B"},
            {"id": "T-D", "project_id": "PC1", "status": "todo", "due_date": "2026-10-11"},
        ],
    )


def test_off_path_change_gives_zero_slip():
    snap = _chain_snapshot()
    delta = _cp.check(snap, "T-D", "2026-10-13")
    assert delta.delta_days == 0
    assert delta.task_on_path is False
    assert delta.baseline_finish == "2026-10-15"


def test_on_path_change_gives_exact_slip():
    snap = _chain_snapshot()
    delta = _cp.check(snap, "T-B", "2026-10-18")
    assert delta.delta_days == 3
    assert delta.predicted_finish == "2026-10-18"
    assert delta.task_on_path is True


def test_moving_task_earlier_gives_zero_slip():
    snap = _chain_snapshot()
    delta = _cp.check(snap, "T-C", "2026-10-09")
    assert delta.delta_days == 0
    assert delta.predicted_finish == "2026-10-12"


def test_project_with_no_dated_tasks_returns_insufficient_data():
    snap = Snapshot(as_of=AS_OF, projects=[{"id": "P0", "name": "Empty"}])
    delta = _cp.check(snap, "T-X", "2026-10-20")
    assert delta.baseline_finish is None
    assert delta.delta_days == 0


def test_cancelled_predecessors_are_ignored():
    snap = _chain_snapshot()
    snap.tasks.append({"id": "T-Z", "project_id": "PC1", "status": "cancelled",
                       "due_date": "2026-12-31"})
    delta = _cp.check(snap, "T-D", "2026-10-13")
    assert delta.baseline_finish == "2026-10-15"
    assert delta.delta_days == 0
