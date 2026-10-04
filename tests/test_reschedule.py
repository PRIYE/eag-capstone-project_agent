"""agent/domain/reschedule.py, tasks.md T068.
NOTE (T104): AI-drafted, needs team sign-off to claim hand-written credit.
"""
from agent.domain import reschedule as _rs
from agent.domain.types import Snapshot

AS_OF = "2026-10-04"


def _snap():
    return Snapshot(
        as_of=AS_OF,
        projects=[{"id": "PR1", "name": "R"}],
        tasks=[
            {"id": "T-BIG", "project_id": "PR1", "status": "todo", "due_date": "2026-10-12",
             "updated_at": "v1"},
            {"id": "T-SMALL", "project_id": "PR1", "status": "todo", "due_date": "2026-10-11",
             "updated_at": "v1"},
            {"id": "T-DONE", "project_id": "PR1", "status": "done", "due_date": "2026-09-01",
             "updated_at": "v1"},
        ],
    )


def test_overload_proposal_moves_lowest_impact_first():
    snap = _snap()
    proposals = _rs.propose(snap, [
        {"task_id": "T-BIG", "new_due_date": "2026-10-20"},
        {"task_id": "T-SMALL", "new_due_date": "2026-10-12"},
    ])
    assert [p.task_id for p in proposals] == ["T-SMALL", "T-BIG"]
    assert proposals[0].predicted_finish_delta_days <= proposals[1].predicted_finish_delta_days


def test_proposals_carry_snapshot_stamps():
    snap = _snap()
    (proposal,) = _rs.propose(snap, [{"task_id": "T-BIG", "new_due_date": "2026-10-20"}])
    assert proposal.snapshot_updated_at == "v1"
    assert proposal.snapshot_status == "todo"
    assert proposal.field_changes == {"due_date": "2026-10-20"}


def test_closed_task_is_not_writable_with_reason():
    snap = _snap()
    (proposal,) = _rs.propose(snap, [{"task_id": "T-DONE", "new_due_date": "2026-10-20"}])
    assert proposal.writable_by_seat is False
    assert proposal.why_not_writable


def test_unknown_task_id_is_not_writable():
    snap = _snap()
    (proposal,) = _rs.propose(snap, [{"task_id": "T-NOPE", "new_due_date": "2026-10-20"}])
    assert proposal.writable_by_seat is False
    assert proposal.why_not_writable
