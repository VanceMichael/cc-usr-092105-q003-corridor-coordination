import datetime as dt
import json
import unittest
from pathlib import Path

from src.commitments import CommitmentStatus, Evidence, EvidenceKind
from src.events import (
    CountersignEvent,
    PlanAdjustmentEvent,
    VersionChangeEvent,
    WithdrawalEvent,
)
from src.model import ApprovalStatus, PlanVersion
from src.platform import platform_from_dict

FIXTURE = Path("fixtures/platform.json")
TODAY = dt.date(2026, 9, 26)


def load():
    return platform_from_dict(json.loads(FIXTURE.read_text(encoding="utf-8")))


def letter(eid="EV-X"):
    return Evidence(eid, EvidenceKind.OFFICIAL_LETTER, "正式函件", TODAY)


class PlatformEventTest(unittest.TestCase):
    def test_initial_state(self):
        p = load()
        self.assertIs(p.approvals["APR-1"].status, ApprovalStatus.EFFECTIVE)
        self.assertIs(p.approvals["APR-4"].status, ApprovalStatus.EFFECTIVE)
        self.assertIs(p.approvals["APR-2"].status, ApprovalStatus.PENDING)
        self.assertIs(p.approvals["APR-3"].status, ApprovalStatus.PENDING)
        self.assertTrue(p.milestones["MIL-1"].at_risk)
        self.assertFalse(p.milestones["MIL-3"].at_risk)

    def test_countersign_then_clear_condition(self):
        p = load()
        p.apply(CountersignEvent("COM-3", "生态环境厅", letter(), TODAY))
        self.assertIs(p.commitments["COM-3"].status, CommitmentStatus.RELEASED)
        # 用海条件尚未解除，审批仍待确认
        self.assertIs(p.approvals["APR-2"].status, ApprovalStatus.PENDING)
        report = p.clear_condition("CON-SEA-01")
        self.assertEqual(report.changed_approvals.get("APR-2"), ApprovalStatus.EFFECTIVE)
        self.assertNotIn("MIL-2", report.at_risk_milestones)

    def test_partial_countersign_keeps_verbal(self):
        p = load()
        self.assertIn("海事局", p.commitments["COM-3"].signatures)
        self.assertIs(p.commitments["COM-3"].status, CommitmentStatus.VERBAL)
        self.assertIs(p.approvals["APR-2"].status, ApprovalStatus.PENDING)

    def test_withdrawal_invalidates_approvals_and_marks_milestones(self):
        p = load()
        report = p.apply(WithdrawalEvent("COM-1", "用地指标调整", letter(), TODAY))
        self.assertEqual(report.changed_approvals["APR-1"], ApprovalStatus.INVALIDATED)
        self.assertEqual(report.changed_approvals["APR-4"], ApprovalStatus.INVALIDATED)
        self.assertIn("MIL-1", report.at_risk_milestones)
        self.assertIn("MIL-3", report.at_risk_milestones)

    def test_cross_year_adjustment_detects_insufficient_validity(self):
        p = load()
        report = p.apply(
            PlanAdjustmentEvent({"MIL-1": dt.date(2029, 6, 30)}, "总体计划跨年调整", TODAY)
        )
        # COM-1 期限到 2028-12-31，覆盖不了调整后的里程碑
        self.assertEqual(report.changed_approvals.get("APR-1"), ApprovalStatus.INVALIDATED)
        self.assertIn("COM-1", report.insufficient_commitments)

    def test_version_change_requires_reconfirmation(self):
        p = load()
        v2 = PlanVersion("PV-2", "2027版预可研方案", dt.date(2027, 1, 10), supersedes="PV-1")
        report = p.apply(VersionChangeEvent(v2, TODAY))
        self.assertIn("CON-LAND-01", report.review_conditions)
        self.assertIn("CON-SEA-01", report.review_conditions)
        self.assertEqual(report.changed_approvals.get("APR-1"), ApprovalStatus.INVALIDATED)
        # APR-4 不依赖资源条件，不受影响
        self.assertNotIn("APR-4", report.changed_approvals)
        restored = p.confirm_condition("CON-LAND-01", "PV-2")
        self.assertEqual(restored.changed_approvals.get("APR-1"), ApprovalStatus.EFFECTIVE)

    def test_resolve_blocker_updates_completion(self):
        p = load()
        before = p.overall_completion()
        p.resolve_blocker("BLK-1")
        self.assertEqual(p.milestone_forecast("MIL-2"), dt.date(2027, 3, 31))
        self.assertIsNotNone(before)


if __name__ == "__main__":
    unittest.main()
