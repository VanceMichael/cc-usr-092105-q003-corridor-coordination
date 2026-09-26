import unittest
from datetime import date

from src.coordination import (
    ApprovalStatus,
    Commitment,
    CommitmentStatus,
    ConditionStatus,
    Evidence,
    EvidenceKind,
)
from src.coordination.demo import AS_OF, build_demo_platform


def formal_doc(ref="某厅函〔2026〕1号"):
    return [Evidence(EvidenceKind.OFFICIAL_DOCUMENT, ref, date(2026, 9, 1))]


class MeetingReportTest(unittest.TestCase):
    """协调会结束时必须能回答的三个问题。"""

    def setUp(self):
        self.platform = build_demo_platform()
        self.report = self.platform.meeting_report(AS_OF)

    def test_verbal_only_lists_conditions_without_formal_release(self):
        ids = [c.id for c in self.report.verbal_only]
        self.assertEqual(ids, ["C-ENG-01"])

    def test_formally_released_lists_only_effective_releases(self):
        ids = [c.id for c in self.report.formally_released]
        self.assertEqual(ids, ["C-LAND-01"])

    def test_schedule_blockers_are_unresolved_and_on_critical_path(self):
        ids = [b.id for b in self.report.schedule_blockers]
        self.assertEqual(ids, ["B-01"])

    def test_critical_path(self):
        self.assertEqual(self.platform.critical_milestones(), {"M1", "M2", "M3"})


class FormalReleaseTest(unittest.TestCase):
    """视频发言永远不能被汇总数字误作正式放行。"""

    def setUp(self):
        self.platform = build_demo_platform()

    def test_video_statement_cannot_support_formal_release(self):
        self.platform.record_commitment(Commitment(
            "CM-SEA-1", "东省自然资源厅", "东省", "C-SEA-01",
            scope="桥位用海", valid_until=date(2027, 12, 31),
        ))
        with self.assertRaises(ValueError):
            self.platform.mark_formal_release(
                "CM-SEA-1",
                scope="桥位用海",
                valid_until=date(2027, 12, 31),
                evidence=[Evidence(EvidenceKind.VIDEO_STATEMENT, "协调会视频第5段", date(2026, 9, 25))],
                as_of=AS_OF,
            )

    def test_video_only_formal_record_is_never_counted_as_released(self):
        # 即使数据里被误标为正式放行，只有视频发言也不得计入
        self.platform.record_commitment(Commitment(
            "CM-SEA-2", "东省自然资源厅", "东省", "C-SEA-01",
            scope="桥位用海", valid_until=date(2027, 12, 31),
            status=CommitmentStatus.FORMAL,
            evidence=[Evidence(EvidenceKind.VIDEO_STATEMENT, "协调会视频第5段", date(2026, 9, 25))],
        ))
        status = self.platform.condition_status("C-SEA-01", AS_OF)
        self.assertIsNot(status, ConditionStatus.RELEASED)
        report = self.platform.meeting_report(AS_OF)
        self.assertNotIn("C-SEA-01", [c.id for c in report.formally_released])

    def test_release_requires_scope_and_future_deadline(self):
        self.platform.record_commitment(Commitment(
            "CM-SEA-3", "东省自然资源厅", "东省", "C-SEA-01",
            scope="桥位用海", valid_until=date(2027, 12, 31),
        ))
        with self.assertRaises(ValueError):
            self.platform.mark_formal_release(
                "CM-SEA-3", scope="  ", valid_until=date(2027, 12, 31),
                evidence=formal_doc(), as_of=AS_OF,
            )
        with self.assertRaises(ValueError):
            self.platform.mark_formal_release(
                "CM-SEA-3", scope="桥位用海", valid_until=date(2026, 1, 1),
                evidence=formal_doc(), as_of=AS_OF,
            )

    def test_expired_release_needs_recheck(self):
        self.assertIs(
            self.platform.condition_status("C-CC-01", AS_OF), ConditionStatus.STALE
        )


class RecomputeTest(unittest.TestCase):
    """会签、撤回、跨年调整、换版都会触发受影响对象的重算。"""

    def setUp(self):
        self.platform = build_demo_platform()

    def _release(self, cid, cmid, dept, scope):
        self.platform.record_commitment(Commitment(
            cmid, dept, "东省", cid, scope=scope, valid_until=date(2027, 12, 31),
        ))
        self.platform.mark_formal_release(
            cmid, scope=scope, valid_until=date(2027, 12, 31),
            evidence=formal_doc(), as_of=AS_OF,
        )

    def test_cosign_completion_makes_approval_ready(self):
        self._release("C-ENG-01", "CM-ENG-9", "东省能源局", "算力园用能")
        self._release("C-SEA-01", "CM-SEA-9", "东省自然资源厅", "桥位用海")
        self.platform.cosign("C-LAND-01", "西省自然资源厅")
        impact = self.platform.recompute(AS_OF)
        self.assertEqual(self.platform.approvals["AP-01"].status, ApprovalStatus.READY)
        self.assertIn("AP-01", impact.approval_ids)

    def test_cosign_rejects_unexpected_department(self):
        with self.assertRaises(ValueError):
            self.platform.cosign("C-LAND-01", "某无关企业")

    def test_withdrawal_stales_approved_approval(self):
        self.test_cosign_completion_makes_approval_ready()
        self.platform.approvals["AP-01"].status = ApprovalStatus.APPROVED
        impact = self.platform.withdraw_release("CM-LAND-1")
        self.assertIn("AP-01", impact.approval_ids)
        self.assertIn("M1", impact.milestone_ids)
        self.platform.recompute(AS_OF)
        self.assertEqual(self.platform.approvals["AP-01"].status, ApprovalStatus.STALE)
        self.assertIs(
            self.platform.condition_status("C-LAND-01", AS_OF),
            ConditionStatus.PENDING,
        )

    def test_only_formal_release_can_be_withdrawn(self):
        with self.assertRaises(ValueError):
            self.platform.withdraw_release("CM-ENG-1")

    def test_plan_version_change_stales_conditions_and_recomputes(self):
        impact = self.platform.change_plan_version("SEG-跨江", "PV-2026B")
        self.assertIn("C-LAND-01", impact.condition_ids)
        self.assertIn("AP-01", impact.approval_ids)
        self.assertIn("M1", impact.milestone_ids)
        self.assertIs(
            self.platform.condition_status("C-LAND-01", AS_OF), ConditionStatus.STALE
        )
        self.platform.reconfirm_condition("C-LAND-01")
        self.assertIs(
            self.platform.condition_status("C-LAND-01", AS_OF), ConditionStatus.RELEASED
        )

    def test_cross_year_adjustment_propagates_downstream(self):
        impact = self.platform.adjust_milestone_start("M1", date(2027, 1, 5))
        self.assertEqual(impact.milestone_ids, ["M2", "M3"])
        schedule = self.platform.schedule()
        self.assertEqual(schedule["M2"][0], date(2027, 3, 6))


class AdjudicationTest(unittest.TestCase):
    """相互冲突的标准进入专门裁决流程。"""

    def setUp(self):
        self.platform = build_demo_platform()

    def test_filed_conflict_blocks_condition(self):
        self.assertIs(
            self.platform.condition_status("C-STD-01", AS_OF),
            ConditionStatus.IN_ADJUDICATION,
        )

    def test_ruling_requires_conclusion_and_evidence(self):
        with self.assertRaises(ValueError):
            self.platform.rule_conflict("ADJ-01", ruling="", evidence_ref="裁字1号")
        with self.assertRaises(ValueError):
            self.platform.rule_conflict("ADJ-01", ruling="采用公-Ⅰ级", evidence_ref=" ")

    def test_ruling_unblocks_condition_and_keeps_evidence(self):
        impact = self.platform.rule_conflict(
            "ADJ-01", ruling="全线统一采用公-Ⅰ级", evidence_ref="联裁字〔2026〕2号",
        )
        self.assertIn("C-STD-01", impact.condition_ids)
        conflict = self.platform.conflicts["ADJ-01"]
        self.assertEqual(conflict.ruling_evidence_ref, "联裁字〔2026〕2号")
        self.assertIs(
            self.platform.condition_status("C-STD-01", AS_OF), ConditionStatus.PENDING
        )
        with self.assertRaises(ValueError):
            self.platform.rule_conflict("ADJ-01", ruling="重复裁决", evidence_ref="x")


class BlockerTest(unittest.TestCase):
    def setUp(self):
        self.platform = build_demo_platform()

    def test_resolution_must_keep_evidence(self):
        with self.assertRaises(ValueError):
            self.platform.resolve_blocker("B-01", evidence_ref="")

    def test_resolved_blocker_leaves_schedule_report(self):
        self.platform.resolve_blocker("B-01", evidence_ref="东能源函〔2026〕18号")
        report = self.platform.meeting_report(AS_OF)
        self.assertEqual(report.schedule_blockers, [])
        self.assertEqual(
            self.platform.blockers["B-01"].resolution_evidence_ref, "东能源函〔2026〕18号"
        )


class AttachmentTest(unittest.TestCase):
    """敏感附件只向获授权地区开放。"""

    def setUp(self):
        self.platform = build_demo_platform()

    def test_sensitive_attachment_restricted_to_authorized_regions(self):
        sensitive = self.platform.attachments["AT-01"]
        self.assertTrue(sensitive.accessible_by("东省"))
        self.assertFalse(sensitive.accessible_by("西省"))

    def test_public_attachment_open_to_all_regions(self):
        public = self.platform.attachments["AT-02"]
        self.assertTrue(public.accessible_by("东省"))
        self.assertTrue(public.accessible_by("西省"))


if __name__ == "__main__":
    unittest.main()
