

from pathlib import Path
from csv_data import load_adjusted_price_csv
from backtester import run_backtest
from benchmark import buy_and_hold_result, buy_and_hold_adjusted_result

folder = Path(__file__).parent
data = load_adjusted_price_csv(
    str(folder / "QQQ_yahoo_10y.csv")
)

initial_cash = 10000.0
fee_rate = 0.001

# 均线策略：使用普通开盘价成交、普通收盘价计算信号
strategy = run_backtest(
    dates=data["dates"],
    open_prices=data["open_prices"],
    close_prices=data["close_prices"],
    symbol="QQQ",
    initial_cash=initial_cash,
    short_window=5,
    long_window=10,
    fee_rate=fee_rate,
)

# 普通价格口径的买入并持有基准
price_benchmark = buy_and_hold_result(
    data["open_prices"],
    data["close_prices"],
    initial_cash=initial_cash,
    fee_rate=fee_rate,
)

# 调整收盘价口径的总回报估算
total_return_benchmark = buy_and_hold_adjusted_result(
    data["adj_close_prices"],
    initial_cash=initial_cash,
    fee_rate=fee_rate,
)

print("===== Yahoo Finance：均线策略与基准比较 =====")
print("回测区间：", data["dates"][0], "至", data["dates"][-1])
print("交易日数量：", len(data["dates"]))

print("\n--- 5日/10日均线策略 ---")
print("期末资产：", strategy["final_equity"])
print("收益率：", strategy["total_return"], "%")
print("最大回撤：", strategy["max_drawdown"], "%")
print("交易次数：", strategy["trade_count"])

print("\n--- 普通价格买入并持有 ---")
print("期末资产：", price_benchmark["final_equity"])
print("收益率：", price_benchmark["total_return"], "%")

print("\n--- 调整收盘价总回报估算 ---")
print("期末资产：", total_return_benchmark["final_equity"])
print("收益率：", total_return_benchmark["total_return"], "%")

print("\n注意：以上基准的持仓与分红处理方式不同，"
      "调整收盘价结果是估算值，不是完整的分红再投资账本。")
