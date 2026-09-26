import unittest

from src.access import Actor, Attachment, Sensitivity, can_open, open_attachment


class AccessTest(unittest.TestCase):
    def setUp(self):
        self.sensitive = Attachment(
            "ATT-1", "海域生态敏感区分布图", Sensitivity.SENSITIVE, frozenset({"乙省"})
        )
        self.internal = Attachment("ATT-2", "协调会纪要", Sensitivity.INTERNAL)
        self.public = Attachment("ATT-3", "规划公示", Sensitivity.PUBLIC)

    def test_sensitive_only_for_authorized_region(self):
        authorized = Actor("工作人员甲", "乙省", Sensitivity.SENSITIVE)
        self.assertTrue(can_open(authorized, self.sensitive))
        outsider = Actor("工作人员乙", "甲省", Sensitivity.SENSITIVE)
        self.assertFalse(can_open(outsider, self.sensitive))
        with self.assertRaises(PermissionError):
            open_attachment(outsider, self.sensitive)

    def test_clearance_must_cover_sensitivity(self):
        low = Actor("工作人员丙", "乙省", Sensitivity.INTERNAL)
        self.assertFalse(can_open(low, self.sensitive))
        self.assertTrue(can_open(low, self.internal))
        anyone = Actor("公众", "丙省", Sensitivity.PUBLIC)
        self.assertTrue(can_open(anyone, self.public))
        self.assertFalse(can_open(anyone, self.internal))

    def test_open_returns_attachment_when_allowed(self):
        actor = Actor("工作人员甲", "乙省", Sensitivity.SENSITIVE)
        self.assertIs(open_attachment(actor, self.sensitive), self.sensitive)


if __name__ == "__main__":
    unittest.main()
