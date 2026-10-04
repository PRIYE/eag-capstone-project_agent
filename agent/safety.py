"""
Safety primitives shared by every story (Constitution Principles II, III,
IV, V): bounded runs, read de-duplication, re-read-before-write,
capability probing, and honest escalation.
"""
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from .mcp_client import HTTPStatusError
from . import config as _config


# ---------------------------------------------------------------------------
# RunBudget / ReadDedup (Constitution Principle V: bounded runs)
# ---------------------------------------------------------------------------

@dataclass
class RunBudget:
    max_steps: int = _config.MAX_STEPS
    deadline_s: float = _config.DEADLINE_S
    finalize_steps_remaining: int = _config.FINALIZE_STEPS_REMAINING
    finalize_seconds_remaining: float = _config.FINALIZE_SECONDS_REMAINING
    steps_used: int = 0
    clock: Callable[[], float] = field(default=time.monotonic)
    started_at: float = field(default=None)

    def __post_init__(self):
        if self.started_at is None:
            self.started_at = self.clock()

    def elapsed(self) -> float:
        return self.clock() - self.started_at

    def remaining_steps(self) -> int:
        return self.max_steps - self.steps_used

    def remaining_seconds(self) -> float:
        return self.deadline_s - self.elapsed()

    def record_step(self) -> None:
        self.steps_used += 1

    def exhausted(self) -> bool:
        return self.remaining_steps() <= 0 or self.remaining_seconds() <= 0

    def must_finalize(self) -> bool:
        """
        True once we are close enough to the limit that the next step
        should be forced to call record_finding rather than another
        tool. "Close" is defined by finalize_steps_remaining /
        finalize_seconds_remaining, not by waiting for exhaustion -
        otherwise the final finding-writing step itself could get cut
        off by the deadline.
        """
        return (
            self.remaining_steps() <= self.finalize_steps_remaining
            or self.remaining_seconds() <= self.finalize_seconds_remaining
        )

    def to_dict(self) -> Dict[str, Any]:
        return {"steps_used": self.steps_used, "elapsed_s": round(self.elapsed(), 1)}


@dataclass
class ReadDedup:
    """
    Short-circuits an identical repeated read (same tool + same
    arguments) within a run, returning the earlier result instead of
    calling the tool again. Keyed on a hash of (tool, sorted args).
    """
    seen: Dict[Tuple[str, str], Any] = field(default_factory=dict)

    @staticmethod
    def _key(tool_name: str, arguments: Dict[str, Any]) -> Tuple[str, str]:
        import json
        args_norm = json.dumps(arguments or {}, sort_keys=True, default=str)
        return (tool_name, args_norm)

    def get(self, tool_name: str, arguments: Dict[str, Any]) -> Optional[Any]:
        return self.seen.get(self._key(tool_name, arguments))

    def put(self, tool_name: str, arguments: Dict[str, Any], result: Any) -> None:
        self.seen[self._key(tool_name, arguments)] = result

    def call_deduped(self, tool_name: str, arguments: Dict[str, Any],
                      do_call: Callable[[], Any]) -> Tuple[Any, bool]:
        """Returns (result, was_cached)."""
        cached = self.get(tool_name, arguments)
        if cached is not None:
            return cached, True
        result = do_call()
        self.put(tool_name, arguments, result)
        return result, False


# ---------------------------------------------------------------------------
# Capability probing (Constitution Principle III)
# ---------------------------------------------------------------------------

def _entity_operations(client, entity: str) -> List[str]:
    """All MCP tool ops registered under `{entity}.` (e.g. Task.update,
    Task.list), used to resolve a wrong op name to the real list."""
    result = client.list_tools()
    if not result.success:
        return []
    tools = result.data.get("tools", []) if isinstance(result.data, dict) else []
    prefix = f"{entity}."
    return sorted(
        t["name"].split(".", 1)[1]
        for t in tools
        if t.get("name", "").startswith(prefix)
    )


def probe_capability(client, entity: str, op: str) -> Dict[str, Any]:
    """
    Returns one of:
      {"visible": True, "status": "ok"}
      {"visible": False, "status": "not_visible"}                 (403: entity exists, outside this seat)
      {"visible": False, "status": "unknown_name"}                (404: name does not exist at all)
      {"visible": True, "status": "unknown_op", "operations": [...]}  (entity visible, op name wrong)

    403 and 404 are NEVER conflated (Constitution Principle III):
    a tool catalogue lookup first checks whether `{entity}.{op}` exists;
    if not, and other `{entity}.*` ops DO exist, this is `unknown_op`
    with the real operation list, not a bare error. If no `{entity}.*`
    op exists at all, we fall back to rest_status to tell "visible but
    nothing named that" (404-ish within our own seat -> unknown_name)
    apart from "not visible to this seat at all" (403 -> not_visible).
    """
    tool_name = f"{entity}.{op}"
    ops = _entity_operations(client, entity)

    if op in ops:
        return {"visible": True, "status": "ok", "tool": tool_name}

    if ops:
        # Entity is visible (other ops exist); this op name is just wrong.
        return {"visible": True, "status": "unknown_op", "operations": ops}

    # No ops at all under this entity name - probe REST directly to tell
    # "exists but outside this seat" (403) from "no such entity" (404).
    status = client.rest_status(f"/api/{entity}")
    if status == 403:
        return {"visible": False, "status": "not_visible", "http_status": 403}
    if status == 404:
        return {"visible": False, "status": "unknown_name", "http_status": 404}
    return {"visible": False, "status": "unknown_name", "http_status": status}


# ---------------------------------------------------------------------------
# Re-read-before-write (Constitution Principle II, NON-NEGOTIABLE)
# ---------------------------------------------------------------------------

@dataclass
class WriteGate:
    allowed_ids: Set[str] = field(default_factory=set)
    conflict_seen: bool = False

    def allow(self, entity_id: str) -> None:
        self.allowed_ids.add(entity_id)

    def is_allowed(self, entity_id: str) -> bool:
        return entity_id in self.allowed_ids

    def mark_conflict(self) -> None:
        self.conflict_seen = True


def guarded_update(client, proposal, gate: WriteGate, entity: str = "Task") -> str:
    """
    Re-read `entity` by proposal.task_id immediately before writing;
    compare `updated_at` and `status` against the values captured when
    the proposal was built (proposal.snapshot_updated_at /
    snapshot_status). If either changed, or the id is outside
    `gate.allowed_ids`, or a conflict was already seen earlier this run,
    skip the write and return the outcome instead of overwriting
    silently. After a successful write, re-read once more to confirm
    the row actually changed.

    Returns one of: 'refused', 'changed_underneath', 'write_rejected',
    'applied', 'write_not_persisted'.

    Mutates `proposal.outcome` to match the return value.
    """
    task_id = proposal.task_id

    if gate.conflict_seen:
        proposal.outcome = "refused"
        return "refused"

    if not gate.is_allowed(task_id):
        proposal.outcome = "refused"
        return "refused"

    read_result = client.call_tool(f"{entity}.get", {"id": task_id})
    if not read_result.success:
        proposal.outcome = "refused"
        return "refused"

    current = read_result.data.get("data", read_result.data) if isinstance(read_result.data, dict) else {}

    if (proposal.snapshot_updated_at is not None
            and current.get("updated_at") != proposal.snapshot_updated_at):
        gate.mark_conflict()
        proposal.outcome = "changed_underneath"
        return "changed_underneath"

    if (proposal.snapshot_status is not None
            and current.get("status") != proposal.snapshot_status):
        gate.mark_conflict()
        proposal.outcome = "changed_underneath"
        return "changed_underneath"

    write_result = client.call_tool(f"{entity}.update", {"id": task_id, **proposal.field_changes})
    if not write_result.success:
        proposal.outcome = "write_rejected"
        return "write_rejected"

    confirm_result = client.call_tool(f"{entity}.get", {"id": task_id})
    if not confirm_result.success:
        proposal.outcome = "write_not_persisted"
        return "write_not_persisted"

    confirmed = confirm_result.data.get("data", confirm_result.data) if isinstance(confirm_result.data, dict) else {}
    for field_name, expected_value in proposal.field_changes.items():
        if confirmed.get(field_name) != expected_value:
            proposal.outcome = "write_not_persisted"
            return "write_not_persisted"

    proposal.outcome = "applied"
    return "applied"


# ---------------------------------------------------------------------------
# Escalation (Constitution Principle IV: escalate rather than fabricate)
# ---------------------------------------------------------------------------

def escalate(client, reason: str, reason_code: str = "other") -> Dict[str, Any]:
    """
    Look up real escalation assignees and raise one escalation if any
    exist. Returns {"raised": bool, "reason": ..., "assignee": ...?,
    "escalation_id": ...?}. Never fabricates a handover: an empty
    assignee list or a platform refusal (even one wrapped in a 200
    success envelope with an error field) yields {"raised": False,
    "reason": "no_assignee"} rather than claiming success.
    """
    if reason_code not in _config.ESCALATION_REASON_CODES:
        reason_code = "other"

    assignees_result = client.call_tool("endpoint.agent_governance.escalations.assignees", {})
    if not assignees_result.success:
        return {"raised": False, "reason": "no_assignee", "detail": assignees_result.error}

    assignees = assignees_result.data.get("data", []) if isinstance(assignees_result.data, dict) else []
    if not assignees:
        return {"raised": False, "reason": "no_assignee"}

    chosen = assignees[0]
    raise_result = client.call_tool("endpoint.agent_governance.escalations.raise", {
        "reason": reason,
        "reason_code": reason_code,
        "assignee_id": chosen.get("id") if isinstance(chosen, dict) else chosen,
    })

    if not raise_result.success:
        return {"raised": False, "reason": "no_assignee", "detail": raise_result.error}

    payload = raise_result.data if isinstance(raise_result.data, dict) else {}
    if payload.get("error") or payload.get("success") is False:
        return {"raised": False, "reason": "no_assignee", "detail": payload}

    return {
        "raised": True,
        "assignee": chosen,
        "escalation_id": payload.get("id") or payload.get("data", {}).get("id") if isinstance(payload.get("data"), dict) else payload.get("id"),
    }
