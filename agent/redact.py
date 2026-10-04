"""
Strip secrets from anything about to be written to a trace, log, or
finding (research.md R12: secrets hygiene).

Deliberately conservative: redacts by *key name* (password/token/key/
secret/authorization, case-insensitive) and additionally by *value shape*
(long opaque tokens, bearer headers) so a secret surviving under an
unexpected key still gets caught.
"""
import re
from typing import Any

REDACTED = "***REDACTED***"

_SENSITIVE_KEY_RE = re.compile(
    r"(password|passwd|secret|token|api[_-]?key|authorization|auth[_-]?header|bearer)",
    re.IGNORECASE,
)

# Bearer token - very specific, low false-positive-risk.
_BEARER_RE = re.compile(r"\bBearer\s+[A-Za-z0-9\-_.=]+\b", re.IGNORECASE)

# Long opaque-looking string heuristic, as a defense-in-depth backstop
# behind the key-name redaction above (which is the primary mechanism -
# .env secrets are never meant to be copied into docs/traces/fixtures
# in the first place, per the constitution).
#
# Deliberately narrow to avoid false positives on ordinary business
# values that happen to be long - e.g. "20261004-073007-suryodaya-cc4e96"
# (a run_id) or UUID-ish ids: those contain hyphens, which real secrets
# almost never use as a separator *throughout* the whole string (hyphens
# only ever appear as a short fixed prefix like "sk-" or "sk-ant-").
# Require >=32 chars with NO hyphens at all, so hyphen-separated ids and
# dates are never touched.
_OPAQUE_TOKEN_RE = re.compile(
    r"\b(?=[A-Za-z0-9_]{32,}\b)(?=[A-Za-z0-9_]*\d)(?=[A-Za-z0-9_]*[A-Za-z])[A-Za-z0-9_]{32,}\b"
)

# Common provider key prefixes (sk-, sk-ant-, sk-proj-, AIza... etc.) -
# matched separately since they DO contain hyphens but have a
# recognizable prefix immediately followed by a long opaque suffix.
_PREFIXED_KEY_RE = re.compile(r"\b(sk-(?:ant-|proj-)?|AIza)[A-Za-z0-9_\-]{20,}\b")


def _redact_string(value: str) -> str:
    value = _BEARER_RE.sub(f"Bearer {REDACTED}", value)
    value = _PREFIXED_KEY_RE.sub(REDACTED, value)
    value = _OPAQUE_TOKEN_RE.sub(REDACTED, value)
    return value


def redact(value: Any, _depth: int = 0) -> Any:
    """
    Recursively redact a value (dict / list / str / scalar). Dict keys
    matching the sensitive-key pattern have their value fully replaced
    regardless of shape; everything else is scanned by _redact_string.
    """
    if _depth > 20:
        return REDACTED  # defensive cap against pathological nesting

    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if isinstance(k, str) and _SENSITIVE_KEY_RE.search(k):
                out[k] = REDACTED
            else:
                out[k] = redact(v, _depth + 1)
        return out

    if isinstance(value, list):
        return [redact(v, _depth + 1) for v in value]

    if isinstance(value, tuple):
        return tuple(redact(v, _depth + 1) for v in value)

    if isinstance(value, str):
        return _redact_string(value)

    return value
