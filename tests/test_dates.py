import unittest
from datetime import date

from utils.dates import cycle_dates


class DateTests(unittest.TestCase):
    def test_cycle_handles_february_for_day_31(self) -> None:
        self.assertEqual(
            cycle_dates(31, date(2026, 2, 15)),
            (date(2026, 1, 31), date(2026, 2, 27)),
        )

    def test_leap_year(self) -> None:
        self.assertEqual(
            cycle_dates(31, date(2028, 2, 20)),
            (date(2028, 1, 31), date(2028, 2, 28)),
        )
