
from pathlib import Path

from csv_data import load_price_csv
from backtester import run_backtest
from strategy_adapter import generate_trend_50_200_targets


DATA_FILE = "QQQ_yahoo_10y.csv"
OOS_START_DATE = "2023-10-18"

INITIAL_CASH = 10000.0
FEE_RATE = 0.001
POSITION_FRACTION = 0.20


def main():
    folder = Path(__file__).parent
    data = load_price_csv(str(folder / DATA_FILE))

    dates = data["dates"]
    opens = data["open_prices"]
    closes = data["close_prices"]

    raw_targets = generate_trend_50_200_targets(closes)

    # 还原持续目标状态：None 代表延续上一个状态。
    state = 0
    states = []

    for target in raw_targets:
        if target is not None:
            state = int(target)
        states.append(state)

    oos_start = next(
        (
            i for i, date in enumerate(dates)
            if str(date) >= OOS_START_DATE
        ),
        None,
    )

    if oos_start is None:
        raise ValueError("找不到样本外起始日期")

    print("=" * 70)
    print("50/200 趋势目标仓位诊断")
    print("=" * 70)
    print(f"数据区间：{dates[0]} 至 {dates[-1]}")
    print(f"样本外起点：索引 {oos_start}，日期 {dates[oos_start]}")
    print()

    print("一、样本外起点附近的目标状态")
    start = max(0, oos_start - 5)
    end = min(len(dates), oos_start + 10)

    for i in range(start, end):
        print(
            f"{dates[i]} | "
            f"收盘价={closes[i]:.2f} | "
            f"原始目标={raw_targets[i]} | "
            f"持续目标={states[i]}"
        )

    print()
    print("二、样本外区间内的状态变化")

    previous = states[oos_start - 1] if oos_start > 0 else 0
    changes = []

    for i in range(oos_start, len(dates)):
        if states[i] != previous:
            changes.append((dates[i], previous, states[i]))
        previous = states[i]

    if changes:
        for date, old, new in changes:
            print(f"{date} | {old} -> {new}")
    else:
        print("样本外区间内没有目标状态变化")

    print()
    print(f"样本外目标为 1 的天数：{sum(states[oos_start:])}")
    print(f"样本外目标为 0 的天数：{len(states[oos_start:]) - sum(states[oos_start:])}")

    print()
    print("三、使用统一回测器运行样本外区间")

    result = run_backtest(
        dates=dates[oos_start:],
        open_prices=opens[oos_start:],
        close_prices=closes[oos_start:],
        symbol="QQQ",
        initial_cash=INITIAL_CASH,
        fee_rate=FEE_RATE,
        position_fraction=POSITION_FRACTION,
        target_positions=states[oos_start:],
    )

    print(f"期末资产：{result['final_equity']:.2f}")
    print(f"累计收益：{result['total_return'] * 100:.2f}%")
    print(f"交易次数：{result['trade_count']}")
    print(f"期末现金：{result['cash']:.2f}")
    print(f"期末持仓：{result['positions']}")

    print()
    print("四、实际成交明细")

    trades = result.get("trades", [])

    if not trades:
        print("没有成交记录")
    else:
        for trade in trades:
            print(
                f"订单={trade.get('order_id')} | "
                f"方向={trade.get('side')} | "
                f"数量={trade.get('qty')} | "
                f"价格={trade.get('price')} | "
                f"手续费={trade.get('fee')} | "
                f"已实现盈亏={trade.get('realized_pnl')}"
            )

    print()
    print("诊断结束。此脚本不修改其他项目文件。")


if __name__ == "__main__":
    main()

