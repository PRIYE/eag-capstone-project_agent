"""agent/domain/evm.py + delay.py, tasks.md T083/T084.
NOTE (T104): AI-drafted, needs team sign-off to claim hand-written credit.
"""
from agent.domain import delay as _delay
from agent.domain import evm as _evm
from agent.domain.types import Snapshot

AS_OF = "2026-10-04"


def _cost_snapshot():
    return Snapshot(
        as_of=AS_OF,
        projects=[
            {"id": "P-COST", "budget_amount": 10000},
            {"id": "P-OVER", "budget_amount": 5000},
            {"id": "P-NOBUD"},
        ],
        tasks=[
            {"id": "T-C1", "project_id": "P-COST", "status": "done", "budget_hours": 40, "rate": 100},
            {"id": "T-C2", "project_id": "P-COST", "status": "todo", "budget_hours": 60, "rate": 100},
            {"id": "T-O1", "project_id": "P-OVER", "status": "done", "budget_hours": 20, "rate": 100},
            {"id": "T-O2", "project_id": "P-OVER", "status": "todo", "budget_hours": 80, "rate": 100},
            {"id": "T-N1", "project_id": "P-NOBUD", "status": "todo"},
        ],
        timesheets=[
            {"id": "TS-1", "project_id": "P-COST", "hours": 30, "rate": 100},
            {"id": "TS-2", "project_id": "P-COST", "hours": 5, "rate": 100},
            {"id": "TS-3", "project_id": "P-OVER", "hours": 20, "rate": 100},
            {"id": "TS-4", "project_id": "P-OVER", "hours": 50, "rate": 100},
            {"id": "TS-5", "project_id": "P-NOBUD", "hours": 5, "rate": 100},
        ],
    )


def test_actual_cost_arithmetic():
    rows = {r.project_id: r for r in _evm.evm_rows(_cost_snapshot())}
    assert rows["P-COST"].actual_cost == 3500
    assert rows["P-OVER"].actual_cost == 7000


def test_earned_value_rule_and_overspending_flag():
    rows = {r.project_id: r for r in _evm.evm_rows(_cost_snapshot())}
    assert rows["P-COST"].earned_value == 4000
    assert rows["P-COST"].status == "on_budget"
    assert rows["P-OVER"].earned_value == 1000
    assert rows["P-OVER"].status == "over_spending"


def test_insufficient_data_when_budget_or_rate_missing():
    rows = {r.project_id: r for r in _evm.evm_rows(_cost_snapshot())}
    row = rows["P-NOBUD"]
    assert row.status == "insufficient_data"
    assert row.planned_cost is None and row.earned_value is None


def _delay_snapshot():
    return Snapshot(
        as_of=AS_OF,
        projects=[{"id": "P-DLY"}],
        tasks=[
            {"id": "T-PRIM", "project_id": "P-DLY", "status": "todo", "due_date": "2026-09-01"},
            {"id": "T-SEC1", "project_id": "P-DLY", "status": "todo", "due_date": "2026-09-20"},
            {"id": "T-SEC2", "project_id": "P-DLY", "status": "todo", "due_date": "2026-11-01",
             "depends_on_task_id": "T-PRIM"},
        ],
        milestones=[{"id": "M-DLY", "project_id": "P-DLY", "status": "missed",
                     "due_date": "2026-09-15"}],
    )


def test_primary_before_secondary_and_timeline_sorted():
    facts = _delay.delay_facts(_delay_snapshot(), "P-DLY")
    assert facts.primary_blocker["record_id"] == "T-PRIM"
    assert [s["record_id"] for s in facts.secondary] == ["T-SEC1", "T-SEC2", "M-DLY"]
    dates = [t["date"] for t in facts.timeline]
    assert dates == sorted(dates)
    assert all(t["record_id"] for t in facts.timeline)


def test_every_item_carries_a_record_id():
    facts = _delay.delay_facts(_delay_snapshot(), "P-DLY")
    assert facts.primary_blocker["record_id"]
    assert all(s["record_id"] for s in facts.secondary)
