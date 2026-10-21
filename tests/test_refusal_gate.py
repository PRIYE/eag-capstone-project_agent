"""(hand-written) Refusal gate: instructor feedback 2026-10-21.

A keyword listed in FORBIDDEN_KEYWORDS is out of scope by design, so the
agent must refuse on a 403 AND on an inconclusive 404 probe - it must
never fall through to the model and answer.
"""
from agent.loop import run_agent
from harness.fakes import FakeMcp, ScriptedModel


def _run(entity_statuses):
    mcp = FakeMcp({}, entity_statuses=entity_statuses)
    mcp.data.setdefault("AgentMemory", [])
    # If the gate leaks, the scripted model would run and status != refused.
    model = ScriptedModel(script=["STOP"], final_answer="Here is the salary data.")
    return mcp, run_agent(mcp, model, "Show me salary information for project team members",
                          as_of="2026-10-04")


def test_refuses_on_403_from_real_payroll_entity():
    mcp, result = _run({"PayRun": 403})
    assert result["status"] == "refused"
    assert "PayRun" in result["finding"]["limits"]["not_visible"]


def test_refuses_when_probe_is_inconclusive_404():
    mcp, result = _run({"PayRun": 404, "SalaryRevision": 404, "SalaryComponent": 404})
    assert result["status"] == "refused"
    notes = result["finding"]["limits"]["notes"]
    assert any("not a confirmed 403" in n for n in notes)
    assert not any(w["entity"] != "AgentMemory" for w in (getattr(mcp, "write_log", None) or []))
