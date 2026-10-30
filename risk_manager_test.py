
import unittest

from risk_manager import RiskManager


class TestRiskManager(unittest.TestCase):

    def setUp(self):
        self.risk = RiskManager()
        self.risk.set_trading_day("2026-10-21")

    def test_normal_status(self):
        result = self.risk.update_equity(10000)

        self.assertAlmostEqual(result["drawdown"], 0)
        self.assertEqual(self.risk.get_status()["level"], "NORMAL")

    def test_warning_at_five_percent(self):
        self.risk.update_equity(10000)
        result = self.risk.update_equity(9500)

        self.assertAlmostEqual(result["drawdown"], 0.05)
        self.assertEqual(self.risk.get_status()["level"], "WARNING")
        self.assertFalse(self.risk.paused)

    def test_pause_at_ten_percent(self):
        self.risk.update_equity(10000)
        self.risk.update_equity(9000)

        self.assertTrue(self.risk.paused)

        result = self.risk.check_open(
            "QQQ", 100, 9000, {}
        )
        self.assertFalse(result["allowed"])
        self.assertIn("风控暂停开仓", result["reasons"])

    def test_severe_at_fifteen_percent(self):
        self.risk.update_equity(10000)
        self.risk.update_equity(8500)

        self.assertTrue(self.risk.severe_triggered)
        self.assertTrue(self.risk.severe_lock)
        self.assertEqual(self.risk.get_status()["level"], "SEVERE")

    def test_symbol_position_limit(self):
        result = self.risk.check_open(
            "QQQ", 1000, 10000, {"QQQ": 2500}
        )

        self.assertFalse(result["allowed"])
        self.assertIn(
            "超过单一标的仓位上限",
            result["reasons"],
        )

    def test_total_position_limit(self):
        result = self.risk.check_open(
            "QQQ", 1000, 10000, {"SPY": 7500}
        )

        self.assertFalse(result["allowed"])
        self.assertIn(
            "超过总持仓比例上限",
            result["reasons"],
        )

    def test_daily_trade_limit(self):
        for _ in range(5):
            self.risk.record_trade("2026-10-21")

        result = self.risk.check_open(
            "QQQ", 100, 10000, {}
        )

        self.assertFalse(result["allowed"])
        self.assertIn(
            "超过每日交易次数上限",
            result["reasons"],
        )

    def test_manual_resume_requires_confirmation(self):
        self.risk.update_equity(10000)
        self.risk.update_equity(9000)

        with self.assertRaises(ValueError):
            self.risk.resume_trading()

        self.assertTrue(self.risk.paused)

        self.risk.resume_trading(confirm=True)
        self.assertFalse(self.risk.paused)

    def test_new_day_resets_daily_count(self):
        for _ in range(5):
            self.risk.record_trade("2026-10-21")

        self.risk.set_trading_day("2026-10-22")

        self.assertEqual(self.risk.daily_trades, 0)

    def test_auto_resume_after_cooldown(self):
        risk = RiskManager(
            auto_resume=True,
            resume_cooldown_days=3,
        )

        risk.set_trading_day("2026-01-01")
        risk.update_equity(10000)
        risk.update_equity(8900)

        self.assertTrue(risk.paused)

        risk.set_trading_day("2026-01-02")
        risk.update_equity(9100)
        self.assertTrue(risk.paused)

        risk.set_trading_day("2026-01-03")
        risk.update_equity(9200)
        self.assertTrue(risk.paused)

        risk.set_trading_day("2026-01-04")
        result = risk.update_equity(9300)

        self.assertFalse(result["paused"])
        self.assertIn(
            "AUTO_RESUME",
            [event["type"] for event in risk.events],
        )

    def test_auto_resume_disabled_by_default(self):
        risk = RiskManager()

        risk.set_trading_day("2026-01-01")
        risk.update_equity(10000)
        risk.update_equity(8900)

        for day in [
            "2026-01-02",
            "2026-01-03",
            "2026-01-04",
            "2026-01-05",
            "2026-01-06",
            "2026-01-07",
            "2026-01-08",
            "2026-01-09",
            "2026-01-10",
            "2026-01-11",
            "2026-01-12",
        ]:
            risk.set_trading_day(day)
            risk.update_equity(9300)

        self.assertTrue(risk.paused)
        self.assertNotIn(
            "AUTO_RESUME",
            [event["type"] for event in risk.events],
        )

    def test_severe_drawdown_requires_manual_resume(self):
        risk = RiskManager(
            auto_resume=True,
            resume_cooldown_days=1,
        )

        risk.set_trading_day("2026-01-01")
        risk.update_equity(10000)
        risk.update_equity(8400)

        self.assertTrue(risk.severe_triggered)
        self.assertTrue(risk.severe_lock)
        self.assertTrue(risk.paused)

        risk.set_trading_day("2026-01-02")
        risk.update_equity(9500)

        # 严重回撤锁定不能被自动恢复绕过。
        self.assertTrue(risk.severe_lock)
        self.assertTrue(risk.paused)

        result = risk.check_open(
            "QQQ", 100, 9500, {}
        )
        self.assertFalse(result["allowed"])

        risk.resume_trading(confirm=True)

        self.assertFalse(risk.severe_lock)
        self.assertFalse(risk.paused)

        # 历史严重回撤记录保留。
        self.assertTrue(risk.severe_triggered)

        self.assertIn(
            "MANUAL_RESUME",
            [event["type"] for event in risk.events],
        )

    def test_severe_resume_event_records_lock_clearance(self):
        risk = RiskManager()

        risk.set_trading_day("2026-01-01")
        risk.update_equity(10000)
        risk.update_equity(8400)

        risk.resume_trading(confirm=True)

        resume_events = [
            event
            for event in risk.events
            if event["type"] == "MANUAL_RESUME"
        ]

        self.assertEqual(len(resume_events), 1)
        self.assertTrue(
            resume_events[0]["severe_lock_cleared"]
        )

    def test_invalid_equity_is_rejected(self):
        for value in [
            0,
            -1,
            float("inf"),
            float("nan"),
            True,
        ]:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    self.risk.update_equity(value)

    def test_invalid_trading_day_is_rejected(self):
        for day in [
            "",
            "2026-13-01",
            "2026-02-30",
            "not-a-date",
        ]:
            with self.subTest(day=day):
                with self.assertRaises(ValueError):
                    self.risk.set_trading_day(day)

    def test_trading_day_cannot_go_backwards(self):
        self.risk.set_trading_day("2026-10-22")

        with self.assertRaises(ValueError):
            self.risk.set_trading_day("2026-10-21")

    def test_invalid_configuration_is_rejected(self):
        with self.assertRaises(ValueError):
            RiskManager(
                warning_drawdown=0.10,
                pause_drawdown=0.05,
                severe_drawdown=0.15,
            )

        with self.assertRaises(ValueError):
            RiskManager(max_daily_trades=-1)

        with self.assertRaises(ValueError):
            RiskManager(resume_cooldown_days=-1)

    def test_same_day_does_not_reset_trade_count(self):
        self.risk.record_trade("2026-10-21")
        self.risk.record_trade("2026-10-21")

        self.risk.set_trading_day("2026-10-21")

        self.assertEqual(self.risk.daily_trades, 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
