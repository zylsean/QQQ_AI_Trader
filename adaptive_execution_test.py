

import unittest

from adaptive_strategy_research import backtest, FEE_RATE, INITIAL_CASH


class TestAdaptiveExecution(unittest.TestCase):

    def test_signal_executes_on_next_day_close(self):
        prices = [100.0, 100.0, 100.0]
        signals = [0, 1, 1]

        result = backtest(prices, signals, start_index=0)

        # 第 1 日信号为 1，应在第 2 日收盘买入
        self.assertEqual(result["trades"], 1)
        self.assertEqual(result["position"], 1)
        self.assertGreater(result["shares"], 0)

        expected_shares = INITIAL_CASH / (
            prices[2] * (1 + FEE_RATE)
        )

        self.assertAlmostEqual(
            result["shares"],
            expected_shares,
            places=8,
        )

    def test_price_gain_is_realized_after_buy(self):
        prices = [100.0, 100.0, 120.0]
        signals = [1, 1, 1]

        result = backtest(prices, signals, start_index=0)

        expected_shares = INITIAL_CASH / (
            prices[1] * (1 + FEE_RATE)
        )
        expected_equity = expected_shares * prices[2]

        self.assertEqual(result["trades"], 1)
        self.assertAlmostEqual(
            result["final_equity"],
            expected_equity,
            places=6,
        )

    def test_switching_position_pays_both_fees(self):
        prices = [100.0, 100.0, 100.0, 100.0]
        signals = [1, 0, 1, 0]

        result = backtest(prices, signals, start_index=0)

        # 第 1 日收盘买入，第 2 日收盘卖出，
        # 第 3 日收盘再次买入。
        self.assertEqual(result["trades"], 3)
        self.assertEqual(result["position"], 1)

        expected_equity = (
            INITIAL_CASH
            / (1 + FEE_RATE)
            * (1 - FEE_RATE)
            / (1 + FEE_RATE)
        )

        self.assertAlmostEqual(
            result["final_equity"],
            expected_equity,
            places=6,
        )

    def test_flat_signal_does_not_trade(self):
        prices = [100.0, 110.0, 105.0, 120.0]
        signals = [0, 0, 0, 0]

        result = backtest(prices, signals, start_index=0)

        self.assertEqual(result["trades"], 0)
        self.assertEqual(result["position"], 0)
        self.assertAlmostEqual(
            result["final_equity"],
            INITIAL_CASH,
            places=8,
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
