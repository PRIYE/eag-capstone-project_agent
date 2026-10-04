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
from .domain import critical_path as _critical_path
from .domain import delay as _delay
from .domain import evm as _evm
from .domain import integrity as _integrity
from .domain import status as _status_mod
from .domain import overload as _overload
from .domain import reschedule as _reschedule
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

    def __init__(self, client, as_of: Optional[str] = None, allowed_write_ids: Optional[set] = None,
                 allow_writes: bool = False):
        self.client = client
        self.as_of = as_of or date.today().isoformat()
        self.snapshot = None
        self.company: Dict[str, Any] = {}
        # Writes are opt-in (`--apply` live, or `allow_apply` on an offline
        # harness task) and, when on, restricted to `allowed_write_ids`.
        self.allow_writes = allow_writes
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


def tool_critical_path_check(state: RunState, args: Dict) -> Dict:
    """Local what-if for one date move (tasks.md T071). Read-only: the
    platform critical path is read as a baseline when visible, never
    written. The delta is stored for the final finding."""
    task_id = args.get("task_id")
    new_due = args.get("new_due_date")
    if not task_id or not new_due:
        return {"error": "task_id and new_due_date are required"}
    state.ensure_snapshot("projects")
    row = state.snapshot.task_by_id(task_id)
    project_id = row.get("project_id") if row else None

    platform_before = None
    try:
        cp_result = state.client.call_tool(
            "endpoint.projects.critical_path",
            {"project_id": project_id} if project_id else {})
        if cp_result.success:
            platform_before = cp_result.data
    except Exception as e:
        platform_before = {"unavailable": str(e)}

    delta = _critical_path.check(state.snapshot, task_id, new_due, project_id=project_id)
    delta.platform_cp_before = platform_before
    state.results.setdefault("critical_path_checks", []).append(delta)
    return _as_dict(delta)


def tool_propose_reschedule(state: RunState, args: Dict) -> Dict:
    """Build writability-classified proposals, lowest slip first
    (tasks.md T072). No write. Writable proposals join the write gate's
    allowed-id set so a later `apply_proposal` can act on them."""
    state.ensure_snapshot("projects")
    requests = args.get("requests")
    if not requests and args.get("task_id"):
        requests = [{"task_id": args.get("task_id"), "new_due_date": args.get("new_due_date")}]
    if not requests:
        return {"error": "requests [{task_id, new_due_date}] is required"}
    proposals = _reschedule.propose(
        state.snapshot, requests, finding_ref=args.get("finding_ref", "behind"))
    state.results["proposals"] = proposals
    for proposal in proposals:
        if proposal.writable_by_seat:
            state.write_gate.allowed_ids.add(proposal.task_id)
    return {"proposals": [_as_dict(p) for p in proposals]}


def tool_apply_proposal(state: RunState, args: Dict) -> Dict:
    """Apply one proposed date move through `guarded_update` (tasks.md
    T072/T073). Requires opt-in writes AND explicit operator confirmation
    (`confirm: true` = the operator answered y). After an applied write,
    the platform critical path is re-read for predicted-vs-actual."""
    from .domain.types import Proposal as _Proposal
    task_id = args.get("task_id")
    if not task_id:
        return {"error": "task_id is required"}
    proposals = state.results.get("proposals") or []
    proposal = next((p for p in proposals if p.task_id == task_id), None)
    if proposal is None:
        return {"error": f"no proposal for task {task_id!r}; call propose_reschedule first"}
    if not state.allow_writes:
        proposal.outcome = "refused"
        return {"outcome": "refused", "reason": "writes need --apply (or allow_apply on a harness task)"}
    if not proposal.writable_by_seat:
        proposal.outcome = "refused"
        return {"outcome": "refused", "reason": proposal.why_not_writable}
    if not args.get("confirm"):
        return {"outcome": "needs_confirmation",
                "predicted_finish_delta_days": proposal.predicted_finish_delta_days,
                "on_critical_path": proposal.on_critical_path,
                "field_changes": dict(proposal.field_changes)}

    outcome = _safety.guarded_update(state.client, proposal, state.write_gate)
    if outcome == "applied":
        # T073: re-read the platform critical path after the write and
        # attach it next to the prediction for predicted-vs-actual.
        try:
            row = state.snapshot.task_by_id(task_id) or {}
            cp_result = state.client.call_tool(
                "endpoint.projects.critical_path",
                {"project_id": row.get("project_id")} if row.get("project_id") else {})
            if cp_result.success:
                state.results["platform_cp_after"] = cp_result.data
        except Exception:
            pass
    result = _as_dict(proposal)
    result["outcome"] = outcome
    return result


def tool_evm_summary(state: RunState, args: Dict) -> Dict:
    """Per-project cost health (tasks.md T087). Read-only; missing
    budget/rate yields `insufficient_data`, never a guess."""
    state.ensure_snapshot("projects")
    state.ensure_snapshot("money")
    rows = _evm.evm_rows(state.snapshot, args.get("project_id"))
    state.results["evm_rows"] = rows
    return {"evm": [_as_dict(r) for r in rows]}


def tool_delay_facts(state: RunState, args: Dict) -> Dict:
    """Structured delay facts for one project (tasks.md T087). The only
    input the narrative may use - the model must cite these record ids."""
    project_id = args.get("project_id")
    if not project_id:
        return {"error": "project_id is required"}
    state.ensure_snapshot("projects")
    facts = _delay.delay_facts(state.snapshot, project_id)
    state.results["delay_facts"] = facts
    return {"delay_facts": _as_dict(facts)}


def tool_status_report_facts(state: RunState, args: Dict) -> Dict:
    """Audience framing over one shared fact object (tasks.md T093):
    platform report (when the seat can see it) merged with DelayFacts +
    EvmRow. If the endpoint is not visible, says so and uses derived
    facts only. Both framings are stored for the finding."""
    project_id = args.get("project_id")
    audience = args.get("audience", "team")
    if not project_id:
        return {"error": "project_id is required"}
    state.ensure_snapshot("projects")
    state.ensure_snapshot("money")
    facts = _status_mod.build_facts(state.snapshot, project_id)

    platform_summary = None
    visible = True
    try:
        report_result = state.client.call_tool(
            "endpoint.projects.client_status_report", {"project_id": project_id})
        if report_result.success:
            payload = report_result.data
            if isinstance(payload, dict):
                data = payload.get("data", payload)
                platform_summary = (data.get("summary") if isinstance(data, dict)
                                    else str(data))
        else:
            visible = False
    except Exception:
        visible = False
    if not visible:
        platform_summary = None

    text = _status_mod.frame(facts, audience, platform_summary)
    entry = {"audience": audience, "text": text, "facts": facts,
             "platform_report_visible": visible}
    reports = state.results.setdefault("status_reports", [])
    reports[:] = [r for r in reports if r.get("audience") != audience] + [entry]
    return {"audience": audience, "text": text,
            "platform_report_visible": visible,
            "note": None if visible else "status report endpoint not visible; derived facts only"}


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
    {"name": "critical_path_check", "description": "What-if: would moving a task's due date move the project finish, and by how many days? Read-only.",
     "parameters": {"type": "object", "properties": {
         "task_id": {"type": "string"}, "new_due_date": {"type": "string"}}, "required": ["task_id", "new_due_date"]}},
    {"name": "propose_reschedule", "description": "Propose date moves (lowest slip first) with writability classification. No write.",
     "parameters": {"type": "object", "properties": {
         "requests": {"type": "array", "items": {"type": "object", "properties": {
             "task_id": {"type": "string"}, "new_due_date": {"type": "string"}}}},
         "finding_ref": {"type": "string"}}, "required": ["requests"]}},
    {"name": "apply_proposal", "description": "Apply one proposed move via guarded_update. Needs opt-in writes and confirm:true (= operator said y).",
     "parameters": {"type": "object", "properties": {
         "task_id": {"type": "string"}, "confirm": {"type": "boolean"}}, "required": ["task_id"]}},
    {"name": "evm_summary", "description": "Per-project cost health (planned vs actual vs earned). Read-only.",
     "parameters": {"type": "object", "properties": {"project_id": {"type": "string"}}}},
    {"name": "delay_facts", "description": "Structured delay facts for one project: primary blocker, secondary causes, timeline. Cite these ids.",
     "parameters": {"type": "object", "properties": {"project_id": {"type": "string"}}, "required": ["project_id"]}},
    {"name": "status_report_facts", "description": "Sponsor/team status framing from one shared fact object (platform report merged when visible).",
     "parameters": {"type": "object", "properties": {
         "project_id": {"type": "string"},
         "audience": {"type": "string", "enum": ["sponsor", "team"]}}, "required": ["project_id", "audience"]}},
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
    "critical_path_check": tool_critical_path_check,
    "propose_reschedule": tool_propose_reschedule,
    "apply_proposal": tool_apply_proposal,
    "evm_summary": tool_evm_summary,
    "delay_facts": tool_delay_facts,
    "status_report_facts": tool_status_report_facts,
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
