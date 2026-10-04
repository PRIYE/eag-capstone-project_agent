"""
Bounded agent loop for Seat 14 (Projects). Rewritten per tasks.md T034:
RunBudget + ReadDedup, parallel tool execution per model turn, a
mandatory finding recorded exactly once (forced finalize near the step/
deadline budget, or built as `partial` on any failure), and a system
prompt free of hardcoded tenant/currency/country text (Constitution
Principle VI - that comes from `company_context` at run time).
"""
import json
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from . import config as _config
from . import findings as _findings
from . import safety as _safety
from . import tools as _tools
from .domain.types import Snapshot

FORBIDDEN_KEYWORDS = {
    "payroll": "Payroll", "salary": "Payroll", "salaries": "Payroll",
    "manufacturing": "WorkOrder", "work order": "WorkOrder", "work orders": "WorkOrder",
    "accounting": "LedgerEntry",
}

SYSTEM_PROMPT = """You are the agent for the Projects seat on AgentSwitch.

You answer questions about project schedule and resource load using ONLY
the tools provided. Call `company_context` first. Call `load_snapshot`
before any tool that needs the data it loads. Never invent a fact that
is not present in a tool result.

If the question is about an entity outside your seat's scope (payroll,
manufacturing work orders, accounting), use `seat_capability` to confirm
it is not visible, then state that boundary plainly - do not attempt a
workaround.

Every run MUST end with your conclusions reflected in a stored finding;
you do not need to call anything special for that - the system records
it automatically once you stop calling tools or the run budget is
reached. Keep calling tools until you have what you need to answer,
then give a concise final answer summarizing what was found.

When explaining why a project slipped, narrate ONLY the fields returned
by `delay_facts`: name the primary blocker first, label every other
cause secondary, cite record ids, and never invent a cause, date, or
id that is not in those facts.

When asked for a status update, call `status_report_facts` once per
audience and keep both versions to the SAME facts: the sponsor version
states blockers and dates with no task ids; the team version names the
blocking tasks and next actions. Never add a fact for one audience that
the other does not share.
"""


def _build_finding_from_state(state: _tools.RunState, run_id: str, instance: str, status: str) -> Dict[str, Any]:
    behind = state.results.get("behind_projects", [])
    insufficient = state.results.get("insufficient_data_projects", [])
    overload = state.results.get("overload")
    integrity_flags = state.results.get("integrity_flags", [])

    truncated = {}
    if state.snapshot is not None:
        truncated = {k: v for k, v in state.snapshot.truncated.items() if v}
    if truncated and status == "complete":
        status = "partial"

    from .domain import integrity as _integrity_mod
    integrity_summary = _integrity_mod.summary_by_kind(integrity_flags) if integrity_flags else {}

    proposals = state.results.get("proposals") or []
    cp_checks = state.results.get("critical_path_checks") or []
    notes = []
    if state.results.get("platform_cp_after") is not None:
        notes.append("platform_cp_after captured after an applied write")

    finding = _findings.assemble_finding(
        run_id=run_id,
        instance=instance,
        as_of=state.as_of,
        company=state.company,
        status=status,
        behind_projects=[b.to_dict() for b in behind] if behind else [],
        insufficient_data_projects=insufficient,
        window=overload.window if overload else [],
        overloaded_employees=[e.to_dict() for e in overload.overloaded] if overload else [],
        capacity_unknown_employees=overload.capacity_unknown if overload else [],
        integrity_summary=integrity_summary,
        proposals=[_tools._as_dict(p) for p in proposals],
        escalations=state.escalations_attempted,
        limits={"not_visible": state.not_visible, "truncated": truncated, "notes": notes},
        budget={},
    )
    # T074/US5 + T087/US7+US4: analysis payloads ride along for the
    # verifier; the persisted schema ignores unknown keys on read-back.
    finding["critical_path_checks"] = [_tools._as_dict(c) for c in cp_checks]
    evm_rows = state.results.get("evm_rows") or []
    if evm_rows:
        finding["evm"] = [_tools._as_dict(r) for r in evm_rows]
    delay_facts = state.results.get("delay_facts")
    if delay_facts is not None:
        finding["delay_facts"] = _tools._as_dict(delay_facts)
    status_reports = state.results.get("status_reports") or []
    if status_reports:
        finding["status_reports"] = [_tools._as_dict(r) for r in status_reports]
    return finding


def _execute_tool_calls_parallel(state: _tools.RunState, tool_calls: List[Dict]) -> List[Dict]:
    """Runs every tool call requested in one model turn in parallel
    (contracts/agent-tools.md: "Tool calls requested in the same turn
    run in parallel")."""

    def run_one(tool_call):
        function = tool_call.get("function", {})
        name = function.get("name")
        try:
            arguments = json.loads(function.get("arguments", "{}"))
        except json.JSONDecodeError:
            arguments = {}
        result = _tools.dispatch(state, name, arguments)
        return {
            "role": "tool",
            "tool_call_id": tool_call.get("id"),
            "_tool_name": name,
            "content": json.dumps(result),
        }

    if len(tool_calls) == 1:
        return [run_one(tool_calls[0])]

    with ThreadPoolExecutor(max_workers=min(8, len(tool_calls))) as pool:
        return list(pool.map(run_one, tool_calls))


def run_agent(client, model, question: str, instance: str = "suryodaya",
              apply_writes: bool = False, allow_escalate: bool = False,
              as_of: Optional[str] = None, run_id: Optional[str] = None,
              on_event=None, budget: Optional[_safety.RunBudget] = None,
              allowed_write_ids: Optional[set] = None) -> Dict[str, Any]:
    """
    One bounded run. Returns:
      {"status": complete|partial|escalated|refused, "run_id": ..., "summary": ..., "finding": {...}}

    `on_event(event: dict)` is called for every loop step if given, so
    callers (run.py) can write a redacted trace.jsonl without this
    function knowing anything about file I/O.
    """
    def emit(event: Dict[str, Any]):
        if on_event:
            on_event(event)

    run_id = run_id or f"{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{instance}-{uuid.uuid4().hex[:6]}"
    budget = budget or _safety.RunBudget()
    state = _tools.RunState(client, as_of=as_of, allowed_write_ids=allowed_write_ids,
                            allow_writes=apply_writes)

    refusal_entity = None
    lowered = question.lower()
    for keyword, entity in FORBIDDEN_KEYWORDS.items():
        if keyword in lowered:
            probe = _safety.probe_capability(client, entity, "list")
            if probe["status"] == "not_visible":
                refusal_entity = entity
            break

    if refusal_entity:
        finding = _build_finding_from_state(state, run_id, instance, status="refused")
        try:
            _findings.record_finding(client, run_id, finding, state.snapshot)
        except Exception as e:
            emit({"event": "record_finding_failed", "error": str(e)})
        summary = (f"That is outside the Projects seat's scope ({refusal_entity} is not visible to this "
                   f"seat). I cannot answer that request.")
        emit({"event": "refused", "entity": refusal_entity})
        return {"status": "refused", "run_id": run_id, "summary": summary, "finding": finding}

    conversation: List[Dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]

    tools_schema = _tools.openai_tools()
    final_text = None
    status = "complete"

    try:
        while True:
            if budget.exhausted():
                status = "partial"
                emit({"event": "budget_exhausted"})
                break

            force_tool = "record_finding" if budget.must_finalize() else None
            emit({"event": "model_call", "step": budget.steps_used, "force_tool": force_tool})

            response = model.chat(messages=conversation, tools=tools_schema, force_tool=force_tool)
            budget.record_step()

            message = response.get("choices", [{}])[0].get("message", {})
            tool_calls = message.get("tool_calls") or []

            # Model signalling it is done finalizing (explicit record_finding
            # call, or no tool_calls at all) -> stop the loop here.
            finalize_now = (not tool_calls) or any(
                (tc.get("function", {}) or {}).get("name") == "record_finding" for tc in tool_calls
            )

            if tool_calls and not finalize_now:
                conversation.append({"role": "assistant", "content": message.get("content"),
                                      "tool_calls": tool_calls})
                tool_results = _execute_tool_calls_parallel(state, tool_calls)
                for tr in tool_results:
                    emit({"event": "tool_result", "tool": tr.get("_tool_name")})
                conversation.extend(tool_results)
                continue

            if tool_calls and finalize_now:
                # Drop the record_finding call itself; any other tool
                # calls bundled in the same forced turn are skipped -
                # we are finalizing now, not doing more reads.
                final_text = message.get("content")
                break

            final_text = message.get("content") or "Done."
            break

    except Exception as e:
        status = "partial"
        emit({"event": "model_or_tool_exception", "error": str(e)})

    finding = _build_finding_from_state(state, run_id, instance, status=status)
    try:
        _findings.record_finding(client, run_id, finding, state.snapshot,
                                  required_escalation_attempted=True)
    except Exception as e:
        emit({"event": "record_finding_failed", "error": str(e)})
        # Still return what we have - the caller sees a non-"complete"
        # status and the finding dict even if the write itself failed,
        # rather than losing everything we computed.

    summary = final_text or (
        f"Behind: {len(finding.get('behind_projects', []))} project(s). "
        f"Overloaded next week: {len(finding.get('overloaded_employees', []))} employee(s)."
    )

    emit({"event": "run_complete", "status": finding.get("status"), "run_id": run_id})

    return {"status": finding.get("status", status), "run_id": run_id, "summary": summary, "finding": finding}


def main():
    """CLI entry point used by `python run.py agent` with no args."""
    from .mcp_client import create_client
    from .ai_models import create_model

    graded_request = "Which projects are behind schedule, and who is overloaded next week?"
    print("Team 14 Project Agent Starting...")
    print(f"Request: {graded_request}")
    print("=" * 60)

    client = create_client()
    model = create_model()

    start = time.time()
    result = run_agent(client, model, graded_request)
    elapsed = time.time() - start

    print("\n" + "=" * 60)
    print("FINAL RESPONSE:")
    print(result["summary"])
    print(f"\nStatus: {result['status']}  run_id: {result['run_id']}  elapsed: {elapsed:.1f}s")


if __name__ == "__main__":
    main()
