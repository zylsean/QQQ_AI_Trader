
from pathlib import Path
import csv
from math import sqrt

from csv_data import load_price_csv
from backtester import run_backtest


# =========================
# 基础配置
# =========================

DATA_FILE = "QQQ_yahoo_10y.csv"

INITIAL_CASH = 10000.0
POSITION_FRACTION = 0.20

OOS_START_DATE = "2023-10-18"

BASE_FEE = 0.001
FEE_SCENARIOS = [0.001, 0.0015, 0.002]

# 检验126日附近的参数是否形成相对平滑的表现区间
LOOKBACK_SCENARIOS = [105, 112, 119, 126, 133, 140, 147]

RESULT_FILE = "momentum_126_robustness_results.csv"
YEARLY_FILE = "momentum_126_yearly_results.csv"


# =========================
# 信号和指标
# =========================

def momentum_targets(close_prices, lookback):
    """
    收盘价高于lookback个交易日前的收盘价，目标仓位为1；
    否则目标仓位为0。
    """
    targets = []

    for i, price in enumerate(close_prices):
        if i < lookback:
            targets.append(0)
        else:
            targets.append(
                1 if price > close_prices[i - lookback] else 0
            )

    return targets


def calculate_metrics(result, initial_cash=INITIAL_CASH):
    """统一计算期末资产、收益、年化收益、夏普、回撤和手续费。"""
    curve = result["equity_curve"]

    if not curve:
        raise ValueError("回测器返回了空的权益曲线")

    equities = [float(row["equity"]) for row in curve]
    final_equity = float(result["final_equity"])

    total_return = final_equity / initial_cash - 1.0

    daily_returns = []
    for previous, current in zip(equities[:-1], equities[1:]):
        if previous > 0:
            daily_returns.append(current / previous - 1.0)

    if len(daily_returns) >= 2:
        mean_return = sum(daily_returns) / len(daily_returns)
        variance = sum(
            (r - mean_return) ** 2 for r in daily_returns
        ) / (len(daily_returns) - 1)
        daily_volatility = sqrt(variance)
    else:
        mean_return = 0.0
        daily_volatility = 0.0

    sharpe = (
        mean_return / daily_volatility * sqrt(252)
        if daily_volatility > 0
        else 0.0
    )

    peak = equities[0]
    max_drawdown = 0.0

    for equity in equities:
        peak = max(peak, equity)
        if peak > 0:
            max_drawdown = min(
                max_drawdown,
                equity / peak - 1.0,
            )

    years = len(daily_returns) / 252.0

    if years > 0 and final_equity > 0:
        annual_return = (
            (final_equity / initial_cash) ** (1.0 / years) - 1.0
        )
    else:
        annual_return = 0.0

    trades = result.get("trades", [])
    fees = sum(float(trade.get("fee", 0.0)) for trade in trades)

    return {
        "final_equity": final_equity,
        "total_return_pct": total_return * 100.0,
        "annual_return_pct": annual_return * 100.0,
        "sharpe": sharpe,
        "max_drawdown_pct": max_drawdown * 100.0,
        "order_count": len(trades),
        "fees": fees,
    }


def run_strategy(dates, opens, closes, targets, fee_rate):
    """统一执行规则：前一日收盘信号，下一交易日开盘执行。"""
    if not (
        len(dates) == len(opens) == len(closes) == len(targets)
    ):
        raise ValueError("日期、价格、目标仓位长度不一致")

    return run_backtest(
        dates=dates,
        open_prices=opens,
        close_prices=closes,
        symbol="QQQ",
        initial_cash=INITIAL_CASH,
        fee_rate=fee_rate,
        position_fraction=POSITION_FRACTION,
        target_positions=targets,
    )


def find_start_index(dates, start_date):
    for i, date in enumerate(dates):
        if str(date) >= start_date:
            return i

    raise ValueError(f"数据中找不到起始日期：{start_date}")


def print_result(name, metrics):
    print(
        f"{name:<20}"
        f"{metrics['final_equity']:>12.2f}"
        f"{metrics['total_return_pct']:>10.2f}"
        f"{metrics['annual_return_pct']:>10.2f}"
        f"{metrics['sharpe']:>9.3f}"
        f"{metrics['max_drawdown_pct']:>11.2f}"
        f"{metrics['order_count']:>9}"
        f"{metrics['fees']:>10.2f}"
    )


# =========================
# 主程序
# =========================

def main():
    folder = Path(__file__).parent
    data = load_price_csv(str(folder / DATA_FILE))

    dates = data["dates"]
    opens = data["open_prices"]
    closes = data["close_prices"]

    if not (len(dates) == len(opens) == len(closes)):
        raise ValueError("行情数据长度不一致")

    oos_start = find_start_index(dates, OOS_START_DATE)

    # 全量历史上生成信号，避免每个区间重新计算预热历史。
    targets_by_lookback = {
        n: momentum_targets(closes, n)
        for n in LOOKBACK_SCENARIOS
    }

    baseline_targets = targets_by_lookback[126]
    results = []

    print("=" * 86)
    print("126日动量策略稳健性检验")
    print(f"数据区间：{dates[0]} 至 {dates[-1]}")
    print(f"重点样本外区间：{dates[oos_start]} 至 {dates[-1]}")
    print(f"初始资金：${INITIAL_CASH:,.2f}")
    print(f"入场仓位：账户权益的 {POSITION_FRACTION:.0%}")
    print("仅做历史模拟，不连接真实券商")
    print("=" * 86)

    # ---------------------------------
    # 1. 时间稳健性：按自然年分别测试
    # ---------------------------------

    print("\n一、时间稳健性：126日动量年度区间表现")
    print("-" * 86)
    print(
        f"{'区间':<24}"
        f"{'期末资产':>12}"
        f"{'收益%':>10}"
        f"{'年化%':>10}"
        f"{'夏普':>9}"
        f"{'回撤%':>11}"
        f"{'订单数':>9}"
        f"{'手续费':>10}"
    )

    yearly_rows = []
    years = sorted(set(str(date)[:4] for date in dates))

    for year in years:
        start = next(
            (i for i, date in enumerate(dates)
             if str(date)[:4] == year),
            None,
        )

        if start is None:
            continue

        end = start
        while end < len(dates) and str(dates[end])[:4] == year:
            end += 1

        # 最初阶段的结果可能受到指标预热不足影响，因此从2019年开始展示。
        if year < "2019":
            continue

        period_dates = dates[start:end]
        period_opens = opens[start:end]
        period_closes = closes[start:end]
        period_targets = baseline_targets[start:end]

        result = run_strategy(
            period_dates,
            period_opens,
            period_closes,
            period_targets,
            BASE_FEE,
        )
        metrics = calculate_metrics(result)

        row = {
            "period": year,
            "start_date": period_dates[0],
            "end_date": period_dates[-1],
            "fee_rate": BASE_FEE,
            **metrics,
        }
        yearly_rows.append(row)

        print_result(year, metrics)

    # ---------------------------------
    # 2. 参数邻域：同一OOS区间比较周期
    # ---------------------------------

    print("\n二、参数稳健性：不同动量周期在同一OOS区间的表现")
    print("-" * 86)
    print(
        f"{'周期':<20}"
        f"{'期末资产':>12}"
        f"{'收益%':>10}"
        f"{'年化%':>10}"
        f"{'夏普':>9}"
        f"{'回撤%':>11}"
        f"{'订单数':>9}"
        f"{'手续费':>10}"
    )

    parameter_rows = []

    for lookback in LOOKBACK_SCENARIOS:
        result = run_strategy(
            dates[oos_start:],
            opens[oos_start:],
            closes[oos_start:],
            targets_by_lookback[lookback][oos_start:],
            BASE_FEE,
        )
        metrics = calculate_metrics(result)

        name = f"{lookback}日动量"
        print_result(name, metrics)

        parameter_rows.append({
            "test_type": "parameter",
            "name": name,
            "start_date": dates[oos_start],
            "end_date": dates[-1],
            "lookback": lookback,
            "fee_rate": BASE_FEE,
            **metrics,
        })

    # ---------------------------------
    # 3. 手续费敏感性：固定126日
    # ---------------------------------

    print("\n三、手续费敏感性：固定126日动量")
    print("-" * 86)
    print(
        f"{'单边手续费':<20}"
        f"{'期末资产':>12}"
        f"{'收益%':>10}"
        f"{'年化%':>10}"
        f"{'夏普':>9}"
        f"{'回撤%':>11}"
        f"{'订单数':>9}"
        f"{'手续费':>10}"
    )

    fee_rows = []

    for fee_rate in FEE_SCENARIOS:
        result = run_strategy(
            dates[oos_start:],
            opens[oos_start:],
            closes[oos_start:],
            baseline_targets[oos_start:],
            fee_rate,
        )
        metrics = calculate_metrics(result)

        name = f"{fee_rate * 100:.2f}%"
        print_result(name, metrics)

        fee_rows.append({
            "test_type": "fee",
            "name": name,
            "start_date": dates[oos_start],
            "end_date": dates[-1],
            "lookback": 126,
            "fee_rate": fee_rate,
            **metrics,
        })

    # ---------------------------------
    # 保存结果
    # ---------------------------------

    result_path = folder / RESULT_FILE
    all_rows = parameter_rows + fee_rows

    with open(
        result_path,
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as f:
        fields = list(all_rows[0].keys())
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(all_rows)

    yearly_path = folder / YEARLY_FILE

    with open(
        yearly_path,
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as f:
        fields = list(yearly_rows[0].keys())
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(yearly_rows)

    print("\n" + "=" * 86)
    print("测试完成")
    print(f"参数和手续费结果：{RESULT_FILE}")
    print(f"年度区间结果：{YEARLY_FILE}")
    print("注意：每个年度区间独立初始化账户，因此年度结果不能直接相加。")
    print("历史回测结果不代表未来收益。")


if __name__ == "__main__":
    main()

