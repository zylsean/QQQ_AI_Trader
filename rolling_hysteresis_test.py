
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

# 评分差距，单位是年化夏普比率的绝对差值
MARGINS = [0.05, 0.10, 0.20, 0.30]


def score_history(daily_returns, first, last):
    values = [
        daily_returns[j]
        for j in range(first, last + 1)
        if daily_returns[j] is not None
    ]

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


def build_hysteresis_signals(
    prices,
    signals,
    results,
    margin,
):
    n = len(prices)
    target_signals = [0] * n
    selected_names = [None] * n
    current_name = None

    for i in range(START_INDEX + 1, n):
        first = max(START_INDEX + 1, i - LOOKBACK + 1)

        scores = {
            name: score_history(
                results[name]["daily_returns"],
                first,
                i,
            )
            for name in NAMES
        }

        valid = [
            name for name in NAMES
            if scores[name] is not None and scores[name] > 0
        ]

        best_name = None

        if valid:
            best_name = max(
                valid,
                key=lambda name: scores[name],
            )

        # 当前没有策略，或当前策略评分失效：
        # 选择当前评分最高的有效策略；没有则空仓。
        if (
            current_name is None
            or scores[current_name] is None
            or scores[current_name] <= 0
        ):
            current_name = best_name

        # 当前策略仍有效时，只有领先幅度超过阈值才切换。
        elif (
            best_name is not None
            and best_name != current_name
            and scores[best_name]
            > scores[current_name] + margin
        ):
            current_name = best_name

        selected_names[i] = current_name

        if current_name is not None:
            target_signals[i] = signals[current_name][i]

    return target_signals, selected_names


def calculate_fees(prices, target_signals):
    cash = 10000.0
    shares = 0.0
    position = 0
    fees = 0.0
    trades = 0
    invested_days = 0
    evaluated_days = len(prices) - START_INDEX - 1

    for i in range(START_INDEX + 1, len(prices)):
        target = target_signals[i - 1]
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

    final_equity = cash + shares * prices[-1]

    return {
        "fees": fees,
        "trades": trades,
        "exposure": (
            invested_days / evaluated_days
            if evaluated_days > 0 else 0
        ),
        "final_equity": final_equity,
    }



def evaluate(prices, target_signals):
    result = backtest(prices, target_signals)
    ledger = calculate_fees(prices, target_signals)

    equity_curve = result["equity_curve"]

    daily_returns = []

    for i in range(1, len(equity_curve)):
        previous_equity = equity_curve[i - 1]
        current_equity = equity_curve[i]

        if previous_equity > 0:
            daily_returns.append(
                current_equity / previous_equity - 1
            )

    if len(daily_returns) >= 2:
        mean_return = sum(daily_returns) / len(daily_returns)

        variance = sum(
            (x - mean_return) ** 2
            for x in daily_returns
        ) / (len(daily_returns) - 1)

        daily_volatility = sqrt(variance)
        annualized_volatility = (
            daily_volatility * sqrt(TRADING_DAYS_PER_YEAR)
        )

        sharpe_ratio = (
            mean_return / daily_volatility
            * sqrt(TRADING_DAYS_PER_YEAR)
            if daily_volatility > 0 else 0.0
        )
    else:
        annualized_volatility = 0.0
        sharpe_ratio = 0.0

    initial_equity = equity_curve[0]
    final_equity = equity_curve[-1]

    if initial_equity > 0 and len(daily_returns) > 0:
        annualized_return = (
            (final_equity / initial_equity)
            ** (TRADING_DAYS_PER_YEAR / len(daily_returns))
            - 1
        )
    else:
        annualized_return = 0.0

    return {
        "result": result,
        "ledger": ledger,
        "annualized_return": annualized_return,
        "annualized_volatility": annualized_volatility,
        "sharpe_ratio": sharpe_ratio,
    }


def main():
    path = Path(__file__).parent / "QQQ_yahoo_10y.csv"
    dates, prices = load_data(path)
    signals = calculate_signals(prices)

    results = {
        name: backtest(prices, signals[name])
        for name in NAMES
    }

    baseline_signals = rolling_select(
        prices, signals, results
    )

    experiments = [
        ("原始选择器", baseline_signals)
    ]

    for margin in MARGINS:
        target_signals, _ = build_hysteresis_signals(
            prices, signals, results, margin
        )
        experiments.append(
            (f"迟滞 {margin:.2f}", target_signals)
        )

    print("=" * 76)
    print("滚动选择迟滞机制对照实验")
    print("数据：", dates[START_INDEX], "至", dates[-1])
    print("手续费：单边", FEE_RATE * 100, "%")
    print("注意：历史回测结果不代表未来收益。")
    print("=" * 76)

    for label, target_signals in experiments:
        evaluated = evaluate(prices, target_signals)
        result = evaluated["result"]
        ledger = evaluated["ledger"]

        print("\n", label)
        print("-" * 50)
        print("期末资产：", round(result["final_equity"], 2))
        print(
            "总收益率：",
            round(result["total_return"] * 100, 2), "%",
        )
        print(
            "年化收益率：",
            round(evaluated["annualized_return"] * 100, 2),
            "%",
        )
        print(
            "年化波动率：",
            round(
                evaluated["annualized_volatility"] * 100, 2
            ),
            "%",
        )
        print(
            "夏普比率：",
            round(evaluated["sharpe_ratio"], 3),
        )
        print(
            "最大回撤：",
            round(result["max_drawdown"] * 100, 2), "%",
        )
        print("交易次数：", ledger["trades"])
        print("总手续费：", round(ledger["fees"], 2))
        print(
            "实际持仓比例：",
            round(ledger["exposure"] * 100, 2), "%",
        )
        print(
            "账本期末资产核对：",
            round(ledger["final_equity"], 2),
        )

        if abs(
            ledger["final_equity"] - result["final_equity"]
        ) > 0.02:
            print("警告：独立账本与回测结果不一致！")

        if ledger["trades"] != result["trades"]:
            print("警告：交易次数不一致！")

    print("\n对照实验结束。")


if __name__ == "__main__":
    main()
