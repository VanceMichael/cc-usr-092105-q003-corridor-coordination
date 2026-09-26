"""部门承诺的生命周期与证据规则。

承诺只能沿“口头赞同 → 正式放行 → 已撤回”流转。
视频发言与会议纪要可以存档，但永远不能作为正式放行的依据，
因此汇总数字只可能统计到凭正式函件或盖章文件放行的承诺。
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from enum import Enum


class EvidenceKind(str, Enum):
    OFFICIAL_LETTER = "正式函件"
    SEALED_DOCUMENT = "盖章文件"
    MEETING_MINUTES = "会议纪要"
    VIDEO_STATEMENT = "视频发言"


#: 只有这两类证据能把承诺转为正式放行
FORMAL_EVIDENCE = frozenset({EvidenceKind.OFFICIAL_LETTER, EvidenceKind.SEALED_DOCUMENT})


class CommitmentStatus(str, Enum):
    VERBAL = "口头赞同"
    RELEASED = "正式放行"
    WITHDRAWN = "已撤回"


@dataclass(frozen=True)
class Evidence:
    evidence_id: str
    kind: EvidenceKind
    title: str
    issued: dt.date
    attachment_id: str | None = None


@dataclass(frozen=True)
class Withdrawal:
    reason: str
    evidence: Evidence
    on: dt.date


@dataclass
class Commitment:
    """部门承诺：附带适用范围、期限与证据。"""

    commitment_id: str
    department: str
    scope: frozenset[str]
    not_before: dt.date
    not_after: dt.date
    required_signatories: frozenset[str] = frozenset()
    evidence: list[Evidence] = field(default_factory=list)
    signatures: dict[str, Evidence] = field(default_factory=dict)
    status: CommitmentStatus = CommitmentStatus.VERBAL
    released_on: dt.date | None = None
    withdrawal: Withdrawal | None = None

    def add_evidence(self, item: Evidence) -> None:
        """归档任意证据，包括视频发言；归档不改变承诺状态。"""
        self.evidence.append(item)

    def release(self, item: Evidence, on: dt.date) -> None:
        """责任部门单方正式放行，必须附正式证据。"""
        if self.status is CommitmentStatus.WITHDRAWN:
            raise ValueError("承诺已撤回，不能放行")
        if self.required_signatories:
            raise ValueError("该承诺需要多方会签，不能单方放行")
        if item.kind not in FORMAL_EVIDENCE:
            raise ValueError("视频发言或会议纪要不能作为正式放行依据")
        self.evidence.append(item)
        self.status = CommitmentStatus.RELEASED
        self.released_on = on

    def countersign(self, party: str, item: Evidence, on: dt.date) -> bool:
        """记录一方会签；全部会签方以正式证据签署后转为正式放行。"""
        if self.status is CommitmentStatus.WITHDRAWN:
            raise ValueError("承诺已撤回，不能会签")
        if item.kind not in FORMAL_EVIDENCE:
            raise ValueError("视频发言或会议纪要不能作为正式放行依据")
        if party not in self.required_signatories:
            raise ValueError(f"{party} 不在会签方清单内")
        self.signatures[party] = item
        self.evidence.append(item)
        if self.required_signatories <= set(self.signatures):
            self.status = CommitmentStatus.RELEASED
            self.released_on = on
            return True
        return False

    def withdraw(self, reason: str, item: Evidence, on: dt.date) -> None:
        """批准后撤回：必须说明理由并附正式证据，留痕备查。"""
        if item.kind not in FORMAL_EVIDENCE:
            raise ValueError("撤回必须附正式证据")
        self.status = CommitmentStatus.WITHDRAWN
        self.withdrawal = Withdrawal(reason, item, on)

    def has_formal_evidence(self) -> bool:
        return any(e.kind in FORMAL_EVIDENCE for e in self.evidence)

    def is_effective(self, on: dt.date) -> bool:
        return (
            self.status is CommitmentStatus.RELEASED
            and self.not_before <= on <= self.not_after
        )
