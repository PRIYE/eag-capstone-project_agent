"""
Tool registry exposed to the model (contracts/agent-tools.md). Each tool
maps to exactly one function in agent/domain/ or agent/safety.py; the
dispatch table never lets the model pass a raw entity name, URL, or
filter string - only the small typed arguments listed in the contract.

Unknown tool names and bad arguments return an error RESULT (a dict),
never raise - the loop must stay able to report back to the model (or
finalize) instead of crashing the whole run on one bad call.
"""
import dataclasses
from datetime import date
from typing import Any, Callable, Dict, List, Optional

from . import config as _config
from . import data as _data
from . import safety as _safety
from .domain import behind as _behind
from .domain import integrity as _integrity
from .domain import overload as _overload
from .domain.types import Proposal


def _as_dict(obj: Any) -> Any:
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {k: _as_dict(v) for k, v in dataclasses.asdict(obj).items()}
    if isinstance(obj, list):
        return [_as_dict(v) for v in obj]
    if isinstance(obj, dict):
        return {k: _as_dict(v) for k, v in obj.items()}
    return obj


class RunState:
    """
    Per-run mutable state threaded through every tool call: the client,
    the growing Snapshot, the write gate, and whatever domain results
    have been computed so far (used both by later tools, e.g.
    propose_reschedule reading behind_projects results, and by the
    loop's `partial` finding fallback on failure).
    """

    def __init__(self, client, as_of: Optional[str] = None, allowed_write_ids: Optional[set] = None):
        self.client = client
        self.as_of = as_of or date.today().isoformat()
        self.snapshot = None
        self.company: Dict[str, Any] = {}
        self.write_gate = _safety.WriteGate(allowed_ids=allowed_write_ids or set())
        self.results: Dict[str, Any] = {}
        self.not_visible: List[str] = []
        self.escalations_attempted: List[Dict[str, Any]] = []

    def ensure_snapshot(self, scope: str):
        from .domain.types import Snapshot
        if self.snapshot is None:
            self.snapshot = Snapshot(as_of=self.as_of, company=self.company)
        self.snapshot = _data.load_snapshot(self.client, scope, as_of=self.as_of,
                                             company=self.company, into=self.snapshot)
        return self.snapshot


def tool_company_context(state: RunState, args: Dict) -> Dict:
    user_info = state.client.get_user_info()
    # Constitution Principle VI: company/currency/country come from the
    # API every run, never hardcoded here.
    company = {
        "name": user_info.get("company_name"),
        "country": user_info.get("country"),
        "currency": user_info.get("currency"),
    }
    state.company = company
    return {"company": company, "as_of": state.as_of}


def tool_load_snapshot(state: RunState, args: Dict) -> Dict:
    scope = args.get("scope")
    if scope not in _data.SCOPE_ENTITIES:
        return {"error": f"unknown scope {scope!r}", "valid_scopes": list(_data.SCOPE_ENTITIES)}
    snapshot = state.ensure_snapshot(scope)
    counts = {
        field: len(getattr(snapshot, field))
        for field in ("projects", "tasks", "milestones", "allocations", "events", "profiles", "timesheets")
    }
    return {"counts": counts, "truncated": dict(snapshot.truncated)}


def tool_schedule_integrity(state: RunState, args: Dict) -> Dict:
    state.ensure_snapshot("projects")
    project_id = args.get("project_id")
    flags = _integrity.scan(state.snapshot, project_id=project_id)
    state.results["integrity_flags"] = flags
    return {
        "flags": [_as_dict(f) for f in flags],
        "summary": _integrity.summary_by_kind(flags),
    }


def tool_behind_schedule_projects(state: RunState, args: Dict) -> Dict:
    state.ensure_snapshot("projects")
    flags = state.results.get("integrity_flags") or _integrity.scan(state.snapshot)
    behind, insufficient = _behind.behind_projects(state.snapshot, flags)
    state.results["behind_projects"] = behind
    state.results["insufficient_data_projects"] = insufficient
    return {
        "behind_projects": [b.to_dict() for b in behind],
        "insufficient_data": insufficient,
        "truncated": {k: v for k, v in state.snapshot.truncated.items() if v},
    }


def tool_overloaded_next_week(state: RunState, args: Dict) -> Dict:
    state.ensure_snapshot("projects")  # for task->project mapping
    state.ensure_snapshot("capacity")
    as_of = args.get("start") or state.as_of
    result = _overload.overloaded(state.snapshot, as_of)
    state.results["overload"] = result
    return _as_dict(result)


def tool_seat_capability(state: RunState, args: Dict) -> Dict:
    entity = args.get("entity")
    if not entity:
        return {"error": "entity is required"}
    probe = _safety.probe_capability(state.client, entity, "list")
    if probe["status"] == "not_visible":
        state.not_visible.append(entity)
    return {"visible": probe["visible"], "reason": probe["status"]}


def tool_escalate(state: RunState, args: Dict) -> Dict:
    reason = args.get("reason", "")
    reason_code = args.get("reason_code", "other")
    result = _safety.escalate(state.client, reason, reason_code)
    state.escalations_attempted.append(result)
    return result


def tool_record_finding(state: RunState, args: Dict) -> Dict:
    """
    This is handled specially by agent/loop.py (it needs the full run
    context - run_id, budget, etc. - not just `args`), so it is
    registered here purely so it appears in the tool catalogue/schema
    sent to the model; the dispatch table below does not route to this
    function.
    """
    return {"error": "record_finding must be invoked by the loop, not dispatched directly"}


TOOL_SCHEMAS: List[Dict[str, Any]] = [
    {"name": "company_context", "description": "Get company name/country/currency and today's date.",
     "parameters": {"type": "object", "properties": {}}},
    {"name": "load_snapshot", "description": "Fetch all rows for a data scope (projects, capacity, or money).",
     "parameters": {"type": "object", "properties": {
         "scope": {"type": "string", "enum": ["projects", "capacity", "money"]}}, "required": ["scope"]}},
    {"name": "schedule_integrity", "description": "Scan tasks for integrity issues (missing assignee/due date, blocked predecessors, effort overruns).",
     "parameters": {"type": "object", "properties": {"project_id": {"type": "string"}}}},
    {"name": "behind_schedule_projects", "description": "List projects behind schedule with dated causes. GRADED.",
     "parameters": {"type": "object", "properties": {}}},
    {"name": "overloaded_next_week", "description": "List employees overloaded across the next 7 days, summed across all projects. GRADED.",
     "parameters": {"type": "object", "properties": {"start": {"type": "string"}}}},
    {"name": "seat_capability", "description": "Check whether this seat can see a given entity (403 vs 404 vs ok).",
     "parameters": {"type": "object", "properties": {"entity": {"type": "string"}}, "required": ["entity"]}},
    {"name": "escalate", "description": "Raise a real escalation if an assignee exists; otherwise honestly reports no_assignee.",
     "parameters": {"type": "object", "properties": {
         "reason": {"type": "string"}, "reason_code": {"type": "string"}}, "required": ["reason"]}},
    {"name": "record_finding", "description": "Persist this run's conclusion. MANDATORY, exactly once per run.",
     "parameters": {"type": "object", "properties": {}}},
]

DISPATCH: Dict[str, Callable[[RunState, Dict], Dict]] = {
    "company_context": tool_company_context,
    "load_snapshot": tool_load_snapshot,
    "schedule_integrity": tool_schedule_integrity,
    "behind_schedule_projects": tool_behind_schedule_projects,
    "overloaded_next_week": tool_overloaded_next_week,
    "seat_capability": tool_seat_capability,
    "escalate": tool_escalate,
    # "record_finding" intentionally absent - handled by the loop itself.
}


def openai_tools() -> List[Dict[str, Any]]:
    """TOOL_SCHEMAS converted to the OpenAI-style `tools` array every
    AIModel.chat() implementation expects (agent/ai_models.py)."""
    return [
        {"type": "function", "function": {
            "name": schema["name"],
            "description": schema.get("description", ""),
            "parameters": schema.get("parameters", {"type": "object", "properties": {}}),
        }}
        for schema in TOOL_SCHEMAS
    ]


def dispatch(state: RunState, tool_name: str, arguments: Dict) -> Dict:
    """Never raises: unknown tool / bad arguments become an error dict."""
    handler = DISPATCH.get(tool_name)
    if handler is None:
        if tool_name == "record_finding":
            return {"error": "record_finding is finalized by the loop automatically"}
        return {"error": f"unknown tool: {tool_name}"}
    try:
        return handler(state, arguments or {})
    except Exception as e:
        return {"error": f"tool {tool_name} failed: {e}"}
