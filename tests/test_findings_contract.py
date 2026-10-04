"""(hand-written) validate_finding, tasks.md T023."""
import pytest

from agent.findings import validate_finding, assemble_finding, FindingValidationError, record_finding
from agent.domain.types import Snapshot
from harness.fakes import FakeMcp


def _base_finding(**overrides):
    finding = assemble_finding(
        run_id="run-1", instance="suryodaya", as_of="2026-10-04", company={},
        status="complete",
        behind_projects=[{"project_id": "PRJ-1", "causes": [{"kind": "overdue_task", "task_id": "TSK-1"}]}],
    )
    finding.update(overrides)
    return finding


def test_empty_causes_is_rejected():
    finding = _base_finding(behind_projects=[{"project_id": "PRJ-1", "causes": []}])
    problems = validate_finding(finding)
    assert any("empty causes" in p for p in problems)


def test_project_with_no_dated_cause_is_rejected():
    finding = _base_finding(behind_projects=[{
        "project_id": "PRJ-1",
        "causes": [{"kind": "no_assignee", "task_id": "TSK-1"}],  # not a dated kind
    }])
    problems = validate_finding(finding)
    assert any("no dated cause" in p for p in problems)


def test_employee_in_both_overloaded_and_capacity_unknown_is_rejected():
    finding = _base_finding(
        overloaded_employees=[{"employee_id": "EMP-1", "week_excess_h": 3}],
        capacity_unknown_employees=["EMP-1"],
    )
    problems = validate_finding(finding)
    assert any("both overloaded and capacity_unknown" in p for p in problems)


def test_id_absent_from_snapshot_is_rejected():
    finding = _base_finding()
    snapshot = Snapshot(as_of="2026-10-04", projects=[{"id": "PRJ-999"}])  # PRJ-1 not present
    problems = validate_finding(finding, snapshot)
    assert any("not in snapshot" in p for p in problems)


def test_valid_finding_against_matching_snapshot_has_no_problems():
    finding = _base_finding()
    snapshot = Snapshot(as_of="2026-10-04",
                         projects=[{"id": "PRJ-1"}],
                         tasks=[{"id": "TSK-1", "project_id": "PRJ-1"}])
    problems = validate_finding(finding, snapshot)
    assert problems == []


def test_serialized_content_carries_no_credentials():
    mcp = FakeMcp({"AgentMemory": []})
    finding = assemble_finding(run_id="run-2", instance="suryodaya", as_of="2026-10-04", company={})
    recorded = record_finding(mcp, "run-2", finding)
    row = mcp.data["AgentMemory"][0]
    assert "password" not in row["content"].lower()
    assert "bearer" not in row["content"].lower()


def test_record_finding_raises_on_invalid_finding():
    mcp = FakeMcp({"AgentMemory": []})
    finding = _base_finding(behind_projects=[{"project_id": "PRJ-1", "causes": []}])
    with pytest.raises(FindingValidationError):
        record_finding(mcp, "run-3", finding)
