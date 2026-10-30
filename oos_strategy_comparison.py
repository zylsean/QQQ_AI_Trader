
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


def materialize_targets(targets, initial_state=0):
    """将状态变化信号展开为每天明确的 0/1 目标状态。"""
    state = initial_state
    result = []

    for target in targets:
        if target is not None:
            state = int(target)
        result.append(state)

    return result


def calculate_metrics(result):
    equity = [x["equity"] for x in result["equity_curve"]]
    previous = [result["initial_cash"]] + equity[:-1]

    daily_returns = [
        current / prior - 1
        for current, prior in zip(equity, previous)
    ]

    years = len(equity) / TRADING_DAYS
    final_equity = result["final_equity"]

    annual_return = (
        ((final_equity / result["initial_cash"]) ** (1 / years) - 1)
        * 100
        if years > 0 and final_equity > 0
        else -100.0
    )

    daily_vol = stdev(daily_returns) if len(daily_returns) > 1 else 0
    annual_vol = daily_vol * sqrt(TRADING_DAYS) * 100

    sharpe = (
        mean(daily_returns) / daily_vol * sqrt(TRADING_DAYS)
        if daily_vol > 0
        else 0.0
    )

    fees = sum(t["fee"] for t in result["trades"])

    return {
        "final": final_equity,
        "return": (final_equity / result["initial_cash"] - 1) * 100,
        "annual": annual_return,
        "vol": annual_vol,
        "sharpe": sharpe,
        "drawdown": result["max_drawdown"],
        "trades": result["trade_count"],
        "fees": fees,
    }


def main():
    folder = Path(__file__).parent
    data = load_price_csv(str(folder / "QQQ_yahoo_10y.csv"))

    dates = data["dates"]
    opens = data["open_prices"]
    closes = data["close_prices"]

    # 前 70% 用作研究区间，后 30% 用作样本外测试。
    split = int(len(dates) * 0.70)

    test_dates = dates[split:]
    test_opens = opens[split:]
    test_closes = closes[split:]

    full_trend = materialize_targets(
        generate_trend_50_200_targets(closes)
    )
    full_momentum = materialize_targets(
        generate_63d_momentum_targets(closes)
    )

    # 测试账户从现金开始。首个测试日的目标状态取自历史信号；
    # 实际成交仍遵守下一交易日开盘执行。
    strategies = {
        "买入持有（20%仓位）": [1] * len(test_dates),
        "50/200 趋势": full_trend[split:],
        "63 日动量": full_momentum[split:],
    }

    results = {}

    for name, targets in strategies.items():
        result = run_backtest(
            dates=test_dates,
            open_prices=test_opens,
            close_prices=test_closes,
            symbol="QQQ",
            initial_cash=INITIAL_CASH,
            fee_rate=FEE_RATE,
            position_fraction=POSITION_FRACTION,
            target_positions=targets,
        )
        results[name] = calculate_metrics(result)

    print("=" * 100)
    print("样本外策略比较（PAPER）")
    print("研究区间：", dates[0], "至", dates[split - 1])
    print("测试区间：", test_dates[0], "至", test_dates[-1])
    print("初始资金：", INITIAL_CASH)
    print("单边手续费：", FEE_RATE * 100, "%")
    print("开仓仓位上限：", POSITION_FRACTION * 100, "%")
    print("成交规则：前一交易日收盘信号，下一交易日开盘执行")
    print("提示：样本外结果仍不代表未来收益")
    print("=" * 100)

    print(
        f"{'策略':<22}{'期末资产':>12}{'累计收益%':>12}"
        f"{'年化收益%':>12}{'波动%':>10}{'夏普':>9}"
        f"{'回撤%':>10}{'成交次数':>10}{'手续费':>12}"
    )

    for name, m in results.items():
        print(
            f"{name:<22}{m['final']:>12.2f}{m['return']:>12.2f}"
            f"{m['annual']:>12.2f}{m['vol']:>10.2f}"
            f"{m['sharpe']:>9.3f}{m['drawdown']:>10.2f}"
            f"{m['trades']:>10}{m['fees']:>12.2f}"
        )


if __name__ == "__main__":
    main()

