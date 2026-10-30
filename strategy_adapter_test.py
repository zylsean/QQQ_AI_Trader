

import unittest

from strategy_adapter import generate_trend_50_200_targets


class StrategyAdapterTest(unittest.TestCase):

    def test_output_length_matches_prices(self):
        prices = [100.0] * 250
        targets = generate_trend_50_200_targets(prices)
        self.assertEqual(len(targets), len(prices))

    def test_insufficient_history_returns_none(self):
        targets = generate_trend_50_200_targets([100.0] * 199)
        self.assertTrue(all(value is None for value in targets))

    def test_flat_prices_remain_flat(self):
        targets = generate_trend_50_200_targets([100.0] * 250)
        self.assertTrue(all(value is None for value in targets))

    def test_rising_prices_eventually_enter(self):
        prices = [100.0] * 200 + [
            100.0 + i for i in range(1, 100)
        ]
        targets = generate_trend_50_200_targets(prices)
        self.assertIn(1, targets)

    def test_invalid_prices_rejected(self):
        with self.assertRaises(ValueError):
            generate_trend_50_200_targets([100.0, -1.0, 102.0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
