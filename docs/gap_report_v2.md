# Team 14 Gap Report v2: Agent tool list vs Nodes & Links

**Seat:** 14 (Projects) · **Date:** 2026-10-06 (rev 2: partly-covered deep dive) · **Supersedes:** section 1–2 framing of [`gap_report.md`](gap_report.md) (kept as the Week‑1 original)

**What changed from v1:** v1 compared the *AgentSwitch platform* to Nodes & Links (N&L) before anything was built.
v2 compares **the agent we actually shipped** — its 14 tools in `agent/tools.py`, offline-graded 17/17 — module by module.

**Competitor:** [Nodes & Links](https://nodeslinks.com/) — AI schedule intelligence for complex/construction projects
(Balfour Beatty, VINCI, AECOM, HS2, Turner, Shell…; $12M Series B, Feb 2025). Modules: Progress Tracking, Schedule Integrity,
Change Control, Delay Navigator, QSRA + Risk, EVM & Resources, Portfolio, AI Reporting. Integrates with Primavera P6 / OPC,
MS Project and Asta Powerproject; ISO 27001; "AI Scheduling Operator" that monitors schedule updates continuously.

Legend: ✅ covered · 🟡 partial · ❌ not covered · *Close by:* **A** = agent work (our code), **P** = needs platform/schema change

---

## 1. Our tool list

| # | Tool | Role | Writes? |
|---|---|---|---|
| 1 | `company_context` | Tenant name, country, currency, today | – |
| 2 | `load_snapshot` | Paginated fetch of projects / capacity / money scopes, reports truncation | – |
| 3 | `schedule_integrity` | Missing assignee/due date, broken/looped/cross-project predecessor, effort overrun >150% | – |
| 4 | `behind_schedule_projects` | **Graded.** Projects behind, each with a dated cause | – |
| 5 | `overloaded_next_week` | **Graded.** Allocated vs daily capacity across all projects; `capacity_unknown` kept separate | – |
| 6 | `critical_path_check` | What-if: does moving task X move the finish date, by how many days | – |
| 7 | `propose_reschedule` | Ranked moves (lowest slip first) + writability (locked/closed/no-assignee) | – |
| 8 | `apply_proposal` | One approved move via `guarded_update` (re-read → compare → write → re-read) | ✅ opt-in |
| 9 | `evm_summary` | Planned vs actual (timesheets) vs earned, per project | – |
| 10 | `delay_facts` | Primary blocker, secondary causes, timeline — ids to cite | – |
| 11 | `status_report_facts` | One fact object, sponsor vs team framing | – |
| 12 | `seat_capability` | 403 vs 404 vs ok probe before touching an entity | – |
| 13 | `escalate` | Real escalation if assignee exists, else honest `no_assignee` | ✅ |
| 14 | `record_finding` | Exactly one validated finding per run (`AgentMemory`) | ✅ |

---

## 2. Module-by-module coverage

| N&L module | What N&L does | Our tool(s) | Coverage | Gap that remains | Close by |
|---|---|---|---|---|---|
| **Progress Tracking** | Compares successive schedule updates; shows what moved since last period | `behind_schedule_projects`, `delay_facts` | 🟡 | We see *today's* state only. Verified in schema: Project/Task/Milestone hold only current `start_date`/`end_date`/`due_date`; no baseline/planned/original field. `ScheduleSnapshot` exists but is manufacturing-only. Our finding stores conclusions, not the date set. | **A** (snapshot findings to `AgentMemory` each run and diff) / **P** (baseline dates) |
| **Schedule Integrity** | Audits logic quality: stale logic, broken links, open ends, dangling activities | `schedule_integrity` | ✅ for our schema | All checks possible on a single `depends_on_task_id`. Cannot check multi-predecessor logic, lags, relationship types, constraints — the fields do not exist. | **P** |
| **Change Control** | Logs every schedule edit (who/when/why) and evaluates impact on critical path / milestones | `critical_path_check`, `propose_reschedule`, `apply_proposal`, `record_finding` | 🟡 | We evaluate and audit **our own** proposed moves. Edits by others go unseen: no projects-domain change log exists (audit logs in the schema are for email, approvals, e-sign, drive, plugins), and `trackable` on Task/Milestone is reserved, not active. | **A** (periodic diff job) / **P** (change-log endpoint) |
| **Delay Navigator** | Root-cause delay analysis, real vs noise, claim-ready narrative | `delay_facts` + model narrative | 🟡 | Grounded narrative per project ✅. Primary blocker = *most days late*, not the upstream root cause (predecessor chain not walked). No slip history; no forensic methods (windows / as-planned vs as-built). | **P** |
| **QSRA + Risk** | Monte-Carlo risk over tens of thousands of activities | – | ❌ | Needs a precedence network with multiple predecessors and duration ranges. One link per task, no 3-point estimates. | **P** |
| **EVM & Resources** | EVM metrics plus resource analytics | `evm_summary`, `overloaded_next_week` | 🟡 | AC and EV computable live, CPI reported. "Planned" is total budget (BAC), not planned value to date, so **no SPI**; in-progress work earns 0; no EAC/ETC forecast; no S-curve. Overload is correct but **empty on live** — zero allocations/profiles and `CalendarEvent.list` not in seat catalogue (BUGS_FILED #1). `completed` tasks not counted as earned (bug N131 follow-up). | **A** (time-phase PV, add `completed`) / **P** (calendar access, data) |
| **Portfolio** | Health scoring across many projects | `behind_schedule_projects`, `evm_summary` over all projects | 🟡 | Company-wide lists ✅ (three separate tools). No composite health score or ranking; no grouping by owner/priority/client; no trend; no cross-company view (seat-scoped by design). | **A** (health score) / **P** (cross-tenant) |
| **AI Reporting** | Role-specific narratives for schedulers, PMs, controllers, execs | `status_report_facts` (+ `endpoint.projects.client_status_report`) | 🟡 | Two audiences (sponsor, team). Sponsor template says "behind schedule" even for on-track projects (bug). Team text shows ids not task titles. No milestones-ahead / people / decisions sections. One project per report. Not delivered anywhere (text lives only in our finding). | **A** |
| **Auditable answers** | Every answer traceable to source; "hallucination-proof" | `record_finding` → `validate_finding` | ✅ | Finding rejected unless every id exists in the snapshot and causes are dated; trace.jsonl per run. No UI to click through to the source row. | **P** (UI) |
| **Tool integrations** | Primavera P6 / OPC, MS Project, Asta import | – | ❌ | Out of scope: AgentSwitch is the system of record. | n/a |
| **Security / ISO 27001** | Certified ISMS, data stays in tenant | Redaction (`redact.py`), seat probe, no secrets in traces | 🟡 | Engineering hygiene, not certification. | n/a |
| **Continuous monitoring** | "AI Scheduling Operator" watches updates as they land | – (one bounded run per question) | ❌ | Each run is on demand, 20 steps / 180 s. | **A** (scheduled runs + diff) |

**Score:** 2 ✅ · 7 🟡 · 3 ❌ out of 12. Of the 10 gaps, **6 can be reduced with agent work alone**; the rest need schema or platform changes.

---

## 2a. Partly-covered gaps in detail

Each gap below was checked against `docs/ENTITY_MAP.raw.json` (platform schema) and our code in `agent/domain/`.

### Root cause shared by five gaps: no history
AgentSwitch overwrites dates in place. There is no baseline field, no readable change log for the projects domain, and our findings do not store the full date set.
`trackable` is listed in `reserved_behaviors` on Project/Task/Milestone (and 139 entities platform-wide) but active on none; the schema does not define it — by ERP convention it most likely means a field-level change log (who/when/old/new). `ProjectStatusReport` is an append-only ledger (`captured_at`, `evidence`) and is the nearest in-domain history source; its `evidence` contents are unverified.
**One agent fix — a run-to-run "diary"** (store task/milestone dates, EVM and health scores in each finding; diff against the previous run) advances Progress Tracking, Change Control, Delay Navigator, EVM trend and Portfolio trend at once. Limits: no history before first run; no *who/why*; intermediate changes between runs are merged.

### Progress Tracking
| Gap | Fix | Who | Size |
|---|---|---|---|
| No "slipped N days since last update" / improving-vs-worsening trend | Run-to-run diary | Us | Medium |
| No baseline for "vs original plan" | Baseline fields or enable `trackable` | Platform | — |

### Change Control
| Gap | Fix | Who | Size |
|---|---|---|---|
| Changes by others are invisible | Diary + scheduled runs; run `critical_path_check` on every detected date change | Us | Medium |
| No who / when / why | Enable `trackable` on Task/Milestone, or expose a projects audit trail to the seat | Platform | — |

### Delay Navigator
| Gap | Fix | Who | Size |
|---|---|---|---|
| "Primary blocker" = most days late, not root cause (e.g. downstream Foundation 16 d late is picked over upstream Excavation that holds it) | Walk `depends_on_task_id` chain; name furthest-upstream open task as root | Us | Small |
| How the slip built up over time | Run-to-run diary | Us | Medium |
| Claim-grade forensic analysis | Baselines + history + multi-predecessor logic | Platform | — |

### EVM & Resources
| Gap | Fix | Who | Size |
|---|---|---|---|
| "Planned" = whole budget, so no "on time?" answer (SPI) | Planned value = budget of tasks due on/before today | Us | Small |
| In-progress tasks earn 0 | Documented rule, e.g. in_progress = 50% | Us | Small |
| `completed` tasks earn 0 (N131) | Add to finished states | Us | Small |
| No cost/finish forecast | EAC = BAC / CPI, ETC = EAC − AC | Us | Small |
| No trend / S-curve | Run-to-run diary | Us | Medium |
| Overload empty on live data | `CalendarEvent.list` access + real allocations/profiles | Platform | — |
| Only "move dates", never "reassign to someone with spare hours" | Propose `assignee_id` changes using spare capacity | Us | Medium |
| Fixed 7-day window | Make window configurable | Us | Small |

### Portfolio
| Gap | Fix | Who | Size |
|---|---|---|---|
| Three separate lists, no single score | `portfolio_health` tool with fixed, documented rules (schedule, CPI, integrity, overload) + ranking | Us | Small–medium |
| No grouping | Group by `owner_id`, `priority`, `status`, `party_id` | Us | Small |
| No trend | Run-to-run diary | Us | Medium |
| Cross-company view | Not available to seat (by design) | Platform | — |

### AI Reporting
| Gap | Fix | Who | Size |
|---|---|---|---|
| **Bug:** sponsor text says "is behind schedule" for on-track projects ("Primary cause: issue (since unknown date)") | Add on-track branch in `status.frame` | Us | Small |
| Only sponsor + team | Add PM, cost controller, executive framings | Us | Small |
| Missing sections: upcoming milestones, people/overload, decisions needed | Reuse `Milestone.due_date`, `overloaded_next_week`, `propose_reschedule` | Us | Small–medium |
| "What changed this period" | Run-to-run diary | Us | Medium |
| Team text shows ids, not task titles | Use `Task.title` with id in brackets | Us | Small |
| One project per report | Portfolio report on top of `portfolio_health` | Us | Small |
| Report not delivered | Write a `ProjectStatusReport` row (schema allows `project_user` create; verify seat) and schedule weekly | Us + platform check | Medium |

### Security
Certification (ISO 27001) and data residency are organisational, not agent work. Our side: redaction, seat probe, no secrets in traces — already in place.

---

## 3. What we do that Nodes & Links does not

| Capability | Our tool | Why N&L can't (as published) |
|---|---|---|
| **Act, not just advise** — apply an approved reschedule and verify it | `propose_reschedule` → `apply_proposal` → post-write re-read | N&L is an analysis layer over P6/MSP; edits happen back in the scheduling tool by a human. |
| **Safe writes under concurrent change** — abort if the row changed since we read it | `guarded_update` (tested: `concurrent_edit_before_write`) | No published write-back; changes are made back in the scheduling tool. |
| **Cross-project people overload** — hours summed across *all* projects vs each person's daily capacity | `overloaded_next_week` | *[inferred]* N&L reads resources from imported schedule files; its public material does not describe combining one person's load across separate files. |
| **Honest escalation / refusal** — `no_assignee`, clean 403 refusals for payroll/manufacturing | `escalate`, `seat_capability` (tested: `refuse_payroll`, `refuse_manufacturing`, `locked_task_no_assignee`) | General Q&A assistant; no hard permission boundary per seat. |
| **Every run leaves an auditable record**, even on budget exhaustion | `record_finding` (tested: `budget_exhausted_still_records`, `slow_reads_deadline`) | Answers are traceable, but no per-run persisted outcome object. |
| **Bounded, cheap, model-agnostic** | 20 steps / 180 s; OpenAI / Anthropic / Gemini | Enterprise SaaS, priced on request, demo-only. |

---

## 4. Recommended next steps (agent-side, ordered by value / effort)

**Quick wins (small, high value)**
1. Treat `completed` as closed in `behind.py`, `critical_path.py`, `reschedule.py`, `integrity.py`, `evm.py` (N131; schema `TaskFlow`: done → completed).
2. Fix the "behind schedule" wording bug for on-track projects in `status.py`.
3. EVM: planned value to date → SPI; in-progress credit rule; EAC/ETC.
4. Delay root cause: walk the predecessor chain in `delay.py`.
5. Dedupe milestones before counting (N374, in review).
6. Reports: task titles instead of ids; add PM / controller / executive framings.

**Medium**
7. **Run-to-run diary** — the single feature that advances five modules (Progress, Change Control, Delay, EVM trend, Portfolio trend).
8. `portfolio_health` score + ranking + grouping.
9. Reassignment proposals using spare capacity.
10. Report delivery via `ProjectStatusReport` + scheduled weekly runs (≈ N&L continuous operator).

## 5. Platform asks (file as bugs / feature requests)

- `CalendarEvent.list` for the Projects seat, so overload works on live data (BUGS_FILED #1).
- Enable `trackable` on Task/Milestone and expose the change log to the Projects seat (or clarify what `trackable` means).
- Confirm the Projects seat may create `ProjectStatusReport` rows.
- Baseline dates on `Task`/`Milestone`; a readable change log.
- Multiple predecessors with lag and relationship type; optional 3-point duration — prerequisite for any QSRA.

---

### Sources
- [Nodes & Links home](https://nodeslinks.com/) · [For project managers](https://nodeslinks.com/project-managers/)
- [Tech.eu — Nodes & Links raises $12M (Feb 2025)](https://tech.eu/2025/02/18/nodes-links-raises-12m-to-streamline-construction-projects/)
- [DataDrivenAEC — Nodes & Links profile](https://datadrivenaec.com/tools/nodes-links)
- Internal: `agent/tools.py`, `docs/gap_report.md`, `docs/BUGS_FILED.md`, `docs/bugs_files.md`, harness offline run 2026-10-06 (17/17 approve)
