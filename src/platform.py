"""约束协同平台：对象登记、事件应用与影响重算。

平台把通道区段、方案版本、沿线城市与产业节点、用地用海用能条件、
标准规则、算力通信配套、风险韧性要求、部门承诺、审批与里程碑
组织成一张依赖图；任何协同事件落地后，沿依赖图重新计算受影响的
审批和里程碑。
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Iterable

from .access import Attachment, Sensitivity
from .adjudication import Resolution, StandardConflict
from .commitments import Commitment, CommitmentStatus, Evidence, EvidenceKind
from .events import (
    CountersignEvent,
    Event,
    PlanAdjustmentEvent,
    VersionChangeEvent,
    WithdrawalEvent,
)
from .model import (
    Approval,
    ApprovalStatus,
    Blocker,
    CityNode,
    DependencyGraph,
    IndustryNode,
    InfraKind,
    InfraProvision,
    Milestone,
    PlanVersion,
    ResourceCondition,
    ResourceKind,
    RiskRequirement,
    RuleStatus,
    Segment,
    StandardRule,
)


@dataclass
class ImpactReport:
    """一次事件重算的结果。"""

    event: str
    changed_approvals: dict[str, ApprovalStatus] = field(default_factory=dict)
    at_risk_milestones: list[str] = field(default_factory=list)
    insufficient_commitments: list[str] = field(default_factory=list)
    review_conditions: list[str] = field(default_factory=list)
    completion: dt.date | None = None


class ConstraintPlatform:
    """约束协同平台门面：持有全部对象与依赖图。"""

    def __init__(self, today: dt.date) -> None:
        self.today = today
        self.segments: dict[str, Segment] = {}
        self.versions: dict[str, PlanVersion] = {}
        self.cities: dict[str, CityNode] = {}
        self.industries: dict[str, IndustryNode] = {}
        self.conditions: dict[str, ResourceCondition] = {}
        self.rules: dict[str, StandardRule] = {}
        self.provisions: dict[str, InfraProvision] = {}
        self.requirements: dict[str, RiskRequirement] = {}
        self.commitments: dict[str, Commitment] = {}
        self.approvals: dict[str, Approval] = {}
        self.milestones: dict[str, Milestone] = {}
        self.blockers: dict[str, Blocker] = {}
        self.attachments: dict[str, Attachment] = {}
        self.conflicts: dict[str, StandardConflict] = {}
        self.graph = DependencyGraph()

    # ---- 登记 ----

    def register_segment(self, segment: Segment) -> None:
        self.segments[segment.segment_id] = segment
        self.graph.add(segment.segment_id)

    def register_version(self, version: PlanVersion) -> None:
        self.versions[version.version_id] = version
        self.graph.add(version.version_id)

    def register_city(self, city: CityNode) -> None:
        self.cities[city.node_id] = city
        self.graph.add(city.node_id, [city.segment_id])

    def register_industry(self, industry: IndustryNode) -> None:
        self.industries[industry.node_id] = industry
        self.graph.add(industry.node_id, [industry.segment_id])

    def register_condition(self, condition: ResourceCondition) -> None:
        self.conditions[condition.condition_id] = condition
        self.graph.add(condition.condition_id, [condition.segment_id, condition.plan_version])

    def register_rule(self, rule: StandardRule) -> None:
        self.rules[rule.rule_id] = rule
        self.graph.add(rule.rule_id)

    def register_provision(self, provision: InfraProvision) -> None:
        self.provisions[provision.provision_id] = provision
        self.graph.add(provision.provision_id, [provision.segment_id])

    def register_requirement(self, requirement: RiskRequirement) -> None:
        self.requirements[requirement.requirement_id] = requirement
        self.graph.add(requirement.requirement_id, [requirement.segment_id])

    def register_commitment(self, commitment: Commitment) -> None:
        self.commitments[commitment.commitment_id] = commitment
        self.graph.add(commitment.commitment_id, sorted(commitment.scope))

    def register_approval(self, approval: Approval) -> None:
        self.approvals[approval.approval_id] = approval
        self.graph.add(
            approval.approval_id,
            [
                *approval.required_commitments,
                *approval.required_conditions,
                *approval.required_rules,
            ],
        )

    def register_milestone(self, milestone: Milestone) -> None:
        self.milestones[milestone.milestone_id] = milestone
        self.graph.add(milestone.milestone_id, milestone.required_approvals)

    def register_blocker(self, blocker: Blocker) -> None:
        self.blockers[blocker.blocker_id] = blocker
        self.graph.add(blocker.blocker_id, [blocker.segment_id])

    def register_attachment(self, attachment: Attachment) -> None:
        self.attachments[attachment.attachment_id] = attachment

    # ---- 重算 ----

    def _horizon(self, approval_id: str) -> dt.date:
        """审批须被承诺期限覆盖到的日期：依赖它的里程碑中最远的计划日。"""
        dates = [
            m.planned
            for m in self.milestones.values()
            if approval_id in m.required_approvals
        ]
        return max(dates, default=self.today)

    def _approval_ok(self, approval: Approval) -> bool:
        horizon = self._horizon(approval.approval_id)
        for cid in approval.required_commitments:
            commitment = self.commitments[cid]
            if not commitment.is_effective(self.today):
                return False
            if commitment.not_after < horizon:
                return False
        for condition_id in approval.required_conditions:
            condition = self.conditions[condition_id]
            if not condition.cleared or condition.needs_review:
                return False
        for rule_id in approval.required_rules:
            if self.rules[rule_id].status is not RuleStatus.VALID:
                return False
        return True

    def recompute(self, changed: Iterable[str], event: str) -> ImpactReport:
        """以 changed 为种子沿依赖图扩散，重算受影响的审批和里程碑。"""
        affected = set(changed) | self.graph.affected_by(changed)
        report = ImpactReport(event=event)
        for approval_id in sorted(affected):
            approval = self.approvals.get(approval_id)
            if approval is None:
                continue
            if self._approval_ok(approval):
                new_status = ApprovalStatus.EFFECTIVE
            elif approval.status is ApprovalStatus.EFFECTIVE:
                new_status = ApprovalStatus.INVALIDATED
            else:
                new_status = ApprovalStatus.PENDING
            if new_status is not approval.status:
                approval.status = new_status
                report.changed_approvals[approval_id] = new_status
        for milestone_id in sorted(self.milestones):
            milestone = self.milestones[milestone_id]
            milestone.at_risk = any(
                self.approvals[a].status is not ApprovalStatus.EFFECTIVE
                for a in milestone.required_approvals
            )
            if milestone.at_risk:
                report.at_risk_milestones.append(milestone_id)
        insufficient = set()
        for approval in self.approvals.values():
            horizon = self._horizon(approval.approval_id)
            for cid in approval.required_commitments:
                commitment = self.commitments[cid]
                if (
                    commitment.status is CommitmentStatus.RELEASED
                    and commitment.not_after < horizon
                ):
                    insufficient.add(cid)
        report.insufficient_commitments = sorted(insufficient)
        report.completion = self.overall_completion()
        return report

    # ---- 事件 ----

    def apply(self, event: Event) -> ImpactReport:
        if isinstance(event, CountersignEvent):
            commitment = self.commitments[event.commitment_id]
            commitment.countersign(event.party, event.evidence, event.on)
            return self.recompute([commitment.commitment_id], "多方会签")
        if isinstance(event, WithdrawalEvent):
            commitment = self.commitments[event.commitment_id]
            commitment.withdraw(event.reason, event.evidence, event.on)
            return self.recompute([commitment.commitment_id], "批准后撤回")
        if isinstance(event, PlanAdjustmentEvent):
            for milestone_id, new_date in event.new_dates.items():
                self.milestones[milestone_id].planned = new_date
            return self.recompute(list(self.approvals), "跨年计划调整")
        if isinstance(event, VersionChangeEvent):
            version = event.version
            self.register_version(version)
            review: list[str] = []
            if version.supersedes:
                for node in sorted(self.graph.affected_by([version.supersedes])):
                    condition = self.conditions.get(node)
                    if condition is not None and condition.plan_version == version.supersedes:
                        condition.needs_review = True
                        review.append(node)
            seeds = review or list(self.approvals)
            report = self.recompute(seeds, "方案换版")
            report.review_conditions = review
            return report
        raise TypeError(f"未知事件类型: {type(event)!r}")

    # ---- 日常动作 ----

    def clear_condition(self, condition_id: str) -> ImpactReport:
        condition = self.conditions[condition_id]
        condition.cleared = True
        return self.recompute([condition_id], "条件解除")

    def confirm_condition(self, condition_id: str, version_id: str) -> ImpactReport:
        """方案换版后，把条件复核确认到新版方案。"""
        if version_id not in self.versions:
            raise KeyError(f"未登记的方案版本: {version_id}")
        condition = self.conditions[condition_id]
        condition.plan_version = version_id
        condition.needs_review = False
        return self.recompute([condition_id], "条件复核")

    def resolve_blocker(self, blocker_id: str) -> ImpactReport:
        self.blockers[blocker_id].resolved = True
        return self.recompute(list(self.approvals), "堵点解除")

    # ---- 标准冲突裁决 ----

    def raise_conflict(
        self,
        conflict_id: str,
        category: str,
        rule_ids: Iterable[str],
        raised_by: str,
    ) -> ImpactReport:
        """相互冲突的标准进入专门裁决流程，裁决期间暂缓使用。"""
        if conflict_id in self.conflicts:
            raise ValueError(f"冲突已存在: {conflict_id}")
        rule_ids = tuple(rule_ids)
        self.conflicts[conflict_id] = StandardConflict(
            conflict_id, category, rule_ids, raised_by
        )
        for rule_id in rule_ids:
            self.rules[rule_id].status = RuleStatus.SUSPENDED
        return self.recompute(list(rule_ids), "标准冲突")

    def submit_argument(
        self, conflict_id: str, party: str, text: str, evidence: Evidence | None = None
    ) -> None:
        self.conflicts[conflict_id].submit_argument(party, text, evidence)

    def decide_conflict(
        self, conflict_id: str, role: str, resolution: Resolution
    ) -> ImpactReport:
        if role != "裁决委员会":
            raise PermissionError("只有裁决委员会可以作出裁决")
        conflict = self.conflicts[conflict_id]
        conflict.decide(resolution)
        for rule_id in conflict.rule_ids:
            self.rules[rule_id].status = RuleStatus.REPLACED
        if resolution.prevailing_rule is not None:
            self.rules[resolution.prevailing_rule].status = RuleStatus.VALID
            # 依赖被替代规则的审批改按占优规则执行
            replaced = set(conflict.rule_ids) - {resolution.prevailing_rule}
            for approval in self.approvals.values():
                if not replaced.intersection(approval.required_rules):
                    continue
                approval.required_rules = tuple(
                    dict.fromkeys(
                        resolution.prevailing_rule if r in replaced else r
                        for r in approval.required_rules
                    )
                )
                self.graph.replace_requires(
                    approval.approval_id,
                    [
                        *approval.required_commitments,
                        *approval.required_conditions,
                        *approval.required_rules,
                    ],
                )
        return self.recompute(list(conflict.rule_ids), "标准裁决")

    # ---- 工期 ----

    def milestone_forecast(self, milestone_id: str) -> dt.date:
        milestone = self.milestones[milestone_id]
        delay = sum(
            b.delay_days
            for b in self.blockers.values()
            if not b.resolved and milestone_id in b.affects_milestones
        )
        return milestone.planned + dt.timedelta(days=delay)

    def overall_completion(self) -> dt.date | None:
        critical = [m.milestone_id for m in self.milestones.values() if m.critical]
        if not critical:
            return None
        return max(self.milestone_forecast(mid) for mid in critical)


def _date(value: str) -> dt.date:
    return dt.date.fromisoformat(value)


def platform_from_dict(data: dict) -> ConstraintPlatform:
    """从字典（如 JSON 样例）装配平台并完成首次重算。"""

    def evidence(item: dict) -> Evidence:
        return Evidence(
            evidence_id=item["evidence_id"],
            kind=EvidenceKind(item["kind"]),
            title=item["title"],
            issued=_date(item["issued"]),
            attachment_id=item.get("attachment_id"),
        )

    platform = ConstraintPlatform(_date(data["today"]))
    for s in data.get("segments", ()):
        platform.register_segment(Segment(s["segment_id"], s["name"], tuple(s.get("provinces", ()))))
    for v in data.get("plan_versions", ()):
        platform.register_version(
            PlanVersion(v["version_id"], v["label"], _date(v["effective"]), v.get("supersedes"))
        )
    for c in data.get("cities", ()):
        platform.register_city(CityNode(c["node_id"], c["name"], c["segment_id"]))
    for i in data.get("industries", ()):
        platform.register_industry(
            IndustryNode(i["node_id"], i["name"], i["segment_id"], i["sector"])
        )
    for c in data.get("conditions", ()):
        platform.register_condition(
            ResourceCondition(
                c["condition_id"],
                ResourceKind(c["kind"]),
                c["segment_id"],
                c["plan_version"],
                c.get("cleared", False),
                c.get("needs_review", False),
            )
        )
    for r in data.get("rules", ()):
        platform.register_rule(
            StandardRule(
                r["rule_id"],
                r["region"],
                r["category"],
                r["clause"],
                RuleStatus(r.get("status", "有效")),
            )
        )
    for p in data.get("provisions", ()):
        platform.register_provision(
            InfraProvision(p["provision_id"], InfraKind(p["kind"]), p["segment_id"], p.get("ready", False))
        )
    for r in data.get("requirements", ()):
        platform.register_requirement(
            RiskRequirement(r["requirement_id"], r["segment_id"], r["description"], r.get("mitigated", False))
        )
    for c in data.get("commitments", ()):
        released_on = c.get("released_on")
        platform.register_commitment(
            Commitment(
                commitment_id=c["commitment_id"],
                department=c["department"],
                scope=frozenset(c.get("scope", ())),
                not_before=_date(c["not_before"]),
                not_after=_date(c["not_after"]),
                required_signatories=frozenset(c.get("required_signatories", ())),
                evidence=[evidence(e) for e in c.get("evidence", ())],
                signatures={k: evidence(v) for k, v in c.get("signatures", {}).items()},
                status=CommitmentStatus(c.get("status", "口头赞同")),
                released_on=_date(released_on) if released_on else None,
            )
        )
    for a in data.get("approvals", ()):
        platform.register_approval(
            Approval(
                a["approval_id"],
                a["name"],
                a["segment_id"],
                tuple(a.get("required_commitments", ())),
                tuple(a.get("required_conditions", ())),
                tuple(a.get("required_rules", ())),
                ApprovalStatus(a.get("status", "待确认")),
            )
        )
    for m in data.get("milestones", ()):
        platform.register_milestone(
            Milestone(
                m["milestone_id"],
                m["name"],
                _date(m["planned"]),
                m.get("critical", False),
                tuple(m.get("required_approvals", ())),
            )
        )
    for b in data.get("blockers", ()):
        platform.register_blocker(
            Blocker(
                b["blocker_id"],
                b["title"],
                b["segment_id"],
                tuple(b.get("affects_milestones", ())),
                b.get("delay_days", 0),
                b.get("resolved", False),
            )
        )
    for a in data.get("attachments", ()):
        platform.register_attachment(
            Attachment(
                a["attachment_id"],
                a["title"],
                Sensitivity(a.get("sensitivity", "内部")),
                frozenset(a.get("authorized_regions", ())),
            )
        )
    platform.recompute(list(platform.approvals), "初始登记")
    return platform
