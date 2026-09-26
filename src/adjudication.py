"""标准规则冲突的专门裁决流程。

相互冲突的标准先进入“已提出 → 举证中 → 已裁决”的流程，
裁决期间涉事规则暂缓使用；裁决结论必须附正式证据，
给出占优规则或统一条款，且只能由裁决委员会作出。
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from enum import Enum

from .commitments import FORMAL_EVIDENCE, Evidence


class ConflictStatus(str, Enum):
    RAISED = "已提出"
    EVIDENCE = "举证中"
    RESOLVED = "已裁决"


@dataclass(frozen=True)
class Argument:
    party: str
    text: str
    evidence: Evidence | None = None


@dataclass(frozen=True)
class Resolution:
    decided_by: str
    decided_on: dt.date
    prevailing_rule: str | None
    harmonized_clause: str | None
    evidence: Evidence


@dataclass
class StandardConflict:
    conflict_id: str
    category: str
    rule_ids: tuple[str, ...]
    raised_by: str
    status: ConflictStatus = ConflictStatus.RAISED
    arguments: list[Argument] = field(default_factory=list)
    resolution: Resolution | None = None

    def submit_argument(self, party: str, text: str, evidence: Evidence | None = None) -> None:
        if self.status is ConflictStatus.RESOLVED:
            raise ValueError("冲突已裁决，不能再举证")
        self.arguments.append(Argument(party, text, evidence))
        self.status = ConflictStatus.EVIDENCE

    def decide(self, resolution: Resolution) -> None:
        if self.status is not ConflictStatus.EVIDENCE:
            raise ValueError("须先完成举证再裁决")
        if resolution.evidence.kind not in FORMAL_EVIDENCE:
            raise ValueError("裁决结论必须附正式证据")
        if resolution.prevailing_rule is None and resolution.harmonized_clause is None:
            raise ValueError("裁决须给出占优规则或统一条款")
        if resolution.prevailing_rule is not None and resolution.prevailing_rule not in self.rule_ids:
            raise ValueError("占优规则必须是冲突规则之一")
        self.resolution = resolution
        self.status = ConflictStatus.RESOLVED
