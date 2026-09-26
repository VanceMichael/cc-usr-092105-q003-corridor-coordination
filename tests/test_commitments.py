import datetime as dt
import unittest

from src.commitments import (
    Commitment,
    CommitmentStatus,
    Evidence,
    EvidenceKind,
)


def make(**overrides):
    base = dict(
        commitment_id="COM-T",
        department="测试厅",
        scope=frozenset({"CON-1"}),
        not_before=dt.date(2026, 1, 1),
        not_after=dt.date(2027, 12, 31),
    )
    base.update(overrides)
    return Commitment(**base)


def evidence(kind, eid="EV-1"):
    return Evidence(eid, kind, "材料", dt.date(2026, 6, 1))


class CommitmentTest(unittest.TestCase):
    def test_video_statement_never_releases(self):
        c = make()
        with self.assertRaises(ValueError):
            c.release(evidence(EvidenceKind.VIDEO_STATEMENT), dt.date(2026, 6, 2))
        self.assertIs(c.status, CommitmentStatus.VERBAL)

    def test_meeting_minutes_never_releases(self):
        c = make()
        with self.assertRaises(ValueError):
            c.release(evidence(EvidenceKind.MEETING_MINUTES), dt.date(2026, 6, 2))
        self.assertIs(c.status, CommitmentStatus.VERBAL)

    def test_single_department_release_and_validity(self):
        c = make()
        c.release(evidence(EvidenceKind.OFFICIAL_LETTER), dt.date(2026, 6, 2))
        self.assertIs(c.status, CommitmentStatus.RELEASED)
        self.assertTrue(c.is_effective(dt.date(2026, 9, 26)))
        self.assertFalse(c.is_effective(dt.date(2028, 1, 1)))
        self.assertFalse(c.is_effective(dt.date(2025, 12, 31)))

    def test_multi_party_countersign(self):
        c = make(required_signatories=frozenset({"甲厅", "乙厅"}))
        with self.assertRaises(ValueError):
            c.release(evidence(EvidenceKind.OFFICIAL_LETTER), dt.date(2026, 6, 2))
        done = c.countersign(
            "甲厅", evidence(EvidenceKind.SEALED_DOCUMENT, "EV-2"), dt.date(2026, 6, 3)
        )
        self.assertFalse(done)
        self.assertIs(c.status, CommitmentStatus.VERBAL)
        with self.assertRaises(ValueError):
            c.countersign(
                "丙厅", evidence(EvidenceKind.OFFICIAL_LETTER, "EV-3"), dt.date(2026, 6, 4)
            )
        with self.assertRaises(ValueError):
            c.countersign(
                "乙厅", evidence(EvidenceKind.VIDEO_STATEMENT, "EV-4"), dt.date(2026, 6, 4)
            )
        done = c.countersign(
            "乙厅", evidence(EvidenceKind.OFFICIAL_LETTER, "EV-5"), dt.date(2026, 6, 5)
        )
        self.assertTrue(done)
        self.assertIs(c.status, CommitmentStatus.RELEASED)
        self.assertEqual(c.released_on, dt.date(2026, 6, 5))

    def test_withdrawal_requires_formal_evidence(self):
        c = make()
        c.release(evidence(EvidenceKind.OFFICIAL_LETTER), dt.date(2026, 6, 2))
        with self.assertRaises(ValueError):
            c.withdraw("调整", evidence(EvidenceKind.VIDEO_STATEMENT, "EV-6"), dt.date(2026, 7, 1))
        c.withdraw("指标调整", evidence(EvidenceKind.OFFICIAL_LETTER, "EV-7"), dt.date(2026, 7, 1))
        self.assertIs(c.status, CommitmentStatus.WITHDRAWN)
        self.assertFalse(c.is_effective(dt.date(2026, 7, 2)))
        self.assertEqual(c.withdrawal.reason, "指标调整")

    def test_withdrawn_commitment_cannot_be_signed(self):
        c = make()
        c.release(evidence(EvidenceKind.OFFICIAL_LETTER), dt.date(2026, 6, 2))
        c.withdraw("调整", evidence(EvidenceKind.OFFICIAL_LETTER, "EV-8"), dt.date(2026, 7, 1))
        with self.assertRaises(ValueError):
            c.release(evidence(EvidenceKind.OFFICIAL_LETTER, "EV-9"), dt.date(2026, 7, 2))


if __name__ == "__main__":
    unittest.main()
