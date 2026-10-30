
from pathlib import Path
from math import sqrt

from adaptive_strategy_research import (
    load_data,
    calculate_signals,
    backtest,
    rolling_select,
    START_INDEX,
    LOOKBACK,
    MIN_HISTORY,
    TRADING_DAYS_PER_YEAR,
    FEE_RATE,
)


NAMES = [
    "63D Momentum",
    "50/200 Trend",
    "20D Mean Reversion",
]


def calculate_score(values):
    if len(values) < MIN_HISTORY:
        return None

    mean_return = sum(values) / len(values)

    variance = sum(
        (x - mean_return) ** 2 for x in values
    ) / (len(values) - 1)

    volatility = sqrt(variance)

    if volatility <= 0 or mean_return <= 0:
        return None

    return mean_return / volatility * sqrt(
        TRADING_DAYS_PER_YEAR
    )


def main():
    path = Path(__file__).parent / "QQQ_yahoo_10y.csv"
    dates, prices = load_data(path)
    signals = calculate_signals(prices)

    results = {
        name: backtest(prices, signals[name])
        for name in NAMES
    }

    original_signals = rolling_select(
        prices, signals, results
    )

    n = len(prices)
    audit_signals = [0] * n
    selected_names = [None] * n
    score_records = {}
    tie_records = []

    # 独立复现选择器，同时记录每天的策略名称与评分。
    # 评分只使用当日及之前已经产生的历史收益。
    for i in range(START_INDEX + 1, n):
        first = max(START_INDEX + 1, i - LOOKBACK + 1)

        scores = {}

        for name in NAMES:
            daily_returns = results[name]["daily_returns"]

            values = [
                daily_returns[j]
                for j in range(first, i + 1)
                if daily_returns[j] is not None
            ]

            scores[name] = calculate_score(values)

        valid_scores = {
            name: score
            for name, score in scores.items()
            if score is not None and score > 0
        }

        best_name = None
        best_score = 0.0

        # 与原选择器一致：仅在评分严格更高时替换。
        # 因此完全并列时，按 NAMES 中的先后顺序选择。
        for name in NAMES:
            score = scores[name]

            if score is not None and score > best_score:
                best_score = score
                best_name = name

        selected_names[i] = best_name
        score_records[i] = scores

        if len(valid_scores) >= 2:
            ranked = sorted(
                valid_scores.items(),
                key=lambda item: item[1],
                reverse=True,
            )

            if abs(ranked[0][1] - ranked[1][1]) < 1e-12:
                tie_records.append(
                    (i, ranked[0][0], ranked[1][0], ranked[0][1])
                )

        if best_name is not None:
            audit_signals[i] = signals[best_name][i]

    mismatch_count = sum(
        audit_signals[i] != original_signals[i]
        for i in range(n)
    )

    print("=" * 72)
    print("滚动选择器深度审计")
    print("数据区间：", dates[START_INDEX], "至", dates[-1])
    print("历史窗口：", LOOKBACK)
    print("最低有效收益数：", MIN_HISTORY)
    print("=" * 72)

    print("\n【实现一致性】")
    print("独立复现与原选择器的仓位差异数：", mismatch_count)

    if mismatch_count != 0:
        print("警告：独立复现与原选择器不一致，需要先检查评分逻辑。")
        return

    # 统计每天最终选中了哪个候选策略，而不只是目标仓位。
    decision_days = n - START_INDEX - 1
    counts = {name: 0 for name in NAMES}
    no_selection = 0

    for i in range(START_INDEX + 1, n):
        name = selected_names[i]

        if name is None:
            no_selection += 1
        else:
            counts[name] += 1

    print("\n【候选策略选择分布】")
    print("评估日数：", decision_days)
    print("未选中任何策略的天数：", no_selection)

    for name in NAMES:
        count = counts[name]
        percentage = count / max(1, decision_days) * 100

        print(
            name,
            "| 被选天数：", count,
            "| 占全部评估日：", round(percentage, 2), "%",
        )

    # 记录候选策略名称变化。
    changes = []
    previous_name = None

    for i in range(START_INDEX + 1, n):
        current_name = selected_names[i]

        if current_name != previous_name:
            if current_name is not None or previous_name is not None:
                changes.append(
                    (
                        i,
                        previous_name,
                        current_name,
                        score_records[i],
                    )
                )

        previous_name = current_name

    print("\n【候选策略切换】")
    print("切换事件数：", len(changes))
    print("日期含义：选择发生在当日收盘，信号最早次日收盘执行。")

    show_limit = 50

    for i, old_name, new_name, scores in changes[:show_limit]:
        print(
            dates[i],
            "|", old_name or "无策略",
            "->", new_name or "无策略",
        )

        print(
            "  评分：",
            "Momentum =", (
                round(scores["63D Momentum"], 3)
                if scores["63D Momentum"] is not None else "无"
            ),
            "| Trend =", (
                round(scores["50/200 Trend"], 3)
                if scores["50/200 Trend"] is not None else "无"
            ),
            "| MeanReversion =", (
                round(scores["20D Mean Reversion"], 3)
                if scores["20D Mean Reversion"] is not None else "无"
            ),
        )

    if len(changes) > show_limit:
        print("其余切换事件省略：", len(changes) - show_limit, "次")

    print("\n【评分并列】")
    print("接近完全并列的评分日数：", len(tie_records))

    for i, name_a, name_b, score in tie_records[:10]:
        print(
            dates[i], "|", name_a, "与", name_b,
            "| 评分：", round(score, 6),
        )

    # 使用与 backtest 相同的执行顺序，独立核算实际手续费。
    cash = 10000.0
    shares = 0.0
    position = 0
    total_fees = 0.0
    trade_count = 0

    for i in range(START_INDEX + 1, n):
        target = audit_signals[i - 1]
        price = prices[i]

        if target == position:
            continue

        if target == 1:
            shares = cash / (price * (1 + FEE_RATE))
            fee = shares * price * FEE_RATE
            cash = 0.0
            total_fees += fee
            position = 1
            trade_count += 1

        else:
            gross = shares * price
            fee = gross * FEE_RATE
            cash = gross - fee
            shares = 0.0
            total_fees += fee
            position = 0
            trade_count += 1

    result = backtest(prices, audit_signals)
    original_result = backtest(prices, original_signals)

    print("\n【交易与手续费核算】")
    print("独立账本交易次数：", trade_count)
    print("原回测交易次数：", result["trades"])
    print("独立核算总手续费：", round(total_fees, 2))
    print("期末现金：", round(cash, 2))
    print("期末持仓股数：", round(shares, 6))
    print("期末资产（独立账本）：", round(
        cash + shares * prices[-1], 2
    ))
    print("期末资产（原回测）：", round(
        result["final_equity"], 2
    ))
    print("期末资产（原始选择器信号）：", round(
        original_result["final_equity"], 2
    ))

    if trade_count != result["trades"]:
        print("警告：交易次数不一致，请检查执行规则。")

    if abs(
        cash + shares * prices[-1] - result["final_equity"]
    ) > 0.02:
        print("警告：独立账本与原回测期末资产不一致。")

    print("\n审计完成。")


if __name__ == "__main__":
    main()

