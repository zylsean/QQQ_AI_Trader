

from csv_data import load_price_csv
from backtester import run_backtest
from performance import calculate_performance
from benchmark import buy_and_hold_result


# 把 CSV 文件放在 Documents 目录中，
# 并将文件名改成 qqq_history.csv。
csv_path = "~/Documents/qqq_history.csv"

import os
csv_path = os.path.expanduser(csv_path)

data = load_price_csv(csv_path)

dates = data["dates"]
opens = data["open_prices"]
closes = data["close_prices"]

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

print("===== CSV 行情信息 =====")
print("数据条数：", len(dates))
print("起始日期：", dates[0])
print("结束日期：", dates[-1])

print("\n===== 均线策略 =====")
print("期末资产：", result["final_equity"])
print("累计收益率：", result["total_return"], "%")
print("最大回撤：", result["max_drawdown"], "%")
print("成交次数：", result["trade_count"])
print("已完成交易：", stats["completed_trades"])
print("胜率：", stats["win_rate"], "%")

print("\n===== 买入并持有基准 =====")
print("基准期末资产：", benchmark["final_equity"])
print("基准收益率：", benchmark["total_return"], "%")
print(
    "收益率差：",
    round(result["total_return"] - benchmark["total_return"], 2),
    "个百分点",
)
