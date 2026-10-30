
import unittest
from datetime import datetime, timedelta

from backtester import run_backtest


class TestBacktesterRisk(unittest.TestCase):

    @staticmethod
    def make_dates(count):
        start_date = datetime(2026, 1, 1)
        return [
            (start_date + timedelta(days=i)).strftime("%Y-%m-%d")
            for i in range(count)
        ]

    @staticmethod
    def make_rising_falling_prices(count=100):
        """先上涨，再持续下跌，确保账户有机会触发回撤风控。"""
        prices = []
        price = 100.0

        for i in range(count):
            if i < 60:
                price += 1.0
            else:
                price -= 3.5

            prices.append(price)

        return prices

    def test_backtest_returns_risk_status(self):
        dates = self.make_dates(100)
        close_prices = self.make_rising_falling_prices()
        open_prices = close_prices[:]

        result = run_backtest(
            dates=dates,
            open_prices=open_prices,
            close_prices=close_prices,
            symbol="QQQ",
            initial_cash=10000.0,
            short_window=5,
            long_window=10,
            fee_rate=0.001,
        )

        self.assertIn("risk_status", result)
        self.assertIn("max_drawdown", result)
        self.assertIn("trades", result)
        self.assertGreater(result["final_equity"], 0)
        self.assertEqual(
            result["final_equity"],
            result["equity_curve"][-1]["equity"],
        )

        print("\n最终风险状态：", result["risk_status"])
        print("最大回撤：", result["max_drawdown"], "%")
        print("交易次数：", result["trade_count"])
        print("最终资产：", result["final_equity"])

    def test_equity_curve_consistency(self):
        dates = self.make_dates(100)

        close_prices = [
            100.0 + i if i < 60 else 160.0 - (i - 59) * 2
            for i in range(100)
        ]
        open_prices = close_prices[:]

        result = run_backtest(
            dates=dates,
            open_prices=open_prices,
            close_prices=close_prices,
            short_window=5,
            long_window=10,
        )

        self.assertEqual(
            result["final_equity"],
            result["equity_curve"][-1]["equity"],
        )

        print("\n净值曲线一致性：通过")

    def test_drawdown_pause_is_triggered(self):
        """确认模拟价格下跌时，回测确实记录交易暂停事件。"""
        dates = self.make_dates(100)
        close_prices = self.make_rising_falling_prices()
        open_prices = close_prices[:]

        # 先持有，再平仓，最后尝试重新买入。
        # 用于测试回撤暂停是否能阻止后续开仓。
        target_positions = [
            1 if i < 85 or i >= 90 else 0
            for i in range(100)
        ]

        result = run_backtest(
            dates=dates,
            open_prices=open_prices,
            close_prices=close_prices,
            symbol="QQQ",
            initial_cash=10000.0,
            fee_rate=0.001,
            position_fraction=0.20,
            target_positions=target_positions,
        )

        events = result["risk_status"]["events"]

        pause_events = [
            event for event in events
            if event.get("type") == "TRADING_PAUSED"
        ]

        self.assertTrue(
            pause_events,
            "预期回撤触发交易暂停，但没有找到 TRADING_PAUSED 事件",
        )

        print("\n回撤暂停事件：", pause_events)

    def test_paused_account_can_exit_but_cannot_reenter(self):
        """暂停期间允许平仓，但不应允许再次开仓。"""
        dates = self.make_dates(100)
        close_prices = self.make_rising_falling_prices()
        open_prices = close_prices[:]

        target_positions = [
            1 if i < 85 or i >= 90 else 0
            for i in range(100)
        ]

        result = run_backtest(
            dates=dates,
            open_prices=open_prices,
            close_prices=close_prices,
            symbol="QQQ",
            initial_cash=10000.0,
            fee_rate=0.001,
            position_fraction=0.20,
            target_positions=target_positions,
        )

        trades = result["trades"]
        buy_trades = [
            trade for trade in trades
            if trade.get("side") == "BUY"
        ]
        sell_trades = [
            trade for trade in trades
            if trade.get("side") == "SELL"
        ]

        events = result["risk_status"]["events"]
        pause_events = [
            event for event in events
            if event.get("type") == "TRADING_PAUSED"
        ]

        self.assertTrue(
            pause_events,
            "没有触发暂停，无法验证暂停期间的交易行为",
        )

        self.assertTrue(
            sell_trades,
            "预期暂停期间或之后执行目标平仓，但没有卖出记录",
        )

        self.assertEqual(
            len(buy_trades),
            1,
            "账户平仓后再次达到开仓目标，但风控暂停期间不应重新买入",
        )

        print("\n买入次数：", len(buy_trades))
        print("卖出次数：", len(sell_trades))
        print("暂停期间禁止重新开仓：通过")


if __name__ == "__main__":
    unittest.main(verbosity=2)
