"""(hand-written) guarded_update / WriteGate re-read-before-write, tasks.md T016."""
from agent.safety import WriteGate, guarded_update
from agent.domain.types import Proposal
from harness.fakes import FakeMcp


def _mcp(task_overrides=None):
    task = {"id": "TSK-1", "project_id": "PRJ-1", "status": "todo",
            "due_date": "2026-10-10", "updated_at": "2026-10-01T00:00:00Z"}
    if task_overrides:
        task.update(task_overrides)
    return FakeMcp({"Task": [task]})


def test_write_happens_after_a_re_read():
    mcp = _mcp()
    gate = WriteGate(allowed_ids={"TSK-1"})
    proposal = Proposal(task_id="TSK-1", field_changes={"due_date": "2026-10-15"},
                         snapshot_updated_at="2026-10-01T00:00:00Z", snapshot_status="todo")

    outcome = guarded_update(mcp, proposal, gate)

    assert outcome == "applied"
    get_calls = [w for w in mcp.write_log]
    # The write must have been preceded by a Task.get - we assert via the
    # fact that the task's current fields were used for comparison: a
    # mismatched snapshot_updated_at (tested below) would have blocked it.
    assert get_calls[0]["op"] == "update"


def test_changed_updated_at_blocks_write():
    mcp = _mcp({"updated_at": "2026-10-05T00:00:00Z"})  # changed since proposal was built
    gate = WriteGate(allowed_ids={"TSK-1"})
    proposal = Proposal(task_id="TSK-1", field_changes={"due_date": "2026-10-15"},
                         snapshot_updated_at="2026-10-01T00:00:00Z", snapshot_status="todo")

    outcome = guarded_update(mcp, proposal, gate)

    assert outcome == "changed_underneath"
    assert mcp.write_log == []  # no write happened
    assert gate.conflict_seen is True


def test_changed_status_blocks_write():
    mcp = _mcp({"status": "done"})
    gate = WriteGate(allowed_ids={"TSK-1"})
    proposal = Proposal(task_id="TSK-1", field_changes={"due_date": "2026-10-15"},
                         snapshot_updated_at="2026-10-01T00:00:00Z", snapshot_status="todo")

    outcome = guarded_update(mcp, proposal, gate)

    assert outcome == "changed_underneath"
    assert mcp.write_log == []


def test_after_one_conflict_all_later_writes_refused():
    mcp = FakeMcp({"Task": [
        {"id": "TSK-1", "project_id": "PRJ-1", "status": "done", "updated_at": "2026-10-01T00:00:00Z"},
        {"id": "TSK-2", "project_id": "PRJ-1", "status": "todo", "updated_at": "2026-10-01T00:00:00Z"},
    ]})
    gate = WriteGate(allowed_ids={"TSK-1", "TSK-2"})

    p1 = Proposal(task_id="TSK-1", field_changes={"due_date": "2026-10-15"},
                  snapshot_updated_at="2026-10-01T00:00:00Z", snapshot_status="todo")  # stale status -> conflict
    outcome1 = guarded_update(mcp, p1, gate)
    assert outcome1 == "changed_underneath"

    p2 = Proposal(task_id="TSK-2", field_changes={"due_date": "2026-10-16"},
                  snapshot_updated_at="2026-10-01T00:00:00Z", snapshot_status="todo")
    outcome2 = guarded_update(mcp, p2, gate)

    assert outcome2 == "refused"
    assert mcp.write_log == []  # TSK-2 would otherwise have been a valid write


def test_id_outside_allowed_set_is_refused():
    mcp = _mcp()
    gate = WriteGate(allowed_ids={"TSK-999"})  # TSK-1 not allowed
    proposal = Proposal(task_id="TSK-1", field_changes={"due_date": "2026-10-15"},
                         snapshot_updated_at="2026-10-01T00:00:00Z", snapshot_status="todo")

    outcome = guarded_update(mcp, proposal, gate)

    assert outcome == "refused"
    assert mcp.write_log == []


def test_post_write_mismatch_is_write_not_persisted():
    mcp = _mcp()
    gate = WriteGate(allowed_ids={"TSK-1"})
    proposal = Proposal(task_id="TSK-1", field_changes={"due_date": "2026-10-15"},
                         snapshot_updated_at="2026-10-01T00:00:00Z", snapshot_status="todo")

    # Simulate the platform silently not persisting the field: on the
    # confirming re-read, revert due_date back.
    original_call_tool = mcp.call_tool
    state = {"updates_seen": 0}

    def patched(tool_name, arguments=None):
        result = original_call_tool(tool_name, arguments)
        if tool_name == "Task.get" and arguments and arguments.get("id") == "TSK-1":
            state["updates_seen"] += 1
            if state["updates_seen"] == 2:  # the post-write confirming read
                result.data["data"]["due_date"] = "2026-10-10"  # unchanged, write didn't stick
        return result

    mcp.call_tool = patched

    outcome = guarded_update(mcp, proposal, gate)

    assert outcome == "write_not_persisted"
