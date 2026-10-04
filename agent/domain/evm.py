"""agent/domain/evm.py, tasks.md T083.
NOTE (T104): AI-drafted, needs team sign-off to claim hand-written credit.
"""
from agent.domain.types import EvmRow, Snapshot


def _planned_cost(snapshot: Snapshot, project_id: str):
    for project in snapshot.projects:
        if project.get("id") == project_id and project.get("budget_amount") is not None:
            return float(project["budget_amount"])
    total, any_rate = 0.0, False
    for task in snapshot.tasks_for(project_id):
        if task.get("budget_hours") is not None and task.get("rate") is not None:
            total += float(task["budget_hours"]) * float(task["rate"])
            any_rate = True
    return total if any_rate else None


def evm_rows(snapshot: Snapshot, project_id=None):
    """Actual = sum(timesheet hours*rate); earned = percent_complete *
    planned with percent_complete = done-budget-hours share; over_spending
    when earned < actual; insufficient_data when budget or rate missing."""
    wanted = [project_id] if project_id else [p.get("id") for p in snapshot.projects]
    rows = []
    for pid in wanted:
        planned = _planned_cost(snapshot, pid)
        actual = None
        usable = [(t.get("hours"), t.get("rate")) for t in snapshot.timesheets
                  if t.get("project_id") == pid and t.get("hours") is not None
                  and t.get("rate") is not None]
        if usable:
            actual = sum(float(h) * float(r) for h, r in usable)

        budgeted = [(t.get("budget_hours")) for t in snapshot.tasks_for(pid)
                    if t.get("budget_hours") is not None]
        done_hours = sum(float(t["budget_hours"]) for t in snapshot.tasks_for(pid)
                         if t.get("status") == "done" and t.get("budget_hours") is not None)
        percent = (done_hours / sum(float(b) for b in budgeted)) if budgeted else None
        earned = round(percent * planned, 2) if percent is not None and planned is not None else None

        if planned is None or earned is None or actual is None:
            rows.append(EvmRow(project_id=pid, status="insufficient_data"))
            continue
        cpi = round(earned / actual, 3) if actual > 0 else None
        rows.append(EvmRow(project_id=pid, planned_cost=planned, actual_cost=actual,
                           earned_value=earned, cpi=cpi,
                           status="over_spending" if earned < actual else "on_budget"))
    return rows
