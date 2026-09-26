"""协同事件：会签、撤回、跨年计划调整与方案换版。"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from .commitments import Evidence
from .model import PlanVersion


@dataclass(frozen=True)
class CountersignEvent:
    """多方会签：一个会签方提交正式证据。"""

    commitment_id: str
    party: str
    evidence: Evidence
    on: dt.date


@dataclass(frozen=True)
class WithdrawalEvent:
    """条件批准后撤回：责任部门撤回已放行的承诺。"""

    commitment_id: str
    reason: str
    evidence: Evidence
    on: dt.date


@dataclass(frozen=True)
class PlanAdjustmentEvent:
    """跨年计划调整：更新里程碑日期，按新口径重算承诺期限是否仍然覆盖。"""

    new_dates: dict[str, dt.date]
    reason: str
    on: dt.date


@dataclass(frozen=True)
class VersionChangeEvent:
    """方案换版：新版生效后，旧版名下的资源条件需重新复核。"""

    version: PlanVersion
    on: dt.date


Event = CountersignEvent | WithdrawalEvent | PlanAdjustmentEvent | VersionChangeEvent
