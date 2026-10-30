
from pathlib import Path
from math import sqrt
import csv

from csv_data import load_price_csv
from backtester import run_backtest
from strategy_adapter import generate_trend_50_200_targets


DATA_FILE = "QQQ_yahoo_10y.csv"

INITIAL_CASH = 10000.0
FEE_RATE = 0.001
POSITION_FRACTION = 0.20

OOS_START_DATE = "2023-10-18"
TRAIN_DAYS = 756
TEST_DAYS = 252
MOMENTUM_LOOKBACKS = [42, 63, 84, 126]

RESULT_FILE = "walk_forward_momentum_results.csv"
SELECTION_FILE = "walk_forward_momentum_selections.csv"


def momentum_targets(close_prices, lookback):
    """使用当日收盘价与 lookback 个交易日前的收盘价生成目标仓位。"""
    targets = []

    for i, price in enumerate(close_prices):
        if i < lookback:
            targets.append(0)
        else:
            targets.append(
                1 if price > close_prices[i - lookback] else 0
            )

    return targets


def materialize_targets(change_targets):
    """把状态变化事件转换成连续的 0/1 目标仓位。"""
    state = 0
    states = []

    for target in change_targets:
        if target is not None:
            state = int(target)

        states.append(state)

    return states


def calculate_metrics(result):
    """
    统一指标口径。
    收益率直接根据期末资产计算，不使用回测器的 total_return 字段。
    """
    equity_curve = result["equity_curve"]
    equities = [float(row["equity"]) for row in equity_curve]

    if not equities:
        raise ValueError("权益曲线为空，无法计算指标")

    final_equity = float(result["final_equity"])

    # 统一收益率口径，避免把 0.099 当成 9.9 再乘 100。
    total_return = final_equity / INITIAL_CASH - 1.0

    daily_returns = []

    for previous, current in zip(equities[:-1], equities[1:]):
        if previous > 0:
            daily_returns.append(current / previous - 1.0)

    if len(daily_returns) >= 2:
        average_return = sum(daily_returns) / len(daily_returns)
        variance = sum(
            (value - average_return) ** 2
            for value in daily_returns
        ) / (len(daily_returns) - 1)
        daily_volatility = sqrt(variance)
    else:
        average_return = 0.0
        daily_volatility = 0.0

    sharpe = (
        average_return / daily_volatility * sqrt(252)
        if daily_volatility > 0
        else 0.0
    )

    peak = equities[0]
    max_drawdown = 0.0

    for equity in equities:
        peak = max(peak, equity)

        if peak > 0:
            drawdown = equity / peak - 1.0
            max_drawdown = min(max_drawdown, drawdown)

    years = len(daily_returns) / 252.0

    if years > 0 and final_equity > 0:
        annual_return = (
            (final_equity / INITIAL_CASH) ** (1.0 / years) - 1.0
        )
    else:
        annual_return = 0.0

    trades = result.get("trades", [])
    total_fees = sum(
        float(trade.get("fee", 0.0))
        for trade in trades
    )

    # trade_count 在本项目中表示成交订单数，不一定是完整往返交易数。
    order_count = len(trades)

    return {
        "final_equity": final_equity,
        "total_return_pct": total_return * 100.0,
        "annual_return_pct": annual_return * 100.0,
        "sharpe": sharpe,
        "max_drawdown_pct": max_drawdown * 100.0,
        "order_count": order_count,
        "total_fees": total_fees,
        "final_cash": float(result["cash"]),
    }


def run_target_backtest(dates, opens, closes, targets):
    """所有策略统一使用同一回测器、初始资金和费用参数。"""
    if not (
        len(dates) == len(opens) == len(closes) == len(targets)
    ):
        raise ValueError("日期、价格和目标仓位长度不一致")

    return run_backtest(
        dates=dates,
        open_prices=opens,
        close_prices=closes,
        symbol="QQQ",
        initial_cash=INITIAL_CASH,
        fee_rate=FEE_RATE,
        position_fraction=POSITION_FRACTION,
        target_positions=targets,
    )


def choose_lookback(
    dates,
    opens,
    closes,
    all_targets,
    train_start,
    train_end,
):
    """只用当前训练窗口内的数据表现选择动量周期。"""
    candidates = []

    train_dates = dates[train_start:train_end]
    train_opens = opens[train_start:train_end]
    train_closes = closes[train_start:train_end]

    for lookback in MOMENTUM_LOOKBACKS:
        targets = all_targets[lookback][train_start:train_end]

        result = run_target_backtest(
            train_dates,
            train_opens,
            train_closes,
            targets,
        )
        metrics = calculate_metrics(result)

        candidates.append({
            "lookback": lookback,
            "training_sharpe": metrics["sharpe"],
            "training_final_equity": metrics["final_equity"],
        })

    # 夏普相同时选择较长周期，避免结果依赖列表顺序。
    return max(
        candidates,
        key=lambda item: (
            item["training_sharpe"],
            item["lookback"],
        ),
    )


def main():
    folder = Path(__file__).parent
    data_path = folder / DATA_FILE

    if not data_path.exists():
        raise FileNotFoundError(f"找不到数据文件：{data_path}")

    data = load_price_csv(str(data_path))

    dates = data["dates"]
    opens = data["open_prices"]
    closes = data["close_prices"]

    if not (len(dates) == len(opens) == len(closes)):
        raise ValueError("日期、开盘价和收盘价长度不一致")

    oos_start = next(
        (
            i for i, date in enumerate(dates)
            if str(date) >= OOS_START_DATE
        ),
        None,
    )

    if oos_start is None:
        raise ValueError(f"数据中找不到样本外日期：{OOS_START_DATE}")

    if oos_start < TRAIN_DAYS:
        raise ValueError("样本外起点前的数据不足以进行训练")

    # 在完整价格序列上生成目标，确保每个日期的动量信号
    # 使用此前历史价格计算，而不是在每个训练窗口内重新预热。
    all_targets = {
        lookback: momentum_targets(closes, lookback)
        for lookback in MOMENTUM_LOOKBACKS
    }

    oos_dates = dates[oos_start:]
    oos_opens = opens[oos_start:]
    oos_closes = closes[oos_start:]

    print("=" * 76)
    print("PAPER 滚动样本外动量测试")
    print("不连接真实券商，不提交真实订单")
    print("=" * 76)
    print(f"数据区间：{dates[0]} 至 {dates[-1]}")
    print(f"样本外起点：{oos_dates[0]}")
    print(f"训练窗口：{TRAIN_DAYS} 个交易日")
    print(f"测试窗口：最多 {TEST_DAYS} 个交易日")
    print(f"候选周期：{MOMENTUM_LOOKBACKS}")
    print(f"手续费：单边 {FEE_RATE * 100:.2f}%")
    print(f"入场仓位比例：{POSITION_FRACTION:.0%}")
    print()

    # 逐窗口选择参数；每个窗口的选择只读取其开始前的训练区间。
    selected_by_index = {}
    selection_rows = []
    test_start = oos_start

    while test_start < len(dates):
        train_end = test_start
        train_start = train_end - TRAIN_DAYS
        test_end = min(test_start + TEST_DAYS, len(dates))

        winner = choose_lookback(
            dates,
            opens,
            closes,
            all_targets,
            train_start,
            train_end,
        )

        chosen = winner["lookback"]

        for i in range(test_start, test_end):
            selected_by_index[i] = chosen

        selection_rows.append({
            "train_start": dates[train_start],
            "train_end": dates[train_end - 1],
            "test_start": dates[test_start],
            "test_end": dates[test_end - 1],
            "selected_lookback": chosen,
            "training_sharpe": winner["training_sharpe"],
            "training_final_equity": winner["training_final_equity"],
        })

        print(
            f"训练 {dates[train_start]} 至 {dates[train_end - 1]} | "
            f"测试 {dates[test_start]} 至 {dates[test_end - 1]} | "
            f"选择 {chosen} 日动量 | "
            f"训练夏普 {winner['training_sharpe']:.3f}"
        )

        test_start = test_end

    # 滚动策略：每个样本外日期采用当时已经选定的周期。
    adaptive_targets = []

    for i in range(oos_start, len(dates)):
        lookback = selected_by_index.get(i)

        if lookback is None:
            raise ValueError(f"索引 {i} 没有对应的选参结果")

        adaptive_targets.append(all_targets[lookback][i])

    strategies = [
        ("滚动选择动量", adaptive_targets)
    ]

    for lookback in MOMENTUM_LOOKBACKS:
        strategies.append((
            f"固定{lookback}日动量",
            all_targets[lookback][oos_start:],
        ))

    # 趋势目标先在完整序列上还原状态，再截取样本外区间。
    trend_changes = generate_trend_50_200_targets(closes)
    trend_states = materialize_targets(trend_changes)
    trend_oos = trend_states[oos_start:]

    strategies.append(("50/200趋势", trend_oos))

    # 基准：样本外第一天收盘信号发出后，按回测规则在下一开盘执行。
    strategies.append((
        "买入持有基准",
        [1] * len(oos_dates),
    ))

    results = []

    print()
    print("=" * 76)
    print("连续样本外账户比较")
    print("-" * 76)

    print(
        f"{'策略':<18}"
        f"{'期末资产':>12}"
        f"{'收益%':>10}"
        f"{'年化%':>10}"
        f"{'夏普':>9}"
        f"{'最大回撤%':>12}"
        f"{'订单数':>9}"
        f"{'手续费':>10}"
    )

    for name, targets in strategies:
        result = run_target_backtest(
            oos_dates,
            oos_opens,
            oos_closes,
            targets,
        )

        metrics = calculate_metrics(result)

        row = {
            "strategy": name,
            **metrics,
            "fee_rate": FEE_RATE,
            "position_fraction": POSITION_FRACTION,
            "oos_start": oos_dates[0],
            "oos_end": oos_dates[-1],
        }
        results.append(row)

        print(
            f"{name:<18}"
            f"{metrics['final_equity']:>12.2f}"
            f"{metrics['total_return_pct']:>10.2f}"
            f"{metrics['annual_return_pct']:>10.2f}"
            f"{metrics['sharpe']:>9.3f}"
            f"{metrics['max_drawdown_pct']:>12.2f}"
            f"{metrics['order_count']:>9}"
            f"{metrics['total_fees']:>10.2f}"
        )

    # 保存结果
    result_path = folder / RESULT_FILE

    with open(
        result_path,
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=list(results[0].keys()),
        )
        writer.writeheader()
        writer.writerows(results)

    selection_path = folder / SELECTION_FILE

    with open(
        selection_path,
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=list(selection_rows[0].keys()),
        )
        writer.writeheader()
        writer.writerows(selection_rows)

    # 自动检查已知的趋势状态问题是否再次出现。
    trend_result = next(
        row for row in results
        if row["strategy"] == "50/200趋势"
    )

    print()
    print("=" * 76)
    print("一致性检查")
    print(f"趋势策略期末资产：{trend_result['final_equity']:.2f}")
    print(f"趋势策略收益率：{trend_result['total_return_pct']:.2f}%")
    print(f"趋势策略订单数：{trend_result['order_count']}")

    if trend_result["order_count"] != 3:
        print("警告：趋势订单数与此前诊断的 3 笔不一致，请检查执行口径。")
    else:
        print("趋势订单数与此前诊断一致。")

    print()
    print(f"结果文件：{RESULT_FILE}")
    print(f"周期选择记录：{SELECTION_FILE}")
    print("所有收益率均按期末资产 / 初始资金 - 1 计算。")
    print("历史回测不代表未来收益。")


if __name__ == "__main__":
    main()

