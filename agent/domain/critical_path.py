"""
Critical-path what-if over the single-predecessor task chain (spec
FR-007, US5 - tasks.md T069). Pure function over a Snapshot.

Model: project finish = latest due_date among open tasks (status not
`done`/`cancelled`). A proposed date change is applied in memory and
the finish recomputed; delta = max(0, predicted - baseline) in days.
A task is "on path" when it determines the finish: it holds the
baseline finish itself, is a transitive predecessor of the task that
does, or its new date sets a new finish.
"""
from typing import Dict, List, Optional

from . import dates as _dates
from .types import CriticalPathDelta, Snapshot

_CLOSED = ("done", "cancelled")


def _open_tasks(snapshot: Snapshot, project_id: Optional[str] = None) -> List[dict]:
    tasks = snapshot.tasks if project_id is None else snapshot.tasks_for(project_id)
    return [t for t in tasks if t.get("status") not in _CLOSED and _dates.parse_date(t.get("due_date"))]


def project_finish(tasks: List[dict], changes: Optional[dict] = None) -> Optional[str]:
    """Latest due_date over open tasks with `changes` ({task_id: new_due}) applied. None if no dated tasks."""
    latest = None
    for task in tasks:
        due = _dates.parse_date((changes or {}).get(task.get("id"), task.get("due_date")))
        if due and (latest is None or due > latest):
            latest = due
    return _dates.to_iso(latest)


def _transitive_predecessors(snapshot: Snapshot, task_id: str) -> set:
    seen = set()
    current = task_id
    while True:
        row = snapshot.task_by_id(current)
        pred = row.get("depends_on_task_id") if row else None
        if not pred or pred in seen:
            break
        seen.add(pred)
        current = pred
    return seen


def check(snapshot: Snapshot, task_id: str, new_due_date: str,
          project_id: Optional[str] = None) -> CriticalPathDelta:
    """Local what-if for moving one task. Never writes. Unknown project or
    no dated tasks -> baseline None and delta 0 (`insufficient_data`)."""
    tasks = _open_tasks(snapshot, project_id)
    baseline = project_finish(tasks)
    if baseline is None:
        return CriticalPathDelta(project_id=project_id or "", baseline_finish=None,
                                 predicted_finish=None, delta_days=0, task_on_path=False,
                                 checked_task_id=task_id, new_due_date=new_due_date)

    predicted = project_finish(tasks, {task_id: new_due_date})
    base_d = _dates.parse_date(baseline)
    pred_d = _dates.parse_date(predicted)
    delta = max(0, (pred_d - base_d).days) if pred_d and base_d else 0

    # On-path test: the task holds the baseline finish, anchors it via
    # predecessors, or sets the new finish.
    finish_holders = [t.get("id") for t in tasks
                      if _dates.to_iso(_dates.parse_date(t.get("due_date"))) == baseline]
    on_path = task_id in finish_holders
    if not on_path:
        for holder in finish_holders:
            if task_id in _transitive_predecessors(snapshot, holder):
                on_path = True
                break
    if predicted is not None and predicted != baseline:
        if _dates.to_iso(_dates.parse_date(new_due_date)) == predicted:
            on_path = True

    return CriticalPathDelta(
        project_id=project_id or "",
        baseline_finish=baseline,
        predicted_finish=predicted,
        delta_days=delta,
        task_on_path=on_path,
        platform_cp_before=None,
        checked_task_id=task_id,
        new_due_date=new_due_date,
    )
