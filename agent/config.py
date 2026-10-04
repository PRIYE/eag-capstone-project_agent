"""
Run configuration and credentials for Team 14 (Projects seat).

Mirrors the role of Team 04's prod_agent/config.py: a single place for
instance selection, .env loading, and the run constants the rest of the
agent depends on (budget, deadline, page size, overrun threshold).

Constitution Principle VI (No Hardcoded Tenancy): this module holds no
currency, country or company-specific values. It only resolves *which*
instance's URL/credentials to use; everything about that instance
(currency, country, capability) is read from the API at run time by
agent/tools.py::company_context, never assumed here.
"""
import os
from pathlib import Path
from typing import Dict, Optional

ROOT = Path(__file__).resolve().parent.parent

# Known AgentSwitch instances for this seat. Spec Assumptions: the agent
# is pointed at one instance per run via --instance; nothing here decides
# behavior differently per instance beyond which URL/credentials to use.
INSTANCES: Dict[str, str] = {
    "suryodaya": "https://agentswitch.theschoolofai.in",
    "keystone": "https://class.agentswitch.theschoolofai.in",
}

DEFAULT_INSTANCE = "suryodaya"

# Run bounds (spec FR-014, SC-006, SC-008; Constitution Principle V).
MAX_STEPS = 20
DEADLINE_S = 180.0
FINALIZE_STEPS_REMAINING = 2
FINALIZE_SECONDS_REMAINING = 20.0

# Read bounds (plan.md Constraints; research.md R8).
PAGE_SIZE = 200
MAX_PAGES = 20

# Domain thresholds (spec FR-004, clarified: >150% of budget/estimate is
# an overrun).
OVERRUN_RATIO = 1.5

# Persisted-finding markers (research.md R3; mirrors Team 04's
# FINDING_PREFIX / HARNESS_MARKER pattern, but namespaced to this seat so
# nothing we write is ever confused with another team's rows).
FINDING_PREFIX = "PROJECT_AGENT_FINDING:"
HARNESS_MARKER = "team14-harness"

# Escalation reason codes this agent is allowed to use (mirrors Team 04's
# ESCALATION_REASON_CODES; kept narrow and explicit per Constitution
# Principle IV).
ESCALATION_REASON_CODES = ("policy_refusal", "unresolved_after_retries", "other")


def load_dotenv(path: Optional[Path] = None) -> None:
    """
    Load `.env` into the process environment. Non-empty values in the
    file win over whatever is already set, matching the existing
    agent/mcp_client.py::load_env behavior (so switching between the two
    loaders is safe during the transition).

    Parses by splitting on the first `=` only; a trailing `#` comment on
    the same line becomes part of the value, so comments must be on
    their own line (same contract the team04 README documents for its
    own .env, and the one our README should follow too).
    """
    env_path = path or (ROOT / ".env")
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        if value:
            os.environ[key] = value


def env(name: str, default: Optional[str] = None) -> Optional[str]:
    load_dotenv()
    return os.environ.get(name, default)


def instance_url(instance: str) -> str:
    if instance not in INSTANCES:
        raise ValueError(
            f"Unknown instance '{instance}'. Known instances: {sorted(INSTANCES)}"
        )
    # AS_URL in .env overrides the table for the default instance, so a
    # developer can point 'suryodaya' at a local/staging URL without
    # editing this file.
    if instance == DEFAULT_INSTANCE:
        return env("AS_URL", INSTANCES[instance])
    if instance == "keystone":
        return env("AS_KEYSTONE_URL", INSTANCES[instance])
    return INSTANCES[instance]


def credentials(instance: str) -> Dict[str, str]:
    """
    Resolve email/password for the given instance from .env.

    Raises if credentials are missing, so a run fails loudly at startup
    rather than producing a confusing auth error deep in the loop.
    """
    email = env("AS_EMAIL")
    if instance == DEFAULT_INSTANCE:
        password = env("AS_PASSWORD")
    elif instance == "keystone":
        password = env("AS_KEYSTONE_PASSWORD")
    else:
        password = None

    if not email or not password:
        raise RuntimeError(
            f"Missing AS_EMAIL or the password for instance '{instance}' in .env"
        )
    return {"url": instance_url(instance), "email": email, "password": password}


def model_settings() -> Dict[str, Optional[str]]:
    return {
        "provider": env("MODEL_PROVIDER", "openai"),
        "model": env("MODEL_NAME", "gpt-4"),
    }
