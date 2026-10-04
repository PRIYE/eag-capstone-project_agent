"""(hand-written) agent/domain/integrity.py, tasks.md T040."""
from agent.domain.integrity import scan
from agent.domain.types import Snapshot


def _snapshot(tasks, as_of="2026-10-04"):
    return Snapshot(as_of=as_of, tasks=tasks)


def test_no_assignee_and_no_due_date_are_two_separate_flags():
    tasks = [{"id": "T1", "project_id": "P1", "status": "todo"}]  # neither set
    flags = scan(_snapshot(tasks))
    kinds = sorted(f.kind for f in flags)
    assert kinds == ["no_assignee", "no_due_date"]


def test_predecessor_cancelled_and_overdue_each_flagged_separately():
    tasks_cancelled_pred = [
        {"id": "PRED", "project_id": "P1", "status": "cancelled", "assignee_id": "E1", "due_date": "2026-09-01"},
        {"id": "T1", "project_id": "P1", "status": "todo", "assignee_id": "E1", "due_date": "2026-10-20",
         "depends_on_task_id": "PRED"},
    ]
    flags = scan(_snapshot(tasks_cancelled_pred))
    assert any(f.kind == "predecessor_cancelled" and f.task_id == "T1" for f in flags)

    tasks_overdue_pred = [
        {"id": "PRED", "project_id": "P1", "status": "in_progress", "assignee_id": "E1", "due_date": "2026-09-01"},
        {"id": "T2", "project_id": "P1", "status": "todo", "assignee_id": "E1", "due_date": "2026-10-20",
         "depends_on_task_id": "PRED"},
    ]
    flags2 = scan(_snapshot(tasks_overdue_pred))
    assert any(f.kind == "predecessor_overdue" and f.task_id == "T2" for f in flags2)


def test_effort_overrun_threshold_is_exactly_150_percent_exclusive():
    tasks_at_150 = [{"id": "T1", "project_id": "P1", "status": "todo", "assignee_id": "E1",
                      "due_date": "2026-10-20", "budget_hours": 10, "logged_hours": 15}]
    flags_at = scan(_snapshot(tasks_at_150))
    assert not any(f.kind == "effort_overrun" for f in flags_at)

    tasks_over_150 = [{"id": "T1", "project_id": "P1", "status": "todo", "assignee_id": "E1",
                        "due_date": "2026-10-20", "budget_hours": 10, "logged_hours": 15.1}]
    flags_over = scan(_snapshot(tasks_over_150))
    assert any(f.kind == "effort_overrun" for f in flags_over)


def test_reference_hours_falls_back_to_estimated_hours():
    tasks = [{"id": "T1", "project_id": "P1", "status": "todo", "assignee_id": "E1",
              "due_date": "2026-10-20", "estimated_hours": 10, "logged_hours": 20}]
    flags = scan(_snapshot(tasks))
    assert any(f.kind == "effort_overrun" for f in flags)


def test_both_hours_missing_yields_no_flag():
    tasks = [{"id": "T1", "project_id": "P1", "status": "todo", "assignee_id": "E1",
              "due_date": "2026-10-20", "logged_hours": 20}]
    flags = scan(_snapshot(tasks))
    assert not any(f.kind == "effort_overrun" for f in flags)
