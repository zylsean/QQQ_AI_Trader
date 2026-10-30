
import unittest
from math import inf, nan

from paper_broker import PaperBroker


class TestPaperBroker(unittest.TestCase):

    def setUp(self):
        self.broker = PaperBroker(
            initial_cash=10000.0,
            fee_rate=0.001,
        )

    def test_initial_state(self):
        self.assertAlmostEqual(self.broker.get_cash(), 10000.0)
        self.assertEqual(self.broker.get_positions(), {})
        self.assertEqual(self.broker.get_trades(), [])
        self.assertEqual(self.broker.environment, "PAPER")

    def test_buy_calculates_fee_and_cash(self):
        self.broker.buy("BUY-001", "QQQ", 10, 100.0)

        self.assertAlmostEqual(self.broker.get_cash(), 8999.0)
        self.assertEqual(self.broker.get_positions()["QQQ"]["qty"], 10)
        self.assertAlmostEqual(
            self.broker.get_positions()["QQQ"]["cost"],
            1001.0,
        )

    def test_sell_calculates_realized_pnl(self):
        self.broker.buy("BUY-001", "QQQ", 10, 100.0)
        self.broker.sell("SELL-001", "QQQ", 5, 110.0)

        # 卖出收入 550，手续费 0.55，分摊成本 500.50
        self.assertAlmostEqual(self.broker.get_cash(), 9548.45)
        self.assertAlmostEqual(self.broker.realized_pnl, 48.95)
        self.assertEqual(self.broker.get_positions()["QQQ"]["qty"], 5)
        self.assertAlmostEqual(
            self.broker.get_positions()["QQQ"]["cost"],
            500.50,
        )

    def test_multiple_buys_use_weighted_cost(self):
        self.broker.buy("BUY-001", "QQQ", 10, 100.0)
        self.broker.buy("BUY-002", "QQQ", 10, 120.0)

        position = self.broker.get_positions()["QQQ"]

        self.assertEqual(position["qty"], 20)
        # 买入总成本：1001 + 1201 = 2202
        self.assertAlmostEqual(position["cost"], 2202.2)

    def test_partial_sales_preserve_remaining_cost(self):
        self.broker.buy("BUY-001", "QQQ", 10, 100.0)
        self.broker.sell("SELL-001", "QQQ", 3, 110.0)
        self.broker.sell("SELL-002", "QQQ", 2, 110.0)

        position = self.broker.get_positions()["QQQ"]

        self.assertEqual(position["qty"], 5)
        self.assertAlmostEqual(position["cost"], 500.50)
        self.assertAlmostEqual(self.broker.realized_pnl, 48.95)

    def test_full_liquidation_removes_position(self):
        self.broker.buy("BUY-001", "QQQ", 10, 100.0)
        self.broker.sell("SELL-001", "QQQ", 10, 110.0)

        self.assertNotIn("QQQ", self.broker.get_positions())
        self.assertAlmostEqual(self.broker.get_positions().get("QQQ", {}).get("cost", 0), 0)

    def test_insufficient_cash_does_not_change_account(self):
        before_cash = self.broker.get_cash()
        before_positions = self.broker.get_positions()
        before_trades = self.broker.get_trades()

        with self.assertRaises(ValueError):
            self.broker.buy("BUY-001", "QQQ", 1000, 100.0)

        self.assertAlmostEqual(self.broker.get_cash(), before_cash)
        self.assertEqual(self.broker.get_positions(), before_positions)
        self.assertEqual(self.broker.get_trades(), before_trades)

    def test_oversell_does_not_change_account(self):
        self.broker.buy("BUY-001", "QQQ", 5, 100.0)

        before_cash = self.broker.get_cash()
        before_positions = self.broker.get_positions()
        before_trades = self.broker.get_trades()
        before_pnl = self.broker.realized_pnl

        with self.assertRaises(ValueError):
            self.broker.sell("SELL-001", "QQQ", 6, 110.0)

        self.assertAlmostEqual(self.broker.get_cash(), before_cash)
        self.assertEqual(self.broker.get_positions(), before_positions)
        self.assertEqual(self.broker.get_trades(), before_trades)
        self.assertAlmostEqual(self.broker.realized_pnl, before_pnl)

    def test_duplicate_order_id_is_rejected(self):
        self.broker.buy("ORDER-001", "QQQ", 1, 100.0)

        with self.assertRaises(ValueError):
            self.broker.buy("ORDER-001", "QQQ", 1, 100.0)

    def test_invalid_prices_are_rejected(self):
        invalid_prices = [0, -1, inf, -inf, nan]

        for price in invalid_prices:
            with self.subTest(price=price):
                with self.assertRaises(ValueError):
                    self.broker.buy(
                        f"BUY-{len(self.broker.get_trades())}-{str(price)}",
                        "QQQ",
                        1,
                        price,
                    )

    def test_invalid_quantities_are_rejected(self):
        invalid_quantities = [0, -1, 1.5, True, "2", None]

        for index, qty in enumerate(invalid_quantities):
            with self.subTest(qty=qty):
                with self.assertRaises((ValueError, TypeError)):
                    self.broker.buy(
                        f"BAD-QTY-{index}",
                        "QQQ",
                        qty,
                        100.0,
                    )

    def test_empty_order_id_and_symbol_are_rejected(self):
        with self.assertRaises((ValueError, TypeError)):
            self.broker.buy("", "QQQ", 1, 100.0)

        with self.assertRaises((ValueError, TypeError)):
            self.broker.buy("BUY-002", "", 1, 100.0)

    def test_unrealized_pnl(self):
        self.broker.buy("BUY-001", "QQQ", 10, 100.0)

        pnl = self.broker.unrealized_pnl({"QQQ": 110.0})

        # 市值 1100 - 含手续费成本 1001
        self.assertAlmostEqual(pnl, 99.0)

    def test_missing_valuation_price_is_rejected(self):
        self.broker.buy("BUY-001", "QQQ", 10, 100.0)

        with self.assertRaises((ValueError, KeyError)):
            self.broker.unrealized_pnl({})

    def test_total_equity_does_not_double_count_realized_pnl(self):
        self.broker.buy("BUY-001", "QQQ", 10, 100.0)
        self.broker.sell("SELL-001", "QQQ", 5, 110.0)

        equity = self.broker.total_equity({"QQQ": 110.0})

        # 现金 9548.45 + 剩余持仓市值 550
        self.assertAlmostEqual(equity, 10098.45)

    def test_returned_positions_are_independent_copies(self):
        self.broker.buy("BUY-001", "QQQ", 10, 100.0)

        positions = self.broker.get_positions()
        positions["QQQ"]["qty"] = 999
        positions["QQQ"]["cost"] = 0
        positions["OTHER"] = {"qty": 1, "cost": 1}

        actual = self.broker.get_positions()

        self.assertEqual(actual["QQQ"]["qty"], 10)
        self.assertAlmostEqual(actual["QQQ"]["cost"], 1001.0)
        self.assertNotIn("OTHER", actual)

    def test_returned_trades_are_independent_copies(self):
        self.broker.buy("BUY-001", "QQQ", 1, 100.0)

        trades = self.broker.get_trades()
        original_count = len(self.broker.get_trades())

        trades.clear()

        self.assertEqual(len(self.broker.get_trades()), original_count)

    def test_invalid_constructor_values(self):
        invalid_cases = [
            {"initial_cash": -1.0, "fee_rate": 0.001},
            {"initial_cash": 10000.0, "fee_rate": -0.001},
            {"initial_cash": inf, "fee_rate": 0.001},
            {"initial_cash": 10000.0, "fee_rate": inf},
            {"initial_cash": nan, "fee_rate": 0.001},
            {"initial_cash": 10000.0, "fee_rate": nan},
        ]

        for index, kwargs in enumerate(invalid_cases):
            with self.subTest(case=index):
                with self.assertRaises((ValueError, TypeError)):
                    PaperBroker(**kwargs)


if __name__ == "__main__":
    unittest.main(verbosity=2)
