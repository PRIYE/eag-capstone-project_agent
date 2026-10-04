# Team 14 AgentSwitch Agent (Projects)

Your Team 14 capstone project for the **Projects** seat at AgentSwitch.

## Graded Request
*"Which projects are behind, who is overloaded next week, and what would you move?"*

## Quick Start

1. **Add your AI model API key to `.env`:**
   ```bash
   # Uncomment one of these in .env:
   OPENAI_API_KEY=sk-your-key-here
   # ANTHROPIC_API_KEY=sk-ant-your-key-here  
   # GOOGLE_API_KEY=AI-your-key-here
   ```

2. **Test connectivity:**
   ```bash
   python run.py check
   ```

3. **Run the agent:**
   ```bash
   python run.py agent
   ```

4. **Run full test harness:**
   ```bash
   python run.py test
   ```

## Project Structure

```
Capstone/
├── .env                    # Your credentials (already set up)
├── .gitignore             # Excludes secrets
├── run.py                 # Main entry point
├── README.md              # This file
│
├── agent/
│   ├── mcp_client.py      # MCP JSON-RPC client
│   ├── ai_models.py       # OpenAI/Anthropic/Google wrappers  
│   └── loop.py            # Main agent logic
│
├── harness/
│   ├── tasks.json         # Test definitions
│   ├── verifiers.py       # Check API state, not just prose
│   ├── runner.py          # Test execution
│   └── runs/              # Results saved here
│
└── gap_report.md          # Week 1 deliverable (create this)
```

## Your Week 1 Tasks

### 1. Study the Domain (10 min)
- Open [https://agentswitch.theschoolofai.in](https://agentswitch.theschoolofai.in)  
- Sign in with your Team 14 credentials (see `.env` — never commit real passwords)
- Click **Projects** → explore real projects, tasks, milestones, resource allocations
- Check task workflow states (todo → in_progress → in_review → done)

### 2. Find Your Competitor (1 day)
Research AI-native project management tools. Suggestions:
- **Linear** (issue tracking + project planning)
- **Motion** (AI scheduling)  
- **Float/Runn** (resource planning)
- **Productive** (project profitability)

Pick one AI-native tool (not "old tool + chatbot"). Sign up, try it, read docs.

### 3. Write Gap Report (`gap_report.md`)
One page, three sections:
- **What they do that we don't** (specific features)
- **Which gaps your agent can close today** (orchestration over existing APIs)  
- **What your agent can do that theirs can't** (multi-step reasoning, state changes)

### 4. Build & Test Your Agent
The agent in `agent/loop.py` needs your AI model key to work. It calls AgentSwitch MCP tools and answers your graded request.

Your test harness checks **actual API state**, not just text responses.

## Key Files Explained

### `.env` - Your Credentials
```bash
# Already configured with your Team 14 passwords (kept in `.env`, never committed)
AS_URL=https://agentswitch.theschoolofai.in           # India
AS_EMAIL=team14@theschoolofai.in
AS_PASSWORD=***set-in-dotenv***

# Switch to US instance:
# AS_URL=https://class.agentswitch.theschoolofai.in   # US
# AS_PASSWORD=***set-in-dotenv***

# Add YOUR model key:
GOOGLE_API_KEY=AI...                                   # ← Add this
MODEL_PROVIDER=google
MODEL_NAME=gemini-3.1-flash-lite-preview
```

### `agent/mcp_client.py` - AgentSwitch API
Pure Python MCP client. No external dependencies except your AI model.

Key methods:
- `create_client()` - authenticate & initialize
- `client.call_tool("Project.list")` - call MCP tools
- `client.get_schemas()` - get all entity schemas

### `harness/tasks.json` - Test Definitions  
10 test cases including:
- Main graded request (40 points)
- **Refusal tests** - agent must refuse payroll/manufacturing data (403 expected)
- Resource overload analysis
- Critical path analysis
- Invalid data handling

### `harness/verifiers.py` - Actual State Checking
Verifiers call the **real API** to check results, not just read agent prose.

Example: `check_projects_analyzed()` calls `Project.list` and verifies the agent actually found delayed projects.

## Important Notes

### Your Seat Permissions
Team 14 has apps: `["projects", "agent", "crm"]`

✅ **You CAN access:** Projects, Tasks, Milestones, ResourceAllocations, Timesheets, CRM  
❌ **You CANNOT access:** Payroll, Manufacturing, Accounting (other teams' seats)

403 errors on other apps are **expected boundaries**, not bugs to report.

### Data Consistency
Teams 1-3 share the same accounting ledger. Other teams may change data while your agent runs.

Your agent must **re-read before acting** and handle changing data gracefully.

### Scoring (from brief)
- Graded request: 40 points
- Other tasks: 5 points each  
- Refusal tests: 10 points each
- **Hand-written tests**: 10 points each (AI-generated tests = 0 points)
- **Real AgentSwitch bugs**: 100 points each

## Commands

```bash
python run.py check --instance suryodaya      # connectivity + capability probe (also: keystone)
python run.py agent "question" [--apply]      # one bounded run (read-only unless --apply)
python run.py test --offline                  # full offline harness (no network, no model key)
python run.py test --live --task <id>         # live grading against the real platform
python run.py verify harness/runs/<run_dir>  # re-grade a stored run from live data
python scripts/snapshot_schemas.py --instance suryodaya  # refresh docs/ENTITY_MAP.md
```

## Next Steps

1. **Add your AI API key** to `.env`
2. **Run** `python run.py check` to verify setup
3. **Study the UI** for 10 minutes to understand the domain
4. **Research a competitor** and write your gap report
5. **Test your agent** with `python run.py agent`
6. **Run full harness** with `python run.py test --offline`

Governing principles: `.specify/memory/constitution.md`. No live secrets are stored in this file — only placeholders; real values live in `.env`, which is git-ignored.

## Switching to US Instance (Keystone)

```bash
# Edit .env:
AS_URL=https://class.agentswitch.theschoolofai.in
AS_PASSWORD=***set-in-dotenv***

# Test:
python run.py check
```

Different accounting standards, tax regimes, data—useful for testing agent robustness.

## Help

- **Connectivity issues:** Check `.env` credentials, try `python run.py check`  
- **403 errors:** Expected for other seats (payroll, manufacturing)
- **MCP errors:** JSON-RPC errors return HTTP 200, check the `error` field
- **Model issues:** Verify your API key in `.env`

Your agent is ready to run. Add your AI model key and test it!


Governing Principles: see .specify/memory/constitution.md"