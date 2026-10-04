"""
Snapshot loading: the only place that calls `call_tool_all` for the
read-heavy list entities. Returns a plain `Snapshot` (agent/domain/types.py);
everything downstream of this module is pure/offline-testable.
"""
from datetime import date
from typing import Any, Dict, Optional

from . import config as _config
from .domain.types import Snapshot

SCOPE_ENTITIES = {
    "projects": ["Project", "Task", "Milestone"],
    "capacity": ["ProjectResourceAllocation", "CalendarEvent", "ProjectResourceProfile"],
    "money": ["Timesheet"],
}

_ENTITY_TO_SNAPSHOT_FIELD = {
    "Project": "projects",
    "Task": "tasks",
    "Milestone": "milestones",
    "ProjectResourceAllocation": "allocations",
    "CalendarEvent": "events",
    "ProjectResourceProfile": "profiles",
    "Timesheet": "timesheets",
}


def _rows_of(result_data: Any) -> list:
    if isinstance(result_data, dict):
        return result_data.get("data", [])
    return []


def load_snapshot(client, scope: str, as_of: Optional[str] = None,
                   company: Optional[Dict[str, Any]] = None,
                   into: Optional[Snapshot] = None) -> Snapshot:
    """
    Fetch all entities for `scope` ('projects', 'capacity', or 'money')
    via call_tool_all (full pagination), merging into an existing
    Snapshot (`into`) if given so repeated scope loads across a run
    accumulate rather than overwrite each other's fields.

    Sets `truncated[entity] = True` whenever a fetch came back short
    (fetched < total) - callers (agent/findings.py via agent/tools.py)
    MUST surface this as `limits.truncated` and `status: partial`
    rather than silently analysing an incomplete list (research.md R8).
    """
    if scope not in SCOPE_ENTITIES:
        raise ValueError(f"Unknown snapshot scope: {scope!r}")

    snapshot = into or Snapshot(as_of=as_of or date.today().isoformat(), company=company or {})
    if as_of:
        snapshot.as_of = as_of
    if company:
        snapshot.company = company

    for entity in SCOPE_ENTITIES[scope]:
        result = client.call_tool_all(f"{entity}.list", {}, page_size=_config.PAGE_SIZE, max_pages=_config.MAX_PAGES)
        field_name = _ENTITY_TO_SNAPSHOT_FIELD[entity]
        if not result.success:
            # A failed read is treated as "nothing fetched, truncated" -
            # never silently treated as "zero rows exist".
            setattr(snapshot, field_name, getattr(snapshot, field_name, []))
            snapshot.truncated[entity] = True
            continue

        setattr(snapshot, field_name, _rows_of(result.data))
        snapshot.truncated[entity] = bool(result.data.get("truncated", False)) if isinstance(result.data, dict) else False

    return snapshot
