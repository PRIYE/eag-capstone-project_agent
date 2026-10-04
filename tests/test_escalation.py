"""(hand-written) escalate(), tasks.md T018."""
from agent.safety import escalate
from harness.fakes import FakeMcp
from agent.mcp_client import MCPResult


def test_empty_assignee_list_yields_honest_no_assignee():
    mcp = FakeMcp({})
    mcp.register_endpoint("endpoint.agent_governance.escalations.assignees",
                           lambda args: MCPResult(success=True, data={"data": []}))

    result = escalate(mcp, reason="no due date on blocking task", reason_code="unresolved_after_retries")

    assert result["raised"] is False
    assert result["reason"] == "no_assignee"


def test_platform_refusal_inside_success_envelope_is_not_raised():
    mcp = FakeMcp({})
    mcp.register_endpoint("endpoint.agent_governance.escalations.assignees",
                           lambda args: MCPResult(success=True, data={"data": [{"id": "USR-1"}]}))
    mcp.register_endpoint("endpoint.agent_governance.escalations.raise",
                           lambda args: MCPResult(success=True, data={"error": "policy blocked"}))

    result = escalate(mcp, reason="locked task", reason_code="policy_refusal")

    assert result["raised"] is False
    assert result["reason"] == "no_assignee"


def test_success_returns_assignee_and_escalation_id():
    mcp = FakeMcp({})
    mcp.register_endpoint("endpoint.agent_governance.escalations.assignees",
                           lambda args: MCPResult(success=True, data={"data": [{"id": "USR-7", "name": "PM"}]}))
    mcp.register_endpoint("endpoint.agent_governance.escalations.raise",
                           lambda args: MCPResult(success=True, data={"id": "ESC-9"}))

    result = escalate(mcp, reason="task TSK-1 is overdue with no assignee", reason_code="other")

    assert result["raised"] is True
    assert result["assignee"]["id"] == "USR-7"
    assert result["escalation_id"] == "ESC-9"
