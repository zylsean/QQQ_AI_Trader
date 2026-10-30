
from pathlib import Path
from math import sqrt

from adaptive_strategy_research import (
    load_data,
    calculate_signals,
    backtest,
    START_INDEX,
    TRADING_DAYS_PER_YEAR,
    FEE_RATE,
)

from rolling_hysteresis_test import (
    NAMES,
    MARGINS,
    build_hysteresis_signals,
    calculate_fees,
)


INITIAL_CASH = 10000.0
TEST_START_DATE = "2022-10-17"
FOLD_DAYS = 252


def get_metrics(result):
    curve = result["equity_curve"]

    returns = []

    for i in range(1, len(curve)):
        if curve[i - 1] > 0:
            returns.append(curve[i] / curve[i - 1] - 1)

    if not returns:
        return 0.0, 0.0, 0.0

    mean_return = sum(returns) / len(returns)

    variance = sum(
        (x - mean_return) ** 2 for x in returns
    ) / max(1, len(returns) - 1)

    daily_volatility = sqrt(variance)

    annualized_return = (
        (curve[-1] / curve[0])
        ** (TRADING_DAYS_PER_YEAR / len(returns))
        - 1
    )

    annualized_volatility = (
        daily_volatility * sqrt(TRADING_DAYS_PER_YEAR)
    )

    sharpe = (
        mean_return / daily_volatility
        * sqrt(TRADING_DAYS_PER_YEAR)
        if daily_volatility > 0 else 0.0
    )

    return annualized_return, annualized_volatility, sharpe


def calculate_fold_fees(prices, signals, start_index, end_index):
    cash = INITIAL_CASH
    shares = 0.0
    position = 0
    fees = 0.0
    trades = 0
    invested_days = 0

    for i in range(start_index + 1, end_index):
        target = signals[i - 1]
        price = prices[i]

        if target != position:
            if target == 1:
                shares = cash / (price * (1 + FEE_RATE))
                fees += shares * price * FEE_RATE
                cash = 0.0
                position = 1
            else:
                gross = shares * price
                fees += gross * FEE_RATE
                cash = gross - gross * FEE_RATE
                shares = 0.0
                position = 0

            trades += 1

        if position == 1:
            invested_days += 1

    final_equity = cash + shares * prices[end_index - 1]

    return {
        "fees": fees,
        "trades": trades,
        "final_equity": final_equity,
        "exposure": invested_days / max(1, end_index - start_index - 1),
    }


def main():
    path = Path(__file__).parent / "QQQ_yahoo_10y.csv"
    dates, prices = load_data(path)
    signals = calculate_signals(prices)

    candidate_results = {
        name: backtest(prices, signals[name])
        for name in NAMES
    }

    original_signals = __import__(
        "adaptive_strategy_research"
    ).rolling_select(prices, signals, candidate_results)

    experiments = [("原始选择器", original_signals)]

    for margin in MARGINS:
        target_signals, _ = build_hysteresis_signals(
            prices, signals, candidate_results, margin
        )
        experiments.append(
            (f"迟滞 {margin:.2f}", target_signals)
        )

    start_index = next(
        (
            i for i, date in enumerate(dates)
            if date >= TEST_START_DATE
        ),
        None,
    )

    if start_index is None or start_index <= START_INDEX:
        raise ValueError("找不到有效的测试起点：" + TEST_START_DATE)

    print("=" * 78)
    print("迟滞机制分阶段稳健性检查")
    print("测试起点：", dates[start_index])
    print("每个窗口：最多", FOLD_DAYS, "个交易日")
    print("每个窗口账户独立从现金开始")
    print("注意：阈值此前已在全历史区间比较，本测试属于稳健性检查，")
    print("不能视为完全独立、未受参数选择影响的样本外验证。")
    print("=" * 78)

    fold_number = 1
    fold_start = start_index

    while fold_start < len(prices) - 1:
        fold_end = min(fold_start + FOLD_DAYS, len(prices))

        if fold_end - fold_start < 30:
            break

        print(
            "\n【窗口", fold_number, "】",
            dates[fold_start], "至", dates[fold_end - 1],
        )

        for label, target_signals in experiments:
            # 截断到本窗口结束，避免误执行窗口结束后的信号。
            window_prices = prices[:fold_end]
            window_signals = target_signals[:fold_end]

            result = backtest(
                window_prices,
                window_signals,
                start_index=fold_start,
            )

            annual_return, annual_volatility, sharpe = get_metrics(result)

            ledger = calculate_fold_fees(
                prices,
                target_signals,
                fold_start,
                fold_end,
            )

            print(
                label,
                "| 收益：", round(result["total_return"] * 100, 2), "%",
                "| 年化：", round(annual_return * 100, 2), "%",
                "| 波动：", round(annual_volatility * 100, 2), "%",
                "| 夏普：", round(sharpe, 3),
                "| 回撤：", round(result["max_drawdown"] * 100, 2), "%",
                "| 交易：", ledger["trades"],
                "| 手续费：", round(ledger["fees"], 2),
            )

            if abs(
                ledger["final_equity"] - result["final_equity"]
            ) > 0.02:
                print("  警告：独立账本和回测期末资产不一致！")

            if ledger["trades"] != result["trades"]:
                print("  警告：独立账本和回测交易次数不一致！")

        fold_start = fold_end
        fold_number += 1

    print("\n分阶段检查完成。")


if __name__ == "__main__":
    main()

