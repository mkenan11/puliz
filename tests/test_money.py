import unittest

from utils.money import format_amount, parse_amount


class MoneyTests(unittest.TestCase):
    def test_parse_supported_amount_formats(self) -> None:
        self.assertEqual(parse_amount("10"), 1000)
        self.assertEqual(parse_amount("10.50"), 1050)
        self.assertEqual(parse_amount("10,50"), 1050)
        self.assertEqual(parse_amount("10 AZN"), 1000)

    def test_reject_invalid_amounts(self) -> None:
        self.assertIsNone(parse_amount("abc"))
        self.assertIsNone(parse_amount("-10"))

    def test_format_amount(self) -> None:
        self.assertEqual(format_amount(1050), "10.50")
