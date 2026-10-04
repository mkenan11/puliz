import unittest
from datetime import date

from database.models import BudgetCycle
from services.chart_service import weekly_chart
from services.weekly_service import week_segments


class WeeklyTests(unittest.TestCase):
    def test_targets_cover_a_30_day_cycle(self) -> None:
        cycle = BudgetCycle(
            start_date=date(2026, 9, 1),
            end_date=date(2026, 9, 30),
            budget_amount_cents=16000,
        )
        segments = week_segments(cycle)
        self.assertEqual(
            [(segment.end_date - segment.start_date).days + 1 for segment in segments],
            [7, 7, 7, 7, 2],
        )
        self.assertEqual(
            sum(segment.target_cents for segment in segments), 16000
        )

    def test_chart_is_png(self) -> None:
        cycle = BudgetCycle(
            start_date=date(2026, 9, 1),
            end_date=date(2026, 9, 30),
            budget_amount_cents=16000,
        )
        image = weekly_chart(cycle, [])
        self.assertEqual(image.read(8), b"\x89PNG\r\n\x1a\n")
