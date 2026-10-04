"""Shared fact object for both audiences, tasks.md T092.
NOTE (T104): AI-drafted, needs team sign-off to claim hand-written credit.
"""
from agent.domain import status as _status
from agent.domain.types import Snapshot


def _snap():
    return Snapshot(
        as_of="2026-10-04",
        projects=[{"id": "P-STAT", "name": "Harbor Bridge", "budget_amount": 20000}],
        tasks=[
            {"id": "T-S1", "project_id": "P-STAT", "status": "todo",
             "due_date": "2026-09-05", "budget_hours": 50, "rate": 100},
            {"id": "T-S2", "project_id": "P-STAT", "status": "todo",
             "due_date": "2026-11-01", "depends_on_task_id": "T-S1",
             "budget_hours": 50, "rate": 100},
        ],
        milestones=[{"id": "M-S1", "project_id": "P-STAT", "status": "missed",
                     "due_date": "2026-09-10"}],
        timesheets=[{"id": "TS-S1", "project_id": "P-STAT", "task_id": "T-S1",
                     "hours": 20, "rate": 100}],
    )


def test_fact_object_identical_for_both_audiences():
    facts_sponsor = _status.build_facts(_snap(), "P-STAT")
    facts_team = _status.build_facts(_snap(), "P-STAT")
    assert facts_sponsor == facts_team
    assert facts_sponsor["primary_blocker"]["record_id"] == "T-S1"


def test_only_audience_label_differs_in_framing():
    facts = _status.build_facts(_snap(), "P-STAT")
    sponsor = _status.frame(facts, "sponsor")
    team = _status.frame(facts, "team")
    import re
    assert not re.search(r"[A-Z]+-[A-Z0-9]+", sponsor)
    assert "T-S1" in team and "T-S2" in team
    assert "Harbor Bridge" in sponsor and "Harbor Bridge" in team
