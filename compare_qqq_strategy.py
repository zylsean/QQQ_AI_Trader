


from pathlib import Path
from csv_data import load_adjusted_price_csv
from backtester import run_backtest

folder = Path(__file__).parent
data = load_adjusted_price_csv(
    str(folder / "QQQ_yahoo_10y.csv")
)

initial_cash = 10000.0
fee_rate = 0.001
position_fractions = [0.25, 0.275, 0.30]

print("===== QQQ 不同目标仓位回测比较 =====")
print("回测区间：", data["dates"][0], "至", data["dates"][-1])
print("交易日数量：", len(data["dates"]))
print("初始资金：", initial_cash)
print("均线参数：5 日 / 10 日")
print("手续费率：", fee_rate)

for fraction in position_fractions:
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
        auto_resume=True,
        resume_cooldown_days=10,
    )

    print("\n" + "-" * 45)
    print("目标仓位：", f"{fraction * 100:.1f}%")
    print("期末资产：", result["final_equity"])
    print("累计收益率：", result["total_return"], "%")
    print("最大回撤：", result["max_drawdown"], "%")
    print("交易次数：", result["trade_count"])
    print("期末现金：", result["cash"])
    print("期末持仓：", result["positions"])
    print("最终风控状态：", result["risk_status"])
    events = result["risk_status"]["events"]

    warning_count = sum(
        event["type"] == "DRAWDOWN_WARNING"
        for event in events
    )

    paused_count = sum(
        event["type"] == "TRADING_PAUSED"
        for event in events
    )

    resume_count = sum(
        event["type"] == "AUTO_RESUME"
        for event in events
    )

    print("回撤预警次数：", warning_count)
    print("暂停交易次数：", paused_count)
    print("自动恢复次数：", resume_count)
print("\n注意：三组测试使用相同历史数据、均线参数和手续费。")
print("历史回测结果不代表未来表现。")
