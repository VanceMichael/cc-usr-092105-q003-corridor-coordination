"""协调会三问：口头赞同、正式放行与工期堵点。

每次协调会结束，项目办公室用 meeting_report 回答三个问题：
哪项条件只是口头赞同，哪项已由责任部门正式放行，哪个堵点会改变整体工期。
汇总数字只统计承诺的正式状态，视频发言永远不会被误作正式放行。
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from .commitments import CommitmentStatus
from .platform import ConstraintPlatform


@dataclass(frozen=True)
class BlockerImpact:
    blocker_id: str
    title: str
    delay_days: int
    critical_milestones: tuple[str, ...]


@dataclass(frozen=True)
class MeetingReport:
    as_of: dt.date
    verbal_only: tuple[str, ...]
    formally_released: tuple[str, ...]
    schedule_blockers: tuple[BlockerImpact, ...]
    milestone_forecast: dict[str, dt.date]
    completion: dt.date | None
    counts: dict[str, int]


def meeting_report(platform: ConstraintPlatform, as_of: dt.date | None = None) -> MeetingReport:
    as_of = as_of or platform.today
    verbal_only: list[str] = []
    formally_released: list[str] = []
    withdrawn = 0
    for cid in sorted(platform.commitments):
        commitment = platform.commitments[cid]
        if commitment.status is CommitmentStatus.VERBAL:
            verbal_only.append(cid)
        elif commitment.status is CommitmentStatus.WITHDRAWN:
            withdrawn += 1
        elif commitment.is_effective(as_of) and commitment.has_formal_evidence():
            formally_released.append(cid)
    blockers: list[BlockerImpact] = []
    for bid in sorted(platform.blockers):
        blocker = platform.blockers[bid]
        if blocker.resolved:
            continue
        critical = tuple(
            mid
            for mid in blocker.affects_milestones
            if platform.milestones[mid].critical
        )
        if critical:
            blockers.append(
                BlockerImpact(blocker.blocker_id, blocker.title, blocker.delay_days, critical)
            )
    forecast = {
        mid: platform.milestone_forecast(mid) for mid in sorted(platform.milestones)
    }
    counts = {
        CommitmentStatus.VERBAL.value: len(verbal_only),
        CommitmentStatus.RELEASED.value: len(formally_released),
        CommitmentStatus.WITHDRAWN.value: withdrawn,
    }
    return MeetingReport(
        as_of=as_of,
        verbal_only=tuple(verbal_only),
        formally_released=tuple(formally_released),
        schedule_blockers=tuple(blockers),
        milestone_forecast=forecast,
        completion=platform.overall_completion(),
        counts=counts,
    )
