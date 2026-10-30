
from pathlib import Path
from math import sqrt

from csv_data import load_price_csv
from backtester import run_backtest
from strategy_adapter import generate_trend_50_200_targets


INITIAL_CASH = 10000.0
FEE_RATE = 0.001
POSITION_FRACTION = 0.20
TRAIN_FRACTION = 0.70
TRADING_DAYS = 252


def load_market_data():
    folder = Path(__file__).parent
    data_path = folder / "QQQ_yahoo_10y.csv"

    if not data_path.exists():
        data_path = folder / "QQQ_history.csv"

    if not data_path.exists():
        raise FileNotFoundError(
            "找不到 QQQ_yahoo_10y.csv 或 QQQ_history.csv"
        )

    data = load_price_csv(str(data_path))

    dates = data["dates"]
    opens = data["open_prices"]
    closes = data["close_prices"]

    if not (len(dates) == len(opens) == len(closes)):
        raise ValueError("日期、开盘价和收盘价长度不一致")

    if len(dates) < 500:
        raise ValueError("数据不足，无法进行样本外诊断")

    return dates, opens, closes, data_path.name


def make_momentum_targets(closes, window=63):
    """使用当日收盘价与63个交易日前收盘价比较。"""
    targets = []
    current_target = 0

    for i, price in enumerate(closes):
        if i < window:
            targets.append(None)
            continue

        new_target = 1 if price > closes[i - window] else 0

        if new_target != current_target:
            targets.append(new_target)
            current_target = new_target
        else:
            targets.append(None)

    return targets


def materialize_targets(targets):
    """将变化信号转换成每天明确的目标仓位。"""
    result = []
    current_target = 0

    for target in targets:
        if target is not None:
            current_target = int(target)
        result.append(current_target)

    return result


def normalize_date(value):
    """统一日期格式，兼容 YYYY-MM-DD 和带时间的日期字符串。"""
    return str(value)[:10]


def trade_date_from_order_id(trade):
    """
    当前 PaperBroker 不保存 date 字段。
    日期来自 backtester.py 创建的订单编号：
    BUY-QQQ-YYYY-MM-DD 或 SELL-QQQ-YYYY-MM-DD。
    """
    order_id = trade.get("order_id", "")

    parts = order_id.split("-", 2)
    if len(parts) != 3:
        raise ValueError(
            "无法从订单编号解析交易日期：{}".format(order_id)
        )

    return normalize_date(parts[2])


def calculate_metrics(result):
    curve = result["equity_curve"]

    if not curve:
        raise ValueError("回测没有返回权益曲线")

    equities = [float(item["equity"]) for item in curve]

    returns = []
    for i in range(1, len(equities)):
        previous = equities[i - 1]
        if previous > 0:
            returns.append(equities[i] / previous - 1)

    if returns:
        mean_return = sum(returns) / len(returns)
        variance = sum(
            (value - mean_return) ** 2 for value in returns
        ) / len(returns)

        daily_vol = sqrt(variance)
        annual_vol = daily_vol * sqrt(TRADING_DAYS)

        annual_return = (
            (equities[-1] / INITIAL_CASH)
            ** (TRADING_DAYS / len(returns)) - 1
            if equities[-1] > 0 else -1.0
        )

        sharpe = (
            mean_return / daily_vol * sqrt(TRADING_DAYS)
            if daily_vol > 0 else 0.0
        )
    else:
        annual_return = 0.0
        annual_vol = 0.0
        sharpe = 0.0

    peak = INITIAL_CASH
    max_drawdown = 0.0

    for equity in equities:
        peak = max(peak, equity)
        if peak > 0:
            max_drawdown = max(
                max_drawdown, (peak - equity) / peak
            )

    return {
        "final_equity": equities[-1],
        "total_return": equities[-1] / INITIAL_CASH - 1,
        "annual_return": annual_return,
        "annual_vol": annual_vol,
        "sharpe": sharpe,
        "max_drawdown": max_drawdown,
    }


def reconstruct_exposure(result, dates, closes):
    """
    用真实成交记录重建每日收盘持仓。
    回测成交在开盘，权益曲线记录收盘权益。
    """
    date_to_index = {
        normalize_date(date): i
        for i, date in enumerate(dates)
    }

    trades_by_day = [[] for _ in dates]
    trades = result.get("trades", [])

    for trade in trades:
        trade_date = trade_date_from_order_id(trade)

        if trade_date not in date_to_index:
            raise ValueError(
                "交易日期不在样本外数据中：{}".format(trade_date)
            )

        index = date_to_index[trade_date]
        trades_by_day[index].append(trade)

    qty = 0
    holding_days = 0
    total_exposure = 0.0
    invested_days = 0
    daily_details = []

    curve = result["equity_curve"]

    if len(curve) != len(dates):
        raise ValueError("权益曲线长度与样本外日期不一致")

    for i, date in enumerate(dates):
        # 先处理当日开盘成交，再按当日收盘价估值。
        for trade in trades_by_day[i]:
            side = str(trade.get("side", "")).upper()
            trade_qty = int(trade["qty"])

            if side == "BUY":
                qty += trade_qty
            elif side == "SELL":
                qty -= trade_qty
            else:
                raise ValueError(
                    "无法识别交易方向：{}".format(side)
                )

            if qty < 0:
                raise ValueError(
                    "重建持仓出现负股数，日期：{}".format(date)
                )

        equity = float(curve[i]["equity"])
        market_value = qty * float(closes[i])
        exposure = (
            market_value / equity if equity > 0 else 0.0
        )

        if qty > 0:
            holding_days += 1

        total_exposure += exposure
        invested_days += 1

        daily_details.append({
            "date": date,
            "qty": qty,
            "close": closes[i],
            "market_value": market_value,
            "equity": equity,
            "exposure": exposure,
        })

    if qty != sum(
        int(position["qty"])
        for position in result.get("positions", {}).values()
    ):
        raise ValueError(
            "根据成交记录重建的期末持仓与经纪账户不一致"
        )

    average_exposure = (
        total_exposure / invested_days
        if invested_days else 0.0
    )

    return {
        "holding_days": holding_days,
        "average_exposure": average_exposure,
        "daily_details": daily_details,
    }


def calculate_trade_stats(result):
    trades = result.get("trades", [])

    buy_trades = [
        t for t in trades
        if str(t.get("side", "")).upper() == "BUY"
    ]
    sell_trades = [
        t for t in trades
        if str(t.get("side", "")).upper() == "SELL"
    ]

    total_fees = sum(float(t.get("fee", 0.0)) for t in trades)

    realized_pnl = sum(
        float(t.get("realized_pnl", 0.0))
        for t in sell_trades
    )

    return {
        "trade_count": len(trades),
        "buy_count": len(buy_trades),
        "sell_count": len(sell_trades),
        "total_fees": total_fees,
        "realized_pnl": realized_pnl,
    }


def print_report(rows, test_dates):
    print("\n" + "=" * 116)
    print("QQQ 样本外交易诊断（修正版）")
    print(
        "{:<20}{:>11}{:>10}{:>10}{:>9}{:>9}"
        "{:>10}{:>9}{:>10}{:>10}{:>11}".format(
            "策略", "期末资产", "累计收益", "年化收益",
            "波动率", "夏普", "最大回撤", "成交次数",
            "手续费", "持仓天数", "平均资金暴露"
        )
    )
    print("-" * 116)

    for row in rows:
        m = row["metrics"]
        s = row["stats"]
        e = row["exposure"]

        print(
            "{:<20}{:>11.2f}{:>9.2f}%{:>9.2f}%"
            "{:>8.2f}%{:>9.3f}{:>9.2f}%{:>9}"
            "{:>10.2f}{:>10}{:>10.2f}%".format(
                row["name"],
                m["final_equity"],
                m["total_return"] * 100,
                m["annual_return"] * 100,
                m["annual_vol"] * 100,
                m["sharpe"],
                m["max_drawdown"] * 100,
                s["trade_count"],
                s["total_fees"],
                e["holding_days"],
                e["average_exposure"] * 100,
            )
        )

    print("=" * 116)

    print("\n【收益差异：相对买入持有】")
    baseline = rows[0]

    for row in rows[1:]:
        print(
            "{}：期末资产差额 {:+.2f}，累计收益差额 {:+.2f} 个百分点".format(
                row["name"],
                row["metrics"]["final_equity"]
                - baseline["metrics"]["final_equity"],
                (
                    row["metrics"]["total_return"]
                    - baseline["metrics"]["total_return"]
                ) * 100,
            )
        )

    print("\n【交易记录】")

    for row in rows:
        print("\n--- {} ---".format(row["name"]))

        trades = row["result"].get("trades", [])

        if not trades:
            print("没有成交")
            continue

        for trade in trades:
            print(
                "日期={} 方向={} 数量={} 价格={:.2f} "
                "手续费={:.2f} 已实现盈亏={:.2f}".format(
                    trade_date_from_order_id(trade),
                    trade.get("side", "?"),
                    trade.get("qty", 0),
                    float(trade.get("price", 0.0)),
                    float(trade.get("fee", 0.0)),
                    float(trade.get("realized_pnl", 0.0)),
                )
            )


def main():
    dates, opens, closes, filename = load_market_data()

    split_index = int(len(dates) * TRAIN_FRACTION)

    test_dates = dates[split_index:]
    test_opens = opens[split_index:]
    test_closes = closes[split_index:]

    if len(test_dates) < 100:
        raise ValueError("样本外交易日不足")

    # 使用完整历史因果生成信号，再切取样本外部分。
    trend_targets = materialize_targets(
        generate_trend_50_200_targets(closes)
    )
    momentum_targets = materialize_targets(
        make_momentum_targets(closes)
    )

    strategies = [
        ("买入持有（20%仓位）", [1] * len(test_dates)),
        ("50/200 趋势", trend_targets[split_index:]),
        ("63 日动量", momentum_targets[split_index:]),
    ]

    print("=" * 80)
    print("数据文件：{}".format(filename))
    print("完整数据：{} 至 {}".format(dates[0], dates[-1]))
    print(
        "样本外区间：{} 至 {}".format(
            test_dates[0], test_dates[-1]
        )
    )
    print("样本外交易日：{}".format(len(test_dates)))
    print("初始资金：{:.2f}".format(INITIAL_CASH))
    print("单边手续费：{:.2f}%".format(FEE_RATE * 100))
    print("单次开仓仓位上限：{:.1f}%".format(
        POSITION_FRACTION * 100
    ))
    print("执行规则：前一交易日收盘信号，下一交易日开盘成交")
    print("注意：回测结果不代表未来收益。")

    rows = []

    for name, targets in strategies:
        result = run_backtest(
            dates=test_dates,
            open_prices=test_opens,
            close_prices=test_closes,
            symbol="QQQ",
            initial_cash=INITIAL_CASH,
            fee_rate=FEE_RATE,
            position_fraction=POSITION_FRACTION,
            target_positions=targets,
        )

        metrics = calculate_metrics(result)
        stats = calculate_trade_stats(result)
        exposure = reconstruct_exposure(
            result, test_dates, test_closes
        )

        rows.append({
            "name": name,
            "result": result,
            "metrics": metrics,
            "stats": stats,
            "exposure": exposure,
        })

    print_report(rows, test_dates)

    print("\n【资金与账本核对】")
    for row in rows:
        result = row["result"]
        exposure = row["exposure"]
        final_position = result.get("positions", {}).get(
            "QQQ", {"qty": 0, "cost": 0.0}
        )

        print(
            "{}：现金={:.2f}，期末股数={}，"
            "持仓成本={:.2f}，持仓天数={}，"
            "平均资金暴露={:.2f}%".format(
                row["name"],
                result["cash"],
                final_position["qty"],
                final_position["cost"],
                exposure["holding_days"],
                exposure["average_exposure"] * 100,
            )
        )


if __name__ == "__main__":
    main()


