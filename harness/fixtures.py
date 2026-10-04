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
