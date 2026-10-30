

from pathlib import Path
from csv_data import load_price_csv
from backtester import run_backtest

folder = Path(__file__).parent
data = load_price_csv(str(folder / "QQQ_history.csv"))

result = run_backtest(
    dates=data["dates"],
    open_prices=data["open_prices"],
    close_prices=data["close_prices"],
    symbol="QQQ",
    initial_cash=10000.0,
    short_window=5,
    long_window=10,
    fee_rate=0.001,
)

print("===== QQQ 历史行情回测 =====")
print("行情条数：", len(data["dates"]))
print("回测区间：", data["dates"][0], "至", data["dates"][-1])
print("均线参数：5 日 / 10 日")
print("初始资金：", 10000.0)
print("最终资产：", round(result["final_equity"], 2))
print("策略收益率：", result["total_return"], "%")
print("最大回撤：", result["max_drawdown"], "%")
print("交易次数：", result["trade_count"])
print("最终风险状态：", result["risk_status"])
print("持仓：", result["positions"])
print("===== 回测结束 =====")
