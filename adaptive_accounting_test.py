
import unittest

from adaptive_strategy_research import backtest


class TestAdaptiveAccounting(unittest.TestCase):

    def test_buy_and_hold_accounting(self):
        prices = [100.0, 110.0, 120.0, 130.0]
        signals = [1, 1, 1, 1]

        result = backtest(
            prices,
            signals,
            start_index=0,
        )

        self.assertAlmostEqual(
            result["final_equity"],
            result["cash"] + result["shares"] * prices[-1],
            places=6,
        )

        self.assertAlmostEqual(
            result["total_return"],
            result["final_equity"] / 10000.0 - 1,
            places=8,
        )

        self.assertEqual(result["trades"], 1)

    def test_round_trip_fees_are_counted(self):
        prices = [100.0, 100.0, 100.0, 100.0]
        signals = [1, 1, 0, 0]

        result = backtest(
            prices,
            signals,
            start_index=0,
        )

        self.assertEqual(result["trades"], 2)

        self.assertLess(result["final_equity"], 10000.0)

        expected = 10000.0 / (1 + 0.001) * (1 - 0.001)

        self.assertAlmostEqual(
            result["final_equity"],
            expected,
            places=6,
        )

    def test_equity_curve_length(self):
        prices = [100.0, 101.0, 102.0, 103.0, 104.0]
        signals = [1, 1, 0, 0, 1]

        result = backtest(
            prices,
            signals,
            start_index=1,
        )

        self.assertEqual(
            len(result["equity_curve"]),
            len(prices) - 1,
        )

    def test_returns_match_equity_curve(self):
        prices = [100.0, 110.0, 105.0, 120.0]
        signals = [1, 1, 1, 1]

        result = backtest(
            prices,
            signals,
            start_index=0,
        )

        curve = result["equity_curve"]
        returns = result["daily_returns"]

        for offset in range(1, len(curve)):
            index = offset

            expected_return = curve[offset] / curve[offset - 1] - 1

            self.assertAlmostEqual(
                returns[index],
                expected_return,
                places=8,
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)