
from math import sqrt


def calculate_performance(result):
    """计算交易统计、手续费和风险收益指标。"""

    trades = result["trades"]
    equity_curve = result["equity_curve"]

    buys = [
        trade for trade in trades
        if trade["side"] == "BUY"
    ]

    sells = [
        trade for trade in trades
        if trade["side"] == "SELL"
    ]

    completed = len(sells)

    # 已完成交易的盈利和亏损
    wins = [
        trade["realized_pnl"]
        for trade in sells
        if trade["realized_pnl"] > 0
    ]

    losses = [
        trade["realized_pnl"]
        for trade in sells
        if trade["realized_pnl"] < 0
    ]

    realized = sum(
        trade["realized_pnl"] for trade in sells
    )

    avg_win = (
        sum(wins) / len(wins) if wins else 0.0
    )

    avg_loss = (
        sum(losses) / len(losses) if losses else 0.0
    )

    win_rate = (
        len(wins) / completed * 100
        if completed else 0.0
    )

    # 盈利因子 = 盈利交易总额 / 亏损交易总额的绝对值
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))

    if gross_loss > 0:
        profit_factor = gross_profit / gross_loss
    elif gross_profit > 0:
        profit_factor = float("inf")
    else:
        profit_factor = 0.0

    # 所有买入和卖出产生的手续费
    total_fees = sum(
        trade.get("fee", 0.0)
        for trade in trades
    )

    buy_fees = sum(
        trade.get("fee", 0.0)
        for trade in buys
    )

    sell_fees = sum(
        trade.get("fee", 0.0)
        for trade in sells
    )

    # 最大回撤
    peak = 0.0
    max_drawdown = 0.0

    for item in equity_curve:
        equity = item["equity"]
        peak = max(peak, equity)

        if peak > 0:
            drawdown = (peak - equity) / peak
            max_drawdown = max(max_drawdown, drawdown)

    # 根据权益曲线计算每日收益率
    equities = [
        item["equity"]
        for item in equity_curve
        if item["equity"] > 0
    ]

    daily_returns = []

    for i in range(1, len(equities)):
        previous_equity = equities[i - 1]
        current_equity = equities[i]

        daily_return = current_equity / previous_equity - 1
        daily_returns.append(daily_return)

    annualized_volatility = 0.0
    sharpe_ratio = 0.0

    if len(daily_returns) >= 2:
        mean_return = (
            sum(daily_returns) / len(daily_returns)
        )

        variance = sum(
            (r - mean_return) ** 2
            for r in daily_returns
        ) / (len(daily_returns) - 1)

        daily_volatility = sqrt(variance)

        annualized_volatility = (
            daily_volatility * sqrt(252)
        )

        if daily_volatility > 0:
            sharpe_ratio = (
                mean_return / daily_volatility
            ) * sqrt(252)

    # 年化收益率：初步估算，后续可进一步校准
    total_return = result["total_return"]
    annualized_return = 0.0

    if len(equities) > 1 and total_return > -100:
        total_days = len(equities)

        annualized_return = (
            (1 + total_return / 100)
            ** (252 / total_days) - 1
        ) * 100

    return {
        "completed_trades": completed,
        "buy_orders": len(buys),
        "sell_orders": len(sells),
        "winning_trades": len(wins),
        "losing_trades": len(losses),
        "win_rate": round(win_rate, 2),
        "average_win": round(avg_win, 2),
        "average_loss": round(avg_loss, 2),
        "gross_profit": round(gross_profit, 2),
        "gross_loss": round(gross_loss, 2),
        "profit_factor": (
            round(profit_factor, 3)
            if profit_factor != float("inf")
            else float("inf")
        ),
        "realized_pnl": round(realized, 2),
        "total_fees": round(total_fees, 2),
        "buy_fees": round(buy_fees, 2),
        "sell_fees": round(sell_fees, 2),
        "max_drawdown": round(max_drawdown * 100, 2),
        "annualized_return": round(annualized_return, 2),
        "annualized_volatility": round(
            annualized_volatility * 100, 2
        ),
        "sharpe_ratio": round(sharpe_ratio, 3),
    }

