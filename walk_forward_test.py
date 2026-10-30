
from pathlib import Path
from math import sqrt

from adaptive_strategy_research import (
    load_data,
    calculate_signals,
    backtest,
    rolling_select,
    sma,
    START_INDEX,
    FEE_RATE,
    INITIAL_CASH,
)


CANDIDATE_NAMES = [
    "63D Momentum",
    "50/200 Trend",
    "20D Mean Reversion",
]

STRATEGY_NAMES = [
    "Buy and Hold",
    "50/200 Trend",
    "Adaptive Rules",
    "Rolling Selection",
]

INITIAL_TRAIN_FRACTION = 0.60
TEST_WINDOW = 252
TRADING_DAYS_PER_YEAR = 252


def score_sharpe(daily_returns, start, end):
    """只用指定历史区间内已经实现的日收益计算夏普。"""
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

    volatility = sqrt(variance)

    if volatility <= 0:
        return None

    return mean_return / volatility * sqrt(TRADING_DAYS_PER_YEAR)


def select_frozen_strategy(results, train_start, train_end):
    """仅根据测试开始前的历史数据选出冻结策略。"""
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
        raise ValueError("训练期没有可用的策略评分")

    return best_name, best_score


def reset_mean_reversion(prices, start_index):
    """在测试窗口重置均值回归策略状态，避免继承训练期持仓。"""
    signals = [0] * len(prices)
    position = 0

    for i in range(start_index, len(prices)):
        ma20 = sma(prices, 20, i)

        if ma20 is None:
            continue

        if position == 0 and prices[i] < ma20 * 0.98:
            position = 1
        elif position == 1 and prices[i] >= ma20:
            position = 0

        signals[i] = position

    return signals


def reset_adaptive_rules(prices, start_index):
    """重置 Adaptive Rules 内部均值回归状态，但保留指标预热历史。"""
    signals = [0] * len(prices)
    mr_position = 0

    for i in range(start_index, len(prices)):
        ma20 = sma(prices, 20, i)
        ma50 = sma(prices, 50, i)
        ma200 = sma(prices, 200, i)

        momentum_positive = (
            i >= 63 and prices[i] > prices[i - 63]
        )
        momentum_negative = (
            i >= 63 and prices[i] < prices[i - 63]
        )

        if ma50 is not None and ma200 is not None and i >= 63:
            if ma50 > ma200 and momentum_positive:
                target = 1
            elif ma50 < ma200 and momentum_negative:
                target = 0
            else:
                if ma20 is not None:
                    if mr_position == 0 and prices[i] < ma20 * 0.98:
                        mr_position = 1
                    elif mr_position == 1 and prices[i] >= ma20:
                        mr_position = 0

                target = mr_position
        else:
            target = 0

        signals[i] = target

    return signals


def evaluate_window(prices, signals, start, end):
    """
    对一个测试窗口单独回测。
    账户在窗口起点为空仓，拥有初始现金。
    当日收盘信号最早在下一交易日收盘执行。
    """
    window_prices = prices[start:end + 1]
    window_signals = signals[start:end + 1]

    return backtest(
        window_prices,
        window_signals,
        start_index=0,
    )


def print_result_table(results):
    print(
        f"{'策略':<24}"
        f"{'期末资产':>12}"
        f"{'收益%':>10}"
        f"{'年化%':>10}"
        f"{'波动%':>10}"
        f"{'夏普':>9}"
        f"{'回撤%':>10}"
        f"{'交易数':>9}"
    )

    for name, result in results.items():
        print(
            f"{name:<24}"
            f"{result['final_equity']:>12.2f}"
            f"{result['total_return'] * 100:>10.2f}"
            f"{result['annualized_return'] * 100:>10.2f}"
            f"{result['volatility'] * 100:>10.2f}"
            f"{result['sharpe']:>9.3f}"
            f"{result['max_drawdown'] * 100:>10.2f}"
            f"{result['trades']:>9}"
        )


def main():
    path = Path(__file__).parent / "QQQ_yahoo_10y.csv"
    dates, prices = load_data(path)

    n = len(prices)

    initial_train_end = int(n * INITIAL_TRAIN_FRACTION) - 1
    first_test_start = initial_train_end + 1

    if first_test_start <= START_INDEX + 252:
        raise ValueError("初始训练区间太短")

    if first_test_start >= n - 2:
        raise ValueError("样本外数据不足")

    signals = calculate_signals(prices)

    # 候选策略历史表现只用于生成截至各日期的历史评分。
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

    # 根据截至当日收盘可知的历史表现选择下一步目标仓位。
    rolling_signals = rolling_select(
        prices,
        signals,
        historical_results,
    )

    window_results = []
    fold = 1
    test_start = first_test_start

    while test_start < n - 1:
        test_end = min(
            test_start + TEST_WINDOW - 1,
            n - 1,
        )

        if test_end <= test_start:
            break

        frozen_name, frozen_score = select_frozen_strategy(
            historical_results,
            START_INDEX + 1,
            test_start - 1,
        )

        mr_signals = reset_mean_reversion(
            prices,
            test_start,
        )

        adaptive_signals = reset_adaptive_rules(
            prices,
            test_start,
        )

        # Buy and Hold 每个窗口都从现金开始，
        # 在窗口首日收盘形成买入目标，下一日收盘执行。
        buy_hold_signals = [0] * n
        for i in range(test_start, n):
            buy_hold_signals[i] = 1

        test_signals = {
            "Buy and Hold": buy_hold_signals,
            "50/200 Trend": signals["50/200 Trend"],
            "Adaptive Rules": adaptive_signals,
            "Rolling Selection": rolling_signals,
        }

        results = {}

        for name in STRATEGY_NAMES:
            results[name] = evaluate_window(
                prices,
                test_signals[name],
                test_start,
                test_end,
            )

        frozen_signals = (
            mr_signals
            if frozen_name == "20D Mean Reversion"
            else signals[frozen_name]
        )

        results[f"Frozen: {frozen_name}"] = evaluate_window(
            prices,
            frozen_signals,
            test_start,
            test_end,
        )

        window_results.append({
            "fold": fold,
            "start": test_start,
            "end": test_end,
            "frozen_name": frozen_name,
            "frozen_score": frozen_score,
            "results": results,
        })

        print("\n" + "=" * 112)
        print(f"测试窗口：第 {fold} 段")
        print(
            "训练区间：",
            dates[START_INDEX],
            "至",
            dates[test_start - 1],
        )
        print(
            "测试区间：",
            dates[test_start],
            "至",
            dates[test_end],
        )
        print("冻结选择：", frozen_name)
        print("冻结策略训练期夏普：", round(frozen_score, 3))
        print("-" * 112)

        print_result_table(results)

        fold += 1
        test_start = test_end + 1

    if not window_results:
        raise ValueError("没有生成测试窗口")

    # 汇总各策略对 Buy and Hold 基准的表现。
    win_counts = {
        name: 0
        for name in STRATEGY_NAMES
        if name != "Buy and Hold"
    }

    sharpe_win_counts = {
        name: 0
        for name in STRATEGY_NAMES
        if name != "Buy and Hold"
    }

    drawdown_better_counts = {
        name: 0
        for name in STRATEGY_NAMES
        if name != "Buy and Hold"
    }

    print("\n" + "=" * 112)
    print("样本外窗口汇总：相对 QQQ Buy and Hold")
    print("=" * 112)

    for item in window_results:
        results = item["results"]
        benchmark = results["Buy and Hold"]

        print(
            f"\n第 {item['fold']} 段 | "
            f"{dates[item['start']]} 至 {dates[item['end']]} | "
            f"基准收益 {benchmark['total_return'] * 100:.2f}%"
        )

        for name in win_counts:
            result = results[name]

            return_diff = (
                result["total_return"] - benchmark["total_return"]
            ) * 100

            sharpe_diff = result["sharpe"] - benchmark["sharpe"]

            print(
                f"  {name:<22}"
                f"收益差 {return_diff:+.2f} 个百分点 | "
                f"夏普差 {sharpe_diff:+.3f} | "
                f"回撤 {result['max_drawdown'] * 100:.2f}%"
            )

            if result["total_return"] > benchmark["total_return"]:
                win_counts[name] += 1

            if result["sharpe"] > benchmark["sharpe"]:
                sharpe_win_counts[name] += 1

            if result["max_drawdown"] < benchmark["max_drawdown"]:
                drawdown_better_counts[name] += 1

    print("\n" + "=" * 112)
    print("最终统计")
    print("=" * 112)
    print("测试窗口数量：", len(window_results))

    for name in win_counts:
        print(
            f"{name}: "
            f"收益胜过基准 {win_counts[name]}/{len(window_results)} 段；"
            f"夏普胜过基准 {sharpe_win_counts[name]}/{len(window_results)} 段；"
            f"最大回撤小于基准 {drawdown_better_counts[name]}/{len(window_results)} 段"
        )

    print("\n统一设置")
    print("每段初始资金：", INITIAL_CASH)
    print("单边手续费：", FEE_RATE * 100, "%")
    print("每段最多交易日：", TEST_WINDOW)
    print("账户：每段独立重置为空仓")
    print("注意：各段结果不可直接当作连续账户收益。")
    print("注意：策略收益超过基准不等于风险调整后表现更好。")
    print("注意：历史回测不保证未来收益。")


if __name__ == "__main__":
    main()

