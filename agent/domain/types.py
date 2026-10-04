"""
Agent-side data structures (data-model.md section 2). Plain dataclasses,
all equality-comparable, all JSON-serializable via dataclasses.asdict.
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Snapshot:
    as_of: str  # ISO date, injected - never read from the clock in domain/
    projects: List[Dict[str, Any]] = field(default_factory=list)
    tasks: List[Dict[str, Any]] = field(default_factory=list)
    milestones: List[Dict[str, Any]] = field(default_factory=list)
    allocations: List[Dict[str, Any]] = field(default_factory=list)
    events: List[Dict[str, Any]] = field(default_factory=list)
    profiles: List[Dict[str, Any]] = field(default_factory=list)
    timesheets: List[Dict[str, Any]] = field(default_factory=list)
    truncated: Dict[str, bool] = field(default_factory=dict)
    company: Dict[str, Any] = field(default_factory=dict)

    def tasks_for(self, project_id: str) -> List[Dict[str, Any]]:
        return [t for t in self.tasks if t.get("project_id") == project_id]

    def milestones_for(self, project_id: str) -> List[Dict[str, Any]]:
        return [m for m in self.milestones if m.get("project_id") == project_id]

    def task_by_id(self, task_id: str) -> Optional[Dict[str, Any]]:
        for t in self.tasks:
            if t.get("id") == task_id:
                return t
        return None

    def any_truncated(self) -> bool:
        return any(self.truncated.values())


@dataclass
class Cause:
    kind: str  # overdue_task | missed_milestone | overdue_milestone |
               # blocked_by_predecessor | effort_overrun | no_assignee | no_due_date
    task_id: Optional[str] = None
    milestone_id: Optional[str] = None
    days_late: Optional[int] = None
    detail: Optional[str] = None

    DATED_KINDS = ("overdue_task", "missed_milestone", "overdue_milestone", "blocked_by_predecessor")

    def is_dated(self) -> bool:
        return self.kind in Cause.DATED_KINDS

    def to_dict(self) -> Dict[str, Any]:
        d = {"kind": self.kind}
        if self.task_id is not None:
            d["task_id"] = self.task_id
        if self.milestone_id is not None:
            d["milestone_id"] = self.milestone_id
        if self.days_late is not None:
            d["days_late"] = self.days_late
        if self.detail is not None:
            d["detail"] = self.detail
        return d


@dataclass
class IntegrityFlag:
    task_id: str
    project_id: str
    kind: str  # no_assignee | no_due_date | predecessor_cancelled |
               # predecessor_overdue | effort_overrun
    detail: Optional[str] = None


@dataclass
class BehindProject:
    project_id: str
    name: str
    causes: List[Cause] = field(default_factory=list)
    primary_cause: Optional[Cause] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "project_id": self.project_id,
            "primary_cause": self.primary_cause.to_dict() if self.primary_cause else None,
            "causes": [c.to_dict() for c in self.causes],
        }


@dataclass
class EmployeeLoad:
    employee_id: str
    days: List[Dict[str, Any]] = field(default_factory=list)  # {date, allocated_h, capacity_h, excess_h}
    week_excess_h: float = 0.0
    projects: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "employee_id": self.employee_id,
            "week_excess_h": round(self.week_excess_h, 2),
            "days": self.days,
            "projects": self.projects,
        }


@dataclass
class OverloadResult:
    window: List[str] = field(default_factory=list)
    overloaded: List[EmployeeLoad] = field(default_factory=list)
    capacity_unknown: List[str] = field(default_factory=list)
    within_capacity_count: int = 0


@dataclass
class Proposal:
    task_id: str
    field_changes: Dict[str, Any]
    snapshot_updated_at: Optional[str] = None
    snapshot_status: Optional[str] = None
    writable_by_seat: bool = True
    why_not_writable: Optional[str] = None
    predicted_finish_delta_days: Optional[int] = None
    on_critical_path: bool = False
    outcome: str = "proposed"  # proposed|approved|declined|applied|changed_underneath|write_rejected|refused|write_not_persisted


@dataclass
class CriticalPathDelta:
    project_id: str
    baseline_finish: Optional[str] = None
    predicted_finish: Optional[str] = None
    delta_days: int = 0
    task_on_path: bool = False
    platform_cp_before: Optional[Any] = None
    platform_cp_after: Optional[Any] = None


@dataclass
class EvmRow:
    project_id: str
    planned_cost: Optional[float] = None
    actual_cost: Optional[float] = None
    earned_value: Optional[float] = None
    cpi: Optional[float] = None
    status: str = "insufficient_data"  # over_spending | on_budget | insufficient_data


@dataclass
class DelayFacts:
    project_id: str
    primary_blocker: Optional[Dict[str, Any]] = None
    secondary: List[Dict[str, Any]] = field(default_factory=list)
    timeline: List[Dict[str, Any]] = field(default_factory=list)
