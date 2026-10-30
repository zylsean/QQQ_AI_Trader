
import unittest

from performance import calculate_performance


class TestPerformance(unittest.TestCase):

    def setUp(self):
        self.result = {
            "trades": [
                {
                    "side": "BUY",
                    "fee": 1.00,
                    "realized_pnl": 0.0,
                },
                {
                    "side": "SELL",
                    "fee": 1.10,
                    "realized_pnl": 50.0,
                },
                {
                    "side": "BUY",
                    "fee": 1.00,
                    "realized_pnl": 0.0,
                },
                {
                    "side": "SELL",
                    "fee": 1.10,
                    "realized_pnl": -20.0,
                },
            ],
            "equity_curve": [
                {"equity": 10000.0},
                {"equity": 10030.0},
                {"equity": 10020.0},
            ],
            "total_return": 0.2,
        }

    def test_trade_counts(self):
        metrics = calculate_performance(self.result)

        self.assertEqual(metrics["completed_trades"], 2)
        self.assertEqual(metrics["buy_orders"], 2)
        self.assertEqual(metrics["sell_orders"], 2)

    def test_win_rate(self):
        metrics = calculate_performance(self.result)

        self.assertEqual(metrics["winning_trades"], 1)
        self.assertEqual(metrics["losing_trades"], 1)
        self.assertEqual(metrics["win_rate"], 50.0)

    def test_profit_factor(self):
        metrics = calculate_performance(self.result)

        self.assertEqual(metrics["gross_profit"], 50.0)
        self.assertEqual(metrics["gross_loss"], 20.0)
        self.assertEqual(metrics["profit_factor"], 2.5)

    def test_fee_statistics(self):
        metrics = calculate_performance(self.result)

        self.assertEqual(metrics["buy_fees"], 2.0)
        self.assertEqual(metrics["sell_fees"], 2.2)
        self.assertEqual(metrics["total_fees"], 4.2)

    def test_realized_pnl(self):
        metrics = calculate_performance(self.result)

        self.assertEqual(metrics["realized_pnl"], 30.0)

    def test_drawdown(self):
        metrics = calculate_performance(self.result)

        self.assertGreater(metrics["max_drawdown"], 0)
        self.assertLess(metrics["max_drawdown"], 1)

    def test_empty_trades(self):
        result = {
            "trades": [],
            "equity_curve": [
                {"equity": 10000.0},
                {"equity": 10000.0},
            ],
            "total_return": 0.0,
        }

        metrics = calculate_performance(result)

        self.assertEqual(metrics["completed_trades"], 0)
        self.assertEqual(metrics["win_rate"], 0.0)
        self.assertEqual(metrics["profit_factor"], 0.0)
        self.assertEqual(metrics["total_fees"], 0.0)


if __name__ == "__main__":
    unittest.main()

