
import unittest
from datetime import datetime, timedelta

from backtester import run_backtest
from risk_manager import RiskManager


def make_dates(count):
    start = datetime(2026, 1, 1)
    return [
        (start + timedelta(days=i)).strftime("%Y-%m-%d")
        for i in range(count)
    ]


class TestManualResumeBoundary(unittest.TestCase):

    def make_severe_risk(self):
        risk = RiskManager()
        risk.set_trading_day("2026-01-01")
        risk.update_equity(10000.0)
        risk.set_trading_day("2026-01-02")
        risk.update_equity(8000.0)  # 回撤 20%
        return risk

    def test_resume_with_high_drawdown_still_blocks_open(self):
        risk = self.make_severe_risk()
        risk.resume_trading(confirm=True)
        risk.set_trading_day("2026-01-03")

        decision = risk.check_open("QQQ", 1000.0, 8000.0, {})

        self.assertFalse(decision["allowed"])
        self.assertIn("当前回撤仍高于暂停阈值", decision["reasons"])

    def test_status_not_warning_when_drawdown_above_pause(self):
        risk = self.make_severe_risk()
        risk.resume_trading(confirm=True)

        self.assertEqual(risk.get_status()["level"], "PAUSED")

    def test_relock_after_resume_is_recorded(self):
        risk = self.make_severe_risk()
        risk.resume_trading(confirm=True)
        risk.set_trading_day("2026-01-03")
        risk.update_equity(8000.0)

        types = [event["type"] for event in risk.events]

        self.assertTrue(risk.severe_lock)
        self.assertIn("SEVERE_RELOCK", types)
        self.assertEqual(types.count("SEVERE_DRAWDOWN"), 1)

    def test_resume_allows_open_after_drawdown_recovers(self):
        risk = self.make_severe_risk()
        risk.resume_trading(confirm=True)
        risk.set_trading_day("2026-01-03")
        risk.update_equity(9500.0)  # 回撤 5%

        decision = risk.check_open("QQQ", 1000.0, 9500.0, {})

        self.assertTrue(decision["allowed"])


class TestAutoResumeWhenFlat(unittest.TestCase):

    def make_paused_risk(self, cooldown=3):
        risk = RiskManager(
            auto_resume=True,
            resume_cooldown_days=cooldown,
        )
        risk.set_trading_day("2026-01-01")
        risk.update_equity(10000.0)
        risk.set_trading_day("2026-01-02")
        risk.update_equity(8800.0)  # 回撤 12%，普通暂停
        return risk

    def test_flat_account_resumes_after_cooldown(self):
        risk = self.make_paused_risk()

        for day in ["2026-01-03", "2026-01-04", "2026-01-05"]:
            risk.set_trading_day(day)
            risk.update_equity(8800.0, has_exposure=False)

        self.assertFalse(risk.paused)
        self.assertEqual(risk.peak_equity, 8800.0)
        resume = [e for e in risk.events if e["type"] == "AUTO_RESUME"]
        self.assertEqual(len(resume), 1)
        self.assertTrue(resume[0]["peak_rebaselined"])

    def test_exposed_account_does_not_resume_while_drawdown_high(self):
        risk = self.make_paused_risk()

        for day in ["2026-01-03", "2026-01-04", "2026-01-05"]:
            risk.set_trading_day(day)
            risk.update_equity(8800.0, has_exposure=True)

        self.assertTrue(risk.paused)

    def test_severe_lock_never_auto_resumes_even_when_flat(self):
        risk = RiskManager(auto_resume=True, resume_cooldown_days=1)
        risk.set_trading_day("2026-01-01")
        risk.update_equity(10000.0)
        risk.set_trading_day("2026-01-02")
        risk.update_equity(8000.0)

        for day in ["2026-01-03", "2026-01-04", "2026-01-05"]:
            risk.set_trading_day(day)
            risk.update_equity(8000.0, has_exposure=False)

        self.assertTrue(risk.paused)
        self.assertTrue(risk.severe_lock)

    def test_invalid_has_exposure_is_rejected(self):
        risk = RiskManager()

        with self.assertRaises(ValueError):
            risk.update_equity(10000.0, has_exposure="yes")


class TestBacktesterRejections(unittest.TestCase):

    def test_oversized_fraction_is_rejected_with_reason(self):
        count = 30
        prices = [100.0] * count

        result = run_backtest(
            dates=make_dates(count),
            open_prices=prices,
            close_prices=prices,
            position_fraction=0.5,
            target_positions=[1] * count,
        )

        self.assertEqual(result["trade_count"], 0)
        self.assertEqual(result["positions"], {})
        self.assertEqual(result["cash"], 10000.0)
        self.assertTrue(result["rejected_orders"])
        self.assertIn(
            "超过单一标的仓位上限",
            result["rejected_orders"][0]["reasons"],
        )

    def test_rejection_does_not_change_account(self):
        count = 30
        prices = [100.0] * count

        result = run_backtest(
            dates=make_dates(count),
            open_prices=prices,
            close_prices=prices,
            position_fraction=0.5,
            target_positions=[1] * count,
        )

        self.assertEqual(result["trades"], [])
        self.assertEqual(result["final_equity"], 10000.0)
        self.assertEqual(result["risk_status"]["daily_trades"], 0)

    def test_no_rejections_in_normal_run(self):
        count = 30
        prices = [100.0] * count

        result = run_backtest(
            dates=make_dates(count),
            open_prices=prices,
            close_prices=prices,
            target_positions=[1] * count,
        )

        self.assertEqual(result["rejected_orders"], [])
        self.assertEqual(result["trade_count"], 1)

    def test_paused_retry_is_logged_each_day_without_trading(self):
        count = 100
        closes = []
        price = 100.0
        for i in range(count):
            price += 1.0 if i < 60 else -3.5
            closes.append(price)
        targets = [1 if i < 85 or i >= 90 else 0 for i in range(count)]

        result = run_backtest(
            dates=make_dates(count),
            open_prices=closes[:],
            close_prices=closes,
            target_positions=targets,
        )

        buys = [t for t in result["trades"] if t["side"] == "BUY"]
        self.assertEqual(len(buys), 1)
        self.assertTrue(result["rejected_orders"])
        self.assertTrue(
            all(
                "风控暂停开仓" in item["reasons"]
                for item in result["rejected_orders"]
            )
        )


class TestAutoResumeEndToEnd(unittest.TestCase):

    def test_flat_account_can_reenter_after_recovery(self):
        count = 200
        closes = (
            [100.0] * 20
            + [100 - (40 / 30) * i for i in range(1, 31)]
            + [60.0] * 10
            + [60 + 1.5 * i for i in range(1, 141)]
        )
        targets = [
            1 if (5 <= i < 55 or i >= 70) else 0
            for i in range(count)
        ]

        result = run_backtest(
            dates=make_dates(count),
            open_prices=closes[:],
            close_prices=closes,
            position_fraction=0.30,
            target_positions=targets,
            auto_resume=True,
            resume_cooldown_days=10,
        )

        buys = [t for t in result["trades"] if t["side"] == "BUY"]
        types = [e["type"] for e in result["risk_status"]["events"]]

        self.assertIn("AUTO_RESUME", types)
        self.assertGreaterEqual(len(buys), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
