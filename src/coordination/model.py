"""约束协同平台的核心对象。

围绕一次跨省通道前期统筹需要回答的三个问题组织数据：

- 哪项条件只是口头赞同
- 哪项条件已由责任部门正式放行
- 哪个堵点会改变整体工期

所有对象只描述公开的业务关系，不对应现实中的个人、企业或业务记录。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum


class NodeKind(str, Enum):
    """沿线城市与产业节点。"""

    CITY = "城市"
    INDUSTRY = "产业节点"


class ConditionCategory(str, Enum):
    """进入依赖图的条件类别。"""

    LAND = "用地"
    SEA = "用海"
    ENERGY = "用能"
    STANDARD = "标准规则"
    COMPUTE_COMM = "算力通信"
    RISK = "风险韧性"


class EvidenceKind(str, Enum):
    """承诺附带的证据类型。"""

    OFFICIAL_DOCUMENT = "正式文件"
    MEETING_MINUTES = "会议纪要"
    VIDEO_STATEMENT = "视频发言"
    EMAIL = "邮件往函"


# 只有正式文件可以支撑正式放行。
# 会议纪要、邮件只算过程性表态；视频发言永远不能被汇总数字误作正式放行。
FORMAL_EVIDENCE_KINDS = frozenset({EvidenceKind.OFFICIAL_DOCUMENT})


class CommitmentStatus(str, Enum):
    VERBAL = "口头赞同"
    FORMAL = "正式放行"
    WITHDRAWN = "已撤回"


class ConditionStatus(str, Enum):
    PENDING = "待协调"
    VERBAL_ONLY = "仅口头赞同"
    RELEASED = "已正式放行"
    IN_ADJUDICATION = "裁决中"
    STALE = "待重核"


class ApprovalStatus(str, Enum):
    PENDING = "待就绪"
    READY = "可报批"
    APPROVED = "已批准"
    STALE = "待复核"


class AdjudicationStatus(str, Enum):
    FILED = "已立案"
    RULED = "已裁决"


@dataclass
class CorridorNode:
    """沿线城市或产业节点，挂在通道区段上。"""

    id: str
    name: str
    kind: NodeKind
    segment_id: str
    region: str


@dataclass
class Evidence:
    """承诺或解除结论的证据来源。"""

    kind: EvidenceKind
    ref: str
    issued_on: date


@dataclass
class Commitment:
    """部门承诺：必须附带适用范围、期限与证据。"""

    id: str
    department: str
    region: str
    condition_id: str
    scope: str
    valid_until: date
    status: CommitmentStatus = CommitmentStatus.VERBAL
    evidence: list[Evidence] = field(default_factory=list)

    def formal_evidence(self) -> list[Evidence]:
        return [e for e in self.evidence if e.kind in FORMAL_EVIDENCE_KINDS]

    def is_effective_release(self, as_of: date) -> bool:
        """正式放行生效的充要条件。

        状态为正式放行、范围明确、期限未过且至少有一份正式文件证据。
        视频发言、会议纪要、邮件再多也不会让这里成立。
        """
        return (
            self.status is CommitmentStatus.FORMAL
            and bool(self.scope.strip())
            and self.valid_until >= as_of
            and bool(self.formal_evidence())
        )


@dataclass
class Condition:
    """一项需要跨区域协同的条件（用地/用海/用能/标准/算力通信/风险韧性）。"""

    id: str
    name: str
    category: ConditionCategory
    segment_id: str
    plan_version: str
    node_id: str | None = None
    required_signatories: frozenset[str] = frozenset()
    cosigned_by: set[str] = field(default_factory=set)
    stale: bool = False

    def cosign_complete(self) -> bool:
        """多方会签是否覆盖全部应签部门。"""
        return self.required_signatories <= self.cosigned_by


@dataclass
class Blocker:
    """项目堵点。解除结论必须保留证据来源。"""

    id: str
    condition_id: str
    description: str
    resolved: bool = False
    resolution_evidence_ref: str | None = None


@dataclass
class Milestone:
    """里程碑：可依赖其他里程碑，并要求若干条件先放行。"""

    id: str
    name: str
    segment_id: str
    duration_days: int
    planned_start: date
    depends_on: list[str] = field(default_factory=list)
    required_conditions: list[str] = field(default_factory=list)


@dataclass
class Approval:
    """审批事项：就绪与否由关联条件的状态推导。"""

    id: str
    name: str
    condition_ids: list[str]
    status: ApprovalStatus = ApprovalStatus.PENDING


@dataclass
class StandardConflict:
    """相互冲突的标准，进入专门裁决流程。"""

    id: str
    condition_id: str
    standard_a: str
    standard_b: str
    regions: tuple[str, ...]
    status: AdjudicationStatus = AdjudicationStatus.FILED
    ruling: str | None = None
    ruling_evidence_ref: str | None = None


@dataclass
class Attachment:
    """条件附件。敏感附件只向获授权地区开放。"""

    id: str
    condition_id: str
    title: str
    sensitive: bool = False
    allowed_regions: frozenset[str] = frozenset()

    def accessible_by(self, region: str) -> bool:
        return not self.sensitive or region in self.allowed_regions
