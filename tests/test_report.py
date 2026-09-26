import datetime as dt
import json
import unittest
from pathlib import Path

from src.platform import platform_from_dict
from src.report import meeting_report


class MeetingReportTest(unittest.TestCase):
    def setUp(self):
        self.platform = platform_from_dict(
            json.loads(Path("fixtures/platform.json").read_text(encoding="utf-8"))
        )
        self.report = meeting_report(self.platform)

    def test_verbal_only_lists_unreleased_commitments(self):
        # 能源局只有视频发言，海事局会签未齐，都只是口头赞同
        self.assertIn("COM-2", self.report.verbal_only)
        self.assertIn("COM-3", self.report.verbal_only)

    def test_formally_released(self):
        self.assertEqual(self.report.formally_released, ("COM-1",))

    def test_video_statement_never_counted_as_release(self):
        # 汇总数字里，视频发言支撑的承诺不得计入正式放行
        self.assertEqual(self.report.counts["正式放行"], 1)
        self.assertEqual(self.report.counts["口头赞同"], 2)
        self.assertEqual(self.report.counts["已撤回"], 0)
        self.assertNotIn("COM-2", self.report.formally_released)

    def test_schedule_blockers_only_critical_chain(self):
        ids = [b.blocker_id for b in self.report.schedule_blockers]
        self.assertIn("BLK-1", ids)
        self.assertNotIn("BLK-2", ids)
        blocker = next(b for b in self.report.schedule_blockers if b.blocker_id == "BLK-1")
        self.assertEqual(blocker.critical_milestones, ("MIL-2",))

    def test_forecast_includes_blocker_delay(self):
        self.assertEqual(
            self.report.milestone_forecast["MIL-2"],
            dt.date(2027, 3, 31) + dt.timedelta(days=120),
        )
        self.assertEqual(self.report.completion, dt.date(2028, 12, 31))


if __name__ == "__main__":
    unittest.main()
