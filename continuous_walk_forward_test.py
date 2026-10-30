
from pathlib import Path
from math import sqrt, isclose

from adaptive_strategy_research import (
    load_data,
    calculate_signals,
    backtest,
    rolling_select,
    START_INDEX,
    FEE_RATE,
    INITIAL_CASH,
)


TRADING_DAYS_PER_YEAR = 252
TRAIN_FRACTION = 0.60
RESELECT_EVERY = 252
AUDIT_TOLERANCE = 1e-7

CANDIDATE_NAMES = [
    "63D Momentum",
    "50/200 Trend",
    "20D Mean Reversion",
]

COMPARE_NAMES = [
    "Buy and Hold",
    "50/200 Trend",
    "Adaptive Rules",
    "Rolling Selection",
    "Annual Frozen Selection",
]


def sharpe_score(daily_returns, global_start, global_end):
    """
    按原始价格数组的全局索引选择收益区间。

    backtest 返回的 daily_returns 从 START_INDEX + 1
    对应的交易日开始，并不是从原始数据第 0 行开始。
    因此这里必须转换索引，避免年度选择误用未来收益。
    """
    first_global_index = START_INDEX + 1

    start = max(global_start, first_global_index)
    end = min(global_end, first_global_index + len(daily_returns) - 1)

    if end < start:
        return None

    values = [
        daily_returns[i - first_global_index]
        for i in range(start, end + 1)
        if daily_returns[i - first_global_index] is not None
    ]

    if len(values) < 2:
        return None

    mean_return = sum(values) / len(values)

    variance = sum(
        (value - mean_return) ** 2
        for value in values
    ) / (len(values) - 1)

    daily_volatility = sqrt(variance)

    if daily_volatility <= 0:
        return None

    return (
        mean_return
        / daily_volatility
        * sqrt(TRADING_DAYS_PER_YEAR)
    )


def choose_strategy(historical_results, train_start, train_end):
    """只使用指定历史区间内已经实现的收益选择策略。"""
    best_name = None
    best_score = None

    for name in CANDIDATE_NAMES:
        score = sharpe_score(
            historical_results[name]["daily_returns"],
            train_start,
            train_end,
        )

        if score is None:
            continue

        if best_score is None or score > best_score:
            best_name = name
            best_score = score

    if best_name is None:
        raise ValueError(
            f"没有可用的历史策略评分，区间索引："
            f"{train_start} 至 {train_end}"
        )

    return best_name, best_score


def build_annual_frozen_signals(
    prices,
    signals,
    historical_results,
    test_start,
):
    """
    每隔 RESELECT_EVERY 个交易日重新选择策略。

    决策时仅使用决策日之前已经完成的历史收益。
    被选中的 signals[i] 仍然按照次日执行规则交易。
    """
    n = len(prices)
    output = [0] * n
    decisions = []

    decision_index = test_start

    while decision_index < n - 1:
        chosen_name, chosen_score = choose_strategy(
            historical_results,
            START_INDEX + 1,
            decision_index - 1,
        )

        next_decision = min(
            decision_index + RESELECT_EVERY,
            n,
        )

        for i in range(decision_index, next_decision):
            output[i] = signals[chosen_name][i]

        decisions.append({
            "index": decision_index,
            "name": chosen_name,
            "score": chosen_score,
            "train_end_index": decision_index - 1,
        })

        decision_index = next_decision

    return output, decisions


def run_continuous_backtest(
    dates,
    prices,
    signals,
    start_index,
    strategy_name="Unknown",
):
    """
    连续账户模拟：
    - 测试起点持有现金、没有持仓
    - 前一日收盘信号在当日收盘执行
    - 买卖手续费均计入现金账本
    - 年度边界不重置资金或持仓
    - 记录信号日期、成交日期及成交前后状态
    """
    cash = float(INITIAL_CASH)
    shares = 0.0

    equity_curve = [INITIAL_CASH]
    daily_returns = []
    trades = []
    exposure_days = 0
    total_fees = 0.0

    previous_equity = INITIAL_CASH

    for i in range(start_index + 1, len(prices)):
        price = float(prices[i])
        target = signals[i - 1]
        signal_date = dates[i - 1]
        execution_date = dates[i]

        if target not in (0, 1):
            raise ValueError(
                f"{strategy_name} 在 {signal_date} "
                f"产生非法信号：{target}"
            )

        cash_before = cash
        shares_before = shares
        fee = 0.0
        qty = 0.0
        side = None

        # 买入：用全部可用现金买入，费用包含在买入预算内。
        if target == 1 and shares <= 0:
            if cash > 0:
                qty = cash / (price * (1 + FEE_RATE))
                fee = qty * price * FEE_RATE

                cash -= qty * price + fee

                # 清除浮点运算产生的极小残差。
                if abs(cash) < AUDIT_TOLERANCE:
                    cash = 0.0

                shares = qty
                total_fees += fee
                side = "BUY"

        # 卖出：全部平仓。
        elif target == 0 and shares > 0:
            qty = shares
            fee = qty * price * FEE_RATE

            cash += qty * price - fee
            shares = 0.0

            if abs(cash) < AUDIT_TOLERANCE:
                cash = 0.0

            total_fees += fee
            side = "SELL"

        equity = cash + shares * price

        if side is not None:
            trades.append({
                "strategy": strategy_name,
                "signal_date": signal_date,
                "execution_date": execution_date,
                "target": target,
                "side": side,
                "price": price,
                "qty": qty,
                "fee": fee,
                "cash_before": cash_before,
                "cash_after": cash,
                "shares_before": shares_before,
                "shares_after": shares,
                "equity_after": equity,
            })

        equity_curve.append(equity)

        if previous_equity > 0:
            daily_returns.append(
                equity / previous_equity - 1
            )
        else:
            daily_returns.append(0.0)

        previous_equity = equity

        if shares > 0:
            exposure_days += 1

    final_equity = equity_curve[-1]
    total_return = final_equity / INITIAL_CASH - 1
    periods = len(daily_returns)

    if periods > 0 and final_equity > 0:
        annualized_return = (
            (final_equity / INITIAL_CASH)
            ** (TRADING_DAYS_PER_YEAR / periods)
            - 1
        )
    else:
        annualized_return = 0.0

    if len(daily_returns) >= 2:
        mean_return = sum(daily_returns) / len(daily_returns)

        variance = sum(
            (value - mean_return) ** 2
            for value in daily_returns
        ) / (len(daily_returns) - 1)

        daily_volatility = sqrt(variance)

        volatility = (
            daily_volatility
            * sqrt(TRADING_DAYS_PER_YEAR)
        )

        if daily_volatility > 0:
            sharpe = (
                mean_return
                / daily_volatility
                * sqrt(TRADING_DAYS_PER_YEAR)
            )
        else:
            sharpe = 0.0
    else:
        volatility = 0.0
        sharpe = 0.0

    peak = equity_curve[0]
    max_drawdown = 0.0

    for equity in equity_curve:
        peak = max(peak, equity)

        if peak > 0:
            drawdown = equity / peak - 1
            max_drawdown = min(max_drawdown, drawdown)

    exposure = (
        exposure_days / periods
        if periods > 0
        else 0.0
    )

    return {
        "final_equity": final_equity,
        "total_return": total_return,
        "annualized_return": annualized_return,
        "volatility": volatility,
        "sharpe": sharpe,
        "max_drawdown": abs(max_drawdown),
        "trades": len(trades),
        "exposure": exposure,
        "total_fees": total_fees,
        "cash": cash,
        "shares": shares,
        "equity_curve": equity_curve,
        "daily_returns": daily_returns,
        "trades_detail": trades,
    }


def audit_account(name, result, dates, prices, start_index):
    """检查交易账本、现金、持仓和权益曲线。"""
    errors = []
    trades = result["trades_detail"]

    fee_sum = sum(trade["fee"] for trade in trades)

    if not isclose(
        fee_sum,
        result["total_fees"],
        rel_tol=1e-9,
        abs_tol=AUDIT_TOLERANCE,
    ):
        errors.append("逐笔手续费之和与总手续费不一致")

    expected_curve_length = len(prices) - start_index

    if len(result["equity_curve"]) != expected_curve_length:
        errors.append(
            f"权益曲线长度异常：实际 {len(result['equity_curve'])}，"
            f"预期 {expected_curve_length}"
        )

    if len(result["daily_returns"]) != len(result["equity_curve"]) - 1:
        errors.append("日收益序列长度与权益曲线不匹配")

    if not isclose(
        result["equity_curve"][0],
        INITIAL_CASH,
        rel_tol=0,
        abs_tol=AUDIT_TOLERANCE,
    ):
        errors.append("初始权益不是初始资金")

    # 从交易记录重建现金与持股数量。
    ledger_cash = float(INITIAL_CASH)
    ledger_shares = 0.0

    for trade in trades:
        if trade["execution_date"] <= trade["signal_date"]:
            errors.append(
                f"成交日期没有晚于信号日期：{trade}"
            )

        if trade["side"] == "BUY":
            ledger_cash -= (
                trade["qty"] * trade["price"] + trade["fee"]
            )
            ledger_shares += trade["qty"]

        elif trade["side"] == "SELL":
            ledger_cash += (
                trade["qty"] * trade["price"] - trade["fee"]
            )
            ledger_shares -= trade["qty"]

        else:
            errors.append(f"未知交易方向：{trade['side']}")

    if abs(ledger_shares) < AUDIT_TOLERANCE:
        ledger_shares = 0.0

    if abs(ledger_cash) < AUDIT_TOLERANCE:
        ledger_cash = 0.0

    if not isclose(
        ledger_cash,
        result["cash"],
        rel_tol=1e-9,
        abs_tol=AUDIT_TOLERANCE,
    ):
        errors.append(
            f"账本现金 {ledger_cash:.8f} 与账户现金 "
            f"{result['cash']:.8f} 不一致"
        )

    if not isclose(
        ledger_shares,
        result["shares"],
        rel_tol=1e-9,
        abs_tol=AUDIT_TOLERANCE,
    ):
        errors.append(
            f"账本持股 {ledger_shares:.8f} 与账户持股 "
            f"{result['shares']:.8f} 不一致"
        )

    final_price = prices[-1]
    ledger_equity = ledger_cash + ledger_shares * final_price

    if not isclose(
        ledger_equity,
        result["final_equity"],
        rel_tol=1e-9,
        abs_tol=AUDIT_TOLERANCE,
    ):
        errors.append(
            f"账本期末权益 {ledger_equity:.8f} 与回测期末权益 "
            f"{result['final_equity']:.8f} 不一致"
        )

    for i, trade in enumerate(trades):
        # 成交日期必须属于回测区间。
        try:
            date_index = dates.index(trade["execution_date"])
        except ValueError:
            errors.append(
                f"交易日期不在行情数据中：{trade['execution_date']}"
            )
            continue

        if date_index <= start_index:
            errors.append(
                f"交易发生在测试账户起点之前："
                f"{trade['execution_date']}"
            )

        if not isclose(
            prices[date_index],
            trade["price"],
            rel_tol=1e-9,
            abs_tol=AUDIT_TOLERANCE,
        ):
            errors.append(
                f"成交价格与行情数据不一致："
                f"{trade['execution_date']}"
            )

        if i > 0:
            previous_trade = trades[i - 1]
            if trade["execution_date"] <= previous_trade["execution_date"]:
                errors.append("交易记录没有按日期严格递增")

    return {
        "name": name,
        "passed": len(errors) == 0,
        "errors": errors,
        "fee_sum": fee_sum,
        "ledger_cash": ledger_cash,
        "ledger_shares": ledger_shares,
        "ledger_equity": ledger_equity,
    }


def print_results(results):
    print(
        f"{'策略':<25}"
        f"{'期末资产':>12}"
        f"{'总收益%':>10}"
        f"{'年化%':>9}"
        f"{'波动%':>9}"
        f"{'夏普':>8}"
        f"{'回撤%':>9}"
        f"{'交易数':>8}"
        f"{'仓位%':>8}"
        f"{'手续费':>10}"
    )

    for name, result in results.items():
        print(
            f"{name:<25}"
            f"{result['final_equity']:>12.2f}"
            f"{result['total_return'] * 100:>10.2f}"
            f"{result['annualized_return'] * 100:>9.2f}"
            f"{result['volatility'] * 100:>9.2f}"
            f"{result['sharpe']:>8.3f}"
            f"{result['max_drawdown'] * 100:>9.2f}"
            f"{result['trades']:>8}"
            f"{result['exposure'] * 100:>8.1f}"
            f"{result['total_fees']:>10.2f}"
        )


def print_trade_audit(results):
    print("\n" + "=" * 120)
    print("逐笔交易审计：信号日期 / 成交日期 / 成交价格 / 数量 / 手续费")
    print("=" * 120)

    for name, result in results.items():
        print(f"\n[{name}]")

        if not result["trades_detail"]:
            print("无成交记录")
            continue

        print(
            f"{'信号日期':<13}"
            f"{'成交日期':<13}"
            f"{'方向':<7}"
            f"{'目标仓位':>8}"
            f"{'成交价':>12}"
            f"{'数量':>14}"
            f"{'手续费':>11}"
            f"{'成交后现金':>14}"
            f"{'成交后持股':>14}"
        )

        for trade in result["trades_detail"]:
            print(
                f"{trade['signal_date']:<13}"
                f"{trade['execution_date']:<13}"
                f"{trade['side']:<7}"
                f"{trade['target']:>8}"
                f"{trade['price']:>12.4f}"
                f"{trade['qty']:>14.6f}"
                f"{trade['fee']:>11.4f}"
                f"{trade['cash_after']:>14.4f}"
                f"{trade['shares_after']:>14.6f}"
            )


def main():
    data_path = Path(__file__).parent / "QQQ_yahoo_10y.csv"
    dates, prices = load_data(data_path)

    n = len(prices)
    test_start = int(n * TRAIN_FRACTION)

    if test_start <= START_INDEX + 252:
        raise ValueError("初始训练数据不足")

    if test_start >= n - 2:
        raise ValueError("样本外测试数据不足")

    print("=" * 100)
    print("连续 Walk-Forward 模拟与账本审计")
    print("=" * 100)
    print("数据区间：", dates[0], "至", dates[-1])
    print("数据条数：", n)
    print("连续模拟起点：", dates[test_start])
    print("连续模拟终点：", dates[-1])
    print("初始资金：", INITIAL_CASH)
    print("单边手续费：", FEE_RATE * 100, "%")
    print("年度重新选择间隔：", RESELECT_EVERY, "个交易日")
    print("测试账户：连续运行，不按年度重置")

    signals = calculate_signals(prices)

    historical_results = {
        name: backtest(
            prices,
            signals[name],
            start_index=START_INDEX,
        )
        for name in [
            "Buy and Hold",
            *CANDIDATE_NAMES,
            "Adaptive Rules",
        ]
    }

    rolling_signals = rolling_select(
        prices,
        signals,
        historical_results,
    )

    annual_signals, decisions = build_annual_frozen_signals(
        prices,
        signals,
        historical_results,
        test_start,
    )

    buy_hold_signals = [0] * n
    for i in range(test_start, n):
        buy_hold_signals[i] = 1

    test_signals = {
        "Buy and Hold": buy_hold_signals,
        "50/200 Trend": signals["50/200 Trend"],
        "Adaptive Rules": signals["Adaptive Rules"],
        "Rolling Selection": rolling_signals,
        "Annual Frozen Selection": annual_signals,
    }

    results = {}

    for name, signal in test_signals.items():
        results[name] = run_continuous_backtest(
            dates,
            prices,
            signal,
            test_start,
            strategy_name=name,
        )

    print("\n" + "=" * 100)
    print("年度策略选择记录")
    print("=" * 100)

    for decision in decisions:
        print(
            f"决策日 {dates[decision['index']]} | "
            f"训练数据截止 {dates[decision['train_end_index']]} | "
            f"选择：{decision['name']} | "
            f"训练期夏普：{decision['score']:.3f}"
        )

    print("\n" + "=" * 100)
    print("连续账户最终结果")
    print("=" * 100)
    print_results(results)

    benchmark = results["Buy and Hold"]

    print("\n" + "=" * 100)
    print("相对 QQQ Buy and Hold 的比较")
    print("=" * 100)

    for name, result in results.items():
        if name == "Buy and Hold":
            continue

        return_difference = (
            result["total_return"] - benchmark["total_return"]
        ) * 100

        sharpe_difference = result["sharpe"] - benchmark["sharpe"]

        drawdown_difference = (
            result["max_drawdown"] - benchmark["max_drawdown"]
        ) * 100

        tolerance = 1e-9

        if result["max_drawdown"] < (
            benchmark["max_drawdown"] - tolerance
        ):
            drawdown_status = "回撤较低"
        elif abs(
            result["max_drawdown"] - benchmark["max_drawdown"]
        ) <= tolerance:
            drawdown_status = "回撤相同"
        else:
            drawdown_status = "回撤较高"

        print(
            f"{name:<25}"
            f"收益差 {return_difference:+.2f} 个百分点 | "
            f"夏普差 {sharpe_difference:+.3f} | "
            f"回撤差 {drawdown_difference:+.2f} 个百分点 | "
            f"{drawdown_status}"
        )

    print("\n" + "=" * 100)
    print("账户状态与账本审计")
    print("=" * 100)

    audit_results = {}

    for name, result in results.items():
        audit = audit_account(
            name,
            result,
            dates,
            prices,
            test_start,
        )
        audit_results[name] = audit

        status = "通过" if audit["passed"] else "失败"

        print(
            f"{name:<25}"
            f"审计：{status} | "
            f"期末现金：{result['cash']:.6f} | "
            f"期末持股：{result['shares']:.6f} | "
            f"逐笔手续费合计：{audit['fee_sum']:.4f} | "
            f"总手续费：{result['total_fees']:.4f}"
        )

        for error in audit["errors"]:
            print("  [异常]", error)

    print_trade_audit(results)

    failed = [
        name
        for name, audit in audit_results.items()
        if not audit["passed"]
    ]

    print("\n" + "=" * 100)
    if failed:
        print("审计结论：发现异常，请先处理，不要调参。")
        print("存在异常的策略：", ", ".join(failed))
    else:
        print("账本基础审计通过：现金、持仓、手续费和期末权益一致。")
        print(
            "注意：账本审计通过不等于所有策略信号都已完成因果性验证；"
            "Rolling Selection 的内部实现仍需单独审查。"
        )

    print("\n说明：")
    print("1. 测试账户在样本外起点以相同资金和空仓开始。")
    print("2. 信号使用前一交易日收盘信息，次日收盘执行。")
    print("3. 年度选择评分已按原始数据索引映射到实际日收益。")
    print("4. 交易审计会显示所有成交的信号日期与执行日期。")
    print("5. 本程序仅用于研究模拟，不连接真实券商，也不保证未来表现。")


if __name__ == "__main__":
    main()

