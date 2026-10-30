
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

print("===== 50/200 策略诊断 =====")

print("\n【期末资产核对】")
print("期末现金：", result["cash"])
print("期末持仓：", result["positions"])
print("回测引擎期末资产：", result["final_equity"])
print("累计收益率：", result["total_return"], "%")
print("最大回撤：", result["max_drawdown"], "%")

print("\n【成交记录】")
for trade in result["trades"]:
    print(trade)

print("\n【风控状态与事件】")
print(result["risk_status"])

print("\n【期末权益曲线记录】")
print(result["equity_curve"][-1])

print("\n【最后 10 条权益记录】")
for item in result["equity_curve"][-10:]:
    print(item)

