"""(hand-written) agent/redact.py, tasks.md T097.

Written early (during Phase 2/3 implementation) because the first
offline harness run caught redact() corrupting a run_id - see the
narrow opaque-token heuristic below. Kept here rather than deferred to
Phase 8 so the regression has a permanent test.
"""
from agent.redact import redact, REDACTED


def test_password_key_is_redacted_regardless_of_value_shape():
    assert redact({"password": "short"}) == {"password": REDACTED}


def test_bearer_token_in_a_string_is_redacted():
    text = "Authorization: Bearer abc123XYZ.def-456"
    assert REDACTED in redact(text)
    assert "abc123XYZ" not in redact(text)


def test_openai_style_key_prefix_is_redacted():
    text = "my key is sk-proj-abcdefghijklmnopqrstuvwxyz0123456789"
    result = redact(text)
    assert "abcdefghijklmnopqrstuvwxyz" not in result
    assert REDACTED in result


def test_nested_dict_and_list_are_redacted():
    payload = {"headers": {"Authorization": "Bearer secrettoken12345"},
               "items": [{"api_key": "sk-live-xxxxxxxxxxxxxxxxxxxx"}, {"ok": True}]}
    result = redact(payload)
    # "Authorization" is a sensitive KEY name -> whole value redacted outright.
    assert result["headers"]["Authorization"] == REDACTED
    assert result["items"][0]["api_key"] == REDACTED
    assert result["items"][1]["ok"] is True


def test_run_id_shaped_value_survives_untouched():
    """Regression: a hyphenated run_id/task_id must NOT be treated as an
    opaque secret just because it is long and alphanumeric."""
    run_id = "20261004-073007-suryodaya-cc4e96"
    assert redact({"run_id": run_id})["run_id"] == run_id
    assert redact(run_id) == run_id


def test_project_and_task_ids_survive_untouched():
    assert redact("PRJ-0000000000000000000001") == "PRJ-0000000000000000000001"


def test_no_password_bearer_or_key_shaped_string_survives_in_a_finding():
    import json
    from agent.findings import assemble_finding

    finding = assemble_finding(
        run_id="20261004-073007-suryodaya-cc4e96",
        instance="suryodaya", as_of="2026-10-04", company={"name": "Acme"},
    )
    serialized = json.dumps(finding).lower()
    assert "password" not in serialized
    assert "bearer " not in serialized or REDACTED.lower() in serialized
    assert finding["run_id"] == "20261004-073007-suryodaya-cc4e96"
