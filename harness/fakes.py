"""
Offline fakes: FakeMcp (same call surface as AgentSwitchClient) and
ScriptedModel (same call surface as agent.ai_models.AIModel), so the
exact same agent/loop.py code path runs in tests as runs live - the
only thing swapped is the transport and the model.
"""
import copy
import itertools
import json
import time
from typing import Any, Callable, Dict, List, Optional

from agent.mcp_client import MCPResult


class FakeMcp:
    """
    In-memory stand-in for AgentSwitchClient. Constructed from a fixture
    dict: {"<Entity>": [{...row...}, ...], ...}. Rows must have unique
    string "id" values within an entity.

    - call_tool("Entity.op", args): op in {list, get, create, update}
      (plus arbitrary endpoint.* ops registered via `register_endpoint`).
    - call_tool_all(...): mirrors AgentSwitchClient's pagination +
      truncated-flag contract.
    - rest_status(path): returns a configured status per entity, 200
      by default.
    - on_read(entity, id, mutator): the NEXT `Entity.get` for that id
      applies `mutator(row)` to the stored row first, then returns the
      mutated row - this is how fixtures inject a concurrent edit
      between an agent's read and its write.
    - write_log: every successful create/update call, for verifiers
      that assert "no write happened" or "only this id was written".
    - latency_s: sleep this long before every call (for deadline tests).
    """

    def __init__(self, data: Dict[str, List[Dict[str, Any]]],
                 entity_statuses: Optional[Dict[str, int]] = None,
                 latency_s: float = 0.0,
                 entity_total_overrides: Optional[Dict[str, int]] = None):
        self.data: Dict[str, List[Dict[str, Any]]] = copy.deepcopy(data)
        self._id_counters = {entity: itertools.count(1) for entity in self.data}
        self.entity_statuses = entity_statuses or {}
        self.latency_s = latency_s
        # Lets a fixture claim a bigger `total` than the rows it actually
        # supplies, to deterministically exercise the truncated-flag path
        # without needing hundreds of fixture rows (harness/fixtures/truncated_projects.json).
        self.entity_total_overrides = entity_total_overrides or {}
        self._on_read_hooks: Dict[tuple, Callable] = {}
        self.write_log: List[Dict[str, Any]] = []
        self._endpoint_handlers: Dict[str, Callable] = {}
        self.tools_list = self._default_tools_list()

    # -- fixture wiring ----------------------------------------------------

    def on_read(self, entity: str, entity_id: str, mutator: Callable[[Dict], None]) -> None:
        self._on_read_hooks[(entity, str(entity_id))] = mutator

    def register_endpoint(self, name: str, handler: Callable[[Dict], MCPResult]) -> None:
        self._endpoint_handlers[name] = handler

    def _default_tools_list(self) -> List[Dict[str, str]]:
        tools = []
        for entity in self.data:
            for op in ("list", "get", "create", "update"):
                tools.append({"name": f"{entity}.{op}", "description": "", "inputSchema": {}})
        for name in self._endpoint_handlers:
            tools.append({"name": name, "description": "", "inputSchema": {}})
        return tools

    # -- call surface --------------------------------------------------------

    def list_tools(self) -> MCPResult:
        return MCPResult(success=True, data={"tools": self.tools_list})

    def get_user_info(self) -> Dict[str, Any]:
        return {"email": "fixture@example.com", "name": "Fixture User", "role": "projects",
                "allowed_apps": ["projects", "agent", "crm"]}

    def rest_status(self, path: str) -> Optional[int]:
        entity = path.strip("/").split("/")[-1]
        return self.entity_statuses.get(entity, 200 if entity in self.data else 404)

    def call_tool(self, tool_name: str, arguments: Optional[Dict] = None) -> MCPResult:
        if self.latency_s:
            time.sleep(self.latency_s)
        arguments = arguments or {}

        if tool_name in self._endpoint_handlers:
            return self._endpoint_handlers[tool_name](arguments)

        if "." not in tool_name:
            return MCPResult(success=False, error=f"Unknown tool: {tool_name}")

        entity, op = tool_name.split(".", 1)
        if entity not in self.data:
            return MCPResult(success=False, error=f"HTTP 404: unknown entity {entity}")

        rows = self.data[entity]

        if op == "list":
            offset = arguments.get("offset", 0)
            limit = arguments.get("limit", 20)
            page = rows[offset:offset + limit]
            total = self.entity_total_overrides.get(entity, len(rows))
            return MCPResult(success=True, data={"data": copy.deepcopy(page), "total": total,
                                                  "limit": limit, "offset": offset})

        if op == "get":
            entity_id = str(arguments.get("id"))
            for row in rows:
                if str(row.get("id")) == entity_id:
                    hook = self._on_read_hooks.pop((entity, entity_id), None)
                    if hook:
                        hook(row)
                    return MCPResult(success=True, data={"data": copy.deepcopy(row)})
            return MCPResult(success=False, error=f"HTTP 404: {entity} {entity_id} not found")

        if op == "create":
            new_id = f"{entity}-{next(self._id_counters.setdefault(entity, itertools.count(1)))}"
            row = dict(arguments)
            row["id"] = new_id
            row.setdefault("updated_at", "2026-01-01T00:00:00Z")
            rows.append(row)
            self.write_log.append({"entity": entity, "op": "create", "id": new_id, "data": dict(row)})
            return MCPResult(success=True, data={"data": copy.deepcopy(row)})

        if op == "update":
            entity_id = str(arguments.get("id"))
            for row in rows:
                if str(row.get("id")) == entity_id:
                    changes = {k: v for k, v in arguments.items() if k != "id"}
                    if row.get("_locked"):
                        return MCPResult(success=False, error="HTTP 423: row is locked")
                    row.update(changes)
                    self.write_log.append({"entity": entity, "op": "update", "id": entity_id, "changes": changes})
                    return MCPResult(success=True, data={"data": copy.deepcopy(row)})
            return MCPResult(success=False, error=f"HTTP 404: {entity} {entity_id} not found")

        return MCPResult(success=False, error=f"Unknown op {op} on {entity}")

    def call_tool_all(self, tool_name: str, arguments: Optional[Dict] = None,
                       page_size: int = 200, max_pages: int = 20) -> MCPResult:
        arguments = dict(arguments or {})
        offset = arguments.get("offset", 0)
        all_data: List[Any] = []
        total = None

        for _ in range(max_pages):
            args = dict(arguments)
            args["offset"] = offset
            args["limit"] = page_size
            result = self.call_tool(tool_name, args)
            if not result.success:
                return result
            page = result.data.get("data", [])
            all_data.extend(page)
            total = result.data.get("total", len(all_data))
            offset += len(page)
            if not page or offset >= total:
                break

        fetched = len(all_data)
        truncated = total is not None and fetched < total
        return MCPResult(success=True, data={"data": all_data, "total": total,
                                              "fetched": fetched, "truncated": truncated})


class ScriptedModel:
    """
    Stand-in for agent.ai_models.AIModel. Replays a fixed script of tool
    calls, one per `.chat()` invocation, then returns a plain final
    answer with no tool_calls. Used by tests/test_loop_bounded.py and
    offline harness tasks so grading does not depend on a live LLM.

    `script` is a list of either:
      - {"name": tool_name, "arguments": {...}}   -> one tool call this turn
      - "STOP"                                    -> final answer, no tools
      - "LOOP_FOREVER"                             -> keeps calling a no-op
                                                      tool forever (bounded-run test)
    """

    def __init__(self, script: List[Any], final_answer: str = "Done."):
        self.script = list(script)
        self.final_answer = final_answer
        self._loop_tool = {"name": "noop_tool", "arguments": {}}
        self._raise_on_call: Optional[Exception] = None

    def raise_next_call(self, exc: Exception) -> None:
        self._raise_on_call = exc

    def chat(self, messages: List[Dict[str, str]], tools: Optional[List[Dict]] = None,
             force_tool: Optional[str] = None) -> Dict:
        if self._raise_on_call is not None:
            exc, self._raise_on_call = self._raise_on_call, None
            raise exc

        if not self.script:
            return self._final_message()

        step = self.script[0]

        if step == "LOOP_FOREVER":
            call = self._loop_tool
        elif step == "STOP":
            self.script.pop(0)
            return self._final_message()
        else:
            call = self.script.pop(0)

        tool_calls = [{
            "id": f"call_{id(call)}_{time.monotonic_ns()}",
            "type": "function",
            "function": {"name": call["name"], "arguments": json.dumps(call.get("arguments", {}))},
        }]
        return {"choices": [{"message": {"role": "assistant", "content": None, "tool_calls": tool_calls}}]}

    def _final_message(self) -> Dict:
        return {"choices": [{"message": {"role": "assistant", "content": self.final_answer}}]}
