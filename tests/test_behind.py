"""(hand-written) agent/domain/behind.py, tasks.md T041."""
from agent.domain.behind import behind_projects
from agent.domain.types import Snapshot

AS_OF = "2026-10-04"


def test_overdue_open_task_makes_project_behind():
    snapshot = Snapshot(
        as_of=AS_OF,
        projects=[{"id": "P1", "name": "Alpha"}],
        tasks=[{"id": "T1", "project_id": "P1", "status": "todo", "due_date": "2026-09-01",
                "assignee_id": "E1"}],
    )
    behind, insufficient = behind_projects(snapshot)
    assert [b.project_id for b in behind] == ["P1"]
    assert behind[0].primary_cause.kind == "overdue_task"


def test_only_integrity_flags_does_not_make_project_behind():
    snapshot = Snapshot(
        as_of=AS_OF,
        projects=[{"id": "P1", "name": "Alpha"}],
        tasks=[{"id": "T1", "project_id": "P1", "status": "todo", "due_date": "2026-11-01"}],  # no assignee, future due
    )
    behind, insufficient = behind_projects(snapshot)
    assert behind == []
    assert insufficient == []


def test_project_with_no_tasks_or_milestones_is_insufficient_data():
    snapshot = Snapshot(as_of=AS_OF, projects=[{"id": "P1", "name": "Empty"}])
    behind, insufficient = behind_projects(snapshot)
    assert behind == []
    assert insufficient == ["P1"]


def test_missed_milestone_makes_project_behind():
    snapshot = Snapshot(
        as_of=AS_OF,
        projects=[{"id": "P1", "name": "Alpha"}],
        milestones=[{"id": "M1", "project_id": "P1", "status": "missed", "date": "2026-09-01"}],
    )
    behind, _ = behind_projects(snapshot)
    assert behind[0].primary_cause.kind == "missed_milestone"


def test_multiple_causes_are_all_reported():
    snapshot = Snapshot(
        as_of=AS_OF,
        projects=[{"id": "P1", "name": "Alpha"}],
        tasks=[{"id": "T1", "project_id": "P1", "status": "todo", "due_date": "2026-09-01"}],
        milestones=[{"id": "M1", "project_id": "P1", "status": "missed", "date": "2026-09-02"}],
    )
    behind, _ = behind_projects(snapshot)
    kinds = {c.kind for c in behind[0].causes}
    assert "overdue_task" in kinds and "missed_milestone" in kinds


def test_primary_cause_is_the_most_days_late():
    snapshot = Snapshot(
        as_of=AS_OF,
        projects=[{"id": "P1", "name": "Alpha"}],
        tasks=[
            {"id": "T1", "project_id": "P1", "status": "todo", "due_date": "2026-10-01"},  # 3 days late
            {"id": "T2", "project_id": "P1", "status": "todo", "due_date": "2026-09-01"},  # 33 days late
        ],
    )
    behind, _ = behind_projects(snapshot)
    assert behind[0].primary_cause.task_id == "T2"


def test_blocked_by_cancelled_predecessor_is_a_dated_cause():
    snapshot = Snapshot(
        as_of=AS_OF,
        projects=[{"id": "P1", "name": "Alpha"}],
        tasks=[
            {"id": "PRED", "project_id": "P1", "status": "cancelled", "due_date": "2026-09-01"},
            {"id": "T1", "project_id": "P1", "status": "todo", "due_date": "2026-11-01",
             "depends_on_task_id": "PRED"},
        ],
    )
    behind, _ = behind_projects(snapshot)
    assert behind[0].primary_cause.kind == "blocked_by_predecessor"
