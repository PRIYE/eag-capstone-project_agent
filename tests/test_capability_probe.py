"""(hand-written) probe_capability, tasks.md T017."""
from agent.safety import probe_capability
from harness.fakes import FakeMcp


def test_403_is_not_visible():
    mcp = FakeMcp({}, entity_statuses={"Payroll": 403})
    result = probe_capability(mcp, "Payroll", "list")
    assert result["status"] == "not_visible"
    assert result["visible"] is False


def test_404_is_unknown_name():
    mcp = FakeMcp({}, entity_statuses={"Nonexistent": 404})
    result = probe_capability(mcp, "Nonexistent", "list")
    assert result["status"] == "unknown_name"
    assert result["visible"] is False


def test_403_and_404_are_never_merged_into_the_same_status():
    mcp = FakeMcp({}, entity_statuses={"Payroll": 403, "Nonexistent": 404})
    forbidden = probe_capability(mcp, "Payroll", "list")
    missing = probe_capability(mcp, "Nonexistent", "list")
    assert forbidden["status"] != missing["status"]


def test_reachable_tool_is_ok():
    mcp = FakeMcp({"Project": [{"id": "PRJ-1"}]})
    result = probe_capability(mcp, "Project", "list")
    assert result["status"] == "ok"
    assert result["visible"] is True


def test_wrong_op_name_on_visible_entity_returns_real_operation_set():
    mcp = FakeMcp({"Task": [{"id": "TSK-1"}]})
    result = probe_capability(mcp, "Task", "updat")  # typo for "update"

    assert result["status"] == "unknown_op"
    assert result["visible"] is True
    assert "update" in result["operations"]
    assert "list" in result["operations"]
    assert "updat" not in result["operations"]
