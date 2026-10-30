
import csv
from pathlib import Path
from math import sqrt, isfinite


FEE_RATE = 0.001
INITIAL_CASH = 10000.0


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
            raise ValueError("需要 Date 和 Adj Close 字段")

        for row in reader:
            date = row[columns["date"]].strip()
            raw_price = row[columns["adj close"]].strip()

            price = float(raw_price)

            if not isfinite(price) or price <= 0:
                raise ValueError(
                    f"无效价格：{date}，{raw_price}"
                )

            dates.append(date)
            prices.append(price)

    if len(prices) < 201:
        raise ValueError("数据不足，无法进行全部策略比较")

    if dates != sorted(dates) or len(set(dates)) != len(dates):
        raise ValueError("日期未严格递增或存在重复")

    return dates, prices


def sma(prices, window, index):
    if index + 1 < window:
        return None

    values = prices[index - window + 1:index + 1]
    return sum(values) / window


def build_signals(prices):
    count = len(prices)

    signals = {
        "Buy and Hold": [1] * count,
        "63D Momentum": [0] * count,
        "50/200 Trend": [0] * count,
        "20D Mean Reversion": [0] * count,
    }

    mean_reversion_position = 0

    for i in range(count):
        # 季度动量：过去 63 个交易日收益为正则持有
        if i >= 63:
            signals["63D Momentum"][i] = int(
                prices[i] > prices[i - 63]
            )

        # 中长期趋势过滤
        ma50 = sma(prices, 50, i)
        ma200 = sma(prices, 200, i)

        if ma50 is not None and ma200 is not None:
            signals["50/200 Trend"][i] = int(ma50 > ma200)

        # 均值回归：
        # 价格比 20 日均线低 2% 时买入；
        # 回到均线附近时退出。
        ma20 = sma(prices, 20, i)

        if ma20 is not None:
            if mean_reversion_position == 0:
                if prices[i] < ma20 * 0.98:
                    mean_reversion_position = 1
            elif prices[i] >= ma20:
                mean_reversion_position = 0

        signals["20D Mean Reversion"][i] = (
            mean_reversion_position
        )

    return signals


def backtest(prices, signals):
    equity = INITIAL_CASH
    position = 0
    shares = 0.0
    equity_curve = [INITIAL_CASH]
    trade_count = 0

    # 第 i 日的信号只能在第 i+1 日执行。
    # 本实验用调整收盘价作为执行价的近似值。
    for i in range(1, len(prices)):
        target = signals[i - 1]
        price = prices[i]

        if target != position:
            if target == 1:
                # 用扣除买入手续费后的资金买入
                shares = (
                    equity / (price * (1 + FEE_RATE))
                )
                equity = shares * price
                trade_count += 1

            else:
                equity = shares * price * (1 - FEE_RATE)
                shares = 0.0
                trade_count += 1

            position = target

        elif position == 1:
            equity = shares * price

        equity_curve.append(equity)

    final_equity = equity_curve[-1]
    total_return = (
        final_equity / INITIAL_CASH - 1
    ) * 100

    peak = equity_curve[0]
    max_drawdown = 0.0

    returns = []

    for i in range(1, len(equity_curve)):
        previous = equity_curve[i - 1]
        current = equity_curve[i]

        peak = max(peak, current)

        if peak > 0:
            max_drawdown = max(
                max_drawdown,
                (peak - current) / peak,
            )

        if previous > 0:
            returns.append(current / previous - 1)

    volatility = 0.0
    sharpe = 0.0

    if len(returns) >= 2:
        mean_return = sum(returns) / len(returns)

        variance = sum(
            (r - mean_return) ** 2
            for r in returns
        ) / (len(returns) - 1)

        volatility = sqrt(variance) * sqrt(252)

        daily_volatility = sqrt(variance)

        if daily_volatility > 0:
            sharpe = (
                mean_return / daily_volatility
            ) * sqrt(252)

    years = (len(prices) - 1) / 252

    annualized_return = 0.0

    if years > 0 and final_equity > 0:
        annualized_return = (
            (final_equity / INITIAL_CASH) ** (1 / years) - 1
        ) * 100

    return {
        "final_equity": round(final_equity, 2),
        "total_return": round(total_return, 2),
        "annualized_return": round(annualized_return, 2),
        "annualized_volatility": round(volatility * 100, 2),
        "sharpe_ratio": round(sharpe, 3),
        "max_drawdown": round(max_drawdown * 100, 2),
        "trade_count": trade_count,
    }


def main():
    path = Path(__file__).parent / "QQQ_yahoo_10y.csv"
    dates, prices = load_data(path)
    strategies = build_signals(prices)

    print("=" * 68)
    print("QQQ 独立策略研究实验")
    print("数据区间：", dates[0], "至", dates[-1])
    print("数据条数：", len(prices))
    print("价格口径：Adj Close")
    print("单边手续费：", FEE_RATE * 100, "%")
    print("执行规则：前一日收盘信号，下一交易日收盘执行")
    print("=" * 68)

    results = []

    for name, signals in strategies.items():
        result = backtest(prices, signals)
        results.append((name, result))

    print(
        f"{'策略':<23}"
        f"{'期末资产':>11}"
        f"{'总收益%':>10}"
        f"{'年化%':>9}"
        f"{'波动%':>9}"
        f"{'夏普':>8}"
        f"{'回撤%':>9}"
        f"{'交易数':>8}"
    )

    for name, r in results:
        print(
            f"{name:<23}"
            f"{r['final_equity']:>11.2f}"
            f"{r['total_return']:>10.2f}"
            f"{r['annualized_return']:>9.2f}"
            f"{r['annualized_volatility']:>9.2f}"
            f"{r['sharpe_ratio']:>8.3f}"
            f"{r['max_drawdown']:>9.2f}"
            f"{r['trade_count']:>8}"
        )

    print("=" * 68)
    print("注意：这是第一版研究原型，不是最终绩效报告。")
    print("尚未纳入滑点、税费、现金利息和完整公司行动账本。")
    print("全区间结果仅用于探索，不能替代样本外验证。")


if __name__ == "__main__":
    main()

