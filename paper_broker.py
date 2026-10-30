
from math import isfinite


class PaperBroker:
    def __init__(self, initial_cash=10000.0, fee_rate=0.001):
        initial_cash = self._to_finite_float(
            initial_cash, "初始现金"
        )
        fee_rate = self._to_finite_float(
            fee_rate, "交易费率"
        )

        if initial_cash < 0:
            raise ValueError("初始现金不能为负数")

        if fee_rate < 0:
            raise ValueError("交易费率不能为负数")

        self.initial_cash = round(initial_cash, 2)
        self.cash = self.initial_cash
        self.fee_rate = fee_rate

        # 持仓格式：symbol -> {"qty": 数量, "cost": 剩余总成本}
        self.positions = {}

        # 成功执行的订单 ID，用于防止重复执行
        self.orders = set()

        # 成交记录
        self.trades = []
        self.realized_pnl = 0.0

        self.environment = "PAPER"

    @staticmethod
    def _to_finite_float(value, field_name):
        """将数值转换为有限浮点数，拒绝布尔值、NaN 和无穷大。"""
        if isinstance(value, bool) or not isinstance(
            value, (int, float)
        ):
            raise ValueError(f"{field_name}必须是有效数值")

        try:
            result = float(value)
        except (ValueError, TypeError, OverflowError):
            raise ValueError(f"{field_name}必须是有限数值")

        if not isfinite(result):
            raise ValueError(f"{field_name}必须是有限数值")

        return result

    def _validate(self, order_id, symbol, qty, price):
        if not isinstance(order_id, str) or not order_id.strip():
            raise ValueError("订单 ID 不能为空")

        if order_id in self.orders:
            raise ValueError("重复订单，拒绝执行")

        if not isinstance(symbol, str) or not symbol.strip():
            raise ValueError("股票代码不能为空")

        if (
            not isinstance(qty, int)
            or isinstance(qty, bool)
            or qty <= 0
        ):
            raise ValueError("交易数量必须是正整数")

        price = self._to_finite_float(price, "交易价格")

        if price <= 0:
            raise ValueError("交易价格必须是有限正数")

        return price

    def buy(self, order_id, symbol, qty, price):
        """按指定模拟价格买入。"""
        price = self._validate(order_id, symbol, qty, price)

        try:
            notional = qty * price
            if not isfinite(notional):
                raise ValueError("买入金额超出有效数值范围")

            fee = round(notional * self.fee_rate, 2)
            total_cost = round(notional + fee, 2)

        except (OverflowError, ValueError):
            raise ValueError("买入金额或手续费计算异常")

        if not isfinite(fee) or not isfinite(total_cost):
            raise ValueError("买入金额或手续费计算异常")

        if total_cost > self.cash:
            raise ValueError("现金不足，买入被拒绝")

        old = self.positions.get(
            symbol, {"qty": 0, "cost": 0.0}
        )

        new_qty = old["qty"] + qty
        new_cost = round(old["cost"] + total_cost, 2)
        new_cash = round(self.cash - total_cost, 2)

        if not all(
            isfinite(value)
            for value in (new_cost, new_cash)
        ):
            raise ValueError("买入后账户数值异常")

        # 所有检查完成后再修改账户状态
        self.cash = new_cash
        self.positions[symbol] = {
            "qty": new_qty,
            "cost": new_cost,
        }

        self.orders.add(order_id)
        self.trades.append({
            "order_id": order_id,
            "environment": self.environment,
            "side": "BUY",
            "symbol": symbol,
            "qty": qty,
            "price": price,
            "fee": fee,
            "realized_pnl": 0.0,
        })

        return self.trades[-1].copy()

    def sell(self, order_id, symbol, qty, price):
        """按指定模拟价格卖出。"""
        price = self._validate(order_id, symbol, qty, price)

        position = self.positions.get(symbol)

        if position is None or qty > position["qty"]:
            raise ValueError("持仓不足，卖出被拒绝")

        try:
            notional = qty * price
            if not isfinite(notional):
                raise ValueError("卖出金额超出有效数值范围")

            fee = round(notional * self.fee_rate, 2)
            proceeds = round(notional - fee, 2)

        except (OverflowError, ValueError):
            raise ValueError("卖出金额或手续费计算异常")

        if not isfinite(fee) or not isfinite(proceeds):
            raise ValueError("卖出金额或手续费计算异常")

        # 按平均成本分摊剩余持仓成本
        old_qty = position["qty"]
        old_cost = position["cost"]

        if qty == old_qty:
            allocated_cost = old_cost
        else:
            allocated_cost = round(
                old_cost * qty / old_qty, 2
            )

        pnl = round(proceeds - allocated_cost, 2)
        new_cash = round(self.cash + proceeds, 2)
        new_realized_pnl = round(
            self.realized_pnl + pnl, 2
        )

        remaining_qty = old_qty - qty
        remaining_cost = round(
            old_cost - allocated_cost, 2
        )

        if not all(
            isfinite(value)
            for value in (
                pnl,
                new_cash,
                new_realized_pnl,
                remaining_cost,
            )
        ):
            raise ValueError("卖出后账户数值异常")

        # 所有检查完成后再修改账户状态
        self.cash = new_cash
        self.realized_pnl = new_realized_pnl

        if remaining_qty == 0:
            del self.positions[symbol]
        else:
            self.positions[symbol] = {
                "qty": remaining_qty,
                "cost": remaining_cost,
            }

        self.orders.add(order_id)
        self.trades.append({
            "order_id": order_id,
            "environment": self.environment,
            "side": "SELL",
            "symbol": symbol,
            "qty": qty,
            "price": price,
            "fee": fee,
            "realized_pnl": pnl,
        })

        return self.trades[-1].copy()

    def get_cash(self):
        return self.cash

    def get_positions(self):
        return {
            symbol: position.copy()
            for symbol, position in self.positions.items()
        }

    def unrealized_pnl(self, prices):
        """计算未实现盈亏，prices 示例：{"QQQ": 450.0}。"""
        total = 0.0

        for symbol, position in self.positions.items():
            if symbol not in prices:
                raise ValueError(f"缺少 {symbol} 的估值价格")

            price = self._to_finite_float(
                prices[symbol], f"{symbol} 的估值价格"
            )

            if price <= 0:
                raise ValueError(
                    f"{symbol} 的估值价格必须为正数"
                )

            market_value = position["qty"] * price
            if not isfinite(market_value):
                raise ValueError(f"{symbol} 的市值计算异常")

            total += market_value - position["cost"]

            if not isfinite(total):
                raise ValueError("未实现盈亏计算异常")

        return round(total, 2)

    def total_equity(self, prices):
        """计算总资产：现金 + 持仓市值，不重复计算已实现盈亏。"""
        market_value = 0.0

        for symbol, position in self.positions.items():
            if symbol not in prices:
                raise ValueError(f"缺少 {symbol} 的估值价格")

            price = self._to_finite_float(
                prices[symbol], f"{symbol} 的估值价格"
            )

            if price <= 0:
                raise ValueError(
                    f"{symbol} 的估值价格必须为正数"
                )

            value = position["qty"] * price

            if not isfinite(value):
                raise ValueError(f"{symbol} 的市值计算异常")

            market_value += value

            if not isfinite(market_value):
                raise ValueError("持仓总市值计算异常")

        equity = self.cash + market_value

        if not isfinite(equity):
            raise ValueError("总资产计算异常")

        return round(equity, 2)

    def get_trades(self):
        return [trade.copy() for trade in self.trades]

