

from pathlib import Path
from csv_data import load_price_csv
from backtester import run_backtest

folder = Path(__file__).parent
data = load_price_csv(str(folder / "QQQ_history.csv"))

result = run_backtest(
    dates=data["dates"],
    open_prices=data["open_prices"],
    close_prices=data["close_prices"],
    symbol="QQQ",
    initial_cash=10000.0,
    short_window=5,
    long_window=10,
    fee_rate=0.001,
)

curve = result["equity_curve"]
trades = result["trades"]

# 检查净值曲线的数据结构
print("===== 净值记录结构 =====")
if curve:
    print(curve[0])
else:
    print("净值曲线为空")

print("\n===== 交易记录结构 =====")
if trades:
    print(trades[0])
else:
    print("交易记录为空")

print("\n===== 基础统计 =====")
print("交易日数量：", len(curve))
print("交易记录数量：", len(trades))
print("期末持仓：", result["positions"])
print("期末现金：", round(result["cash"], 2))
print("期末资产：", round(result["final_equity"], 2))

print("\n===== 市场参与率诊断 =====")

# 按交易日顺序处理买卖记录
trades_by_date = {}

for trade in trades:
    # 订单编号格式示例：BUY-QQQ-2016-11-11
    order_id = trade["order_id"]
    trade_date = order_id.split("QQQ-", 1)[1]

    trades_by_date.setdefault(trade_date, []).append(trade)

position_qty = 0
held_days = 0
flat_days = 0
daily_position_values = []
daily_cash_values = []

cash = 10000.0
fee_rate = 0.001

for day in curve:
    date = day["date"]
    price = None

    # 找到当日收盘价
    idx = data["dates"].index(date)
    price = data["close_prices"][idx]

    # 按当日成交记录重建现金和持仓
    for trade in trades_by_date.get(date, []):
        qty = trade["qty"]
        trade_price = trade["price"]
        fee = trade["fee"]

        if trade["side"] == "BUY":
            cash -= qty * trade_price + fee
            position_qty += qty
        elif trade["side"] == "SELL":
            cash += qty * trade_price - fee
            position_qty -= qty

    position_value = position_qty * price

    if position_qty > 0:
        held_days += 1
    else:
        flat_days += 1

    daily_position_values.append(position_value)
    daily_cash_values.append(cash)

total_days = len(curve)

print("总交易日：", total_days)
print("持仓交易日：", held_days)
print("空仓交易日：", flat_days)
print(
    "市场参与率：",
    round(held_days / total_days * 100, 2),
    "%"
)
print(
    "平均持仓市值：",
    round(sum(daily_position_values) / total_days, 2)
)
print(
    "平均现金余额：",
    round(sum(daily_cash_values) / total_days, 2)
)
print("重建期末持仓数量：", position_qty)
print("重建期末现金：", round(cash, 2))

print("\n===== 仓位与交易诊断 =====")

buy_trades = [
    t for t in trades
    if t["side"] == "BUY"
]

sell_trades = [
    t for t in trades
    if t["side"] == "SELL"
]

print("买入次数：", len(buy_trades))
print("卖出次数：", len(sell_trades))

if buy_trades:
    buy_values = [
        t["qty"] * t["price"]
        for t in buy_trades
    ]

    print("平均单笔买入金额：", round(
        sum(buy_values) / len(buy_values), 2
    ))
    print("最小单笔买入金额：", round(
        min(buy_values), 2
    ))
    print("最大单笔买入金额：", round(
        max(buy_values), 2
    ))

print("买入前 5 笔交易：")

for trade in buy_trades[:5]:
    print(
        trade["order_id"],
        "数量 =", trade["qty"],
        "价格 =", trade["price"],
        "手续费 =", trade["fee"]
    )

print("\n===== 十年净值曲线抽样 =====")

curve = result["equity_curve"]

if curve:
    print("起始净值：", curve[0])
    print("最终净值：", curve[-1])

    print("\n每年最后一个交易日的净值：")
    yearly = {}

    for row in curve:
        year = row["date"][:4]
        yearly[year] = row

    for year, row in yearly.items():
        print(
            year,
            "日期 =", row["date"],
            "净值 =", row["equity"],
            "回撤 =", row["drawdown"]
        )

    print("\n净值最低的 5 个交易日：")
    lowest = sorted(
        curve,
        key=lambda row: row["equity"]
    )[:5]

    for row in lowest:
        print(row)

print("\n===== 年度收益与回撤核查 =====")

curve = result["equity_curve"]

yearly = {}

for row in curve:
    year = row["date"][:4]
    if year not in yearly:
        yearly[year] = {
            "first": row,
            "last": row,
            "peak": row["equity"],
            "max_drawdown": 0.0,
        }

    item = yearly[year]
    item["last"] = row
    item["peak"] = max(item["peak"], row["equity"])

    drawdown = (
        item["peak"] - row["equity"]
    ) / item["peak"]

    item["max_drawdown"] = max(
        item["max_drawdown"], drawdown
    )

for year, item in yearly.items():
    start_equity = item["first"]["equity"]
    end_equity = item["last"]["equity"]

    annual_return = (
        end_equity / start_equity - 1
    ) * 100

    print(
        year,
        "年初净值 =", round(start_equity, 2),
        "年末净值 =", round(end_equity, 2),
        "年度收益 =", round(annual_return, 2), "%",
        "年内最大回撤 =", round(
            item["max_drawdown"] * 100, 2
        ), "%"
    )

print("\n回测返回的最大回撤：", result["max_drawdown"], "%")

curve_max_drawdown = max(
    row["drawdown"] for row in curve
)

print(
    "净值曲线最大回撤：",
    round(curve_max_drawdown * 100, 2),
    "%"
)

print("\n===== 买卖配对检查 =====")

trades = result["trades"]
position_qty = 0
buy_count = 0
sell_count = 0
issues = []

for trade in trades:
    if trade["side"] == "BUY":
        if position_qty != 0:
            issues.append(
                "买入时已有持仓：" + trade["order_id"]
            )
        position_qty += trade["qty"]
        buy_count += 1

    elif trade["side"] == "SELL":
        if trade["qty"] > position_qty:
            issues.append(
                "卖出数量超过持仓：" + trade["order_id"]
            )
        position_qty -= trade["qty"]
        sell_count += 1

print("买入记录数：", buy_count)
print("卖出记录数：", sell_count)
print("按成交记录重建的期末持仓：", position_qty)
print("回测返回的期末持仓：", result["positions"])
print("异常数量：", len(issues))

for issue in issues[:10]:
    print(issue)

print("\n===== 交易时间顺序检查 =====")

dates = [trade["order_id"].split("QQQ-", 1)[1]
         for trade in trades]

print("交易日期是否按时间排序：", dates == sorted(dates))
print("第一笔交易：", trades[0] if trades else None)
print("最后一笔交易：", trades[-1] if trades else None)

