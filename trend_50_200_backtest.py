
from pathlib import Path

from csv_data import load_price_csv
from backtester import run_backtest
from strategy_adapter import generate_trend_50_200_targets


folder = Path(__file__).parent
data = load_price_csv(str(folder / "QQQ_yahoo_10y.csv"))

dates = data["dates"]
open_prices = data["open_prices"]
close_prices = data["close_prices"]

targets = generate_trend_50_200_targets(close_prices)

result = run_backtest(
    dates=dates,
    open_prices=open_prices,
    close_prices=close_prices,
    symbol="QQQ",
    initial_cash=10000.0,
    fee_rate=0.001,
    position_fraction=0.20,
    target_positions=targets,
)

print("===== 50/200 趋势策略：统一回测 =====")
print("数据区间：", dates[0], "至", dates[-1])
print("初始资金：", result["initial_cash"])
print("期末资产：", result["final_equity"])
print("累计收益率：", result["total_return"], "%")
print("最大回撤：", result["max_drawdown"], "%")
print("交易次数：", result["trade_count"])
print("期末现金：", result["cash"])
print("期末持仓：", result["positions"])
print("风控状态：", result["risk_status"]["level"])
print("总成交记录：", len(result["trades"]))

