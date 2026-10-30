
from pathlib import Path
from math import sqrt

from adaptive_strategy_research import (
    load_data,
    calculate_signals,
    backtest,
    rolling_select,
    START_INDEX,
    FEE_RATE,
    INITIAL_CASH,
    sma,
)


CANDIDATE_NAMES = [
    "63D Momentum",
    "50/200 Trend",
    "20D Mean Reversion",
]


def score_sharpe(daily_returns, start, end):
    """只使用指定区间内已经实现的收益计算年化夏普。"""
    values = [
        daily_returns[i]
        for i in range(start, end + 1)
        if daily_returns[i] is not None
    ]

    if len(values) < 2:
        return None

    mean_return = sum(values) / len(values)

    variance = sum(
        (value - mean_return) ** 2
        for value in values
    ) / (len(values) - 1)

    daily_volatility = sqrt(variance)

    if daily_volatility <= 0:
        return None

    return mean_return / daily_volatility * sqrt(252)


def select_frozen_strategy(results, train_start, train_end):
    """只使用训练期收益选择一次策略。"""
    best_name = None
    best_score = None

    for name in CANDIDATE_NAMES:
        score = score_sharpe(
            results[name]["daily_returns"],
            train_start,
            train_end,
        )

        if score is None:
            continue

        if best_score is None or score > best_score:
            best_name = name
            best_score = score

    if best_name is None:
        raise ValueError("训练区间没有可用的候选策略评分")

    return best_name, best_score


def reset_mean_reversion_at_test_start(prices, split_index):
    """
    保留测试起点之前的价格用于计算20日均线，
    但不继承训练期均值回归持仓状态。

    返回的信号在测试起点之前全部设为0；
    从测试起点开始，依据当日价格和均线重新建立状态。
    """
    n = len(prices)
    signals = [0] * n
    position = 0

    for i in range(split_index, n):
        ma20 = sma(prices, 20, i)

        if ma20 is None:
            signals[i] = 0
            continue

        if position == 0 and prices[i] < ma20 * 0.98:
            position = 1

        elif position == 1 and prices[i] >= ma20:
            position = 0

        signals[i] = position

    return signals


def print_result(name, result):
    print(
        f"{name:<22}"
        f"{result['final_equity']:>12.2f}"
        f"{result['total_return'] * 100:>10.2f}"
        f"{result['annualized_return'] * 100:>9.2f}"
        f"{result['volatility'] * 100:>9.2f}"
        f"{result['sharpe']:>8.3f}"
        f"{result['max_drawdown'] * 100:>9.2f}"
        f"{result['trades']:>8}"
        f"{result['exposure'] * 100:>8.1f}%"
    )


def main():
    path = Path(__file__).parent / "QQQ_yahoo_10y.csv"
    dates, prices = load_data(path)

    signals = calculate_signals(prices)

    split_index = int(len(prices) * 0.70)

    if split_index <= START_INDEX + 252:
        raise ValueError("训练区间不足，无法进行可靠的策略比较")

    if split_index >= len(prices) - 2:
        raise ValueError("样本外区间不足")

    # 所有候选策略的完整历史结果仅用于历史评分。
    historical_results = {
        name: backtest(
            prices,
            signals[name],
            start_index=START_INDEX,
        )
        for name in [
            "Buy and Hold",
            *CANDIDATE_NAMES,
            "Adaptive Rules",
        ]
    }

    # 冻结策略只使用训练区间内已实现的收益。
    frozen_name, frozen_score = select_frozen_strategy(
        historical_results,
        START_INDEX + 1,
        split_index - 1,
    )

    # 滚动选择依据当时及以前已经实现的候选策略收益。
    rolling_signals = rolling_select(
        prices,
        signals,
        historical_results,
    )

    # 为样本外测试生成独立的均值回归信号。
    # 历史价格仍用于计算均线，但训练期持仓状态不延续。
    test_mr_signals = reset_mean_reversion_at_test_start(
        prices,
        split_index,
    )

    strategies = [
        ("Buy and Hold", signals["Buy and Hold"]),
        ("63D Momentum", signals["63D Momentum"]),
        ("50/200 Trend", signals["50/200 Trend"]),
        ("20D Mean Reversion", test_mr_signals),
        ("Adaptive Rules", signals["Adaptive Rules"]),
        (f"Frozen: {frozen_name}", signals[frozen_name]),
        ("Rolling Selection", rolling_signals),
    ]

    print("=" * 104)
    print("QQQ 自适应策略样本外检验")
    print("完整数据：", dates[0], "至", dates[-1])
    print("训练区间：", dates[START_INDEX], "至", dates[split_index - 1])
    print("样本外区间：", dates[split_index], "至", dates[-1])
    print("总数据条数：", len(prices))
    print("训练/测试切分比例：70% / 30%")
    print("初始资金：", INITIAL_CASH)
    print("单边手续费：", FEE_RATE * 100, "%")
    print("信号执行：前一日收盘信号，下一交易日收盘执行")
    print("冻结式策略：", frozen_name)
    print("训练期夏普：", round(frozen_score, 3))
    print("均值回归测试状态：测试期重新初始化")
    print("=" * 104)

    print(
        f"{'策略':<22}"
        f"{'期末资产':>12}"
        f"{'总收益%':>10}"
        f"{'年化%':>9}"
        f"{'波动%':>9}"
        f"{'夏普':>8}"
        f"{'回撤%':>9}"
        f"{'交易数':>8}"
        f"{'持仓%':>9}"
    )

    results = {}

    for name, signal in strategies:
        result = backtest(
            prices,
            signal,
            start_index=split_index,
        )

        results[name] = result
        print_result(name, result)

    print("=" * 104)
    print("评估口径说明：")
    print("1. 所有测试组合均从相同初始资金和空仓状态开始。")
    print("2. 冻结策略只在训练期选择一次。")
    print("3. 滚动策略允许使用截至当日已实现的历史收益更新选择。")
    print("4. 均值回归测试信号不继承训练期的持仓状态。")
    print("5. 滚动策略的评分来自候选策略独立历史收益，不是自身历史收益。")
    print("6. 尚未纳入滑点、现金利息、税费和完整公司行动账本。")
    print("7. Adj Close 只是研究价格口径，不代表实际可成交价格。")
    print("8. 单个样本外区间不足以证明长期优势。")


if __name__ == "__main__":
    main()
