"""约束协同平台的核心对象与依赖图。"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from enum import Enum
from typing import Iterable


class ResourceKind(str, Enum):
    LAND = "用地"
    SEA = "用海"
    ENERGY = "用能"


class InfraKind(str, Enum):
    COMPUTE = "算力"
    NETWORK = "通信"
    DATA = "数据"


class RuleStatus(str, Enum):
    VALID = "有效"
    SUSPENDED = "裁决中"
    REPLACED = "已替代"


class ApprovalStatus(str, Enum):
    PENDING = "待确认"
    EFFECTIVE = "有效"
    INVALIDATED = "已失效"


@dataclass(frozen=True)
class Segment:
    segment_id: str
    name: str
    provinces: tuple[str, ...]


@dataclass(frozen=True)
class PlanVersion:
    version_id: str
    label: str
    effective: dt.date
    supersedes: str | None = None


@dataclass(frozen=True)
class CityNode:
    node_id: str
    name: str
    segment_id: str


@dataclass(frozen=True)
class IndustryNode:
    node_id: str
    name: str
    segment_id: str
    sector: str


@dataclass
class ResourceCondition:
    condition_id: str
    kind: ResourceKind
    segment_id: str
    plan_version: str
    cleared: bool = False
    needs_review: bool = False


@dataclass
class StandardRule:
    rule_id: str
    region: str
    category: str
    clause: str
    status: RuleStatus = RuleStatus.VALID


@dataclass
class InfraProvision:
    provision_id: str
    kind: InfraKind
    segment_id: str
    ready: bool = False


@dataclass
class RiskRequirement:
    requirement_id: str
    segment_id: str
    description: str
    mitigated: bool = False


@dataclass
class Approval:
    approval_id: str
    name: str
    segment_id: str
    required_commitments: tuple[str, ...] = ()
    required_conditions: tuple[str, ...] = ()
    required_rules: tuple[str, ...] = ()
    status: ApprovalStatus = ApprovalStatus.PENDING


@dataclass
class Milestone:
    milestone_id: str
    name: str
    planned: dt.date
    critical: bool
    required_approvals: tuple[str, ...] = ()
    at_risk: bool = False


@dataclass
class Blocker:
    blocker_id: str
    title: str
    segment_id: str
    affects_milestones: tuple[str, ...]
    delay_days: int
    resolved: bool = False


class DependencyGraph:
    """记录“谁依赖谁”，事件发生后沿反向边找出受影响对象。"""

    def __init__(self) -> None:
        self._requires: dict[str, set[str]] = {}

    def add(self, node: str, requires: Iterable[str] = ()) -> None:
        self._requires.setdefault(node, set()).update(requires)
        for dep in requires:
            self._requires.setdefault(dep, set())

    def requires(self, node: str) -> set[str]:
        return set(self._requires.get(node, ()))

    def replace_requires(self, node: str, requires: Iterable[str]) -> None:
        """整体重写一个节点的依赖（如裁决后审批改按占优规则执行）。"""
        self._requires[node] = set(requires)
        for dep in requires:
            self._requires.setdefault(dep, set())

    def affected_by(self, nodes: Iterable[str]) -> set[str]:
        """返回（传递）依赖于给定节点的全部对象，不含种子本身。"""
        reverse: dict[str, set[str]] = {}
        for node, deps in self._requires.items():
            for dep in deps:
                reverse.setdefault(dep, set()).add(node)
        seen: set[str] = set()
        stack = list(nodes)
        while stack:
            current = stack.pop()
            for nxt in reverse.get(current, ()):
                if nxt not in seen:
                    seen.add(nxt)
                    stack.append(nxt)
        return seen
