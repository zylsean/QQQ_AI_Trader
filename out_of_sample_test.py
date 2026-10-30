
from pathlib import Path
from math import sqrt

from csv_data import load_adjusted_price_csv
from backtester import run_backtest
from benchmark import buy_and_hold_result
from performance import calculate_performance


def calculate_price_metrics(prices, total_return):
    """根据价格序列计算基准的风险收益指标。"""

    daily_returns = []

    for i in range(1, len(prices)):
        if prices[i - 1] > 0:
            daily_returns.append(
                prices[i] / prices[i - 1] - 1
            )

    annualized_return = 0.0
    annualized_volatility = 0.0
    sharpe_ratio = 0.0
    max_drawdown = 0.0

    if len(prices) > 1 and total_return > -100:
        annualized_return = (
            (1 + total_return / 100)
            ** (252 / len(prices)) - 1
        ) * 100

    if len(daily_returns) >= 2:
        mean_return = (
            sum(daily_returns) / len(daily_returns)
        )

        variance = sum(
            (r - mean_return) ** 2
            for r in daily_returns
        ) / (len(daily_returns) - 1)

        daily_volatility = sqrt(variance)

        annualized_volatility = (
            daily_volatility * sqrt(252) * 100
        )

        if daily_volatility > 0:
            sharpe_ratio = (
                mean_return / daily_volatility
            ) * sqrt(252)

    peak = 0.0

    for price in prices:
        peak = max(peak, price)

        if peak > 0:
            drawdown = (peak - price) / peak
            max_drawdown = max(max_drawdown, drawdown)

    return {
        "annualized_return": round(annualized_return, 2),
        "annualized_volatility": round(
            annualized_volatility, 2
        ),
        "sharpe_ratio": round(sharpe_ratio, 3),
        "max_drawdown": round(max_drawdown * 100, 2),
    }


# 读取历史数据
folder = Path(__file__).parent

data = load_adjusted_price_csv(
    str(folder / "QQQ_yahoo_10y.csv")
)

dates = data["dates"]
open_prices = data["open_prices"]
close_prices = data["close_prices"]

initial_cash = 10000.0
fee_rate = 0.001
short_window = 5
long_window = 10

position_fractions = [0.25, 0.275, 0.30]

# 前 70% 为训练期，后 30% 为测试期
split_index = int(len(dates) * 0.70)

periods = [
    ("训练期", 0, split_index),
    ("测试期", split_index, len(dates)),
]

print("===== QQQ 样本内与样本外回测 =====")
print("全部数据：", dates[0], "至", dates[-1])
print("总交易日数：", len(dates))
print("训练期：", dates[0], "至", dates[split_index - 1])
print("测试期：", dates[split_index], "至", dates[-1])
print("初始资金：", initial_cash)
print("均线参数：", short_window, "/", long_window)
print("手续费率：", fee_rate)

for period_name, start, end in periods:
    period_dates = dates[start:end]
    period_open = open_prices[start:end]
    period_close = close_prices[start:end]

    print("\n" + "=" * 50)
    print(period_name)
    print("日期：", period_dates[0], "至", period_dates[-1])
    print("交易日数：", len(period_dates))

    # 只在测试期输出 QQQ 买入持有基准
    if period_name == "测试期":
        benchmark = buy_and_hold_result(
            period_open,
            period_close,
            initial_cash=initial_cash,
            fee_rate=fee_rate,
        )

        benchmark_metrics = calculate_price_metrics(
            period_close,
            benchmark["total_return"],
        )

        print("\n--- 测试期 QQQ 买入并持有基准 ---")
        print("期末资产：", round(benchmark["final_equity"], 2))
        print("累计收益率：", benchmark["total_return"], "%")
        print(
            "年化收益率：",
            benchmark_metrics["annualized_return"], "%"
        )
        print(
            "年化波动率：",
            benchmark_metrics["annualized_volatility"], "%"
        )
        print(
            "夏普比率：",
            benchmark_metrics["sharpe_ratio"]
        )
        print(
            "最大回撤：",
            benchmark_metrics["max_drawdown"], "%"
        )

    for fraction in position_fractions:
        result = run_backtest(
            dates=period_dates,
            open_prices=period_open,
            close_prices=period_close,
            initial_history_close_prices=close_prices[:start],
            symbol="QQQ",
            initial_cash=initial_cash,
            short_window=short_window,
            long_window=long_window,
            fee_rate=fee_rate,
            position_fraction=fraction,
            auto_resume=True,
            resume_cooldown_days=10,
        )

        metrics = calculate_performance(result)

        print("\n--- 均线策略 ---")
        print("目标仓位：", f"{fraction * 100:.1f}%")
        print("期末资产：", round(result["final_equity"], 2))
        print("累计收益率：", result["total_return"], "%")
        print("年化收益率：", metrics["annualized_return"], "%")
        print(
            "年化波动率：",
            metrics["annualized_volatility"], "%"
        )
        print("夏普比率：", metrics["sharpe_ratio"])
        print("最大回撤：", result["max_drawdown"], "%")
        print("交易次数：", result["trade_count"])
        print("已完成交易数：", metrics["completed_trades"])
        print("交易胜率：", metrics["win_rate"], "%")
        print("已实现盈亏：", metrics["realized_pnl"])

        events = result["risk_status"]["events"]

        print(
            "暂停次数：",
            sum(
                e["type"] == "TRADING_PAUSED"
                for e in events
            ),
        )

        print(
            "自动恢复次数：",
            sum(
                e["type"] == "AUTO_RESUME"
                for e in events
            ),
        )

print("\n===== 结果说明 =====")
print("每个阶段、每档仓位均使用独立的 10000 美元模拟账户。")
print("测试期策略使用测试期之前的收盘价预热均线。")
print("基准的波动率和回撤根据测试期收盘价序列估算。")
print("夏普比率暂不扣除无风险利率。")
print("本结果仅用于历史模拟分析，不代表未来表现。")
