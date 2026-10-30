
from pathlib import Path
from math import sqrt
import csv

from csv_data import load_price_csv
from backtester import run_backtest
from strategy_adapter import generate_trend_50_200_targets


FOLDER = Path(__file__).parent
DATA_FILE = FOLDER / "QQQ_yahoo_10y.csv"
OUTPUT_FILE = FOLDER / "oos_momentum_robustness_results.csv"

INITIAL_CASH = 10000.0
POSITION_FRACTION = 0.20
SPLIT_RATIO = 0.70

LOOKBACKS = [42, 63, 84, 126]
FEE_RATES = [0.001, 0.0015, 0.002]


def materialize_targets(changes, initial_target=0):
    """将目标仓位变化转换成每日持续目标仓位。"""
    result = []
    current = initial_target

    for target in changes:
        if target is not None:
            current = target
        result.append(current)

    return result


def momentum_targets(close_prices, lookback):
    """
    收盘价高于 lookback 个交易日前的收盘价时持有；
    否则空仓。
    信号在收盘后产生，由回测引擎在下一交易日开盘执行。
    """
    targets = []
    current_target = 0

    for i, price in enumerate(close_prices):
        if i < lookback:
            targets.append(current_target)
            continue

        old_price = close_prices[i - lookback]

        if price > old_price:
            new_target = 1
        else:
            new_target = 0

        current_target = new_target
        targets.append(current_target)

    return targets


def calculate_metrics(result):
    """统一从回测权益曲线计算绩效指标。"""
    curve = result["equity_curve"]

    equities = [
        float(row["equity"])
        for row in curve
    ]

    if not equities:
        raise ValueError("回测没有生成权益曲线。")

    final_equity = equities[-1]
    total_return = final_equity / INITIAL_CASH - 1

    daily_returns = []

    for previous, current in zip(equities[:-1], equities[1:]):
        if previous > 0:
            daily_returns.append(current / previous - 1)

    n = len(daily_returns)

    if n > 0:
        annual_return = (
            (final_equity / INITIAL_CASH) ** (252 / n) - 1
            if final_equity > 0
            else -1.0
        )
    else:
        annual_return = 0.0

    if len(daily_returns) > 1:
        mean_return = sum(daily_returns) / len(daily_returns)

        variance = sum(
            (r - mean_return) ** 2
            for r in daily_returns
        ) / (len(daily_returns) - 1)

        daily_volatility = sqrt(variance)
        annual_volatility = daily_volatility * sqrt(252)

        if daily_volatility > 0:
            sharpe = mean_return / daily_volatility * sqrt(252)
        else:
            sharpe = 0.0
    else:
        annual_volatility = 0.0
        sharpe = 0.0

    peak = equities[0]
    max_drawdown = 0.0

    for equity in equities:
        peak = max(peak, equity)

        if peak > 0:
            drawdown = equity / peak - 1
            max_drawdown = min(max_drawdown, drawdown)

    total_fees = sum(
        float(trade.get("fee", 0))
        for trade in result["trades"]
    )

    return {
        "final_equity": final_equity,
        "total_return_pct": total_return * 100,
        "annual_return_pct": annual_return * 100,
        "annual_volatility_pct": annual_volatility * 100,
        "sharpe": sharpe,
        "max_drawdown_pct": max_drawdown * 100,
        "trade_count": result["trade_count"],
        "total_fees": total_fees,
    }


def run_one(
    dates,
    opens,
    closes,
    split,
    targets,
    fee_rate,
    strategy_name,
):
    """
    加入一个不交易的前置日，使前一日收盘信号
    能在第一个样本外交易日开盘执行。
    """
    previous_date = dates[split - 1]
    previous_close = closes[split - 1]

    test_dates = [previous_date] + dates[split:]
    test_opens = [previous_close] + opens[split:]
    test_closes = [previous_close] + closes[split:]

    # 前置日的目标代表此前收盘已经形成的信号。
    # 回测引擎在下一日开盘执行该目标。
    test_targets = [targets[split - 1]] + targets[split:]

    result = run_backtest(
        dates=test_dates,
        open_prices=test_opens,
        close_prices=test_closes,
        symbol="QQQ",
        initial_cash=INITIAL_CASH,
        fee_rate=fee_rate,
        position_fraction=POSITION_FRACTION,
        target_positions=test_targets,
    )

    metrics = calculate_metrics(result)
    metrics["strategy"] = strategy_name
    metrics["fee_rate_pct"] = fee_rate * 100
    metrics["oos_start"] = dates[split]
    metrics["oos_end"] = dates[-1]
    metrics["oos_days"] = len(dates) - split

    return metrics


def main():
    print("=" * 78)
    print("QQQ 样本外动量策略稳健性检验")
    print("PAPER 回测；不进行真实交易")
    print("=" * 78)

    data = load_price_csv(str(DATA_FILE))

    dates = [str(d)[:10] for d in data["dates"]]
    opens = [float(x) for x in data["open_prices"]]
    closes = [float(x) for x in data["close_prices"]]

    if not (len(dates) == len(opens) == len(closes)):
        raise ValueError("日期、开盘价、收盘价数量不一致。")

    if len(dates) < 300:
        raise ValueError("历史数据不足以进行本次测试。")

    split = int(len(dates) * SPLIT_RATIO)

    if split <= 200 or split >= len(dates):
        raise ValueError("样本外切分位置异常。")

    print(f"数据区间：{dates[0]} 至 {dates[-1]}")
    print(f"样本外区间：{dates[split]} 至 {dates[-1]}")
    print(f"样本外交易日：{len(dates) - split}")
    print(f"初始资金：${INITIAL_CASH:.2f}")
    print(f"入场仓位比例：{POSITION_FRACTION:.0%}")
    print("执行规则：前一交易日收盘信号，下一交易日开盘执行")
    print("注意：入场仓位比例不等于持续目标资金暴露。")

    # 生成 50/200 趋势目标，保留全历史预热过程。
    trend_changes = generate_trend_50_200_targets(closes)
    trend_all = materialize_targets(trend_changes)

    # 买入持有：样本外首日收盘后形成买入目标，
    # 因此从下一交易日开盘开始持有。
    buy_hold_all = [0] * len(dates)
    for i in range(split, len(dates)):
        buy_hold_all[i] = 1

    scenarios = []

    for fee_rate in FEE_RATES:
        # 基准策略
        scenarios.append(
            run_one(
                dates, opens, closes, split,
                buy_hold_all, fee_rate,
                "买入持有（20%入场仓位）",
            )
        )

        scenarios.append(
            run_one(
                dates, opens, closes, split,
                trend_all, fee_rate,
                "50/200 趋势",
            )
        )

        # 不同动量回看周期
        for lookback in LOOKBACKS:
            targets = momentum_targets(closes, lookback)

            scenarios.append(
                run_one(
                    dates, opens, closes, split,
                    targets, fee_rate,
                    f"{lookback}日动量",
                )
            )

    fields = [
        "strategy",
        "fee_rate_pct",
        "oos_start",
        "oos_end",
        "oos_days",
        "final_equity",
        "total_return_pct",
        "annual_return_pct",
        "annual_volatility_pct",
        "sharpe",
        "max_drawdown_pct",
        "trade_count",
        "total_fees",
    ]

    with open(
        OUTPUT_FILE, "w", encoding="utf-8-sig", newline=""
    ) as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()

        for row in scenarios:
            writer.writerow({
                "strategy": row["strategy"],
                "fee_rate_pct": round(row["fee_rate_pct"], 4),
                "oos_start": row["oos_start"],
                "oos_end": row["oos_end"],
                "oos_days": row["oos_days"],
                "final_equity": round(row["final_equity"], 2),
                "total_return_pct": round(row["total_return_pct"], 4),
                "annual_return_pct": round(row["annual_return_pct"], 4),
                "annual_volatility_pct": round(
                    row["annual_volatility_pct"], 4
                ),
                "sharpe": round(row["sharpe"], 4),
                "max_drawdown_pct": round(
                    row["max_drawdown_pct"], 4
                ),
                "trade_count": row["trade_count"],
                "total_fees": round(row["total_fees"], 2),
            })

    print("\n【手续费 0.1% 时的策略比较】")
    print(
        f"{'策略':<25}{'期末资产':>12}{'总收益%':>10}"
        f"{'年化%':>9}{'夏普':>8}{'最大回撤%':>12}"
        f"{'交易次数':>9}"
    )

    for row in scenarios:
        if abs(row["fee_rate_pct"] - 0.1) > 1e-8:
            continue

        print(
            f"{row['strategy']:<25}"
            f"{row['final_equity']:>12.2f}"
            f"{row['total_return_pct']:>10.2f}"
            f"{row['annual_return_pct']:>9.2f}"
            f"{row['sharpe']:>8.3f}"
            f"{row['max_drawdown_pct']:>12.2f}"
            f"{row['trade_count']:>9}"
        )

    print("\n【63 日动量手续费敏感性】")
    print(
        f"{'单边手续费%':>12}{'期末资产':>12}"
        f"{'总收益%':>10}{'夏普':>8}"
        f"{'交易次数':>10}{'总手续费':>12}"
    )

    for row in scenarios:
        if row["strategy"] != "63日动量":
            continue

        print(
            f"{row['fee_rate_pct']:>12.2f}"
            f"{row['final_equity']:>12.2f}"
            f"{row['total_return_pct']:>10.2f}"
            f"{row['sharpe']:>8.3f}"
            f"{row['trade_count']:>10}"
            f"{row['total_fees']:>12.2f}"
        )

    print("\n【动量回看周期敏感性：单边手续费 0.1%】")
    print(
        f"{'周期':>10}{'期末资产':>12}{'总收益%':>10}"
        f"{'夏普':>8}{'最大回撤%':>12}"
        f"{'交易次数':>10}{'手续费':>10}"
    )

    for row in scenarios:
        if (
            row["strategy"].endswith("日动量")
            and abs(row["fee_rate_pct"] - 0.1) < 1e-8
        ):
            print(
                f"{row['strategy']:>10}"
                f"{row['final_equity']:>12.2f}"
                f"{row['total_return_pct']:>10.2f}"
                f"{row['sharpe']:>8.3f}"
                f"{row['max_drawdown_pct']:>12.2f}"
                f"{row['trade_count']:>10}"
                f"{row['total_fees']:>10.2f}"
            )

    print("\n【输出文件】")
    print(OUTPUT_FILE.name)
    print("\n稳健性测试完成。")
    print("不同参数的历史结果不构成未来收益保证。")


if __name__ == "__main__":
    main()

