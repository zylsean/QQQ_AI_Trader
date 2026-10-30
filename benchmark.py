

def buy_and_hold_result(
    open_prices,
    close_prices,
    initial_cash=10000.0,
    fee_rate=0.001,
):
    """以首日开盘买入、末日收盘估值，计算买入并持有收益。"""

    if len(open_prices) != len(close_prices) or len(open_prices) < 2:
        raise ValueError("开盘价和收盘价必须等长，且至少有两天数据")

    if initial_cash <= 0:
        raise ValueError("初始资金必须大于0")

    if fee_rate < 0:
        raise ValueError("手续费率不能小于0")

    for price in list(open_prices) + list(close_prices):
        if (
            isinstance(price, bool)
            or not isinstance(price, (int, float))
            or price <= 0
        ):
            raise ValueError("价格必须是正数")

    buy_price = open_prices[0]
    buy_fee_rate = fee_rate

    # 将买入手续费计入可购买资金。
    qty = int(initial_cash / (buy_price * (1 + buy_fee_rate)))

    buy_notional = qty * buy_price
    buy_fee = round(buy_notional * buy_fee_rate, 2)
    cash_after_buy = round(initial_cash - buy_notional - buy_fee, 2)

    final_price = close_prices[-1]
    market_value = round(qty * final_price, 2)
    final_equity = round(cash_after_buy + market_value, 2)

    return {
        "initial_cash": round(initial_cash, 2),
        "qty": qty,
        "buy_price": buy_price,
        "final_price": final_price,
        "final_equity": final_equity,
        "total_return": round(
            (final_equity / initial_cash - 1) * 100, 2
        ),
    }
    

def buy_and_hold_adjusted_result(
    adj_close_prices,
    initial_cash=10000.0,
    fee_rate=0.001,
):
    """使用调整收盘价估算买入并持有的总回报。

    这是总回报指数口径的基准估算，不是逐笔模拟
    实际成交、分红到账和分红再投资的完整交易账本。
    """

    if len(adj_close_prices) < 2:
        raise ValueError("调整收盘价至少需要两天数据")

    if initial_cash <= 0:
        raise ValueError("初始资金必须大于0")

    if not 0 <= fee_rate < 1:
        raise ValueError("手续费率必须在0到1之间")

    for price in adj_close_prices:
        if (
            isinstance(price, bool)
            or not isinstance(price, (int, float))
            or not 0 < price < float("inf")
        ):
            raise ValueError("调整收盘价必须是有限正数")

    first_price = adj_close_prices[0]
    final_price = adj_close_prices[-1]

    # 用总回报指数估算持有收益，并扣除买入、卖出费用。
    invested_cash = initial_cash * (1 - fee_rate)
    gross_final_value = invested_cash * final_price / first_price
    final_equity = gross_final_value * (1 - fee_rate)

    return {
        "initial_cash": round(initial_cash, 2),
        "first_adj_close": round(first_price, 4),
        "final_adj_close": round(final_price, 4),
        "final_equity": round(final_equity, 2),
        "total_return": round(
            (final_equity / initial_cash - 1) * 100, 2
        ),
        "method": "调整收盘价总回报指数估算",
    }
