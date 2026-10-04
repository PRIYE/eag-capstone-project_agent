"""Audience framing over one shared fact object (spec FR-012, US8).
Deterministic templates guarantee the invariant (same facts, sponsor
omits ids); the model may polish wording live. tasks.md T092/T093.
NOTE (T104): AI-drafted, needs team sign-off to claim hand-written credit.
"""
from typing import Dict

from . import delay as _delay
from . import evm as _evm
from .types import Snapshot


def build_facts(snapshot: Snapshot, project_id: str) -> Dict:
    """The ONE fact object both audiences share (T092: equal by value)."""
    name = next((p.get("name", project_id) for p in snapshot.projects
                 if p.get("id") == project_id), project_id)
    facts = _delay.delay_facts(snapshot, project_id)
    rows = _evm.evm_rows(snapshot, project_id)
    return {
        "project_id": project_id,
        "project_name": name,
        "primary_blocker": facts.primary_blocker,
        "secondary": facts.secondary,
        "timeline": facts.timeline,
        "evm": rows[0].__dict__ if rows else None,
    }


def frame(facts: Dict, audience: str, platform_summary=None) -> str:
    """Same facts, different framing (T094). Sponsor: no record ids.
    Team: blocking tasks named with next actions."""
    name = facts.get("project_name")
    primary = facts.get("primary_blocker") or {}
    secondary = facts.get("secondary") or []
    p_name = _display_name(primary)
    s_names = [_display_name(s) for s in secondary]
    dates = sorted({t.get("date") for t in facts.get("timeline", []) if t.get("date")})
    when = dates[0] if dates else "unknown date"

    if audience == "sponsor":
        # Sponsor framing never carries record ids (spec FR-012).
        p_plain = (primary.get("kind", "issue") or "issue").replace("_", " ")
        s_plain = [(s.get("kind", "issue") or "issue").replace("_", " ") for s in secondary]
        lines = [f"{name} is behind schedule.",
                 f"Primary cause: {p_plain} (since {when}).",
                 f"Also affecting the date: {', '.join(s_plain)}." if s_plain else ""]
        if platform_summary:
            lines.append(f"Platform status: {platform_summary}.")
        return " ".join(line for line in lines if line)

    actions = [f"Next: unblock {p_name}."] + [f"Next: clear {s}." for s in s_names]
    lines = [f"{name} status for the team.",
             f"Primary blocker: {p_name} [{primary.get('record_id')}] ({primary.get('days_late')} days late)."]
    for s in secondary:
        lines.append(f"Secondary: {_display_name(s)} [{s.get('record_id')}].")
    lines.extend(actions)
    timeline_bits = [f"{t.get('date')} {t.get('record_id')}" for t in facts.get("timeline", [])
                     if t.get("date")]
    if timeline_bits:
        lines.append("Timeline: " + ", ".join(timeline_bits) + ".")
    return " ".join(lines)


def _display_name(cause: Dict) -> str:
    kind = (cause or {}).get("kind", "issue").replace("_", " ")
    return f"{kind} {cause.get('record_id')}" if cause.get("record_id") else kind
