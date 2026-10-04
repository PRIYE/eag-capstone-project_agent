"""(hand-written) agent/loop.py bounded run guarantees, tasks.md T033."""
import time

from agent.loop import run_agent
from agent.safety import RunBudget
from harness.fakes import FakeMcp, ScriptedModel


def _empty_mcp():
    return FakeMcp({"Project": [], "Task": [], "Milestone": [],
                     "ProjectResourceAllocation": [], "CalendarEvent": [], "ProjectResourceProfile": [],
                     "AgentMemory": []})


def test_model_that_never_stops_still_ends_with_partial_finding_at_budget():
    mcp = _empty_mcp()
    model = ScriptedModel(script=["LOOP_FOREVER"])
    budget = RunBudget(max_steps=5, deadline_s=1000)

    result = run_agent(mcp, model, "Which projects are behind schedule?", budget=budget)

    assert result["status"] == "partial"
    assert len(mcp.data["AgentMemory"]) == 1  # record_finding called exactly once


def test_deadline_hit_ends_with_stored_finding():
    class _FakeClock:
        def __init__(self):
            self.now = 0.0

        def __call__(self):
            self.now += 50.0  # each check advances past the deadline quickly
            return self.now

    mcp = _empty_mcp()
    model = ScriptedModel(script=["LOOP_FOREVER"])
    budget = RunBudget(max_steps=1000, deadline_s=10, clock=_FakeClock())

    result = run_agent(mcp, model, "Which projects are behind schedule?", budget=budget)

    assert result["status"] in ("partial", "complete")
    assert len(mcp.data["AgentMemory"]) == 1


def test_model_exception_ends_with_partial_finding_stored():
    mcp = _empty_mcp()
    model = ScriptedModel(script=[])
    model.raise_next_call(RuntimeError("provider is down"))

    result = run_agent(mcp, model, "Which projects are behind schedule?")

    assert result["status"] == "partial"
    assert len(mcp.data["AgentMemory"]) == 1


def test_record_finding_called_exactly_once_on_normal_completion():
    mcp = _empty_mcp()
    model = ScriptedModel(
        script=[{"name": "company_context", "arguments": {}}, "STOP"],
        final_answer="No projects behind schedule.",
    )

    result = run_agent(mcp, model, "Which projects are behind schedule?")

    assert result["status"] == "complete"
    assert len(mcp.data["AgentMemory"]) == 1


def test_forced_finalize_near_budget_still_stores_one_finding():
    mcp = _empty_mcp()
    # Script has far more steps queued than the budget allows; the loop
    # must stop and finalize rather than exhausting the script.
    long_script = [{"name": "company_context", "arguments": {}} for _ in range(50)]
    model = ScriptedModel(script=long_script)
    budget = RunBudget(max_steps=4, deadline_s=1000)

    result = run_agent(mcp, model, "Which projects are behind schedule?", budget=budget)

    assert len(mcp.data["AgentMemory"]) == 1
    assert budget.steps_used <= 4
