#!/usr/bin/env python3
"""
Main entry point for the Seat 14 (Projects) agent. See
specs/001-project-agent/contracts/cli.md for the full command contract.

Usage:
  python run.py check [--instance suryodaya|keystone]
  python run.py agent ["<question>"] [--instance ...] [--apply] [--escalate]
  python run.py test [--offline|--live] [--task ID] [--instance ...]
  python run.py verify <run_dir>
  python run.py help
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

DEFAULT_GRADED_REQUEST = (
    "Which projects are behind schedule, and who is overloaded next week?"
)


def cmd_check(args) -> int:
    """
    Connectivity + capability probe (tasks.md T010). Confirms: auth,
    tool list, AgentMemory.create visibility (finding storage), the
    escalation assignee endpoint, and the shape of
    endpoint.projects.critical_path / endpoint.projects.client_status_report.
    Exits 2 on any hard failure so this is scriptable in CI-style checks.
    """
    from agent.mcp_client import create_client_for
    from agent import safety

    instance = args.instance
    print(f"Checking AgentSwitch connectivity for instance '{instance}'...")
    try:
        client = create_client_for(instance)
    except Exception as e:
        print(f"FAIL: could not authenticate/initialize: {e}")
        return 2

    user_info = client.get_user_info()
    print(f"OK  logged in as {user_info.get('email')} (role={user_info.get('role')})")
    print(f"OK  allowed_apps={user_info.get('allowed_apps')}")

    tools_result = client.list_tools()
    if not tools_result.success:
        print(f"FAIL: could not list tools: {tools_result.error}")
        return 2
    tools = tools_result.data.get("tools", [])
    print(f"OK  {len(tools)} MCP tools visible")

    # Finding storage visibility.
    mem_probe = safety.probe_capability(client, "AgentMemory", "create")
    print(f"{'OK' if mem_probe['visible'] else 'WARN'}  AgentMemory.create -> {mem_probe}")

    # Escalation assignee endpoint visibility.
    esc_probe = safety.probe_capability(client, "endpoint.agent_governance.escalations", "assignees")
    print(f"{'OK' if esc_probe['visible'] else 'WARN'}  escalation assignees endpoint -> {esc_probe}")

    # Critical path / status report endpoint shape.
    for tool_name in ("endpoint.projects.critical_path", "endpoint.projects.client_status_report"):
        probe = safety.probe_capability(client, "endpoint.projects", tool_name.rsplit(".", 1)[-1])
        print(f"{'OK' if probe['visible'] else 'WARN'}  {tool_name} -> {probe}")

    print("\nDone. See docs/ENTITY_MAP.md (run scripts/snapshot_schemas.py) for full field confirmation.")
    return 0


def cmd_agent(args) -> int:
    """
    One bounded run (tasks.md T034/T035; contracts/cli.md). Read-only
    unless --apply; --escalate allows raising one real escalation.
    """
    from agent.mcp_client import create_client_for
    from agent.ai_models import create_model
    from agent.loop import run_agent

    question = args.question or DEFAULT_GRADED_REQUEST
    instance = args.instance

    try:
        client = create_client_for(instance)
    except Exception as e:
        print(f"Agent error: could not connect: {e}")
        return 2

    model = create_model()

    def on_event(event):
        print(f"EVENT: {event}")

    result = run_agent(
        client,
        model,
        question,
        instance=instance,
        apply_writes=args.apply,
        allow_escalate=args.escalate,
        on_event=on_event,
    )

    print("\n" + "=" * 60)
    print("SUMMARY:")
    print(result.get("summary", "<no summary produced>"))
    print(f"\nStatus: {result.get('status')}  run_id: {result.get('run_id')}")
    print(f"Trace: {result.get('run_dir')}")

    status = result.get("status")
    if status == "complete" or status == "escalated" or status == "refused":
        return 0
    if status == "partial":
        return 1
    return 2


def cmd_test(args) -> int:
    """Offline (fixture-based) or live harness run (tasks.md T027)."""
    from harness.runner import run_tasks

    mode = "live" if args.live else "offline"
    verdicts = run_tasks(mode=mode, task_id=args.task, instance=args.instance)

    all_approved = all(v == "approve" for v in verdicts.values())
    for task_id, verdict in verdicts.items():
        marker = "PASS" if verdict == "approve" else "FAIL"
        print(f"[{marker}] {task_id}: {verdict}")

    return 0 if all_approved else 1


def cmd_verify(args) -> int:
    """Re-grade a stored run from its result.json + the live database."""
    from harness.verify import verify_run

    verdict = verify_run(args.run_dir)
    print(f"Verdict: {verdict}")
    return 0 if verdict == "approve" else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="run.py", description="Seat 14 Project Agent CLI")
    sub = parser.add_subparsers(dest="command")

    p_check = sub.add_parser("check", help="Connectivity and capability check")
    p_check.add_argument("--instance", default="suryodaya", choices=["suryodaya", "keystone"])

    p_agent = sub.add_parser("agent", help="Run one bounded agent turn")
    p_agent.add_argument("question", nargs="?", default=None)
    p_agent.add_argument("--instance", default="suryodaya", choices=["suryodaya", "keystone"])
    p_agent.add_argument("--apply", action="store_true", help="Allow writes (per-write y/n prompt)")
    p_agent.add_argument("--escalate", action="store_true", help="Allow raising a real escalation")

    p_test = sub.add_parser("test", help="Run the harness")
    p_test.add_argument("--offline", action="store_true", default=True)
    p_test.add_argument("--live", action="store_true", help="Run against the real platform (read-only unless fixture_owned)")
    p_test.add_argument("--task", default=None, help="Run only this task id")
    p_test.add_argument("--instance", default="suryodaya", choices=["suryodaya", "keystone"])

    p_verify = sub.add_parser("verify", help="Re-grade a stored run")
    p_verify.add_argument("run_dir")

    sub.add_parser("help", help="Show this help")
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    if not args.command or args.command == "help":
        parser.print_help()
        return 0

    try:
        if args.command == "check":
            return cmd_check(args)
        if args.command == "agent":
            return cmd_agent(args)
        if args.command == "test":
            return cmd_test(args)
        if args.command == "verify":
            return cmd_verify(args)
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return 2

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
