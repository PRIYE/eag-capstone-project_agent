# Feature Specification: Project Agent (Seat 14)

**Feature Branch**: `001-project-agent`

**Created**: 2026-10-04

**Status**: Draft

**Input**: User description: "Build \"Project Agent\" for Seat 14 (apps: projects, agent,
crm) on the AgentSwitch platform. The seat's graded questions, per Objective.md, are:
Which projects are behind schedule? (predicate: project.behind_schedule) and Who is
overloaded next week? (predicate: project.overloaded_next_week). The agent must answer
both from live platform data via the shared MCP/REST API. Use Team 04's production agent
(AgentSwitch_team04-main) as the structural reference, not as code to copy. Required
capabilities, derived from gap_report.md against competitor Nodes & Links: schedule
integrity scan, behind-schedule detection, resource-overload detection,
critical-path-aware change control, EVM proxy, delay-cause narrative, role-specific
status reporting, and reschedule proposals."

## Clarifications

### Session 2026-10-04

- Q: What numeric threshold should trigger the effort-overrun flag (used both in the schedule-integrity scan and as a stated cause of "behind schedule")? → A: Logged hours > 150% of budgeted/estimated hours (a 50% overrun).
- Q: Should "capacity unknown" employees be excluded from the overloaded list while still being surfaced separately? → A: Excluded from the overloaded list; reported separately in the same finding.
- Q: What is the maximum execution time for a run answering a graded question before it counts as a timeout/failure? → A: 3 minutes per run.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Identify which projects are behind schedule (Priority: P1)

A Seat 14 operator asks the agent "which projects are behind schedule?" The agent
examines every project's tasks and milestones and returns a list of behind-schedule
projects, each with at least one dated reason it is behind (an overdue task, a missed
milestone, or a task blocked on a predecessor that is itself overdue or cancelled). A
missing assignee or an effort overrun (logged hours exceeding 150% of budget) is reported
alongside as a contributing risk factor, but neither one by itself puts a project on this
list — only a dated fact does.

**Why this priority**: This is one of the two questions this seat is directly graded on
(`project.behind_schedule`). Without a correct, state-backed answer here, the seat fails
its primary evaluation regardless of any other capability.

**Independent Test**: Run the agent against the live/sandboxed project data with no other
capability implemented. Confirm its answer, and a corresponding persisted finding, name
exactly the projects that are actually behind (verified independently by reading overdue
tasks/milestones from the database) and give a correct reason for each.

**Acceptance Scenarios**:

1. **Given** a project with a task past its due date and still not done, **When** the
   operator asks which projects are behind schedule, **Then** that project appears in the
   answer with "overdue task" (or equivalent) named as a cause, and that answer is also
   readable back from the database afterward.
2. **Given** a project where every task and milestone is on track, **When** the operator
   asks which projects are behind schedule, **Then** that project does NOT appear in the
   answer.
3. **Given** a project with a task blocked on a predecessor task that is itself overdue
   or cancelled, **When** the operator asks which projects are behind schedule, **Then**
   the answer names the blocking predecessor as the cause, not just "task is late."

---

### User Story 2 - Identify who is overloaded next week (Priority: P1)

A Seat 14 operator asks the agent "who is overloaded next week?" The agent compares each
employee's committed hours for each of the next 7 days against their declared capacity
for that same day and returns the names of overloaded employees with the amount of
overload (hours over capacity, and which days).

**Why this priority**: This is the second of the two directly graded questions
(`project.overloaded_next_week`). It is equal in grading weight to User Story 1 and must
be independently correct.

**Independent Test**: Run the agent against live/sandboxed resource-allocation and
capacity data with no other capability implemented. Confirm the named overloaded
employees match an independent manual sum of allocated hours vs. capacity for the next 7
days, and that a corresponding finding is persisted.

**Acceptance Scenarios**:

1. **Given** an employee whose allocated hours for a day next week exceed their declared
   capacity for that day, **When** the operator asks who is overloaded next week,
   **Then** that employee appears in the answer with the overload amount.
2. **Given** an employee whose allocated hours next week stay within capacity every day,
   **When** the operator asks who is overloaded next week, **Then** that employee does
   NOT appear in the answer.
3. **Given** an employee with no capacity profile on file, **When** the operator asks who
   is overloaded next week, **Then** the agent excludes them from the overloaded list but
   includes them in a separate "capacity unknown" note attached to the same finding.

---

### User Story 3 - Surface the specific blocker behind a late or at-risk project (Priority: P2)

Beyond just naming behind-schedule projects (User Story 1), the operator wants the
specific, actionable blocker: which task is stuck, why, and since when — so the next
action is obvious without manually digging through the project.

**Why this priority**: Directly strengthens the credibility and usefulness of the User
Story 1 answer; a project named "behind" with no actionable cause is of limited value.

**Independent Test**: For a project already identified as behind schedule, verify the
agent's stated blocker (missing assignee, missing due date, blocked predecessor,
overrun effort) matches what is actually true of that project's data when checked
directly.

**Acceptance Scenarios**:

1. **Given** a task with no assignee and no due date, **When** the integrity scan runs
   over that project, **Then** both issues are flagged individually, not merged into one
   vague "incomplete task" note.
2. **Given** a task whose logged hours exceed 150% of its budgeted/estimated hours (a
   50% overrun), **When** the integrity scan runs, **Then** the task is flagged as an
   effort overrun with the specific numbers (logged vs. budget).

---

### User Story 4 - Explain what actually drove a project's slip (Priority: P3)

For a project already known to be behind, the operator wants a short, readable narrative
explaining the sequence of events that caused the slip (e.g., "Task X missed its date on
[date], which delayed Milestone Y by N days"), suitable for sharing with a stakeholder.

**Why this priority**: Adds explanatory depth on top of User Stories 1 and 3, useful for
communication but not required to answer the graded predicate itself.

**Independent Test**: For a known behind-schedule project, confirm the narrative
references real task/milestone names, dates, and statuses from that project — no
fabricated details — and matches the causes already identified in User Story 3.

**Acceptance Scenarios**:

1. **Given** a project flagged as behind schedule with a known blocking task, **When**
   the operator requests a delay explanation, **Then** the narrative names the specific
   task, its status, and the date it became late.
2. **Given** a project with multiple contributing issues, **When** the operator requests
   a delay explanation, **Then** the narrative distinguishes the primary blocker from
   secondary contributing issues rather than listing them as equally responsible.

---

### User Story 5 - Check whether a proposed date change is safe before making it (Priority: P2)

Before the agent (or operator) changes a task's dates to resolve lateness or overload, it
must first check whether that change pushes out the project's overall finish date, so no
"fix" silently creates a new, bigger delay.

**Why this priority**: This is the safety gate in front of User Story 6 (reschedule
proposals); without it, the agent's own writes could make the behind-schedule answer
worse. Ranked above the explanatory/reporting stories because it protects data integrity.

**Independent Test**: Propose a date change on a task that is NOT on the critical path and
confirm the agent reports "no impact on finish date." Propose a date change on a task that
IS on the critical path and confirm the agent reports the exact number of days the finish
date would slip, without actually committing the change until explicitly approved.

**Acceptance Scenarios**:

1. **Given** a task not on the project's critical path, **When** a date change for that
   task is evaluated, **Then** the agent reports the project's finish date is unaffected.
2. **Given** a task on the project's critical path, **When** a date change for that task
   is evaluated, **Then** the agent reports the new finish date and the number of days of
   slip before any write is committed.

---

### User Story 6 - Propose and apply safe reschedules (Priority: P3)

Where the agent has write permission on a task (e.g., it is still a draft/unlocked
status), the agent proposes new dates or a new assignee to resolve a lateness or overload
finding, and applies the change only after confirmation and only if the record has not
changed since it was last read.

**Why this priority**: Turns the diagnosis (User Stories 1–5) into resolution, but is
only valuable once the diagnosis is trustworthy, so it is sequenced after the detection
and safety-check stories.

**Independent Test**: Propose a reschedule for an editable task; confirm it is written
only after approval and only if unchanged since being read. Propose a reschedule for a
locked/non-editable task; confirm the agent reports the limitation and escalates instead
of silently failing or fabricating a write.

**Acceptance Scenarios**:

1. **Given** an editable task causing an overload, **When** a reschedule is proposed and
   approved, **Then** the task's new date is written and a follow-up check confirms the
   change took effect.
2. **Given** the same task's underlying record changed after it was read but before the
   write was applied, **When** the write is attempted, **Then** the agent skips the write,
   reports the conflict, and does not overwrite the newer change.
3. **Given** a task the seat cannot write to (locked or outside seat permissions), **When**
   a reschedule is proposed, **Then** the agent states the limitation and raises an
   escalation to a real assignee rather than claiming the change was made.

---

### User Story 7 - Show project cost health alongside schedule health (Priority: P4)

The operator wants, per project, a comparison of planned cost, actual cost incurred so
far, and the value of work actually completed, so a project that looks "on schedule" but
is burning budget faster than it is delivering value is also visible.

**Why this priority**: Valuable complementary insight, but neither project is directly
graded on it and it depends on the same underlying data already surfaced by User Story 1.

**Independent Test**: For a sample project, independently compute planned cost vs. logged
cost vs. earned value from its budget, timesheet, and task-completion data, and confirm
the agent's reported figures match.

**Acceptance Scenarios**:

1. **Given** a project with logged time at a known rate, **When** the operator requests
   its cost health, **Then** the reported actual cost matches hours × rate from the
   underlying time records.
2. **Given** a project where completed-work value is below money already spent, **When**
   the operator requests its cost health, **Then** the agent flags the project as
   over-spending relative to progress.

---

### User Story 8 - Produce an audience-appropriate status update (Priority: P4)

The operator asks for a status update on a project tailored to a specific audience (e.g.,
"write this for my sponsor" vs. "write this for the project team"), based on the same
underlying facts already established.

**Why this priority**: Lowest priority — a presentation layer over findings already
produced by the higher-priority stories, valuable for communication but not required for
either graded predicate.

**Independent Test**: Request the same project's status for two different audiences and
confirm both versions state the same underlying facts (same blockers, same dates) while
differing only in tone/detail level appropriate to the audience.

**Acceptance Scenarios**:

1. **Given** a behind-schedule project, **When** a sponsor-facing status update is
   requested, **Then** the update is concise and outcome-focused without internal task
   IDs or jargon.
2. **Given** the same project, **When** a project-team-facing status update is requested,
   **Then** the update includes the specific blocking tasks and next actions.

---

### Edge Cases

- What happens when a project has no tasks or milestones at all? The agent must not
  report it as either "behind" or "on track" without basis — it should state there is
  insufficient data rather than guessing.
- What happens when an employee is allocated to tasks across multiple projects, each
  individually within capacity, but the combined total exceeds capacity? The overload
  check must sum across all of that employee's allocations, not per-project.
- How does the agent handle a project or task it can read but not write to (outside this
  seat's write permissions)? It must say so explicitly and escalate rather than silently
  skipping or claiming success.
- How does the agent handle data that changes between when it reads a record and when it
  tries to act on it (concurrent edits by other teams/humans)? It must re-check immediately
  before writing and abandon the write with a clear "changed underneath" report if the
  record moved.
- What happens when the request references a project, task, or employee that does not
  exist? The agent must say the record was not found rather than guessing or inventing
  data.
- What happens when the agent is asked about data outside this seat's permitted scope
  (e.g., payroll)? It must refuse clearly rather than attempting a workaround.
- What happens when two different reasons for lateness apply to the same project at once
  (e.g., missing assignee AND a blocked predecessor)? The agent must report both, not just
  the first one found.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The agent MUST produce a list of all projects that are behind schedule,
  each with at least one specific, **dated** cause (overdue task, missed milestone, or a
  task blocked on a predecessor that is itself overdue or cancelled). A missing assignee
  or an effort overrun MUST be reported as a contributing factor when present, but MUST
  NOT by itself be sufficient to place a project on this list.
- **FR-002**: The agent MUST produce a list of all employees overloaded for the next 7
  days, each with the amount of overload (hours and/or specific days).
- **FR-003**: The agent MUST persist both answers above as records readable back from the
  platform's database, not only as reply text, so correctness can be verified
  independently of the conversation.
- **FR-004**: The agent MUST scan tasks for integrity issues (no assignee, no due date,
  predecessor pointing at a cancelled/overdue task, logged effort exceeding 150% of
  budgeted/estimated effort — a 50% overrun) and attribute each flagged project's "behind
  schedule" cause to the specific issue(s) found.
- **FR-005**: The agent MUST compute next-week overload per employee by summing that
  employee's allocated hours across ALL projects for each of the next 7 days and
  comparing against that employee's declared daily capacity.
- **FR-006**: The agent MUST exclude employees with allocations but no capacity profile
  from the overloaded list itself, but MUST always include them in a separate "capacity
  unknown" note attached to the same finding.
- **FR-007**: Before proposing or applying any date change to a task, the agent MUST
  check the project's critical path before and after the proposed change and report
  whether, and by how many days, the project finish date would move.
- **FR-008**: The agent MUST NOT write a change to any record without first re-reading
  that record immediately beforehand; if the record has changed since it was last read,
  the agent MUST skip the write and report the conflict instead of overwriting.
- **FR-009**: The agent MUST only write date/assignee changes to tasks that this seat has
  write permission on; for tasks it cannot write to, it MUST state the limitation and
  raise an escalation to a real recipient instead of claiming the change was made.
- **FR-010**: The agent MUST compute, per project, planned cost, actual cost (from logged
  time and rate), and earned value (percent complete × budget), using only data already
  available on the project/task/timesheet records.
- **FR-011**: The agent MUST produce a plain-language narrative of what drove a given
  project's delay, grounded only in that project's actual task/milestone history (no
  fabricated events).
- **FR-012**: The agent MUST produce an audience-tailored status update for a project
  (e.g., sponsor vs. project-team framing) that states the same underlying facts
  regardless of audience.
- **FR-013**: The agent MUST refuse requests for data or actions outside Seat 14's
  permitted scope (e.g., payroll, manufacturing) with a clear statement of the boundary,
  rather than attempting a workaround.
- **FR-014**: The agent MUST operate within a bounded number of steps per run and MUST
  leave a recorded result (success, partial result, or escalation) in every run, even
  when it cannot fully answer the request. A run answering a graded question MUST finish
  within 3 minutes.
- **FR-015**: The agent MUST read company/currency/capability information at runtime
  rather than assuming a single fixed tenant configuration.

### Key Entities

- **Project**: A unit of work with a status, budget, and finish date; the subject of the
  "behind schedule" determination and of cost-health reporting.
- **Task**: A unit of work within a project, with status, due date, assignee, a single
  predecessor relationship, and budgeted vs. logged vs. billed effort; the primary source
  of integrity-scan findings and of schedule/cost evidence. An effort overrun is defined
  as logged hours exceeding 150% of budgeted/estimated hours (a 50% overrun).
- **Milestone**: A dated checkpoint within a project with a status (upcoming, reached,
  missed); contributes to behind-schedule and delay-narrative determinations.
- **Resource Allocation**: A time-bound assignment of an employee's effort to a task;
  summed per employee per day to detect overload.
- **Resource Capacity Profile**: An employee's declared available hours per day of the
  week; the comparison baseline for overload detection.
- **Timesheet Entry**: Logged hours (and implied cost via rate) against a task; the input
  to actual-cost and earned-value calculations.
- **Finding**: The agent's persisted conclusion for a given run (e.g., "Project X is
  behind schedule because Task Y is overdue"), stored so it can be read back and verified
  independently of the conversation that produced it.
- **Escalation**: A routed handover to a real person, raised when the agent cannot safely
  complete a write or resolve a situation itself.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For a representative sample of projects with known, independently-verified
  schedule status, the agent's behind-schedule list matches the independently verified
  list with no missed behind-schedule projects and no false positives.
- **SC-002**: For a representative sample of employees with known, independently-computed
  next-week allocation totals, the agent's overload list matches the independently
  computed list with no missed overloaded employees and no false positives.
- **SC-003**: 100% of runs that produce a behind-schedule or overload answer leave a
  corresponding record retrievable from the platform afterward.
- **SC-004**: 100% of attempted writes are preceded by a re-read of the target record
  within the same run, and 0% of writes proceed when that re-read shows the record
  changed underneath.
- **SC-005**: 100% of requests for out-of-seat data or actions are refused with an
  explicit boundary statement rather than attempted.
- **SC-006**: 100% of runs complete within the agent's step budget with a persisted
  outcome (answer, partial answer, or escalation) — zero runs end with nothing recorded.
- **SC-008**: Each run answering a graded question (behind-schedule or overloaded-next-week)
  completes, with its finding persisted, within 3 minutes; a run exceeding 3 minutes is
  treated as a timeout failure.
- **SC-007**: For every project reported as behind schedule, the stated cause can be
  manually confirmed by inspecting that project's tasks/milestones directly, in under 2
  minutes of manual lookup.

## Assumptions

- "Next week" for overload detection means the 7 calendar days following the day the
  agent runs; this is the default interpretation absent a different operator-specified
  window.
- Writes to task dates/assignees require that the task record is in an editable
  (e.g., draft/not-yet-locked) state as determined by the live permissions returned by
  the platform at run time; the agent does not maintain its own separate list of which
  states are editable.
- Baseline-vs-current "slip" tracking (true historical schedule drift) is approximated
  using the agent's own stored snapshots over time, since the platform does not currently
  provide baseline date fields; this approximation is a known limitation, not a defect to
  silently work around further.
- Full probabilistic/Monte-Carlo risk simulation across multi-predecessor networks is out
  of scope for this feature, since the underlying data model supports only a single
  predecessor per task; this is recorded as a platform gap, not solved by the agent.
- Cross-tenant/cross-company portfolio rollups are out of scope; all reporting is scoped
  to the operator's own company, matching this seat's data access.
- The agent runs on an operator's own machine with the operator's own model credentials;
  it is not assumed to run as an unattended background service for this feature.
- Where a write requires human approval before being committed, that approval is obtained
  through the agent's existing run-time confirmation mechanism (e.g., an interactive
  prompt); the exact mechanism is a planning/implementation detail, not a scope decision
  for this spec.
