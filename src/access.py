"""敏感附件的分级与地区授权。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Sensitivity(str, Enum):
    PUBLIC = "公开"
    INTERNAL = "内部"
    SENSITIVE = "敏感"


_ORDER = {Sensitivity.PUBLIC: 0, Sensitivity.INTERNAL: 1, Sensitivity.SENSITIVE: 2}


@dataclass(frozen=True)
class Attachment:
    attachment_id: str
    title: str
    sensitivity: Sensitivity
    authorized_regions: frozenset[str] = frozenset()


@dataclass(frozen=True)
class Actor:
    name: str
    region: str
    clearance: Sensitivity = Sensitivity.INTERNAL


def can_open(actor: Actor, attachment: Attachment) -> bool:
    """密级须达标；敏感附件只向获授权地区开放。"""
    if _ORDER[actor.clearance] < _ORDER[attachment.sensitivity]:
        return False
    if attachment.sensitivity is Sensitivity.SENSITIVE:
        return actor.region in attachment.authorized_regions
    return True


def open_attachment(actor: Actor, attachment: Attachment) -> Attachment:
    if not can_open(actor, attachment):
        raise PermissionError(
            f"{actor.name}（{actor.region}）无权查阅附件 {attachment.attachment_id}"
        )
    return attachment
