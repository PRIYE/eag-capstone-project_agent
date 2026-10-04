# Team 14 Gap Analysis: AgentSwitch (Projects) vs Nodes & Links

**Team:** 14 (Projects)
**Seat apps:** `projects`, `agent`, `crm`
**Competitor analyzed:** [Nodes & Links](https://nodeslinks.com/) — "AI Project Expert" for
complex/construction project scheduling. Used by Balfour Beatty, VINCI, BAM Nuttall,
Costain, Ferrovial, MTR, Worley and others. Products: Schedule Integrity, Change Control,
Delay Navigator, QSRA + Risk, EVM & Resources, Portfolio, AI Reporting.

Grounded against AgentSwitch's real `Project`, `Task`, `Milestone`,
`ProjectResourceAllocation`, `ProjectResourceProfile`, and `Timesheet` schemas
(`GET /api/schemas`) and the live Suryodaya data (101 real projects) — not guessed.

---

## 1. What They Do That We Don't

| Feature | What it actually does |
|---|---|
| **Schedule Integrity checks** | Continuously scans the schedule for stale logic, broken predecessor links, "good enough" updates that quietly corrupt the network — flags exactly where the data is untrustworthy before anyone plans off it. |
| **Change Control with critical-path impact** | Every schedule edit is logged (who/when/why) and immediately evaluated against the critical path/milestones, so a "small" date change that actually threatens the finish date is surfaced instantly, not discovered a month later. |
| **Delay Navigator** | Produces a narrative delay-cause analysis suitable for contractor claims — traces which activities actually drove the slip, not just "the date moved." |
| **QSRA + Risk** | Runs quantitative schedule risk analysis (Monte-Carlo style "what-if" stress tests) against the full multi-predecessor network to find which risks genuinely move the finish date. |
| **EVM & Resources** | Earned Value Management (planned vs. earned vs. actual cost) fused with resource/capacity views. |
| **Portfolio rollups** | Cross-project reporting/status for PMOs, not just one project at a time. |
| **Auditable, hallucination-resistant AI answers** | Every AI answer traces back to the underlying schedule model (P6-compatible); ISO 27001 certified; customer data never touches a public LLM. |
| **Role-specific narrative reporting** | "Turn this schedule update into a status email for my PM" / "prepare a summary for my sponsor" — tailored, on-demand, per audience. |

**"Accounting feels thin" is not useful — here's the concrete version:** AgentSwitch has
Projects, Tasks (with a single `depends_on_task_id` predecessor, status flow, budget/logged/
billed hours), Milestones, per-employee weekly capacity profiles, and time-based resource
allocations. It has **no schedule-quality scanner, no critical-path-aware change log, no
delay-cause narrative, no risk simulation, no EVM report, and no portfolio rollup view.**

---

## 2. Which Gaps Can an Agent Close Today

### ✅ Agent can build now (pure orchestration over existing tools/schema — verified live)

- **Schedule integrity scan** — walk `Task.list` (paginated; there are 101+ records per
  entity, default page size is 20) and flag: tasks with no `assignee_id`, no `due_date`,
  a `depends_on_task_id` pointing at a task that is itself `cancelled`/overdue, or
  `logged_hours` far exceeding `budget_hours`/`estimated_hours`. None of this needs a new
  endpoint — it's exactly the "AgentTask that walks the ledger and reports what's blocking
  it" pattern the brief describes, just for schedules instead of the close.
- **Critical-path-aware change control** — Team 14's seat already has
  `endpoint.projects.critical_path`. An agent can snapshot the critical path before and
  after a proposed `Task.update`, and only then tell a human "this move slips the finish
  date by N days" vs. "this is safe." That is Nodes & Links' Change Control feature,
  built entirely from tools we already have.
- **Basic EVM proxy** — `Project` has `budget_amount`, `budget_hours`, `estimated_cost`;
  `Task` has `budget_hours`/`logged_hours`/`billed_hours`/`rate`; `Timesheet` has
  `hours × rate = amount`. An agent can compute planned cost vs. actual cost
  (Timesheet-derived) vs. earned value (% of task complete × budget) per project today.
  This is **not** a platform gap — it was our own assumption error until we checked the
  schema.
- **Delay-cause narrative** — combine `Task.status`/`due_date` history with
  `Milestone.status` (`upcoming`/`reached`/`missed`) and the LLM to produce the same kind
  of "here's what actually drove the slip" writeup Delay Navigator sells, per project.
- **Resource overload / "who's overloaded next week"** — `ProjectResourceProfile` gives
  per-employee daily capacity (`monday_hours` … `sunday_hours`); `ProjectResourceAllocation`
  links a `Task` to a `CalendarEvent` (the actual time block). Sum allocated hours per
  employee per day, compare to profile capacity → this is literally the Team 14 graded
  request, and it's fully computable with tools we already have.
- **Role-specific status report** — `endpoint.projects.client_status_report` +
  LLM rewriting for the intended audience (PM/sponsor/exec) is orchestration, not new
  platform work.

### ❌ Needs platform work (genuinely not buildable with today's schema)

- **Full QSRA / Monte-Carlo risk simulation** — `Task` only has a single
  `depends_on_task_id` (one predecessor, no lag/lead, no multiple-predecessor DAG, no
  duration-distribution fields). A real risk simulation needs a proper precedence
  network with uncertainty ranges per task — that's new schema, not just a smarter agent.
- **Baseline snapshots for true "slip vs. baseline"** — there is no
  `baseline_start_date`/`baseline_due_date` on `Task`/`Milestone`. Until then, an agent
  can *approximate* this by writing its own snapshots to `AgentMemory` (private to Team 14)
  each run and diffing against the previous snapshot — a workaround, not a full fix.
- **Auditable "answer traces to source" UX + ISO 27001-grade data isolation** — that's a
  platform/compliance investment (citation plumbing, data residency), not something an
  agent orchestrating existing endpoints can manufacture.
- **Portfolio rollup UI across many companies/tenants** — `Project.list` scopes to our
  company only by seat design; a true cross-portfolio view needs either a new endpoint or
  admin-level aggregation we don't have from this seat.

---

## 3. What Our Agent Can Do That Nodes & Links Cannot

Nodes & Links is explicit about its model: *"Your experts keep full hands-on control, with
every tool they need to run projects exactly to your standards."* It is a very good
**answer engine** — a human still asks each question and clicks through to act.

Our agent, by contrast, holds MCP tools that can **read and write** the same objects it
reasons about, in one continuous run:

- **End-to-end resolution, not just a report.** "This work order is late" (or for us:
  "which projects are behind, who's overloaded, what would you move") doesn't stop at a
  dashboard — the agent can call `Task.update`, reassign via `ProjectResourceAllocation`,
  and re-run `endpoint.projects.critical_path` to confirm the fix actually worked, then
  report the *outcome*, not just the recommendation.
- **Re-reads state that changed underneath it.** Team 14's ledger/seat data can be
  modified by other processes mid-run (per the platform's design). Nodes & Links assumes a
  human-paced, single-operator workflow; our agent is built to re-fetch before acting and
  tolerate concurrent change — genuinely different failure mode.
- **Chains reasoning across apps in one seat.** Team 14 also holds `crm` — an agent can
  connect a slipping project to the customer record and draft the client-facing update in
  the same run, something a scheduling-only tool structurally can't do.
- **Refuses instead of guessing.** When asked something outside its seat (payroll, work
  orders), the agent gets a clean `403`/`tool_not_available` and must say so — a discipline
  a general BI/chat tool bolted onto a dashboard rarely enforces as a hard boundary.

---

## Summary

- **Platform gaps to raise:** multi-predecessor scheduling network + duration uncertainty
  (for real QSRA), baseline snapshots, cross-portfolio aggregation endpoint, answer
  citation/audit plumbing.
- **Agent opportunities (buildable now):** schedule integrity scanner, critical-path-aware
  change control, EVM proxy from existing budget/timesheet fields, delay-cause narrative,
  resource-overload detection (the graded request), audience-specific status reporting.
- **Agent's structural advantage:** action, not just answers — and doing it while other
  writers change the same data underneath it.

**Recommended focus for Team 14:** build the resource-overload + reschedule-recommendation
flow first (directly answers the graded request), then layer the critical-path-aware
change check on top of any `Task.update` the agent proposes, since that's the single
Nodes & Links feature we can fully replicate today with zero new platform work.