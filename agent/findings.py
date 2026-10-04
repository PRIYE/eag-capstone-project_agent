"""
Finding assembly, validation and persistence per
specs/001-project-agent/contracts/finding-schema.md.

Constitution Principle I (State Over Prose): every answer-bearing run
MUST end here. T010a note: if the live `project.behind_schedule` /
`project.overloaded_next_week` predicates turn out to read something
other than this AgentMemory row (unconfirmed as of this implementation
pass - see docs/ENTITY_MAP.md), only `record_finding`'s storage call
changes; `validate_finding` and the finding's internal shape stay.
"""
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from . import config as _config
from .redact import redact
from .domain.types import Snapshot

SCHEMA_VERSION = 1


class FindingValidationError(ValueError):
    pass


def _collect_known_ids(snapshot: Snapshot) -> set:
    ids = set()
    for bucket in (snapshot.projects, snapshot.tasks, snapshot.milestones,
                   snapshot.allocations, snapshot.events, snapshot.profiles,
                   snapshot.timesheets):
        for row in bucket:
            if isinstance(row, dict) and "id" in row:
                ids.add(str(row["id"]))
    return ids


def validate_finding(finding: Dict[str, Any], snapshot: Optional[Snapshot] = None) -> List[str]:
    """
    Returns a list of validation problems (empty list = valid), per
    contracts/finding-schema.md rules 1-6. Does not raise; callers
    decide whether a non-empty list blocks persistence.
    """
    problems: List[str] = []

    status = finding.get("status")
    if status not in ("complete", "partial", "escalated", "refused"):
        problems.append(f"invalid status: {status!r}")

    for bp in finding.get("behind_projects", []):
        causes = bp.get("causes", [])
        if not causes:
            problems.append(f"behind project {bp.get('project_id')} has empty causes")
            continue
        dated_kinds = {"overdue_task", "missed_milestone", "overdue_milestone", "blocked_by_predecessor"}
        if not any(c.get("kind") in dated_kinds for c in causes):
            problems.append(f"behind project {bp.get('project_id')} has no dated cause")

    overloaded_ids = {e.get("employee_id") for e in finding.get("overloaded_employees", [])}
    capacity_unknown_ids = set(finding.get("capacity_unknown_employees", []))
    overlap = overloaded_ids & capacity_unknown_ids
    if overlap:
        problems.append(f"employees in both overloaded and capacity_unknown: {sorted(overlap)}")

    if snapshot is not None:
        known_ids = _collect_known_ids(snapshot)
        for bp in finding.get("behind_projects", []):
            pid = str(bp.get("project_id"))
            if pid not in known_ids:
                problems.append(f"behind project id {pid} not in snapshot")
            for cause in bp.get("causes", []):
                for id_field in ("task_id", "milestone_id"):
                    val = cause.get(id_field)
                    if val is not None and str(val) not in known_ids:
                        problems.append(f"cause references unknown id {id_field}={val}")

    serialized = json.dumps(finding)
    if "password" in serialized.lower() or "bearer" in serialized.lower():
        problems.append("finding content appears to contain credential-shaped text")

    return problems


def assemble_finding(
    run_id: str,
    instance: str,
    as_of: str,
    company: Dict[str, Any],
    status: str = "complete",
    behind_projects: Optional[List[Dict[str, Any]]] = None,
    insufficient_data_projects: Optional[List[str]] = None,
    window: Optional[List[str]] = None,
    overloaded_employees: Optional[List[Dict[str, Any]]] = None,
    capacity_unknown_employees: Optional[List[str]] = None,
    integrity_summary: Optional[Dict[str, int]] = None,
    proposals: Optional[List[Dict[str, Any]]] = None,
    escalations: Optional[List[Dict[str, Any]]] = None,
    limits: Optional[Dict[str, Any]] = None,
    budget: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    finding = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "instance": instance,
        "as_of": as_of,
        "company": company or {},
        "status": status,
        "behind_projects": behind_projects or [],
        "insufficient_data_projects": insufficient_data_projects or [],
        "window": window or [],
        "overloaded_employees": overloaded_employees or [],
        "capacity_unknown_employees": capacity_unknown_employees or [],
        "integrity_summary": integrity_summary or {},
        "proposals": proposals or [],
        "escalations": escalations or [],
        "limits": limits or {"not_visible": [], "truncated": {}, "notes": []},
        "budget": budget or {},
    }
    return redact(finding)


def record_finding(client, run_id: str, finding: Dict[str, Any], snapshot: Optional[Snapshot] = None,
                    required_escalation_attempted: bool = True) -> Dict[str, Any]:
    """
    Writes exactly one AgentMemory row for this run_id. Refuses (raises
    FindingValidationError) when validation fails, or when the finding
    claims an escalation outcome without `required_escalation_attempted`
    being true (i.e. we never actually called safety.escalate).

    A retry after a transient write failure must pass the SAME finding
    dict (same run_id) - this function does not mutate run_id, so a
    caller retrying keeps rule 5 (written exactly once per run_id;
    retries keep the same fields).
    """
    problems = validate_finding(finding, snapshot)
    if problems:
        raise FindingValidationError("; ".join(problems))

    if finding.get("escalations") and not required_escalation_attempted:
        raise FindingValidationError(
            "finding claims escalation outcomes but no escalation was actually attempted this run"
        )

    content = _config.FINDING_PREFIX + json.dumps(finding, sort_keys=True)
    result = client.call_tool("AgentMemory.create", {
        "content": content,
        "category": "fact",
        "source": "system",
        "importance": "high",
        "is_active": True,
    })
    if not result.success:
        raise RuntimeError(f"Failed to persist finding: {result.error}")
    return finding


def read_finding(client, run_id: str) -> Optional[Dict[str, Any]]:
    """Reads back the AgentMemory row for `run_id`, if any. Used by
    verifiers (harness/verifiers_state.py) and `run.py verify`."""
    result = client.call_tool_all("AgentMemory.list", {})
    if not result.success:
        return None
    rows = result.data.get("data", []) if isinstance(result.data, dict) else []
    prefix = _config.FINDING_PREFIX
    for row in rows:
        content = row.get("content", "") if isinstance(row, dict) else ""
        if content.startswith(prefix):
            try:
                parsed = json.loads(content[len(prefix):])
            except json.JSONDecodeError:
                continue
            if parsed.get("run_id") == run_id:
                return parsed
    return None
