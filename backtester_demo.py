from datetime import date, timedelta

from backtester import run_backtest
from benchmark import buy_and_hold_result
from performance import calculate_performance

dates = []
opens = []
closes = []

price = 100.0
start_date = date(2026, 1, 5)

for i in range(100):
    dates.append(
        (start_date + timedelta(days=i)).isoformat()
    )

    # 前30个数据点下跌，之后逐渐上涨。
    if i < 30:
        price -= 0.5
    else:
        price += 0.8

    opens.append(round(price - 0.2, 2))
    closes.append(round(price, 2))


result = run_backtest(
    dates=dates,
    open_prices=opens,
    close_prices=closes,
    symbol="QQQ",
)
stats = calculate_performance(result)

benchmark = buy_and_hold_result(
    open_prices=opens,
    close_prices=closes,
    initial_cash=10000.0,
    fee_rate=0.001,
)
print("===== 回测报告 =====")
print("标的：", result["symbol"])
print("初始资金：", result["initial_cash"])
print("期末资产：", result["final_equity"])
print("累计收益率：", result["total_return"], "%")
print("最大回撤：", result["max_drawdown"], "%")
print("成交次数：", result["trade_count"])
print("剩余现金：", result["cash"])
print("最终持仓：", result["positions"])
print("风险状态：", result["risk_status"])

print("\n===== 成交记录 =====")
for trade in result["trades"]:
    print(trade)

print("\n===== 最近5个交易日的资产记录 =====")
for item in result["equity_curve"][-5:]:
    print(item)
print("\n===== 交易绩效 =====")
print("已完成交易数：", stats["completed_trades"])
print("胜率：", stats["win_rate"], "%")
print("平均盈利：", stats["average_win"])
print("平均亏损：", stats["average_loss"])
print("已实现盈亏：", stats["realized_pnl"])
print("绩效模块最大回撤：", stats["max_drawdown"], "%")

print("\n===== 买入并持有基准 =====")
print("基准期末资产：", benchmark["final_equity"])
print("基准收益率：", benchmark["total_return"], "%")
print(
    "策略与基准收益率差：",
    round(result["total_return"] - benchmark["total_return"], 2),
    "个百分点",
)
