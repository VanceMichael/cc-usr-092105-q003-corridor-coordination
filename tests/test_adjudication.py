import datetime as dt
import json
import unittest
from pathlib import Path

from src.adjudication import ConflictStatus, Resolution
from src.commitments import Evidence, EvidenceKind
from src.model import ApprovalStatus, RuleStatus
from src.platform import platform_from_dict

TODAY = dt.date(2026, 9, 26)


def load():
    return platform_from_dict(json.loads(Path("fixtures/platform.json").read_text(encoding="utf-8")))


def resolution(evidence_kind=EvidenceKind.SEALED_DOCUMENT):
    return Resolution(
        decided_by="裁决委员会",
        decided_on=TODAY,
        prevailing_rule="RULE-JA-LOAD",
        harmonized_clause=None,
        evidence=Evidence("EV-R", evidence_kind, "裁决书", TODAY),
    )


class AdjudicationTest(unittest.TestCase):
    def setUp(self):
        self.platform = load()

    def raise_load_conflict(self):
        return self.platform.raise_conflict(
            "CONFLICT-LOAD", "桥梁荷载", ["RULE-JA-LOAD", "RULE-YI-LOAD"], "项目办公室"
        )

    def test_conflict_suspends_rules_and_blocks_approval(self):
        p = self.platform
        self.assertIs(p.approvals["APR-4"].status, ApprovalStatus.EFFECTIVE)
        report = self.raise_load_conflict()
        self.assertIs(p.rules["RULE-JA-LOAD"].status, RuleStatus.SUSPENDED)
        self.assertIs(p.rules["RULE-YI-LOAD"].status, RuleStatus.SUSPENDED)
        self.assertEqual(report.changed_approvals.get("APR-4"), ApprovalStatus.INVALIDATED)
        self.assertIn("MIL-3", report.at_risk_milestones)

    def test_full_flow_restores_prevailing_rule(self):
        p = self.platform
        self.raise_load_conflict()
        p.submit_argument("CONFLICT-LOAD", "甲省交通厅", "主张采用甲省荷载标准")
        p.submit_argument("CONFLICT-LOAD", "乙省交通厅", "主张采用乙省荷载标准")
        report = p.decide_conflict("CONFLICT-LOAD", "裁决委员会", resolution())
        conflict = p.conflicts["CONFLICT-LOAD"]
        self.assertIs(conflict.status, ConflictStatus.RESOLVED)
        self.assertIs(p.rules["RULE-JA-LOAD"].status, RuleStatus.VALID)
        self.assertIs(p.rules["RULE-YI-LOAD"].status, RuleStatus.REPLACED)
        # 审批改按占优规则执行
        self.assertEqual(p.approvals["APR-4"].required_rules, ("RULE-JA-LOAD",))
        self.assertEqual(report.changed_approvals.get("APR-4"), ApprovalStatus.EFFECTIVE)

    def test_decide_requires_evidence_phase(self):
        p = self.platform
        self.raise_load_conflict()
        with self.assertRaises(ValueError):
            p.decide_conflict("CONFLICT-LOAD", "裁决委员会", resolution())

    def test_decide_requires_committee_role(self):
        p = self.platform
        self.raise_load_conflict()
        p.submit_argument("CONFLICT-LOAD", "甲省交通厅", "主张采用甲省荷载标准")
        with self.assertRaises(PermissionError):
            p.decide_conflict("CONFLICT-LOAD", "项目办公室", resolution())

    def test_video_statement_cannot_decide(self):
        p = self.platform
        self.raise_load_conflict()
        p.submit_argument("CONFLICT-LOAD", "甲省交通厅", "主张采用甲省荷载标准")
        with self.assertRaises(ValueError):
            p.decide_conflict(
                "CONFLICT-LOAD", "裁决委员会", resolution(EvidenceKind.VIDEO_STATEMENT)
            )

    def test_prevailing_rule_must_be_party_to_conflict(self):
        p = self.platform
        self.raise_load_conflict()
        p.submit_argument("CONFLICT-LOAD", "甲省交通厅", "主张采用甲省荷载标准")
        bad = Resolution(
            decided_by="裁决委员会",
            decided_on=TODAY,
            prevailing_rule="RULE-EIA-01",
            harmonized_clause=None,
            evidence=Evidence("EV-R2", EvidenceKind.SEALED_DOCUMENT, "裁决书", TODAY),
        )
        with self.assertRaises(ValueError):
            p.decide_conflict("CONFLICT-LOAD", "裁决委员会", bad)


if __name__ == "__main__":
    unittest.main()
