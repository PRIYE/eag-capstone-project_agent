"""agent/domain/delay.py, tasks.md T084.
NOTE (T104): AI-drafted, needs team sign-off to claim hand-written credit.
"""
from agent.domain import behind as _behind
from agent.domain import dates as _dates
from agent.domain.types import DelayFacts, Snapshot


def _cause_date(snapshot: Snapshot, cause) -> object:
    if cause.task_id:
        row = snapshot.task_by_id(cause.task_id)
        return _dates.parse_date((row or {}).get("due_date"))
    if cause.milestone_id:
        for milestone in snapshot.milestones:
            if milestone.get("id") == cause.milestone_id:
                return _dates.parse_date(milestone.get("due_date", milestone.get("date")))
    return None


def _cause_record_id(cause) -> str:
    return cause.task_id or cause.milestone_id or ""


def delay_facts(snapshot: Snapshot, project_id: str) -> DelayFacts:
    """Primary blocker first (most days late), other dated causes as
    secondary, timeline sorted by date. Every item cites a record id -
    the only input the narrative may use (spec FR-011)."""
    behind, _ = _behind.behind_projects(snapshot)
    entry = next((b for b in behind if b.project_id == project_id), None)
    if entry is None:
        return DelayFacts(project_id=project_id)

    dated = [c for c in entry.causes if c.is_dated()]
    if not dated:
        return DelayFacts(project_id=project_id)
    primary = max(dated, key=lambda c: c.days_late or 0)
    secondary = [c for c in dated if c is not primary]

    timeline = []
    for cause in [primary] + secondary:
        day = _cause_date(snapshot, cause)
        timeline.append({"date": _dates.to_iso(day),
                         "event": f"{cause.kind} {_cause_record_id(cause)}".strip(),
                         "record_id": _cause_record_id(cause)})
    timeline.sort(key=lambda item: (item["date"] or "", item["record_id"]))

    return DelayFacts(
        project_id=project_id,
        primary_blocker={"kind": primary.kind, "record_id": _cause_record_id(primary),
                         "days_late": primary.days_late},
        secondary=[{"kind": c.kind, "record_id": _cause_record_id(c),
                    "days_late": c.days_late} for c in secondary],
        timeline=timeline,
    )
