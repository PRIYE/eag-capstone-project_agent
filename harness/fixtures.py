"""
Fixture loading for the offline harness. A fixture JSON lives in
harness/fixtures/ and has the shape:

{
  "note": "hand-written" | "AI-assisted",
  "data": {"Project": [...], "Task": [...], ...},
  "entity_statuses": {"Payroll": 403},          # optional, for refusal tasks
  "expected": { ... independently authored ... }
}

`expected` must be written independently of agent/domain/* (by reasoning
about the data directly), so a verifier comparing the agent's output to
`expected` is not just comparing the implementation to itself.
"""
import json
from pathlib import Path
from typing import Any, Dict

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"

REQUIRED_KEYS = ("data", "expected")
VALID_NOTES = ("hand-written", "AI-assisted")


class FixtureError(ValueError):
    pass


def load_fixture(name: str) -> Dict[str, Any]:
    """
    Load `harness/fixtures/<name>.json` (or `<name>` if it already ends
    in .json). Raises FixtureError if the required `data`/`expected`
    blocks are missing, or if `note` is present but not one of the two
    recognized values.
    """
    filename = name if name.endswith(".json") else f"{name}.json"
    path = FIXTURES_DIR / filename
    if not path.exists():
        raise FixtureError(f"Fixture not found: {path}")

    fixture = json.loads(path.read_text(encoding="utf-8"))

    missing = [k for k in REQUIRED_KEYS if k not in fixture]
    if missing:
        raise FixtureError(f"Fixture {filename} missing required keys: {missing}")

    note = fixture.get("note")
    if note is not None and note not in VALID_NOTES:
        raise FixtureError(f"Fixture {filename} has invalid note: {note!r}")

    return fixture


def create_owned_rows(client, marker: str):
    """T075: create the dedicated live-harness project + one future-dated
    task (never overdue, so the graded predicates can't see it). Returns
    (project_id, task_id). Everything created carries `marker` in its
    name/title for exclusion and cleanup."""
    from agent import config as _config

    project_name = f"{marker}-reschedule"
    project_result = client.call_tool("Project.create", {
        "name": project_name,
        "status": "active",
    })
    if not project_result.success:
        raise RuntimeError(f"fixture_owned project create failed: {project_result.error}")
    project = project_result.data.get("data", project_result.data)
    project_id = project.get("id")

    task_result = client.call_tool("Task.create", {
        "title": f"{marker}-task",
        "project_id": project_id,
        "status": "todo",
        "due_date": "2027-06-01",
    })
    if not task_result.success:
        raise RuntimeError(f"fixture_owned task create failed: {task_result.error}")
    task = task_result.data.get("data", task_result.data)
    return project_id, task.get("id")


def delete_owned_rows(client, project_id: str, task_id: str) -> None:
    """Best-effort cleanup of T075 rows (task first, then project)."""
    for entity, row_id in (("Task", task_id), ("Project", project_id)):
        try:
            client.call_tool(f"{entity}.update", {"id": row_id, "is_active": False})
        except Exception:
            pass
        try:
            client.call_tool(f"{entity}.delete", {"id": row_id})
        except Exception:
            pass
