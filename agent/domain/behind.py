"""
Behind-schedule detection (spec FR-001, US1 - **graded predicate**).
Pure function over a Snapshot + the IntegrityFlag list from
agent/domain/integrity.py (used only as *contributing*, never sufficient
on their own, causes - see spec FR-001 remediated wording).
"""
from typing import List, Optional

from . import dates as _dates
from .types import BehindProject, Cause, IntegrityFlag, Snapshot
from . import integrity as _integrity


def _dated_causes_for_project(snapshot: Snapshot, project_id: str) -> List[Cause]:
    causes: List[Cause] = []
    as_of = _dates.parse_date(snapshot.as_of)
    tasks = snapshot.tasks_for(project_id)
    task_ids = {t.get("id") for t in tasks}

    for task in tasks:
        status = task.get("status")
        if status in ("done", "cancelled"):
            continue

        due = _dates.parse_date(task.get("due_date"))
        if due and as_of and due < as_of:
            causes.append(Cause(kind="overdue_task", task_id=task.get("id"),
                                 days_late=_dates.days_between(due, as_of)))

        predecessor_id = task.get("depends_on_task_id")
        if predecessor_id:
            predecessor = snapshot.task_by_id(predecessor_id)
            if predecessor:
                if predecessor.get("status") == "cancelled":
                    causes.append(Cause(kind="blocked_by_predecessor", task_id=task.get("id"),
                                         detail=f"predecessor {predecessor_id} cancelled"))
                else:
                    pred_due = _dates.parse_date(predecessor.get("due_date"))
                    if (pred_due and as_of and pred_due < as_of
                            and predecessor.get("status") != "done"):
                        causes.append(Cause(kind="blocked_by_predecessor", task_id=task.get("id"),
                                             days_late=_dates.days_between(pred_due, as_of),
                                             detail=f"predecessor {predecessor_id} overdue"))

    for milestone in snapshot.milestones_for(project_id):
        m_status = milestone.get("status")
        m_date = _dates.parse_date(milestone.get("date"))
        if m_status == "missed":
            causes.append(Cause(kind="missed_milestone", milestone_id=milestone.get("id")))
        elif m_status == "upcoming" and m_date and as_of and m_date < as_of:
            causes.append(Cause(kind="overdue_milestone", milestone_id=milestone.get("id"),
                                 days_late=_dates.days_between(m_date, as_of)))

    return causes


def _contributing_causes_for_project(flags: List[IntegrityFlag], project_id: str) -> List[Cause]:
    """
    no_assignee / effort_overrun on this project's tasks, reported as
    contributing factors when the project is already behind for a
    dated reason - never sufficient to place a project on the behind
    list by themselves (spec FR-001 remediated).
    """
    causes = []
    for flag in flags:
        if flag.project_id != project_id:
            continue
        if flag.kind in ("no_assignee", "effort_overrun"):
            causes.append(Cause(kind=flag.kind, task_id=flag.task_id, detail=flag.detail))
    return causes


def behind_projects(snapshot: Snapshot, integrity_flags: Optional[List[IntegrityFlag]] = None):
    """
    Returns (behind: list[BehindProject], insufficient_data: list[str]).

    A project with no tasks and no milestones is reported under
    `insufficient_data`, never classified as behind or on track.
    """
    flags = integrity_flags if integrity_flags is not None else _integrity.scan(snapshot)

    behind: List[BehindProject] = []
    insufficient_data: List[str] = []

    for project in snapshot.projects:
        project_id = project.get("id")
        tasks = snapshot.tasks_for(project_id)
        milestones = snapshot.milestones_for(project_id)

        if not tasks and not milestones:
            insufficient_data.append(project_id)
            continue

        dated_causes = _dated_causes_for_project(snapshot, project_id)
        if not dated_causes:
            continue  # on track - integrity flags alone never put it on this list

        contributing = _contributing_causes_for_project(flags, project_id)
        all_causes = dated_causes + contributing

        primary = max(dated_causes, key=lambda c: c.days_late or 0)

        behind.append(BehindProject(
            project_id=project_id,
            name=project.get("name", project_id),
            causes=all_causes,
            primary_cause=primary,
        ))

    return behind, insufficient_data
