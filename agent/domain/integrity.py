"""
Schedule integrity scan (data-model.md IntegrityFlag; spec US3, FR-004).
Pure function over a Snapshot - no I/O.
"""
from typing import List, Optional

from . import dates as _dates
from .types import IntegrityFlag, Snapshot
from .. import config as _config


def _reference_hours(task: dict) -> Optional[float]:
    """budget_hours if present and > 0, else estimated_hours, else None."""
    budget = task.get("budget_hours")
    if budget:
        return float(budget)
    estimated = task.get("estimated_hours")
    if estimated:
        return float(estimated)
    return None


def scan(snapshot: Snapshot, project_id: Optional[str] = None) -> List[IntegrityFlag]:
    """
    Returns one IntegrityFlag per issue found (a task can carry several).
    Kinds: no_assignee, no_due_date, predecessor_cancelled,
    predecessor_overdue, effort_overrun.

    effort_overrun threshold (clarified spec FR-004): logged_hours >
    OVERRUN_RATIO (1.5) * reference_hours, where reference_hours is
    budget_hours, falling back to estimated_hours; if both are missing
    or zero, no flag is raised (can't compute a ratio against nothing).
    """
    flags: List[IntegrityFlag] = []
    tasks = snapshot.tasks_for(project_id) if project_id else snapshot.tasks

    # Only non-terminal tasks are scanned for assignee/due-date hygiene;
    # a cancelled or done task missing those fields isn't an active risk.
    active_statuses = {"todo", "in_progress", "in_review"}

    for task in tasks:
        task_id = task.get("id")
        proj_id = task.get("project_id")
        status = task.get("status")

        if status in active_statuses:
            if not task.get("assignee_id"):
                flags.append(IntegrityFlag(task_id=task_id, project_id=proj_id, kind="no_assignee"))
            if not task.get("due_date"):
                flags.append(IntegrityFlag(task_id=task_id, project_id=proj_id, kind="no_due_date"))

        predecessor_id = task.get("depends_on_task_id")
        if predecessor_id:
            predecessor = snapshot.task_by_id(predecessor_id)
            if predecessor:
                if predecessor.get("status") == "cancelled":
                    flags.append(IntegrityFlag(task_id=task_id, project_id=proj_id,
                                                kind="predecessor_cancelled",
                                                detail=f"blocked on cancelled task {predecessor_id}"))
                else:
                    pred_due = _dates.parse_date(predecessor.get("due_date"))
                    as_of = _dates.parse_date(snapshot.as_of)
                    if (pred_due and as_of and pred_due < as_of
                            and predecessor.get("status") not in ("done",)):
                        flags.append(IntegrityFlag(task_id=task_id, project_id=proj_id,
                                                    kind="predecessor_overdue",
                                                    detail=f"blocked on overdue task {predecessor_id}"))

        reference = _reference_hours(task)
        logged = task.get("logged_hours")
        if reference and logged is not None:
            if float(logged) > _config.OVERRUN_RATIO * reference:
                flags.append(IntegrityFlag(task_id=task_id, project_id=proj_id, kind="effort_overrun",
                                            detail=f"logged {logged}h vs reference {reference}h"))

    return flags


def summary_by_kind(flags: List[IntegrityFlag]) -> dict:
    counts: dict = {}
    for flag in flags:
        counts[flag.kind] = counts.get(flag.kind, 0) + 1
    return counts
