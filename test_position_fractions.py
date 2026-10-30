

from pathlib import Path
from csv_data import load_adjusted_price_csv
from backtester import run_backtest

folder = Path(__file__).parent
data = load_adjusted_price_csv(
    str(folder / "QQQ_yahoo_10y.csv")
)

initial_cash = 10000.0
fee_rate = 0.001
fractions = [0.20, 0.25, 0.30]

print("===== QQQ 不同目标仓位对照实验 =====")
print("回测区间：", data["dates"][0], "至", data["dates"][-1])
print("初始资金：", initial_cash)
print("均线参数：5 日 / 10 日")
print("手续费率：", fee_rate)
print()

for fraction in fractions:
    result = run_backtest(
        dates=data["dates"],
        open_prices=data["open_prices"],
        close_prices=data["close_prices"],
        symbol="QQQ",
        initial_cash=initial_cash,
        short_window=5,
        long_window=10,
        fee_rate=fee_rate,
        position_fraction=fraction,
    )
    print("风险事件列表：", result["risk_status"]["events"])
    print("最后 10 条交易记录：")
    for trade in result["trades"][-10:]:
        print(trade)
        
    print("暂停前后净值检查：")
    for point in result["equity_curve"]:
        if "2022-11-17" <= point["date"] <= "2022-12-05":
            print(
                point["date"],
                "资产：", point["equity"],
                "回撤：", point["drawdown"]
            )

    pause_days = [
        point for point in result["equity_curve"]
        if point["drawdown"] >= 0.10
    ]

    if pause_days:
        print("首次达到 10% 回撤的日期：", pause_days[0]["date"])
        print("当日回撤：", pause_days[0]["drawdown"])
    else:
        print("没有达到 10% 回撤")


    final_equity = result["final_equity"]
    total_return = result["total_return"]
    max_drawdown = result["max_drawdown"]
    trade_count = result["trade_count"]
    cash = result["cash"]

    positions = result["positions"]
    position_qty = positions.get("QQQ", {}).get("qty", 0)

    print("目标仓位：", f"{fraction:.0%}")
    print("期末资产：", final_equity)
    print("收益率：", f"{total_return:.2f}%")
    print("最大回撤：", f"{max_drawdown:.2f}%")
    print("交易次数：", trade_count)
    print("期末现金：", cash)
    print("期末持股数量：", position_qty)
    print("风险状态：", result["risk_status"]["level"])
    print("风险事件数量：",
len(result["risk_status"]["events"]))
    for event in result["risk_status"]["events"]:

        print("风险事件：", event)
    print("-" * 35)
