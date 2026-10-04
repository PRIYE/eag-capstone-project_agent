"""
AgentSwitch MCP Client for Team 14 (Projects)
Pure Python MCP client using urllib - no external dependencies except for AI model.
"""
import json
import os
import time
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Any, Optional, List
from dataclasses import dataclass

# Transient-error retry: HTTP 429/5xx and connection-level failures are
# retried with linear backoff; 4xx (other than 429) are not retried,
# since those are the agent's own mistake, not a blip.
_RETRYABLE_STATUS = {429, 500, 502, 503, 504}
_RETRY_ATTEMPTS = 3
_RETRY_BACKOFF_S = 0.5


class HTTPStatusError(Exception):
    """HTTP error carrying the status code, so callers can branch on
    403 vs 404 vs other without re-parsing the message string."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


@dataclass
class MCPResult:
    """Wrapper for MCP call results"""
    success: bool
    data: Any = None
    error: Optional[Dict] = None
    raw_response: Optional[Dict] = None


class AgentSwitchClient:
    """MCP client for AgentSwitch platform"""
    
    def __init__(self, base_url: str, email: str, password: str):
        self.base_url = base_url.rstrip('/')
        self.email = email
        self.password = password
        self.token: Optional[str] = None
        self.initialized = False
        self.request_id = 0
        
    def _next_id(self) -> int:
        self.request_id += 1
        return self.request_id
    
    def _http_request(self, method: str, path: str, data: Optional[Dict] = None,
                     headers: Optional[Dict] = None, _retries: int = _RETRY_ATTEMPTS) -> Dict:
        """
        Make HTTP request with error handling and retry on transient
        failures (429/5xx or a connection-level error). Non-transient
        4xx errors (401, 403, 404, etc.) are raised immediately so a
        real permissions/capability result isn't masked by a retry loop.
        """
        url = f"{self.base_url}{path}"
        req_headers = {"Content-Type": "application/json"}

        if headers:
            req_headers.update(headers)

        if self.token:
            req_headers["Authorization"] = f"Bearer {self.token}"

        req_data = json.dumps(data).encode() if data else None

        attempt = 0
        while True:
            attempt += 1
            try:
                req = urllib.request.Request(url, data=req_data, headers=req_headers, method=method)
                with urllib.request.urlopen(req, timeout=30) as response:
                    return json.loads(response.read().decode())
            except urllib.error.HTTPError as e:
                if e.code in _RETRYABLE_STATUS and attempt < _retries:
                    time.sleep(_RETRY_BACKOFF_S * attempt)
                    continue
                error_body = e.read().decode() if e.fp else ""
                raise HTTPStatusError(e.code, f"HTTP {e.code}: {error_body}") from e
            except urllib.error.HTTPError:
                raise
            except Exception as e:
                if attempt < _retries:
                    time.sleep(_RETRY_BACKOFF_S * attempt)
                    continue
                raise Exception(f"Request failed: {str(e)}")

    def rest_status(self, path: str) -> Optional[int]:
        """
        Independent REST status probe (Constitution Principle III): used
        to tell a real 403 (entity exists, outside this seat) from a 404
        (name does not exist), without retrying 403/404 as if they were
        transient. Returns the HTTP status code, or None if the request
        could not be made at all (e.g. network failure).
        """
        url = f"{self.base_url}{path}"
        req_headers = {"Content-Type": "application/json"}
        if self.token:
            req_headers["Authorization"] = f"Bearer {self.token}"
        try:
            req = urllib.request.Request(url, headers=req_headers, method="GET")
            with urllib.request.urlopen(req, timeout=15) as response:
                return response.status
        except urllib.error.HTTPError as e:
            return e.code
        except Exception:
            return None
    
    def login(self) -> bool:
        """Authenticate and get token"""
        try:
            response = self._http_request("POST", "/api/auth/login", {
                "email": self.email,
                "password": self.password
            })
            
            if "token" in response:
                self.token = response["token"]
                return True
            else:
                print(f"Login failed: {response}")
                return False
                
        except Exception as e:
            print(f"Login error: {e}")
            return False
    
    def get_user_info(self) -> Dict:
        """Get current user info and permissions"""
        if not self.token:
            raise Exception("Not logged in")
        return self._http_request("GET", "/api/auth/me")
    
    def mcp_call(self, method: str, params: Optional[Dict] = None) -> MCPResult:
        """Make MCP JSON-RPC call"""
        if not self.token:
            raise Exception("Not logged in")
            
        payload = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": method,
            "params": params or {}
        }
        
        try:
            response = self._http_request("POST", "/api/mcp", payload)
            
            if "result" in response:
                return MCPResult(success=True, data=response["result"], raw_response=response)
            elif "error" in response:
                return MCPResult(success=False, error=response["error"], raw_response=response)
            else:
                return MCPResult(success=False, error={"code": -1, "message": "Invalid response format"}, raw_response=response)
                
        except Exception as e:
            return MCPResult(success=False, error={"code": -1, "message": str(e)})
    
    def initialize(self) -> MCPResult:
        """Initialize MCP connection"""
        result = self.mcp_call("initialize", {
            "protocolVersion": "2025-11-25",
            "capabilities": {},
            "clientInfo": {"name": "team-14", "version": "0.1"}
        })
        
        if result.success:
            self.initialized = True
            # Send the initialized notification. Per JSON-RPC 2.0, notifications
            # carry NO "id" field and expect no response body - unlike our other
            # calls. Fire-and-forget; ignore failures here.
            try:
                self._http_request("POST", "/api/mcp", {
                    "jsonrpc": "2.0",
                    "method": "notifications/initialized",
                    "params": {}
                })
            except Exception:
                pass

        return result
    
    def list_tools(self) -> MCPResult:
        """List available MCP tools"""
        if not self.initialized:
            raise Exception("MCP not initialized")
        return self.mcp_call("tools/list")
    
    def call_tool(self, tool_name: str, arguments: Optional[Dict] = None) -> MCPResult:
        """
        Call a specific MCP tool and unwrap the result.

        IMPORTANT: AgentSwitch's tools/call does NOT return entity data directly
        in `result`. The real shape is:
            result = {
                "content": [{"type": "text", "text": "<json-encoded entity payload>"}],
                "structuredContent": { ...the actual parsed entity payload... },
                "isError": false
            }
        For list-style tools, structuredContent looks like:
            {"data": [...], "total": N, "limit": L, "offset": O}

        This method unwraps structuredContent (falling back to parsing
        content[0].text) so callers can treat MCPResult.data as the real
        entity payload, e.g. result.data["data"] for a list call.
        """
        if not self.initialized:
            raise Exception("MCP not initialized")

        raw = self.mcp_call("tools/call", {
            "name": tool_name,
            "arguments": arguments or {}
        })

        if not raw.success:
            return raw

        envelope = raw.data if isinstance(raw.data, dict) else {}

        # A tool can "succeed" at the JSON-RPC layer but still report a
        # tool-level failure via isError. Treat that as a failed call.
        if envelope.get("isError"):
            content = envelope.get("content", [])
            message = content[0].get("text") if content and isinstance(content[0], dict) else str(envelope)
            return MCPResult(success=False, error={"code": "tool_error", "message": message}, raw_response=raw.raw_response)

        unwrapped = envelope.get("structuredContent")

        if unwrapped is None:
            # Fallback: parse the JSON string out of content[0].text
            content = envelope.get("content", [])
            if content and isinstance(content[0], dict) and "text" in content[0]:
                try:
                    unwrapped = json.loads(content[0]["text"])
                except (json.JSONDecodeError, TypeError):
                    unwrapped = envelope
            else:
                unwrapped = envelope

        return MCPResult(success=True, data=unwrapped, raw_response=raw.raw_response)

    def call_tool_all(self, tool_name: str, arguments: Optional[Dict] = None,
                     page_size: int = 200, max_pages: int = 20) -> MCPResult:
        """
        Call a list-style tool and page through ALL results using offset/limit.

        AgentSwitch list tools default to limit=20 (max 1000) and report
        {"data": [...], "total": N, "limit": L, "offset": O}. Relying on the
        default page size will silently truncate results (e.g. we saw 101
        Projects but only 20 came back on the first page) - use this whenever
        you need the complete set, not just a sample.

        Returns data={"data": [...], "total": N, "fetched": M, "truncated": bool}.
        `truncated` is True whenever fetched < total (e.g. max_pages hit before
        the full set was read) - callers (agent/data.py) MUST check this and
        mark the run `partial` rather than silently analysing a short list
        (research.md R8).

        Once the first page reveals `total`, remaining pages are fetched in
        parallel (bounded thread pool) instead of sequentially.
        """
        arguments = dict(arguments or {})
        offset = arguments.get("offset", 0)
        arguments["limit"] = page_size

        first_args = dict(arguments)
        first_args["offset"] = offset
        first = self.call_tool(tool_name, first_args)
        if not first.success:
            return first

        first_page = first.data.get("data", []) if isinstance(first.data, dict) else []
        total = first.data.get("total", len(first_page)) if isinstance(first.data, dict) else len(first_page)

        all_data: List[Any] = list(first_page)
        fetched = len(first_page)
        next_offset = offset + fetched

        remaining_offsets = []
        o = next_offset
        pages_used = 1
        while fetched < total and pages_used < max_pages and first_page:
            remaining_offsets.append(o)
            o += page_size
            fetched += page_size
            pages_used += 1
        # fetched above is an over-estimate for sizing; recompute from real pages below.
        all_data = list(first_page)

        def _fetch_page(off: int):
            args = dict(arguments)
            args["offset"] = off
            return off, self.call_tool(tool_name, args)

        if remaining_offsets:
            results: Dict[int, Any] = {}
            with ThreadPoolExecutor(max_workers=min(8, len(remaining_offsets))) as pool:
                futures = [pool.submit(_fetch_page, off) for off in remaining_offsets]
                for fut in as_completed(futures):
                    off, result = fut.result()
                    if not result.success:
                        return result
                    page = result.data.get("data", []) if isinstance(result.data, dict) else []
                    results[off] = page
            for off in sorted(results):
                all_data.extend(results[off])

        fetched_count = len(all_data)
        truncated = fetched_count < total
        return MCPResult(success=True, data={
            "data": all_data,
            "total": total,
            "fetched": fetched_count,
            "truncated": truncated,
        })
    
    def get_schemas(self) -> Dict:
        """Get entity schemas (REST endpoint)"""
        return self._http_request("GET", "/api/schemas")


def load_env() -> Dict[str, str]:
    """Load environment variables from .env file"""
    env_vars = {}
    env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')
    
    if os.path.exists(env_path):
        with open(env_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    value = value.strip()
                    if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
                        value = value[1:-1]
                    env_vars[key.strip()] = value
    
    return env_vars


def create_client_for(instance: str) -> AgentSwitchClient:
    """
    Build and authenticate a client for a named instance ('suryodaya' or
    'keystone') using agent/config.py, instead of always reading the
    default AS_URL/AS_EMAIL/AS_PASSWORD triplet. Constitution Principle
    VI: this only selects *which* credentials to use - it reads nothing
    tenant-specific (currency, country) itself.
    """
    from . import config as _config  # local import avoids a cycle at module load

    creds = _config.credentials(instance)
    client = AgentSwitchClient(creds["url"], creds["email"], creds["password"])

    if not client.login():
        raise Exception(f"Failed to authenticate against instance '{instance}'")

    init_result = client.initialize()
    if not init_result.success:
        raise Exception(f"Failed to initialize MCP for '{instance}': {init_result.error}")

    return client


def create_client() -> AgentSwitchClient:
    """Create and authenticate AgentSwitch client from .env"""
    env = load_env()
    
    url = env.get('AS_URL')
    email = env.get('AS_EMAIL') 
    password = env.get('AS_PASSWORD')
    
    if not all([url, email, password]):
        raise Exception("Missing AS_URL, AS_EMAIL, or AS_PASSWORD in .env file")
    
    client = AgentSwitchClient(url, email, password)
    
    if not client.login():
        raise Exception("Failed to authenticate")
        
    init_result = client.initialize()
    if not init_result.success:
        raise Exception(f"Failed to initialize MCP: {init_result.error}")
    
    return client


if __name__ == "__main__":
    # Test the client
    try:
        client = create_client()
        
        # Get user info
        user_info = client.get_user_info()
        print("User info:", json.dumps(user_info, indent=2))
        
        # List tools
        tools_result = client.list_tools()
        if tools_result.success:
            tools = tools_result.data.get('tools', [])
            print(f"\nFound {len(tools)} tools")
            
            # Show project-related tools
            project_tools = [t['name'] for t in tools if 'project' in t['name'].lower() or 'task' in t['name'].lower()]
            print("Project/Task tools:")
            for tool in sorted(project_tools):
                print(f"  {tool}")
        else:
            print("Failed to list tools:", tools_result.error)
            
        # Test a simple tool call - use call_tool_all to avoid the default
        # page size of 20 silently truncating results.
        projects_result = client.call_tool_all("Project.list")
        if projects_result.success:
            projects = projects_result.data
            print(f"\nProjects: {len(projects.get('data', []))} of {projects.get('total')} total")
            for project in projects.get('data', [])[:3]:  # Show first 3
                print(f"  - {project.get('name', 'Unnamed')} ({project.get('status', 'unknown')})")
        else:
            print("Failed to list projects:", projects_result.error)
            
    except Exception as e:
        print(f"Error: {e}")