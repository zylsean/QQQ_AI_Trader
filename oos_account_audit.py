
import csv
from pathlib import Path

from csv_data import load_price_csv
from backtester import run_backtest
from strategy_adapter import generate_trend_50_200_targets


INITIAL_CASH = 10000.0
FEE_RATE = 0.001
POSITION_FRACTION = 0.20
TRAIN_FRACTION = 0.70
TOLERANCE = 0.03


def normalize_date(value):
    return str(value)[:10]


def get_trade_date(trade):
    order_id = trade.get("order_id", "")
    parts = order_id.split("-", 2)

    if len(parts) != 3:
        raise ValueError(
            "无法从订单编号解析日期：{}".format(order_id)
        )

    return normalize_date(parts[2])


def load_data():
    folder = Path(__file__).parent

    path = folder / "QQQ_yahoo_10y.csv"
    if not path.exists():
        path = folder / "QQQ_history.csv"

    if not path.exists():
        raise FileNotFoundError(
            "找不到 QQQ_yahoo_10y.csv 或 QQQ_history.csv"
        )

    data = load_price_csv(str(path))

    dates = data["dates"]
    opens = data["open_prices"]
    closes = data["close_prices"]

    if not (len(dates) == len(opens) == len(closes)):
        raise ValueError("日期、开盘价、收盘价长度不一致")

    if len(dates) < 500:
        raise ValueError("历史数据不足")

    return dates, opens, closes, path.name, folder


def make_momentum_targets(closes, window=63):
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
    result = []
    current_target = 0

    for target in targets:
        if target is not None:
            current_target = int(target)

        result.append(current_target)

    return result


def reconstruct_account(dates, closes, result, strategy_name):
    """
    根据逐笔成交重建每日现金、持股数量和收盘权益。

    买入：现金减少 成交数量*价格 + 手续费
    卖出：现金增加 成交数量*价格 - 手续费
    """
    curve = result["equity_curve"]
    trades = result["trades"]

    if len(curve) != len(dates):
        raise ValueError(
            "{}：权益曲线长度不匹配".format(strategy_name)
        )

    date_to_index = {
        normalize_date(date): i
        for i, date in enumerate(dates)
    }

    trades_by_day = [[] for _ in dates]

    for trade in trades:
        trade_date = get_trade_date(trade)

        if trade_date not in date_to_index:
            raise ValueError(
                "{}：成交日期不在回测区间内：{}".format(
                    strategy_name, trade_date
                )
            )

        trades_by_day[date_to_index[trade_date]].append(trade)

    cash = INITIAL_CASH
    qty = 0

    daily_rows = []
    trade_rows = []

    max_equity_diff = 0.0
    max_cash_diff = 0.0
    negative_cash_count = 0
    negative_qty_count = 0

    for i, date in enumerate(dates):
        date_text = normalize_date(date)
        day_actions = []

        # 成交在开盘发生，先更新账户，再按收盘价估值。
        for trade in trades_by_day[i]:
            side = str(trade["side"]).upper()
            trade_qty = int(trade["qty"])
            price = float(trade["price"])
            fee = float(trade.get("fee", 0.0))

            if trade_qty <= 0 or price <= 0 or fee < 0:
                raise ValueError(
                    "{}：发现不合法的成交记录".format(
                        strategy_name
                    )
                )

            if side == "BUY":
                cash -= trade_qty * price + fee
                qty += trade_qty
            elif side == "SELL":
                cash += trade_qty * price - fee
                qty -= trade_qty
            else:
                raise ValueError(
                    "{}：未知成交方向 {}".format(
                        strategy_name, side
                    )
                )

            if cash < -TOLERANCE:
                negative_cash_count += 1

            if qty < 0:
                negative_qty_count += 1

            day_actions.append(
                "{} {}股 @ {:.2f}".format(
                    side, trade_qty, price
                )
            )

            trade_rows.append({
                "strategy": strategy_name,
                "date": date_text,
                "order_id": trade.get("order_id", ""),
                "side": side,
                "qty": trade_qty,
                "price": price,
                "fee": fee,
                "realized_pnl": trade.get(
                    "realized_pnl", ""
                ),
                "cash_after_trade": round(cash, 4),
                "qty_after_trade": qty,
            })

        close_price = float(closes[i])
        market_value = qty * close_price
        reconstructed_equity = cash + market_value

        engine_equity = float(curve[i]["equity"])
        engine_drawdown = float(curve[i]["drawdown"])

        equity_diff = reconstructed_equity - engine_equity
        max_equity_diff = max(
            max_equity_diff, abs(equity_diff)
        )

        # 重建持仓市值和权益，用于计算实际资金暴露。
        exposure = (
            market_value / reconstructed_equity
            if reconstructed_equity > 0 else 0.0
        )

        daily_rows.append({
            "strategy": strategy_name,
            "date": date_text,
            "open": "",
            "close": close_price,
            "trades": "; ".join(day_actions),
            "qty": qty,
            "cash_reconstructed": round(cash, 4),
            "market_value": round(market_value, 4),
            "equity_reconstructed": round(
                reconstructed_equity, 4
            ),
            "equity_engine": round(engine_equity, 2),
            "equity_diff": round(equity_diff, 4),
            "engine_drawdown": engine_drawdown,
            "exposure": round(exposure, 6),
        })

    # 核对期末持仓。
    final_positions = result.get("positions", {})
    final_position = final_positions.get(
        "QQQ", {"qty": 0, "cost": 0.0}
    )

    engine_qty = int(final_position["qty"])
    engine_cash = float(result["cash"])

    final_cash_diff = cash - engine_cash
    max_cash_diff = abs(final_cash_diff)

    qty_match = qty == engine_qty
    cash_match = max_cash_diff <= TOLERANCE
    equity_match = max_equity_diff <= TOLERANCE
    no_negative_qty = negative_qty_count == 0
    no_negative_cash = negative_cash_count == 0

    passed = (
        qty_match
        and cash_match
        and equity_match
        and no_negative_qty
        and no_negative_cash
    )

    holding_days = sum(
        1 for row in daily_rows if row["qty"] > 0
    )

    average_exposure = (
        sum(row["exposure"] for row in daily_rows)
        / len(daily_rows)
        if daily_rows else 0.0
    )

    audit_summary = {
        "strategy": strategy_name,
        "status": "PASS" if passed else "FAIL",
        "trade_count": len(trades),
        "holding_days": holding_days,
        "average_exposure_pct": average_exposure * 100,
        "max_equity_diff": max_equity_diff,
        "cash_diff": final_cash_diff,
        "reconstructed_qty": qty,
        "engine_qty": engine_qty,
        "reconstructed_cash": cash,
        "engine_cash": engine_cash,
        "final_equity": float(result["final_equity"]),
        "max_negative_cash_events": negative_cash_count,
        "negative_qty_events": negative_qty_count,
    }

    return daily_rows, trade_rows, audit_summary


def write_csv(path, rows):
    if not rows:
        print("没有数据，未写入：{}".format(path.name))
        return

    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(
            f, fieldnames=list(rows[0].keys())
        )
        writer.writeheader()
        writer.writerows(rows)


def main():
    dates, opens, closes, filename, folder = load_data()

    split_index = int(len(dates) * TRAIN_FRACTION)

    test_dates = dates[split_index:]
    test_opens = opens[split_index:]
    test_closes = closes[split_index:]

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

    print("=" * 76)
    print("QQQ 样本外账户审计")
    print("数据文件：{}".format(filename))
    print("完整数据：{} 至 {}".format(dates[0], dates[-1]))
    print(
        "样本外区间：{} 至 {}".format(
            test_dates[0], test_dates[-1]
        )
    )
    print("样本外交易日：{}".format(len(test_dates)))
    print("审计容差：{:.2f} 美元".format(TOLERANCE))
    print("执行规则：前一交易日收盘信号，下一交易日开盘成交")
    print("注意：这是 PAPER 回测审计，不是实盘交易。")

    all_daily_rows = []
    all_trade_rows = []
    summaries = []

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

        daily_rows, trade_rows, summary = reconstruct_account(
            test_dates, test_closes, result, name
        )

        all_daily_rows.extend(daily_rows)
        all_trade_rows.extend(trade_rows)
        summaries.append(summary)

    print("\n【审计结果】")
    print(
        "{:<20}{:<8}{:>10}{:>12}{:>12}{:>10}{:>10}".format(
            "策略", "状态", "成交次数", "期末资产",
            "最大权益差", "现金差", "期末股数"
        )
    )
    print("-" * 84)

    for item in summaries:
        print(
            "{:<20}{:<8}{:>10}{:>12.2f}{:>12.4f}"
            "{:>10.4f}{:>10}".format(
                item["strategy"],
                item["status"],
                item["trade_count"],
                item["final_equity"],
                item["max_equity_diff"],
                item["cash_diff"],
                item["reconstructed_qty"],
            )
        )

    print("\n【持仓与资金暴露】")
    for item in summaries:
        print(
            "{}：持仓天数 {}，平均资金暴露 {:.2f}%，"
            "重建股数 {}，引擎股数 {}".format(
                item["strategy"],
                item["holding_days"],
                item["average_exposure_pct"],
                item["reconstructed_qty"],
                item["engine_qty"],
            )
        )

    daily_path = folder / "oos_daily_account_audit.csv"
    trades_path = folder / "oos_trade_ledger_audit.csv"

    write_csv(daily_path, all_daily_rows)
    write_csv(trades_path, all_trade_rows)

    print("\n【输出文件】")
    print(daily_path.name)
    print(trades_path.name)

    failed = [
        item for item in summaries
        if item["status"] != "PASS"
    ]

    if failed:
        print("\n审计未全部通过。请保留输出文件，不要修改核心模块。")
        raise RuntimeError(
            "{} 个策略未通过账户审计".format(len(failed))
        )

    print("\n全部策略均通过账户重建核对。")
    print("注意：审计通过只说明账本能对上，不代表策略有效。")


if __name__ == "__main__":
    main()

