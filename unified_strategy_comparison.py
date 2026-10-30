
from pathlib import Path
from math import sqrt
from statistics import mean, stdev

from csv_data import load_price_csv
from backtester import run_backtest
from strategy_adapter import generate_trend_50_200_targets


INITIAL_CASH = 10000.0
FEE_RATE = 0.001
POSITION_FRACTION = 0.20
TRADING_DAYS = 252


def generate_63d_momentum_targets(close_prices):
    """63 日动量：只使用当日及此前已经出现的收盘价。"""
    targets = []
    current_target = 0

    for i, price in enumerate(close_prices):
        if i < 63:
            targets.append(None)
            continue

        new_target = 1 if price > close_prices[i - 63] else 0

        if new_target != current_target:
            targets.append(new_target)
            current_target = new_target
        else:
            targets.append(None)

    return targets


def calculate_metrics(result):
    """从统一回测引擎的权益曲线计算绩效指标。"""
    equity = [item["equity"] for item in result["equity_curve"]]

    # 将初始资金纳入第一段收益的计算。
    previous = [result["initial_cash"]] + equity[:-1]
    daily_returns = [
        current / prior - 1
        for current, prior in zip(equity, previous)
    ]

    final_equity = result["final_equity"]
    total_return = final_equity / result["initial_cash"] - 1

    years = len(daily_returns) / TRADING_DAYS
    annual_return = (
        (final_equity / result["initial_cash"]) ** (1 / years) - 1
        if years > 0 and final_equity > 0
        else -1.0
    )

    daily_volatility = (
        stdev(daily_returns) if len(daily_returns) > 1 else 0.0
    )
    annual_volatility = daily_volatility * sqrt(TRADING_DAYS)

    sharpe = (
        mean(daily_returns) / daily_volatility * sqrt(TRADING_DAYS)
        if daily_volatility > 0
        else 0.0
    )

    total_fees = sum(trade["fee"] for trade in result["trades"])

    return {
        "total_return": total_return * 100,
        "annual_return": annual_return * 100,
        "annual_volatility": annual_volatility * 100,
        "sharpe": sharpe,
        "max_drawdown": result["max_drawdown"],
        "trades": result["trade_count"],
        "fees": total_fees,
        "final_equity": final_equity,
    }


def main():
    folder = Path(__file__).parent
    data = load_price_csv(str(folder / "QQQ_yahoo_10y.csv"))

    dates = data["dates"]
    open_prices = data["open_prices"]
    close_prices = data["close_prices"]

    strategies = {
        "买入持有（统一仓位）": [1] * len(dates),
        "50/200 趋势": generate_trend_50_200_targets(close_prices),
        "63 日动量": generate_63d_momentum_targets(close_prices),
    }

    results = {}

    for name, targets in strategies.items():
        result = run_backtest(
            dates=dates,
            open_prices=open_prices,
            close_prices=close_prices,
            symbol="QQQ",
            initial_cash=INITIAL_CASH,
            fee_rate=FEE_RATE,
            position_fraction=POSITION_FRACTION,
            target_positions=targets,
        )
        results[name] = calculate_metrics(result)

    print("=" * 92)
    print("统一规则策略比较（PAPER 回测）")
    print("数据区间：", dates[0], "至", dates[-1])
    print("初始资金：", INITIAL_CASH)
    print("单边手续费：", FEE_RATE * 100, "%")
    print("单次开仓仓位上限：", POSITION_FRACTION * 100, "%")
    print("执行方式：前一交易日收盘信号，下一交易日开盘执行")
    print("注意：历史回测不代表未来收益")
    print("=" * 92)

    header = (
        f"{'策略':<22}"
        f"{'期末资产':>12}"
        f"{'累计收益%':>12}"
        f"{'年化收益%':>12}"
        f"{'年化波动%':>12}"
        f"{'夏普':>9}"
        f"{'最大回撤%':>12}"
        f"{'成交次数':>10}"
        f"{'手续费':>12}"
    )
    print(header)
    print("-" * len(header))

    for name, metrics in results.items():
        print(
            f"{name:<22}"
            f"{metrics['final_equity']:>12.2f}"
            f"{metrics['total_return']:>12.2f}"
            f"{metrics['annual_return']:>12.2f}"
            f"{metrics['annual_volatility']:>12.2f}"
            f"{metrics['sharpe']:>9.3f}"
            f"{metrics['max_drawdown']:>12.2f}"
            f"{metrics['trades']:>10}"
            f"{metrics['fees']:>12.2f}"
        )

    print("\n【初步排名参考】")
    best_return = max(
        results.items(),
        key=lambda item: item[1]["total_return"]
    )
    best_sharpe = max(
        results.items(),
        key=lambda item: item[1]["sharpe"]
    )
    lowest_drawdown = min(
        results.items(),
        key=lambda item: item[1]["max_drawdown"]
    )

    print("累计收益最高：", best_return[0])
    print("夏普比率最高：", best_sharpe[0])
    print("最大回撤最低：", lowest_drawdown[0])


if __name__ == "__main__":
    main()

