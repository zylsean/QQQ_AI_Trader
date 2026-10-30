import csv
from collections import defaultdict, deque
from datetime import date as Date
from pathlib import Path

from csv_data import load_price_csv


FOLDER = Path(__file__).parent

PRICE_FILE = FOLDER / "QQQ_yahoo_10y.csv"
DAILY_FILE = FOLDER / "oos_daily_account_audit.csv"
LEDGER_FILE = FOLDER / "oos_trade_ledger_audit.csv"

CLOSED_FILE = FOLDER / "oos_closed_trade_attribution.csv"
DAILY_OUTPUT_FILE = FOLDER / "oos_daily_market_attribution.csv"

INITIAL_CASH = 10000.0
SPLIT_RATIO = 0.70
EPSILON = 1e-8


def read_csv(path):
    if not path.exists():
        raise FileNotFoundError(f"找不到文件：{path.name}")

    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))

    if not rows:
        raise ValueError(f"文件没有数据：{path.name}")

    return rows


def write_csv(path, fields, rows):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def number(value, field):
    try:
        result = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"字段 {field} 不是有效数字：{value!r}")

    return result


def day_string(value):
    return str(value).strip()[:10]


def round_money(value):
    return round(float(value), 4)


def match_trades(strategy, ledger, day_index):
    """FIFO 配对买卖，买入和卖出手续费均计入净盈亏。"""
    rows = sorted(
        [r for r in ledger if r["strategy"] == strategy],
        key=lambda r: (r["date"], r["_sequence"]),
    )

    lots = deque()
    closed = []

    for row in rows:
        side = row["side"].strip().upper()
        qty = int(number(row["qty"], "qty"))
        price = number(row["price"], "price")
        fee = number(row["fee"], "fee")
        trade_date = day_string(row["date"])

        if qty <= 0 or price <= 0 or fee < 0:
            raise ValueError(f"成交数据异常：{row}")

        if side == "BUY":
            lots.append({
                "buy_date": trade_date,
                "buy_price": price,
                "remaining_qty": qty,
                "buy_cost_per_share": price + fee / qty,
                "buy_fee_per_share": fee / qty,
            })

        elif side == "SELL":
            remaining = qty
            sell_fee_per_share = fee / qty

            while remaining > 0:
                if not lots:
                    raise ValueError(
                        f"{strategy} 的卖出交易找不到对应买入：{row}"
                    )

                lot = lots[0]
                matched_qty = min(remaining, lot["remaining_qty"])

                buy_cost = (
                    matched_qty * lot["buy_cost_per_share"]
                )
                sell_proceeds = matched_qty * (
                    price - sell_fee_per_share
                )
                pnl = sell_proceeds - buy_cost

                buy_date = lot["buy_date"]
                if buy_date in day_index and trade_date in day_index:
                    trading_days = (
                        day_index[trade_date] - day_index[buy_date]
                    )
                else:
                    trading_days = ""

                calendar_days = (
                    Date.fromisoformat(trade_date)
                    - Date.fromisoformat(buy_date)
                ).days

                closed.append({
                    "strategy": strategy,
                    "status": "CLOSED",
                    "buy_date": buy_date,
                    "sell_date": trade_date,
                    "qty": matched_qty,
                    "buy_price": round_money(lot["buy_price"]),
                    "sell_price": round_money(price),
                    "allocated_buy_fee": round_money(
                        matched_qty * lot["buy_fee_per_share"]
                    ),
                    "allocated_sell_fee": round_money(
                        matched_qty * sell_fee_per_share
                    ),
                    "buy_cost_including_fee": round_money(buy_cost),
                    "net_pnl": round_money(pnl),
                    "return_pct": round_money(
                        pnl / buy_cost * 100 if buy_cost else 0
                    ),
                    "trading_days_held": trading_days,
                    "calendar_days_held": calendar_days,
                })

                lot["remaining_qty"] -= matched_qty
                remaining -= matched_qty

                if lot["remaining_qty"] == 0:
                    lots.popleft()

        else:
            raise ValueError(f"未知交易方向：{side}")

    return closed, list(lots)


def main():
    print("=" * 72)
    print("QQQ 样本外交易归因分析")
    print("PAPER 回测研究，不进行真实交易")
    print("=" * 72)

    price_data = load_price_csv(str(PRICE_FILE))
    all_dates = [day_string(x) for x in price_data["dates"]]
    all_opens = [float(x) for x in price_data["open_prices"]]
    all_closes = [float(x) for x in price_data["close_prices"]]

    if not (
        len(all_dates) == len(all_opens) == len(all_closes)
    ):
        raise ValueError("价格数据长度不一致。")

    if len(set(all_dates)) != len(all_dates):
        raise ValueError("价格文件存在重复日期。")

    split = int(len(all_dates) * SPLIT_RATIO)
    oos_dates = all_dates[split:]
    oos_opens = all_opens[split:]
    oos_closes = all_closes[split:]

    day_index = {d: i for i, d in enumerate(all_dates)}

    daily_rows = read_csv(DAILY_FILE)
    ledger_rows = read_csv(LEDGER_FILE)

    daily_by_strategy = defaultdict(list)
    ledger_by_strategy = defaultdict(list)

    for row in daily_rows:
        row["date"] = day_string(row["date"])
        daily_by_strategy[row["strategy"]].append(row)

    for seq, row in enumerate(ledger_rows):
        row["date"] = day_string(row["date"])
        row["_sequence"] = seq
        ledger_by_strategy[row["strategy"]].append(row)

    expected_dates = set(oos_dates)
    strategies = list(daily_by_strategy.keys())

    if not strategies:
        raise ValueError("每日审计文件没有策略记录。")

    for strategy, rows in daily_by_strategy.items():
        actual_dates = {r["date"] for r in rows}
        if actual_dates != expected_dates:
            raise ValueError(
                f"{strategy} 的日期范围与价格文件不一致。"
                "请确认审计文件和价格文件来自同一次回测。"
            )

    closed_output = []
    daily_output = []
    summaries = {}

    for strategy in strategies:
        daily = sorted(
            daily_by_strategy[strategy],
            key=lambda r: r["date"],
        )
        ledger = ledger_by_strategy.get(strategy, [])

        closed, open_lots = match_trades(
            strategy, ledger, day_index
        )
        closed_output.extend(closed)

        # 已平仓交易统计
        pnls = [float(r["net_pnl"]) for r in closed]
        wins = [x for x in pnls if x > EPSILON]
        losses = [x for x in pnls if x < -EPSILON]
        breakeven = [x for x in pnls if abs(x) <= EPSILON]

        total_fees = sum(number(r["fee"], "fee") for r in ledger)
        final_equity = number(
            daily[-1]["equity_reconstructed"],
            "equity_reconstructed",
        )
        net_profit = final_equity - INITIAL_CASH

        gross_wins = sum(wins)
        gross_losses = abs(sum(losses))

        if gross_losses > EPSILON:
            pf = round(gross_wins / gross_losses, 4)
        elif gross_wins > EPSILON:
            pf = "INF"
        else:
            pf = ""

        fee_ratio = (
            round(total_fees / net_profit * 100, 4)
            if net_profit > EPSILON else ""
        )

        summaries[strategy] = {
            "closed_count": len(closed),
            "win_rate": (
                len(wins) / len(closed) * 100 if closed else 0
            ),
            "avg_win": sum(wins) / len(wins) if wins else 0,
            "avg_loss": sum(losses) / len(losses) if losses else 0,
            "profit_factor": pf,
            "best": max(pnls) if pnls else 0,
            "worst": min(pnls) if pnls else 0,
            "closed_pnl": sum(pnls),
            "fees": total_fees,
            "final_equity": final_equity,
            "net_profit": net_profit,
            "fee_ratio": fee_ratio,
        }

        # 每个策略单独计算期末未平仓成本和浮动盈亏
        remaining_qty = sum(
            lot["remaining_qty"] for lot in open_lots
        )
        remaining_cost = sum(
            lot["remaining_qty"] * lot["buy_cost_per_share"]
            for lot in open_lots
        )
        remaining_market_value = remaining_qty * oos_closes[-1]
        remaining_unrealized = remaining_market_value - remaining_cost

        summaries[strategy].update({
            "open_qty": remaining_qty,
            "open_cost": remaining_cost,
            "open_market_value": remaining_market_value,
            "open_unrealized": remaining_unrealized,
        })

        daily_map = {r["date"]: r for r in daily}
        trades_by_date = defaultdict(list)

        for row in ledger:
            trades_by_date[row["date"]].append(row)

        for i, d in enumerate(oos_dates):
            qty_end = int(round(number(daily_map[d]["qty"], "qty")))
            net_change = 0
            day_fee = 0.0

            for trade in trades_by_date.get(d, []):
                qty = int(number(trade["qty"], "qty"))
                side = trade["side"].strip().upper()

                if side == "BUY":
                    net_change += qty
                elif side == "SELL":
                    net_change -= qty
                else:
                    raise ValueError(f"未知交易方向：{side}")

                day_fee += number(trade["fee"], "fee")

            qty_before_open = qty_end - net_change
            if qty_before_open < 0 or qty_end < 0:
                raise ValueError(
                    f"{strategy} 在 {d} 重建出了负持仓。"
                )

            open_price = oos_opens[i]
            close_price = oos_closes[i]

            if i == 0:
                overnight_pnl = 0.0
                qqq_return = ""
            else:
                overnight_pnl = qty_before_open * (
                    open_price - oos_closes[i - 1]
                )
                qqq_return = round(
                    (close_price / oos_closes[i - 1] - 1) * 100,
                    6,
                )

            intraday_pnl = qty_end * (close_price - open_price)

            daily_output.append({
                "strategy": strategy,
                "date": d,
                "qty_before_open": qty_before_open,
                "qty_after_open": qty_end,
                "open_price": round_money(open_price),
                "close_price": round_money(close_price),
                "overnight_price_pnl": round_money(overnight_pnl),
                "intraday_price_pnl": round_money(intraday_pnl),
                "total_price_pnl": round_money(
                    overnight_pnl + intraday_pnl
                ),
                "fees_paid": round_money(day_fee),
                "price_pnl_after_fees": round_money(
                    overnight_pnl + intraday_pnl - day_fee
                ),
                "qqq_close_to_close_return_pct": qqq_return,
                "held_overnight": int(qty_before_open > 0),
                "held_after_open": int(qty_end > 0),
            })

    # 输出文件
    closed_fields = [
        "strategy", "status", "buy_date", "sell_date", "qty",
        "buy_price", "sell_price", "allocated_buy_fee",
        "allocated_sell_fee", "buy_cost_including_fee",
        "net_pnl", "return_pct", "trading_days_held",
        "calendar_days_held",
    ]

    daily_fields = [
        "strategy", "date", "qty_before_open", "qty_after_open",
        "open_price", "close_price", "overnight_price_pnl",
        "intraday_price_pnl", "total_price_pnl", "fees_paid",
        "price_pnl_after_fees", "qqq_close_to_close_return_pct",
        "held_overnight", "held_after_open",
    ]

    write_csv(CLOSED_FILE, closed_fields, closed_output)
    write_csv(DAILY_OUTPUT_FILE, daily_fields, daily_output)

    print("\n【已平仓交易统计】")
    print(
        f"{'策略':<22}{'笔数':>7}{'胜率%':>10}"
        f"{'平均盈利':>12}{'平均亏损':>12}{'盈亏因子':>11}"
    )

    for strategy in strategies:
        s = summaries[strategy]
        print(
            f"{strategy:<22}{s['closed_count']:>7}"
            f"{s['win_rate']:>10.2f}{s['avg_win']:>12.2f}"
            f"{s['avg_loss']:>12.2f}{str(s['profit_factor']):>11}"
        )

    print("\n【账户收益与手续费】")
    print(
        f"{'策略':<22}{'期末资产':>12}{'净收益':>12}"
        f"{'总手续费':>12}{'手续费/净收益%':>17}"
    )

    for strategy in strategies:
        s = summaries[strategy]
        ratio = s["fee_ratio"]
        ratio_text = f"{ratio:.2f}" if isinstance(
            ratio, (int, float)
        ) else "N/A"

        print(
            f"{strategy:<22}{s['final_equity']:>12.2f}"
            f"{s['net_profit']:>12.2f}{s['fees']:>12.2f}"
            f"{ratio_text:>17}"
        )

    print("\n【逐策略期末持仓】")
    for strategy in strategies:
        s = summaries[strategy]
        print(f"\n{strategy}")
        print(f"  未平仓股数：{s['open_qty']}")
        print(f"  持仓成本（含买入手续费）：{s['open_cost']:.2f}")
        print(f"  期末市值：{s['open_market_value']:.2f}")
        print(f"  未实现盈亏：{s['open_unrealized']:.2f}")
        print(f"  已平仓交易净盈亏：{s['closed_pnl']:.2f}")
        print(f"  最佳已平仓交易：{s['best']:.2f}")
        print(f"  最差已平仓交易：{s['worst']:.2f}")

    print("\n【每日价格盈亏归因】")
    print("说明：此处仅显示隔夜与日内价格盈亏，不打印持仓成本。")

    for strategy in strategies:
        rows = [
            r for r in daily_output
            if r["strategy"] == strategy
        ]

        overnight = sum(float(r["overnight_price_pnl"]) for r in rows)
        intraday = sum(float(r["intraday_price_pnl"]) for r in rows)
        fees = sum(float(r["fees_paid"]) for r in rows)

        overnight_days = sum(int(r["held_overnight"]) for r in rows)
        after_open_days = sum(int(r["held_after_open"]) for r in rows)
        flat_days = sum(
            1 for r in rows
            if not int(r["held_overnight"])
            and not int(r["held_after_open"])
        )

        print(f"\n{strategy}")
        print(f"  隔夜价格盈亏：{overnight:.2f}")
        print(f"  日内价格盈亏：{intraday:.2f}")
        print(f"  价格盈亏合计：{overnight + intraday:.2f}")
        print(f"  当期手续费：{fees:.2f}")
        print(f"  开盘前有持仓的天数：{overnight_days}")
        print(f"  开盘后有持仓的天数：{after_open_days}")
        print(f"  全天空仓天数：{flat_days}")

    print("\n【生成文件】")
    print(CLOSED_FILE.name)
    print(DAILY_OUTPUT_FILE.name)
    print("\n分析完成。历史回测结果不代表未来表现。")


if __name__ == "__main__":
    main()