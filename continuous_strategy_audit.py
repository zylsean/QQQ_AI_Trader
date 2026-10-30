
from pathlib import Path
import csv
from math import sqrt

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

LOOKBACKS = [42, 63, 84, 126]

SUMMARY_FILE = "continuous_strategy_audit_summary.csv"
TRADES_FILE = "continuous_strategy_audit_trades.csv"
BOUNDARIES_FILE = "continuous_strategy_audit_boundaries.csv"


def momentum_targets(closes, lookback):
    """收盘信号：价格高于lookback个交易日前的收盘价则持有。"""
    targets = []

    for i, close in enumerate(closes):
        if i < lookback:
            targets.append(0)
        else:
            targets.append(
                1 if close > closes[i - lookback] else 0
            )

    return targets


def materialize_targets(changes):
    """把None表示的状态延续事件转换为连续的目标状态。"""
    state = 0
    states = []

    for target in changes:
        if target is not None:
            state = int(target)
        states.append(state)

    return states


def calculate_metrics(result):
    curve = result["equity_curve"]
    equities = [float(row["equity"]) for row in curve]

    if not equities:
        raise ValueError("回测结果没有权益曲线")

    final_equity = float(result["final_equity"])
    total_return = final_equity / INITIAL_CASH - 1.0

    daily_returns = []

    for previous, current in zip(equities[:-1], equities[1:]):
        if previous > 0:
            daily_returns.append(current / previous - 1.0)

    if len(daily_returns) >= 2:
        mean_return = sum(daily_returns) / len(daily_returns)
        variance = sum(
            (r - mean_return) ** 2
            for r in daily_returns
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
            (final_equity / INITIAL_CASH) ** (1.0 / years) - 1.0
        )
    else:
        annual_return = 0.0

    trades = result.get("trades", [])
    total_fees = sum(
        float(trade.get("fee", 0.0))
        for trade in trades
    )

    return {
        "final_equity": final_equity,
        "total_return_pct": total_return * 100.0,
        "annual_return_pct": annual_return * 100.0,
        "sharpe": sharpe,
        "max_drawdown_pct": max_drawdown * 100.0,
        "order_count": len(trades),
        "total_fees": total_fees,
        "final_cash": float(result["cash"]),
        "final_positions": str(result["positions"]),
    }


def run_one(dates, opens, closes, targets):
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
        fee_rate=FEE_RATE,
        position_fraction=POSITION_FRACTION,
        target_positions=targets,
    )


def choose_lookback(dates, opens, closes, all_targets,
                    train_start, train_end):
    """只使用测试窗口开始前的训练数据选参。"""
    candidates = []

    for lookback in LOOKBACKS:
        result = run_one(
            dates[train_start:train_end],
            opens[train_start:train_end],
            closes[train_start:train_end],
            all_targets[lookback][train_start:train_end],
        )

        metrics = calculate_metrics(result)

        candidates.append({
            "lookback": lookback,
            "sharpe": metrics["sharpe"],
            "training_final_equity": metrics["final_equity"],
        })

    return max(
        candidates,
        key=lambda item: (
            item["sharpe"],
            item["lookback"],
        ),
    )


def find_start(dates, start_date):
    for i, date in enumerate(dates):
        if str(date) >= start_date:
            return i

    raise ValueError(f"找不到样本外起点：{start_date}")


def date_from_order_id(trade):
    """从本项目的订单编号提取日期；若格式不同则返回空值。"""
    order_id = str(trade.get("order_id", ""))
    parts = order_id.split("-")

    if len(parts) >= 5:
        return "-".join(parts[-3:])

    return ""


def main():
    folder = Path(__file__).parent
    data = load_price_csv(str(folder / DATA_FILE))

    dates = data["dates"]
    opens = data["open_prices"]
    closes = data["close_prices"]

    if not (len(dates) == len(opens) == len(closes)):
        raise ValueError("行情数据长度不一致")

    oos_start = find_start(dates, OOS_START_DATE)

    if oos_start < TRAIN_DAYS:
        raise ValueError("样本外起点前的训练数据不足")

    oos_dates = dates[oos_start:]
    oos_opens = opens[oos_start:]
    oos_closes = closes[oos_start:]

    all_targets = {
        n: momentum_targets(closes, n)
        for n in LOOKBACKS
    }

    # 滚动选择：每个测试窗口只使用此前训练窗口选出的参数。
    selected_by_index = {}
    selection_rows = []
    boundaries = []

    test_start = oos_start

    while test_start < len(dates):
        train_end = test_start
        train_start = train_end - TRAIN_DAYS
        test_end = min(test_start + TEST_DAYS, len(dates))

        selected = choose_lookback(
            dates,
            opens,
            closes,
            all_targets,
            train_start,
            train_end,
        )

        lookback = selected["lookback"]

        for i in range(test_start, test_end):
            selected_by_index[i] = lookback

        selection_rows.append({
            "train_start": dates[train_start],
            "train_end": dates[train_end - 1],
            "test_start": dates[test_start],
            "test_end": dates[test_end - 1],
            "lookback": lookback,
            "training_sharpe": selected["sharpe"],
        })

        boundaries.append(test_start)

        print(
            f"训练 {dates[train_start]} 至 {dates[train_end - 1]} | "
            f"测试 {dates[test_start]} 至 {dates[test_end - 1]} | "
            f"选中 {lookback} 日 | "
            f"训练夏普 {selected['sharpe']:.3f}"
        )

        test_start = test_end

    adaptive_targets = [
        all_targets[selected_by_index[i]][i]
        for i in range(oos_start, len(dates))
    ]

    fixed126_targets = all_targets[126][oos_start:]

    trend_full = materialize_targets(
        generate_trend_50_200_targets(closes)
    )
    trend_targets = trend_full[oos_start:]

    strategies = [
        ("滚动选择动量", adaptive_targets),
        ("固定126日动量", fixed126_targets),
        ("50/200趋势", trend_targets),
        ("买入持有基准", [1] * len(oos_dates)),
    ]

    summary_rows = []
    trade_rows = []
    equity_rows = []

    print("\n" + "=" * 100)
    print("连续样本外账户审计")
    print(f"区间：{oos_dates[0]} 至 {oos_dates[-1]}")
    print("每个策略均从样本外起点初始化账户，测试窗口之间不重置账户。")
    print("-" * 100)

    print(
        f"{'策略':<18}"
        f"{'期末资产':>12}"
        f"{'收益%':>10}"
        f"{'年化%':>10}"
        f"{'夏普':>9}"
        f"{'回撤%':>10}"
        f"{'订单数':>9}"
        f"{'手续费':>10}"
    )

    results_by_name = {}

    for name, targets in strategies:
        result = run_one(
            oos_dates,
            oos_opens,
            oos_closes,
            targets,
        )
        metrics = calculate_metrics(result)
        results_by_name[name] = result

        summary_rows.append({
            "strategy": name,
            "start_date": oos_dates[0],
            "end_date": oos_dates[-1],
            "fee_rate": FEE_RATE,
            "position_fraction": POSITION_FRACTION,
            **metrics,
        })

        print(
            f"{name:<18}"
            f"{metrics['final_equity']:>12.2f}"
            f"{metrics['total_return_pct']:>10.2f}"
            f"{metrics['annual_return_pct']:>10.2f}"
            f"{metrics['sharpe']:>9.3f}"
            f"{metrics['max_drawdown_pct']:>10.2f}"
            f"{metrics['order_count']:>9}"
            f"{metrics['total_fees']:>10.2f}"
        )

        # 保存成交明细。日期从订单编号提取。
        for trade in result.get("trades", []):
            trade_rows.append({
                "strategy": name,
                "date": date_from_order_id(trade),
                "order_id": trade.get("order_id", ""),
                "side": trade.get("side", ""),
                "qty": trade.get("qty", ""),
                "price": trade.get("price", ""),
                "fee": trade.get("fee", ""),
                "realized_pnl": trade.get("realized_pnl", ""),
            })

        # 保存每日权益曲线，便于独立计算收益和回撤。
        for row in result.get("equity_curve", []):
            equity_rows.append({
                "strategy": name,
                "date": row.get("date", ""),
                "equity": row.get("equity", ""),
                "drawdown": row.get("drawdown", ""),
            })

    # 窗口边界审计：检查选参变化前后目标是否发生变化。
    print("\n窗口边界目标仓位检查")
    print("-" * 100)

    boundary_rows = []

    for boundary in boundaries:
        for idx in range(max(oos_start, boundary - 2),
                         min(len(dates), boundary + 3)):
            local_idx = idx - oos_start

            row = {
                "boundary_date": dates[boundary],
                "date": dates[idx],
                "selected_lookback": selected_by_index.get(idx),
                "adaptive_target": adaptive_targets[local_idx],
                "fixed126_target": fixed126_targets[local_idx],
                "trend_target": trend_targets[local_idx],
            }
            boundary_rows.append(row)

            print(
                f"边界={dates[boundary]} | "
                f"日期={dates[idx]} | "
                f"滚动周期={row['selected_lookback']} | "
                f"滚动目标={row['adaptive_target']} | "
                f"固定126目标={row['fixed126_target']} | "
                f"趋势目标={row['trend_target']}"
            )

    # 趋势策略一致性检查。
    trend_metrics = next(
        row for row in summary_rows
        if row["strategy"] == "50/200趋势"
    )

    print("\n趋势策略基准检查")
    print(f"期末资产：{trend_metrics['final_equity']:.2f}")
    print(f"收益率：{trend_metrics['total_return_pct']:.2f}%")
    print(f"订单数：{trend_metrics['order_count']}")

    if trend_metrics["order_count"] != 3:
        print("提示：订单数与之前的诊断结果不同，应检查数据或执行规则。")
    else:
        print("订单数与此前诊断的3笔成交一致。")

    # 保存汇总、成交和边界文件。
    def write_csv(path, rows):
        if not rows:
            print(f"跳过空结果文件：{path.name}")
            return

        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=list(rows[0].keys()),
            )
            writer.writeheader()
            writer.writerows(rows)

    write_csv(folder / SUMMARY_FILE, summary_rows)
    write_csv(folder / TRADES_FILE, trade_rows)
    write_csv(folder / BOUNDARIES_FILE, boundary_rows)
    write_csv(
        folder / "continuous_strategy_audit_equity.csv",
        equity_rows,
    )
    write_csv(
        folder / "continuous_strategy_audit_selections.csv",
        selection_rows,
    )

    print("\n审计文件已生成：")
    print(SUMMARY_FILE)
    print(TRADES_FILE)
    print(BOUNDARIES_FILE)
    print("continuous_strategy_audit_equity.csv")
    print("continuous_strategy_audit_selections.csv")
    print("\n注意：历史回测不代表未来收益。")


if __name__ == "__main__":
    main()

