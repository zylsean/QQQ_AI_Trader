

import unittest

from adaptive_strategy_research import (
    START_INDEX,
    calculate_signals,
    rolling_select,
)


class TestAdaptiveStrategy(unittest.TestCase):

    def setUp(self):
        # 构造确定性的模拟价格序列，不依赖网络
        self.prices = [
            100 + i * 0.03 + (i % 17) * 0.2
            for i in range(600)
        ]

    def test_future_prices_do_not_change_past_signals(self):
        cutoff = 400

        original = calculate_signals(self.prices)

        changed_prices = self.prices.copy()

        # 大幅修改 cutoff 之后的价格
        for i in range(cutoff + 1, len(changed_prices)):
            changed_prices[i] *= 1.5

        changed = calculate_signals(changed_prices)

        for name in original:
            self.assertEqual(
                original[name][:cutoff + 1],
                changed[name][:cutoff + 1],
                msg=f"{name} 的过去信号受到未来价格影响",
            )

    def test_future_returns_do_not_change_past_selections(self):
        n = len(self.prices)
        cutoff = 400

        candidate_names = [
            "63D Momentum",
            "50/200 Trend",
            "20D Mean Reversion",
        ]

        candidate_signals = {
            name: [
                int((i // (index + 2)) % 3 != 0)
                for i in range(n)
            ]
            for index, name in enumerate(candidate_names)
        }

        # 构造可重复的历史日收益
        results = {}

        for index, name in enumerate(candidate_names):
            returns = [
                ((i % (index + 3)) - 1) * 0.001
                for i in range(n)
            ]

            results[name] = {
                "daily_returns": returns
            }

        original = rolling_select(
            self.prices,
            candidate_signals,
            results,
        )

        # 只改变 cutoff 之后的历史收益记录
        changed_results = {}

        for name in candidate_names:
            changed_returns = results[name][
                "daily_returns"
            ].copy()

            for i in range(cutoff + 1, n):
                changed_returns[i] = 0.10

            changed_results[name] = {
                "daily_returns": changed_returns
            }

        changed = rolling_select(
            self.prices,
            candidate_signals,
            changed_results,
        )

        self.assertEqual(
            original[:cutoff + 1],
            changed[:cutoff + 1],
            "未来收益影响了过去的策略选择",
        )

    def test_signal_arrays_have_same_length(self):
        signals = calculate_signals(self.prices)

        for name, values in signals.items():
            with self.subTest(strategy=name):
                self.assertEqual(
                    len(values),
                    len(self.prices),
                )


    def test_bearish_flat_signal_clears_stale_mean_reversion_state(self):
        """已进入明确空仓分支后，不应因旧均值回归状态再次做多。"""
        from pathlib import Path
        from adaptive_strategy_research import load_data

        data_path = Path(__file__).parent / "QQQ_yahoo_10y.csv"
        dates, prices = load_data(str(data_path))
        signals = calculate_signals(prices)["Adaptive Rules"]

        # 这些历史转折点曾因均值回归状态残留而错误地重新输出做多信号。
        expected_flat_dates = {
            "2022-09-09",
            "2022-09-12",
            "2023-01-09",
        }
        date_to_index = {date: i for i, date in enumerate(dates)}

        for date in expected_flat_dates:
            with self.subTest(date=date):
                self.assertIn(date, date_to_index)
                self.assertEqual(signals[date_to_index[date]], 0)

    def test_rolling_selection_is_deterministic(self):
        signals = calculate_signals(self.prices)

        candidate_names = [
            "63D Momentum",
            "50/200 Trend",
            "20D Mean Reversion",
        ]

        from adaptive_strategy_research import backtest

        results = {
            name: backtest(
                self.prices,
                signals[name],
                start_index=START_INDEX,
            )
            for name in candidate_names
        }

        first = rolling_select(
            self.prices, signals, results
        )

        second = rolling_select(
            self.prices, signals, results
        )

        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main(verbosity=2)
