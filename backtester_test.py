

import unittest

from backtester import run_backtest


class TestBacktester(unittest.TestCase):

    def make_data(self, count=80):
        dates = []
        opens = []
        closes = []

        price = 100.0

        for i in range(count):
            dates.append("2026-{:02d}-{:02d}".format(
                i // 28 + 1,
                i % 28 + 1
            ))

            # 构造一段先下跌、后上涨的样例价格。
            if i < 30:
                price -= 0.5
            else:
                price += 0.8

            opens.append(round(price - 0.2, 2))
            closes.append(round(price, 2))

        return dates, opens, closes

    def test_returns_summary(self):
        dates, opens, closes = self.make_data()

        result = run_backtest(
            dates,
            opens,
            closes,
            symbol="QQQ",
        )

        self.assertIn("final_equity", result)
        self.assertIn("total_return", result)
        self.assertIn("max_drawdown", result)
        self.assertIn("trade_count", result)
        self.assertIn("equity_curve", result)

    def test_equity_curve_length(self):
        dates, opens, closes = self.make_data()

        result = run_backtest(dates, opens, closes)

        self.assertEqual(
            len(result["equity_curve"]),
            len(dates),
        )

    def test_prices_must_be_positive(self):
        dates, opens, closes = self.make_data()
        opens[10] = 0

        with self.assertRaises(ValueError):
            run_backtest(dates, opens, closes)

    def test_data_lengths_must_match(self):
        dates, opens, closes = self.make_data()
        opens.pop()

        with self.assertRaises(ValueError):
            run_backtest(dates, opens, closes)

    def test_dates_must_be_ordered(self):
        dates, opens, closes = self.make_data()
        dates[0], dates[1] = dates[1], dates[0]

        with self.assertRaises(ValueError):
            run_backtest(dates, opens, closes)


if __name__ == "__main__":
    unittest.main()
