"""约束协同引擎：依赖图、事件传播与协调会三问报告。

多方同时会签、条件批准后撤回、跨年计划调整或方案换版时，
recompute 会沿依赖图重新计算受影响的审批和里程碑。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from .model import (
    Approval,
    ApprovalStatus,
    Attachment,
    Blocker,
    Commitment,
    CommitmentStatus,
    Condition,
    ConditionStatus,
    CorridorNode,
    Evidence,
    FORMAL_EVIDENCE_KINDS,
    Milestone,
    StandardConflict,
    AdjudicationStatus,
)


@dataclass
class Impact:
    """一次重算波及的对象。"""

    condition_ids: list[str] = field(default_factory=list)
    approval_ids: list[str] = field(default_factory=list)
    milestone_ids: list[str] = field(default_factory=list)


@dataclass
class MeetingReport:
    """协调会结束时必须能回答的三个问题。"""

    as_of: date
    verbal_only: list[Condition]
    formally_released: list[Condition]
    schedule_blockers: list[Blocker]


class CoordinationPlatform:
    """跨区域大通道的约束协同平台。"""

    def __init__(self) -> None:
        self.nodes: dict[str, CorridorNode] = {}
        self.conditions: dict[str, Condition] = {}
        self.commitments: dict[str, Commitment] = {}
        self.blockers: dict[str, Blocker] = {}
        self.milestones: dict[str, Milestone] = {}
        self.approvals: dict[str, Approval] = {}
        self.conflicts: dict[str, StandardConflict] = {}
        self.attachments: dict[str, Attachment] = {}

    # ---- 登记 ----

    def register_node(self, node: CorridorNode) -> None:
        self.nodes[node.id] = node

    def register_condition(self, condition: Condition) -> None:
        self.conditions[condition.id] = condition

    def register_milestone(self, milestone: Milestone) -> None:
        self.milestones[milestone.id] = milestone

    def register_approval(self, approval: Approval) -> None:
        self.approvals[approval.id] = approval

    def register_attachment(self, attachment: Attachment) -> None:
        self.attachments[attachment.id] = attachment

    def register_blocker(self, blocker: Blocker) -> Impact:
        self.blockers[blocker.id] = blocker
        return Impact(condition_ids=[blocker.condition_id])

    # ---- 承诺与会签 ----

    def record_commitment(self, commitment: Commitment) -> Impact:
        """登记部门承诺。新承诺默认只是口头赞同。"""
        if commitment.condition_id not in self.conditions:
            raise ValueError(f"未知条件: {commitment.condition_id}")
        self.commitments[commitment.id] = commitment
        return self._impact_from_conditions({commitment.condition_id})

    def mark_formal_release(
        self,
        commitment_id: str,
        *,
        scope: str,
        valid_until: date,
        evidence: list[Evidence],
        as_of: date,
    ) -> Impact:
        """把承诺转为正式放行。

        必须附带适用范围、未过期的期限和至少一份正式文件证据；
        视频发言、会议纪要、邮件不能作为放行依据。
        """
        commitment = self.commitments[commitment_id]
        if not scope.strip():
            raise ValueError("正式放行必须附带适用范围")
        if valid_until < as_of:
            raise ValueError("正式放行的期限不得早于当前日期")
        if not any(e.kind in FORMAL_EVIDENCE_KINDS for e in evidence):
            raise ValueError("正式放行必须附正式文件证据，视频发言不能作为放行依据")
        commitment.scope = scope
        commitment.valid_until = valid_until
        commitment.evidence = list(evidence)
        commitment.status = CommitmentStatus.FORMAL
        return self._impact_from_conditions({commitment.condition_id})

    def withdraw_release(self, commitment_id: str) -> Impact:
        """条件批准后撤回：沿依赖图重算受影响的审批和里程碑。"""
        commitment = self.commitments[commitment_id]
        if commitment.status is not CommitmentStatus.FORMAL:
            raise ValueError("只有正式放行的承诺才能撤回")
        commitment.status = CommitmentStatus.WITHDRAWN
        return self._impact_from_conditions({commitment.condition_id})

    def cosign(self, condition_id: str, department: str) -> Impact:
        """多方会签。部门可任意顺序签署，覆盖应签部门即完成。"""
        condition = self.conditions[condition_id]
        if department not in condition.required_signatories:
            raise ValueError(f"{department} 不在 {condition_id} 的应签部门中")
        condition.cosigned_by.add(department)
        return self._impact_from_conditions({condition_id})

    # ---- 计划事件 ----

    def change_plan_version(self, segment_id: str, new_version: str) -> Impact:
        """方案换版：区段内绑定旧版的条件全部转为待重核。"""
        changed = set()
        for condition in self.conditions.values():
            if condition.segment_id == segment_id and condition.plan_version != new_version:
                condition.plan_version = new_version
                condition.stale = True
                changed.add(condition.id)
        return self._impact_from_conditions(changed)

    def reconfirm_condition(self, condition_id: str) -> Impact:
        """责任部门重新确认后解除待重核状态。"""
        self.conditions[condition_id].stale = False
        return self._impact_from_conditions({condition_id})

    def adjust_milestone_start(self, milestone_id: str, new_start: date) -> Impact:
        """跨年计划调整：沿里程碑依赖重算下游。"""
        self.milestones[milestone_id].planned_start = new_start
        downstream = self._downstream_milestones({milestone_id})
        downstream.discard(milestone_id)
        return Impact(milestone_ids=sorted(downstream))

    # ---- 标准裁决 ----

    def file_conflict(self, conflict: StandardConflict) -> Impact:
        """相互冲突的标准进入专门裁决流程，关联条件转为裁决中。"""
        if conflict.condition_id not in self.conditions:
            raise ValueError(f"未知条件: {conflict.condition_id}")
        self.conflicts[conflict.id] = conflict
        return self._impact_from_conditions({conflict.condition_id})

    def rule_conflict(self, conflict_id: str, *, ruling: str, evidence_ref: str) -> Impact:
        """作出裁决。每项解除结论必须保留证据来源。"""
        conflict = self.conflicts[conflict_id]
        if conflict.status is AdjudicationStatus.RULED:
            raise ValueError("该冲突已裁决")
        if not ruling.strip() or not evidence_ref.strip():
            raise ValueError("裁决结论和证据来源都不能为空")
        conflict.status = AdjudicationStatus.RULED
        conflict.ruling = ruling
        conflict.ruling_evidence_ref = evidence_ref
        return self._impact_from_conditions({conflict.condition_id})

    # ---- 堵点 ----

    def resolve_blocker(self, blocker_id: str, *, evidence_ref: str) -> Impact:
        """解除堵点。每项解除结论必须保留证据来源。"""
        blocker = self.blockers[blocker_id]
        if not evidence_ref.strip():
            raise ValueError("解除堵点必须保留证据来源")
        blocker.resolved = True
        blocker.resolution_evidence_ref = evidence_ref
        return self._impact_from_conditions({blocker.condition_id})

    # ---- 状态推导 ----

    def condition_status(self, condition_id: str, as_of: date) -> ConditionStatus:
        condition = self.conditions[condition_id]
        if any(
            c.condition_id == condition_id and c.status is AdjudicationStatus.FILED
            for c in self.conflicts.values()
        ):
            return ConditionStatus.IN_ADJUDICATION
        if condition.stale:
            return ConditionStatus.STALE
        related = [
            c
            for c in self.commitments.values()
            if c.condition_id == condition_id and c.status is not CommitmentStatus.WITHDRAWN
        ]
        if any(c.is_effective_release(as_of) for c in related):
            return ConditionStatus.RELEASED
        if any(c.status is CommitmentStatus.FORMAL for c in related):
            # 有正式放行记录但已失效（过期或证据不足），需要重核而不是当作放行
            return ConditionStatus.STALE
        if related:
            return ConditionStatus.VERBAL_ONLY
        return ConditionStatus.PENDING

    def approval_ready(self, approval: Approval, as_of: date) -> bool:
        return all(
            self.condition_status(cid, as_of) is ConditionStatus.RELEASED
            and self.conditions[cid].cosign_complete()
            for cid in approval.condition_ids
        )

    # ---- 依赖图与重算 ----

    def _downstream_milestones(self, milestone_ids: set[str]) -> set[str]:
        seen = set(milestone_ids)
        queue = list(milestone_ids)
        while queue:
            current = queue.pop()
            for milestone in self.milestones.values():
                if current in milestone.depends_on and milestone.id not in seen:
                    seen.add(milestone.id)
                    queue.append(milestone.id)
        return seen

    def _impact_from_conditions(self, condition_ids: set[str]) -> Impact:
        """从变化的条件出发，沿依赖图找出受影响的审批和里程碑。"""
        if not condition_ids:
            return Impact()
        gated = {
            m.id for m in self.milestones.values() if condition_ids & set(m.required_conditions)
        }
        milestones = self._downstream_milestones(gated)
        approvals = {
            a.id for a in self.approvals.values() if condition_ids & set(a.condition_ids)
        }
        return Impact(
            condition_ids=sorted(condition_ids),
            approval_ids=sorted(approvals),
            milestone_ids=sorted(milestones),
        )

    def recompute(self, as_of: date) -> Impact:
        """全量重算：刷新所有审批状态，返回状态发生变化的审批。"""
        changed = []
        for approval in self.approvals.values():
            before = approval.status
            if approval.status is ApprovalStatus.APPROVED:
                if not self.approval_ready(approval, as_of):
                    # 批准后条件被打破（撤回、换版、过期），必须复核
                    approval.status = ApprovalStatus.STALE
            else:
                approval.status = (
                    ApprovalStatus.READY
                    if self.approval_ready(approval, as_of)
                    else ApprovalStatus.PENDING
                )
            if approval.status is not before:
                changed.append(approval.id)
        return Impact(approval_ids=sorted(changed))

    # ---- 工期与关键路径 ----

    def schedule(self) -> dict[str, tuple[date, date]]:
        """每个里程碑的（最早开始， 最早完成）。"""
        starts: dict[str, date] = {}
        finishes: dict[str, date] = {}
        for milestone in self._topological_milestones():
            start = milestone.planned_start
            for dep in milestone.depends_on:
                start = max(start, finishes[dep])
            starts[milestone.id] = start
            finishes[milestone.id] = start + timedelta(days=milestone.duration_days)
        return {mid: (starts[mid], finishes[mid]) for mid in starts}

    def critical_milestones(self) -> set[str]:
        """总时差为零的里程碑；其上的堵点会改变整体工期。"""
        sched = self.schedule()
        if not sched:
            return set()
        project_finish = max(finish for _, finish in sched.values())
        successors: dict[str, list[str]] = {mid: [] for mid in sched}
        for milestone in self.milestones.values():
            for dep in milestone.depends_on:
                successors[dep].append(milestone.id)
        latest_finish = {mid: project_finish for mid in sched}
        for milestone in reversed(self._topological_milestones()):
            for succ in successors[milestone.id]:
                latest_start_succ = latest_finish[succ] - timedelta(
                    days=self.milestones[succ].duration_days
                )
                latest_finish[milestone.id] = min(
                    latest_finish[milestone.id], latest_start_succ
                )
        critical = set()
        for mid, (start, _) in sched.items():
            latest_start = latest_finish[mid] - timedelta(
                days=self.milestones[mid].duration_days
            )
            if latest_start <= start:
                critical.add(mid)
        return critical

    def _topological_milestones(self) -> list[Milestone]:
        ordered: list[Milestone] = []
        seen: set[str] = set()

        def visit(mid: str) -> None:
            if mid in seen:
                return
            seen.add(mid)
            for dep in self.milestones[mid].depends_on:
                visit(dep)
            ordered.append(self.milestones[mid])

        for mid in sorted(self.milestones):
            visit(mid)
        return ordered

    # ---- 协调会三问 ----

    def meeting_report(self, as_of: date) -> MeetingReport:
        verbal_only: list[Condition] = []
        formally_released: list[Condition] = []
        for condition in self.conditions.values():
            status = self.condition_status(condition.id, as_of)
            if status is ConditionStatus.VERBAL_ONLY:
                verbal_only.append(condition)
            elif status is ConditionStatus.RELEASED:
                formally_released.append(condition)
        critical = self.critical_milestones()
        gating_conditions = {
            cid
            for mid in critical
            for cid in self.milestones[mid].required_conditions
        }
        schedule_blockers = [
            b
            for b in self.blockers.values()
            if not b.resolved and b.condition_id in gating_conditions
        ]
        return MeetingReport(
            as_of=as_of,
            verbal_only=sorted(verbal_only, key=lambda c: c.id),
            formally_released=sorted(formally_released, key=lambda c: c.id),
            schedule_blockers=sorted(schedule_blockers, key=lambda b: b.id),
        )
