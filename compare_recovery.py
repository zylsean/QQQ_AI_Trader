

import csv
from backtester import run_backtest


DATA_FILE = "QQQ_yahoo_10y.csv"


def load_data(filename):
    dates = []
    open_prices = []
    close_prices = []

    with open(filename, "r", newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)

        for row in reader:
            dates.append(row["Date"])
            open_prices.append(float(row["Open"]))
            close_prices.append(float(row["Close"]))

    return dates, open_prices, close_prices


def print_result(name, result):
    print("\n" + "=" * 45)
    print(name)
    print("=" * 45)

    print("期末资产：", round(result["final_equity"], 2))
    print("收益率：", round(result["total_return"], 2), "%")
    print("最大回撤：", round(result["max_drawdown"], 2), "%")
    print("交易次数：", result["trade_count"])

    risk_status = result.get("risk_status", {})
    print("最终风险状态：", risk_status)

    trades = result.get("trades", [])
    print("成交记录数：", len(trades))

    events = risk_status.get("events", [])
    print("风险事件：")
    for event in events:
        if event.get("type") in (
            "TRADING_PAUSED",
            "AUTO_RESUME",
            "SEVERE_DRAWDOWN",
        ):
            print(event)


dates, open_prices, close_prices = load_data(DATA_FILE)

manual_result = run_backtest(
    dates,
    open_prices,
    close_prices,
    symbol="QQQ",
    initial_cash=10000.0,
    short_window=5,
    long_window=10,
    fee_rate=0.001,
    position_fraction=0.30,
    auto_resume=False,
)

auto_result = run_backtest(
    dates,
    open_prices,
    close_prices,
    symbol="QQQ",
    initial_cash=10000.0,
    short_window=5,
    long_window=10,
    fee_rate=0.001,
    position_fraction=0.30,
    auto_resume=True,
    resume_cooldown_days=10,
)

print_result("模式 A：手动恢复", manual_result)
print_result("模式 B：自动恢复", auto_result)
