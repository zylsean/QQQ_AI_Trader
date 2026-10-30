
import csv
import math
from pathlib import Path

import adaptive_strategy_research as research


# ============================================================
# 逐年扩展窗口实验
# 仅用于历史研究，不连接真实券商
# ============================================================

DATA_FILE = "QQQ_yahoo_10y.csv"

INITIAL_CASH = 10000.0
FEE_RATE = 0.001

START_INDEX = research.START_INDEX
LOOKBACK = research.LOOKBACK
MIN_HISTORY = research.MIN_HISTORY
TRADING_DAYS_PER_YEAR = 252

# 0.0 表示不设置迟滞门槛，作为原始滚动选择的对照组
MARGINS = [0.0, 0.05, 0.10, 0.20, 0.30]


def sharpe_from_returns(values):
    """根据日收益计算年化夏普，不使用未来数据。"""
    values = [
        float(x)
        for x in values
        if x is not None and math.isfinite(float(x))
    ]

    if len(values) < MIN_HISTORY:
        return None

    mean_value = sum(values) / len(values)
    variance = sum(
        (x - mean_value) ** 2 for x in values
    ) / (len(values) - 1)

    std_value = math.sqrt(variance)

    if std_value <= 1e-12:
        return None

    return mean_value / std_value * math.sqrt(
        TRADING_DAYS_PER_YEAR
    )


def get_scores(candidate_results, index):
    """仅使用截至 index 当日已经实现的候选策略收益。"""
    first = max(
        START_INDEX + 1,
        index - LOOKBACK + 1
    )

    scores = {}

    for name, result in candidate_results.items():
        daily_returns = result["daily_returns"]
        values = daily_returns[first:index + 1]

        # None 不计入有效样本
        valid = [
            x for x in values
            if x is not None
            and math.isfinite(float(x))
        ]

        if len(valid) < MIN_HISTORY:
            continue

        score = sharpe_from_returns(valid)

        if score is not None and score > 0:
            scores[name] = score

    return scores


def update_selector(
    index,
    current_name,
    margin,
    candidate_signals,
    candidate_results
):
    """
    在 index 当日收盘后更新选择器。

    当日产生的目标仓位，最早在下一交易日收盘执行。
    """
    scores = get_scores(candidate_results, index)

    if not scores:
        return current_name, 0

    best_name = max(scores, key=scores.get)

    if current_name not in scores:
        current_name = best_name

    elif (
        best_name != current_name
        and scores[best_name] > scores[current_name] + margin
    ):
        current_name = best_name

    target = int(candidate_signals[current_name][index])

    return current_name, target


def generate_hysteresis_signals(
    prices,
    candidate_signals,
    candidate_results,
    margin,
    end_index,
    initial_name=None
):
    """
    生成 [START_INDEX + 1, end_index) 的信号。
    end_index 为右侧开区间。
    """
    targets = [0] * len(prices)
    current_name = initial_name

    for i in range(START_INDEX + 1, end_index):
        current_name, target = update_selector(
            i,
            current_name,
            margin,
            candidate_signals,
            candidate_results
        )
        targets[i] = target

    return targets, current_name


def simulate_account(prices, signals, start_index):
    """
    连续账户模拟：
    - 初始资金只投入一次
    - 前一日收盘信号，次日收盘执行
    - 买入时扣手续费
    - 卖出时扣手续费
    - 不在测试结束时强制平仓
    """
    n = len(prices)

    cash = INITIAL_CASH
    shares = 0.0
    fees = 0.0
    trades = 0
    invested_days = 0

    equity_curve = [None] * n
    equity_curve[start_index] = INITIAL_CASH

    for i in range(start_index + 1, n):
        price = prices[i]
        target = int(signals[i - 1])

        if target not in (0, 1):
            raise ValueError(
                f"非法目标仓位：index={i - 1}, target={target}"
            )

        holding = shares > 0

        if target == 1 and not holding:
            fee = cash * FEE_RATE
            shares = (cash - fee) / price
            fees += fee
            cash = 0.0
            trades += 1

        elif target == 0 and holding:
            gross_value = shares * price
            fee = gross_value * FEE_RATE
            cash = gross_value - fee
            fees += fee
            shares = 0.0
            trades += 1

        if shares > 0:
            invested_days += 1

        equity_curve[i] = cash + shares * price

    valid_equity = equity_curve[start_index:]
    daily_returns = []

    for previous, current in zip(
        valid_equity[:-1],
        valid_equity[1:]
    ):
        daily_returns.append(current / previous - 1.0)

    final_equity = valid_equity[-1]
    total_return = final_equity / INITIAL_CASH - 1.0

    elapsed_days = len(daily_returns)

    if elapsed_days > 0:
        annualized_return = (
            (final_equity / INITIAL_CASH)
            ** (TRADING_DAYS_PER_YEAR / elapsed_days)
            - 1.0
        )
    else:
        annualized_return = 0.0

    if len(daily_returns) > 1:
        mean_return = sum(daily_returns) / len(daily_returns)

        variance = sum(
            (x - mean_return) ** 2
            for x in daily_returns
        ) / (len(daily_returns) - 1)

        volatility = math.sqrt(variance) * math.sqrt(
            TRADING_DAYS_PER_YEAR
        )

        daily_std = math.sqrt(variance)

        sharpe = (
            mean_return / daily_std
            * math.sqrt(TRADING_DAYS_PER_YEAR)
            if daily_std > 1e-12
            else 0.0
        )
    else:
        volatility = 0.0
        sharpe = 0.0

    peak = valid_equity[0]
    max_drawdown = 0.0

    for equity in valid_equity:
        peak = max(peak, equity)

        if peak > 0:
            drawdown = equity / peak - 1.0
            max_drawdown = min(max_drawdown, drawdown)

    return {
        "final_equity": final_equity,
        "total_return": total_return,
        "annualized_return": annualized_return,
        "volatility": volatility,
        "sharpe": sharpe,
        "max_drawdown": max_drawdown,
        "trades": trades,
        "fees": fees,
        "exposure": (
            invested_days / elapsed_days
            if elapsed_days > 0 else 0.0
        ),
        "equity_curve": equity_curve,
    }


def choose_margin(
    dates,
    prices,
    candidate_signals,
    candidate_results,
    train_end
):
    """
    仅用 train_end 之前已完成的交易日训练。

    训练账户在 train_end 收盘结束；
    train_end 当日产生的信号不用于训练收益。
    """
    train_prices = prices[:train_end + 1]
    best_margin = None
    best_score = -float("inf")
    best_state = None

    for margin in MARGINS:
        train_signals, state = generate_hysteresis_signals(
            prices,
            candidate_signals,
            candidate_results,
            margin,
            end_index=train_end
        )

        result = research.backtest(
            train_prices,
            train_signals[:train_end + 1],
            start_index=START_INDEX
        )

        score = result.get("sharpe")

        if score is None or not math.isfinite(float(score)):
            continue

        # 若分数相同，优先较小的迟滞门槛
        if (
            score > best_score
            or (
                math.isclose(score, best_score)
                and (
                    best_margin is None
                    or margin < best_margin
                )
            )
        ):
            best_score = float(score)
            best_margin = margin
            best_state = state

    if best_margin is None:
        raise RuntimeError(
            f"无法选择迟滞阈值，训练截止日期：{dates[train_end]}"
        )

    return best_margin, best_score, best_state


def print_metrics(name, result):
    print(
        f"{name:<25}"
        f"{result['final_equity']:>12,.2f}"
        f"{result['total_return']:>10.2%}"
        f"{result['annualized_return']:>10.2%}"
        f"{result['volatility']:>10.2%}"
        f"{result['sharpe']:>9.3f}"
        f"{result['max_drawdown']:>10.2%}"
        f"{result['trades']:>8}"
        f"{result['fees']:>11,.2f}"
    )


def main():
    folder = Path(__file__).resolve().parent
    data_path = folder / DATA_FILE

    if not data_path.exists():
        raise FileNotFoundError(
            f"找不到数据文件：{data_path}"
        )

    dates, prices = research.load_data(str(data_path))

    if len(dates) != len(prices):
        raise ValueError("日期和价格数组长度不一致")

    if len(prices) <= START_INDEX + 2 * TRADING_DAYS_PER_YEAR:
        raise ValueError("历史数据不足，无法进行逐年扩展窗口检验")

    print("正在计算候选策略信号与历史收益……")

    candidate_signals = research.calculate_signals(prices)

    candidate_results = {
        name: research.backtest(
            prices,
            signals,
            start_index=START_INDEX
        )
        for name, signals in candidate_signals.items()
    }

    # 首个样本外窗口前，至少留出约一年的初始训练历史
    first_test_start = START_INDEX + TRADING_DAYS_PER_YEAR

    boundaries = list(
        range(
            first_test_start,
            len(prices),
            TRADING_DAYS_PER_YEAR
        )
    )

    if not boundaries or boundaries[0] != first_test_start:
        raise RuntimeError("无法构建样本外窗口")

    boundaries.append(len(prices))

    adaptive_signals = [0] * len(prices)
    chosen_margins = []

    current_name = None

    print("\n===== 逐年扩展窗口：参数选择记录 =====")
    print(
        f"{'测试开始':<13}{'测试结束':<13}"
        f"{'训练选中阈值':>13}{'训练夏普':>12}"
    )

    for fold in range(len(boundaries) - 1):
        fold_start = boundaries[fold]
        fold_end = boundaries[fold + 1]

        margin, train_sharpe, training_state = choose_margin(
            dates,
            prices,
            candidate_signals,
            candidate_results,
            fold_start
        )

        # 第一段从训练期末的选择器状态开始；
        # 后续年度保留实际运行中的选择器状态。
        if fold == 0:
            current_name = training_state

        chosen_margins.append(margin)

        for i in range(fold_start, fold_end):
            current_name, target = update_selector(
                i,
                current_name,
                margin,
                candidate_signals,
                candidate_results
            )
            adaptive_signals[i] = target

        print(
            f"{dates[fold_start]:<13}"
            f"{dates[fold_end - 1]:<13}"
            f"{margin:>13.2f}"
            f"{train_sharpe:>12.3f}"
        )

    # 所有策略都从同一个样本外起点开始，
    # 使用相同初始资金、费用和执行规则。
    test_signals = {
        "Adaptive Walk Forward": adaptive_signals,
        "Rolling Selection 0.00": [0] * len(prices),
    }

    # 对照组：固定候选策略
    for name, signals in candidate_signals.items():
        test_signals[name] = signals

    # 原始滚动选择：固定零迟滞门槛
    original_signals, _ = generate_hysteresis_signals(
        prices,
        candidate_signals,
        candidate_results,
        margin=0.0,
        end_index=len(prices)
    )
    test_signals["Rolling Selection 0.00"] = original_signals

    results = {}

    for name, signals in test_signals.items():
        results[name] = simulate_account(
            prices,
            signals,
            start_index=first_test_start
        )

    print("\n===== 样本外总结果 =====")
    print(f"样本外起点：{dates[first_test_start]}")
    print(f"样本外终点：{dates[-1]}")
    print(f"初始资金：{INITIAL_CASH:,.2f}")
    print(f"单边手续费：{FEE_RATE:.2%}")
    print(
        f"{'策略':<25}"
        f"{'期末资产':>12}"
        f"{'总收益':>10}"
        f"{'年化收益':>10}"
        f"{'年化波动':>10}"
        f"{'夏普':>9}"
        f"{'最大回撤':>10}"
        f"{'交易数':>8}"
        f"{'手续费':>11}"
    )

    for name, result in results.items():
        print_metrics(name, result)

    print("\n===== 年度样本外收益 =====")
    print(
        f"{'开始日期':<13}{'结束日期':<13}"
        f"{'选中阈值':>10}{'年度收益':>12}"
    )

    adaptive_equity = results[
        "Adaptive Walk Forward"
    ]["equity_curve"]

    for fold, margin in enumerate(chosen_margins):
        start = boundaries[fold]
        end = boundaries[fold + 1]

        start_equity = adaptive_equity[start]
        end_equity = adaptive_equity[end - 1]

        period_return = end_equity / start_equity - 1.0

        print(
            f"{dates[start]:<13}"
            f"{dates[end - 1]:<13}"
            f"{margin:>10.2f}"
            f"{period_return:>11.2%}"
        )

    print("\n注意：历史回测不代表未来收益。")
    print(
        "参数选择只使用每个测试窗口开始前的数据；"
        "测试期间账户连续运行。"
    )


if __name__ == "__main__":
    main()

