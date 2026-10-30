
import unittest

from backtester import run_backtest


class SignalBacktestTest(unittest.TestCase):

    def test_signal_executes_next_day_open(self):
        result = run_backtest(
            dates=["D1", "D2", "D3"],
            open_prices=[100, 110, 120],
            close_prices=[100, 110, 120],
            initial_cash=10000,
            position_fraction=0.20,
            target_positions=[1, 1, 0],
        )

        trades = result["trades"]
        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0]["side"], "BUY")
        self.assertEqual(trades[0]["price"], 110.0)

    def test_target_zero_exits_existing_position(self):
        result = run_backtest(
            dates=["D1", "D2", "D3", "D4"],
            open_prices=[100, 100, 110, 120],
            close_prices=[100, 100, 110, 120],
            initial_cash=10000,
            position_fraction=0.20,
            target_positions=[1, 1, 0, 0],
        )

        sides = [trade["side"] for trade in result["trades"]]
        self.assertEqual(sides, ["BUY", "SELL"])
        self.assertEqual(result["positions"], {})

    def test_invalid_target_signal_length(self):
        with self.assertRaises(ValueError):
            run_backtest(
                dates=["D1", "D2", "D3"],
                open_prices=[100, 100, 100],
                close_prices=[100, 100, 100],
                target_positions=[1, 0],
            )

    def test_invalid_target_value(self):
        with self.assertRaises(ValueError):
            run_backtest(
                dates=["D1", "D2", "D3"],
                open_prices=[100, 100, 100],
                close_prices=[100, 100, 100],
                target_positions=[1, 0, 0.5],
            )

    def test_none_means_no_new_signal(self):
        result = run_backtest(
            dates=["D1", "D2", "D3", "D4", "D5"],
            open_prices=[100, 100, 100, 100, 100],
            close_prices=[100, 100, 100, 100, 100],
            initial_cash=10000,
            position_fraction=0.20,
            target_positions=[1, None, None, 0, None],
        )

        trades = result["trades"]
        sides = [trade["side"] for trade in trades]

        self.assertEqual(sides, ["BUY", "SELL"])
        self.assertEqual(trades[0]["price"], 100.0)
        self.assertEqual(trades[1]["price"], 100.0)
        self.assertEqual(result["positions"], {})
    if __name__ == "__main__":
        unittest.main(verbosity=2)

