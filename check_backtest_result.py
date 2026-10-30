

from csv_data import load_price_csv
from backtester import run_backtest
from performance import calculate_performance
from benchmark import buy_and_hold_result
import os

# 读取之前创建的模拟行情
path = os.path.expanduser("~/Documents/qqq_history.csv")
data = load_price_csv(path)

# 运行均线策略
result = run_backtest(
    dates=data["dates"],
    open_prices=data["open_prices"],
    close_prices=data["close_prices"],
    symbol="QQQ",
    initial_cash=10000.0,
    short_window=20,
    long_window=50,
    fee_rate=0.001
)

# 计算绩效和买入并持有基准
stats = calculate_performance(result)
benchmark = buy_and_hold_result(
    data["open_prices"],
    data["close_prices"],
    initial_cash=10000.0,
    fee_rate=0.001
)

print("===== 1. 回测基本信息 =====")
print("交易标的：", result["symbol"])
print("初始资金：", result["initial_cash"])
print("期末资产：", result["final_equity"])
print("累计收益率：", result["total_return"], "%")
print("最大回撤：", result["max_drawdown"], "%")

print("\n===== 2. 交易记录 =====")
print("成交次数：", result["trade_count"])
print("交易记录条数：", len(result["trades"]))

for trade in result["trades"]:
    print(trade)

print("\n===== 3. 绩效统计 =====")
for key, value in stats.items():
    print(key, ":", value)

print("\n===== 4. 资产曲线检查 =====")
curve = result["equity_curve"]
print("曲线记录数：", len(curve))
print("前 3 条：", curve[:3])
print("最后 3 条：", curve[-3:])

print("\n===== 5. 基准比较 =====")
print("基准期末资产：", benchmark["final_equity"])
print("基准收益率：", benchmark["total_return"], "%")

# 检查基础一致性
print("\n===== 6. 自动检查 =====")
print("行情条数与曲线条数一致：",
      len(data["dates"]) == len(curve))
print("成交次数与交易记录一致：",
      result["trade_count"] == len(result["trades"]))
print("期末资产与曲线最后一条一致：",
      result["final_equity"] == curve[-1]["equity"])
print("期末资产大于零：", result["final_equity"] > 0)
print("\n===== 7. 最大回撤专项检查 =====")

curve = result["equity_curve"]

peak = curve[0]["equity"]
max_dd = 0.0
max_dd_date = None

for item in curve:
    equity = item["equity"]

    if equity > peak:
        peak = equity

    dd = (peak - equity) / peak if peak > 0 else 0.0

    if dd > max_dd:
        max_dd = dd
        max_dd_date = item["date"]

print("资产曲线最低资产：", min(x["equity"] for x in curve))
print("资产曲线最高资产：", max(x["equity"] for x in curve))
print("独立计算的最大回撤：", round(max_dd * 100, 2), "%")
print("最大回撤发生日期：", max_dd_date)
print("原程序最大回撤：", result["max_drawdown"], "%")

print("\n===== 8. 资产曲线波动检查 =====")

curve = result["equity_curve"]

declines = []

for i in range(1, len(curve)):
    previous = curve[i - 1]["equity"]
    current = curve[i]["equity"]

    if current < previous:
        declines.append({
            "date": curve[i]["date"],
            "previous_equity": previous,
            "current_equity": current,
            "change": round(current - previous, 2)
        })

print("资产下降的天数：", len(declines))
print("前 10 条下降记录：", declines[:10])
print("前 10 条资产记录：", curve[:10])

