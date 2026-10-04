"""
Reschedule proposals with writability classification (spec FR-009,
US6 - tasks.md T070). Pure function over a Snapshot.

`propose(snapshot, requests)` takes [{task_id, new_due_date}] and
returns [Proposal] ordered lowest predicted finish-slip first, so an
overload-driven flow moves the lowest-impact task first. Each proposal
carries the snapshot stamps `guarded_update` needs, a writability
verdict with a reason, and the predicted critical-path delta.
"""
from typing import Dict, List

from . import critical_path as _cp
from .types import Proposal, Snapshot

_CLOSED_REASON = "task is closed (done/cancelled)"


def propose(snapshot: Snapshot, requests: List[Dict],
            finding_ref: str = "behind") -> List[Proposal]:
    proposals: List[Proposal] = []
    for req in requests or []:
        task_id = req.get("task_id")
        new_due = req.get("new_due_date")
        row = snapshot.task_by_id(task_id)

        if row is None:
            proposals.append(Proposal(
                task_id=task_id, field_changes={"due_date": new_due},
                writable_by_seat=False, why_not_writable="unknown task id",
                predicted_finish_delta_days=0, on_critical_path=False))
            continue

        if row.get("_locked"):
            writable, reason = False, "task is locked by the platform"
        elif row.get("status") in ("done", "cancelled"):
            writable, reason = False, _CLOSED_REASON
        else:
            writable, reason = True, None

        delta = _cp.check(snapshot, task_id, new_due,
                          project_id=row.get("project_id"))
        proposals.append(Proposal(
            task_id=task_id,
            field_changes={"due_date": new_due},
            snapshot_updated_at=row.get("updated_at"),
            snapshot_status=row.get("status"),
            writable_by_seat=writable,
            why_not_writable=reason,
            predicted_finish_delta_days=delta.delta_days,
            on_critical_path=delta.task_on_path,
        ))

    proposals.sort(key=lambda p: (p.predicted_finish_delta_days or 0))
    return proposals
