import csv
from pathlib import Path
from math import sqrt, isfinite


INITIAL_CASH = 10000.0
FEE_RATE = 0.001
START_INDEX = 200
LOOKBACK = 252
MIN_HISTORY = 126
TRADING_DAYS_PER_YEAR = 252


def load_data(path):
    dates = []
    prices = []

    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)

        if not reader.fieldnames:
            raise ValueError("CSV 缺少表头")

        columns = {
            name.strip().lower(): name
            for name in reader.fieldnames
            if name
        }

        if "date" not in columns or "adj close" not in columns:
            raise ValueError("CSV 必须包含 Date 和 Adj Close")

        for row in reader:
            date = row[columns["date"]].strip()

            try:
                price = float(row[columns["adj close"]])
            except (TypeError, ValueError):
                raise ValueError(f"无效价格：{date}")

            if not isfinite(price) or price <= 0:
                raise ValueError(f"无效价格：{date} {price}")

            dates.append(date)
            prices.append(price)

    if len(prices) <= START_INDEX + MIN_HISTORY:
        raise ValueError("数据不足")

    if dates != sorted(dates) or len(set(dates)) != len(dates):
        raise ValueError("日期未严格递增或存在重复")

    return dates, prices


def sma(prices, window, i):
    if window <= 0:
        raise ValueError("均线窗口必须大于零")

    if i + 1 < window:
        return None

    return sum(prices[i - window + 1:i + 1]) / window


def calculate_signals(prices):
    n = len(prices)

    signals = {
        "Buy and Hold": [1] * n,
        "63D Momentum": [0] * n,
        "50/200 Trend": [0] * n,
        "20D Mean Reversion": [0] * n,
        "Adaptive Rules": [0] * n,
    }

    mr_position = 0
    adaptive_mr_position = 0

    for i in range(n):
        ma20 = sma(prices, 20, i)
        ma50 = sma(prices, 50, i)
        ma200 = sma(prices, 200, i)

        momentum_positive = (
            i >= 63 and prices[i] > prices[i - 63]
        )

        momentum_negative = (
            i >= 63 and prices[i] < prices[i - 63]
        )

        signals["63D Momentum"][i] = int(momentum_positive)

        if ma50 is not None and ma200 is not None:
            signals["50/200 Trend"][i] = int(ma50 > ma200)

        # 独立均值回归策略
        if ma20 is not None:
            if mr_position == 0 and prices[i] < ma20 * 0.98:
                mr_position = 1
            elif mr_position == 1 and prices[i] >= ma20:
                mr_position = 0

        signals["20D Mean Reversion"][i] = mr_position

        # 自适应规则
        if ma50 is not None and ma200 is not None and i >= 63:
            if ma50 > ma200 and momentum_positive:
                target = 1

            elif ma50 < ma200 and momentum_negative:
                # 进入明确的空仓状态时，清除旧的均值回归持仓状态。
                # 否则后续回到中性分支时，过期状态可能重新触发做多。
                adaptive_mr_position = 0
                target = 0

            else:
                if ma20 is not None:
                    if (
                        adaptive_mr_position == 0
                        and prices[i] < ma20 * 0.98
                    ):
                        adaptive_mr_position = 1

                    elif (
                        adaptive_mr_position == 1
                        and prices[i] >= ma20
                    ):
                        adaptive_mr_position = 0

                target = adaptive_mr_position

        else:
            target = 0

        signals["Adaptive Rules"][i] = target

    return signals


def backtest(prices, signals, start_index=START_INDEX):
    """
    单标的、全仓做多或空仓的组合回测。

    signals[i]：第 i 日收盘后产生的目标仓位。
    执行时间：第 i+1 日收盘。
    交易费用：买入和卖出分别按成交金额收取 FEE_RATE。

    组合权益 = 现金 + 持仓股数 * 当前价格。
    equity_curve 从 start_index 对应的初始资金开始。
    """

    n = len(prices)

    if len(signals) != n:
        raise ValueError("信号长度必须与价格数据一致")

    if not 0 <= start_index < n - 1:
        raise ValueError("start_index 超出有效范围")

    if any(signal not in (0, 1) for signal in signals):
        raise ValueError("策略信号只能为 0 或 1")

    if any(
        not isfinite(price) or price <= 0
        for price in prices
    ):
        raise ValueError("价格必须是有限的正数")

    cash = INITIAL_CASH
    shares = 0.0
    position = 0

    equity_curve = [INITIAL_CASH]
    daily_returns = [None] * n

    trades = 0
    exposure_days = 0

    for i in range(start_index + 1, n):
        # 只执行前一日已经产生的信号
        target = signals[i - 1]
        price = prices[i]

        if target != position:

            if target == 1:
                # 全部可用现金用于买入，预留买入手续费
                shares = cash / (price * (1 + FEE_RATE))
                cash = 0.0
                trades += 1

            else:
                # 卖出全部持仓，并扣除卖出手续费
                cash = shares * price * (1 - FEE_RATE)
                shares = 0.0
                trades += 1

            position = target

        # 每日权益按现金和持仓市值计算
        equity = cash + shares * price

        if not isfinite(equity) or equity < 0:
            raise ArithmeticError("组合权益出现异常")

        previous_equity = equity_curve[-1]

        if previous_equity > 0:
            daily_returns[i] = equity / previous_equity - 1

        equity_curve.append(equity)

        if position == 1:
            exposure_days += 1

    # 最大回撤基于同一条每日组合权益曲线
    peak = equity_curve[0]
    max_drawdown = 0.0

    for equity in equity_curve:
        peak = max(peak, equity)

        if peak > 0:
            drawdown = (peak - equity) / peak
            max_drawdown = max(max_drawdown, drawdown)

    # 每日收益与权益曲线使用完全相同的评估区间
    returns = [
        daily_returns[i]
        for i in range(start_index + 1, n)
        if daily_returns[i] is not None
    ]

    volatility = 0.0
    sharpe = 0.0

    if len(returns) >= 2:
        mean_return = sum(returns) / len(returns)

        variance = sum(
            (r - mean_return) ** 2 for r in returns
        ) / (len(returns) - 1)

        daily_volatility = sqrt(variance)
        volatility = daily_volatility * sqrt(
            TRADING_DAYS_PER_YEAR
        )

        if daily_volatility > 0:
            sharpe = (
                mean_return
                / daily_volatility
                * sqrt(TRADING_DAYS_PER_YEAR)
            )

    final_equity = equity_curve[-1]
    total_return = final_equity / INITIAL_CASH - 1

    years = (
        len(equity_curve) - 1
    ) / TRADING_DAYS_PER_YEAR

    annualized_return = 0.0

    if years > 0 and final_equity > 0:
        annualized_return = (
            (final_equity / INITIAL_CASH) ** (1 / years) - 1
        )

    return {
        "final_equity": final_equity,
        "total_return": total_return,
        "annualized_return": annualized_return,
        "volatility": volatility,
        "sharpe": sharpe,
        "max_drawdown": max_drawdown,
        "trades": trades,
        "exposure": exposure_days / max(1, len(equity_curve) - 1),
        "daily_returns": daily_returns,
        "equity_curve": equity_curve,
        "cash": cash,
        "shares": shares,
        "position": position,
    }


def rolling_select(prices, candidate_signals, candidate_results):
    """
    根据截至当日已经实现的候选策略收益进行滚动选择。

    selected[i] 是第 i 日收盘后确定的目标仓位，
    最早在第 i+1 日收盘执行。

    这里输出目标仓位，而不是把候选策略的权益曲线拼接起来。
    实际交易和切换费用由 backtest() 统一模拟。
    """

    n = len(prices)
    selected = [0] * n

    names = [
        "63D Momentum",
        "50/200 Trend",
        "20D Mean Reversion",
    ]

    for name in names:
        if name not in candidate_signals:
            raise ValueError(f"缺少候选策略信号：{name}")

        if name not in candidate_results:
            raise ValueError(f"缺少候选策略绩效：{name}")

        if len(candidate_signals[name]) != n:
            raise ValueError(f"{name} 信号长度不一致")

        daily_returns = candidate_results[name].get(
            "daily_returns"
        )

        if daily_returns is None or len(daily_returns) != n:
            raise ValueError(f"{name} 日收益序列长度不一致")

    for i in range(START_INDEX + 1, n):
        first = max(
            START_INDEX + 1,
            i - LOOKBACK + 1,
        )

        best_name = None
        best_sharpe = 0.0

        for name in names:
            daily_returns = candidate_results[name]["daily_returns"]

            # 仅使用截至 i 日已实现的收益，不读取 i 之后的数据
            values = [
                daily_returns[j]
                for j in range(first, i + 1)
                if daily_returns[j] is not None
            ]

            if len(values) < MIN_HISTORY:
                continue

            mean_return = sum(values) / len(values)

            variance = sum(
                (value - mean_return) ** 2
                for value in values
            ) / (len(values) - 1)

            daily_volatility = sqrt(variance)

            if daily_volatility <= 0 or mean_return <= 0:
                continue

            score = (
                mean_return
                / daily_volatility
                * sqrt(TRADING_DAYS_PER_YEAR)
            )

            if score > best_sharpe:
                best_sharpe = score
                best_name = name

        if best_name is not None:
            selected[i] = candidate_signals[best_name][i]
        else:
            selected[i] = 0

    return selected


def main():
    path = Path(__file__).parent / "QQQ_yahoo_10y.csv"
    dates, prices = load_data(path)

    signals = calculate_signals(prices)

    candidate_names = [
        "63D Momentum",
        "50/200 Trend",
        "20D Mean Reversion",
    ]

    results = {
        name: backtest(prices, signals[name])
        for name in [
            "Buy and Hold",
            *candidate_names,
            "Adaptive Rules",
        ]
    }

    signals["Rolling Selection"] = rolling_select(
        prices,
        signals,
        results,
    )

    results["Rolling Selection"] = backtest(
        prices,
        signals["Rolling Selection"],
    )

    names = [
        "Buy and Hold",
        "63D Momentum",
        "50/200 Trend",
        "20D Mean Reversion",
        "Adaptive Rules",
        "Rolling Selection",
    ]

    print("=" * 104)
    print("QQQ 自适应策略研究")
    print("数据区间：", dates[START_INDEX], "至", dates[-1])
    print("总数据条数：", len(prices))
    print("共同评估起点索引：", START_INDEX)
    print("手续费：单边", FEE_RATE * 100, "%")
    print("执行规则：前一日收盘信号，下一交易日收盘执行")
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

    for name in names:
        result = results[name]

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

    print("=" * 104)
    print("研究限制：")
    print("1. 仅模拟单标的全仓做多或空仓，不支持部分仓位和做空。")
    print("2. 买卖费用已计入组合权益。")
    print("3. 滚动选择依据候选策略的历史独立收益评分。")
    print("4. 尚未纳入滑点、现金利息、税费和完整公司行动账本。")
    print("5. Adj Close 用于研究收益近似，不代表实际可成交价格。")
    print("6. 当前结果仍需通过测试和样本外验证。")


if __name__ == "__main__":
    main()
