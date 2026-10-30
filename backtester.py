

from math import isfinite

from strategy import generate_signal
from paper_broker import PaperBroker
from risk_manager import RiskManager

def run_backtest(
    dates,
    open_prices,
    close_prices,
    symbol="QQQ",
    initial_cash=10000.0,
    short_window=20,
    long_window=50,
    fee_rate=0.001,
    position_fraction=0.20,
    auto_resume=False,
    resume_cooldown_days=10,
    initial_history_close_prices=None,
    target_positions=None,
):
    """
    PAPER 模拟回测。

    默认模式：
        使用 generate_signal() 生成均线信号。

    外部目标仓位模式：
        1    = 目标持仓
        0    = 目标空仓
        None = 保持之前的目标状态

    信号在收盘后生成，下一交易日开盘执行。
    """

    # 1. 参数校验
    if (
        isinstance(short_window, bool)
        or isinstance(long_window, bool)
        or not isinstance(short_window, int)
        or not isinstance(long_window, int)
        or short_window <= 0
        or long_window <= short_window
    ):
        raise ValueError("均线周期设置不合法")

    if (
        isinstance(position_fraction, bool)
        or not isinstance(position_fraction, (int, float))
        or not isfinite(position_fraction)
        or not 0 < position_fraction <= 1
    ):
        raise ValueError("仓位比例必须大于 0 且不超过 1")

    if (
        isinstance(initial_cash, bool)
        or not isinstance(initial_cash, (int, float))
        or not isfinite(initial_cash)
        or initial_cash <= 0
    ):
        raise ValueError("初始资金必须是有限正数")

    if (
        isinstance(fee_rate, bool)
        or not isinstance(fee_rate, (int, float))
        or not isfinite(fee_rate)
        or fee_rate < 0
    ):
        raise ValueError("交易费率必须是有限非负数")

    if not isinstance(symbol, str) or not symbol.strip():
        raise ValueError("股票代码不能为空")

    # 2. 数据校验
    if not (len(dates) == len(open_prices) == len(close_prices)):
        raise ValueError("日期、开盘价和收盘价长度必须一致")

    if len(dates) == 0:
        raise ValueError("回测数据不能为空")

    if target_positions is None and len(dates) < long_window + 1:
        raise ValueError("数据不足，至少需要长期均线周期加一天")

    if len(set(dates)) != len(dates):
        raise ValueError("日期不能重复")

    if list(dates) != sorted(dates):
        raise ValueError("日期必须按从早到晚排列")

    for price in list(open_prices) + list(close_prices):
        if (
            isinstance(price, bool)
            or not isinstance(price, (int, float))
            or not isfinite(price)
            or price <= 0
        ):
            raise ValueError("所有价格必须是有限的正数")

    if target_positions is not None:
        if len(target_positions) != len(dates):
            raise ValueError("目标仓位信号长度必须与日期一致")

        for target in target_positions:
            if target is None:
                continue

            if (
                isinstance(target, bool)
                or not isinstance(target, (int, float))
                or not isfinite(target)
                or target not in (0, 1)
            ):
                raise ValueError("目标仓位只能是 0、1 或 None")

    initial_history = list(initial_history_close_prices or [])

    for price in initial_history:
        if (
            isinstance(price, bool)
            or not isinstance(price, (int, float))
            or not isfinite(price)
            or price <= 0
        ):
            raise ValueError("预热历史价格必须是有限的正数")

    # 3. 初始化模拟券商与风控模块
    broker = PaperBroker(
        initial_cash=initial_cash,
        fee_rate=fee_rate,
    )

    risk = RiskManager(
        auto_resume=auto_resume,
        resume_cooldown_days=resume_cooldown_days,
    )

    # 关键修复：
    # 在第一次交易之前，先把初始资金登记为风控权益基准。
    # 这样第一天发生亏损时，风控模块也能正确计算回撤。
    risk.update_equity(float(initial_cash))

    pending_signal = None
    rejected_orders = []

    # 如果有足够的历史数据，在回测开始前生成初始信号。
    if target_positions is None and len(initial_history) >= long_window:
        pending_signal = generate_signal(
            initial_history,
            short_window=short_window,
            long_window=long_window,
        )

    # 外部目标仓位模式：持久保存目标状态。
    desired_target = 0

    equity_curve = []
    trade_count = 0
    peak_equity = float(initial_cash)
    max_drawdown = 0.0

    # 4. 逐日回测
    for i, date in enumerate(dates):
        risk.set_trading_day(date)

        # 4.1 执行前一交易日收盘后生成的信号
        if pending_signal is not None:
            action = pending_signal["signal"]
            pending_signal = None

            price = open_prices[i]
            positions = broker.get_positions()
            position = positions.get(
                symbol,
                {"qty": 0, "cost": 0.0},
            )
            qty = position["qty"]

            # 平仓不受暂停开仓限制。
            if action == "CANDIDATE_EXIT" and qty > 0:
                order_id = "SELL-{}-{}".format(symbol, date)

                broker.sell(
                    order_id,
                    symbol,
                    qty,
                    price,
                )

                risk.record_trade(date)
                trade_count += 1

            # 只有空仓时才考虑开仓。
            elif action == "CANDIDATE_LONG" and qty == 0:
                if i > 0:
                    reference_price = close_prices[i - 1]
                elif initial_history:
                    reference_price = initial_history[-1]
                else:
                    reference_price = None

                if reference_price is not None:
                    equity = broker.total_equity(
                        {symbol: reference_price}
                    )

                    order_value = min(
                        equity * position_fraction,
                        broker.get_cash() / (1 + fee_rate),
                    )

                    shares = int(order_value / price)

                    # 当前实现是单标的回测。
                    # 现有持仓按该标的开盘价估值。
                    current_positions = {
                        name: item["qty"] * price
                        for name, item in broker.get_positions().items()
                        if name == symbol
                    }

                    if shares > 0:
                        decision = risk.check_open(
                            symbol=symbol,
                            order_value=shares * price,
                            equity=equity,
                            positions_value=current_positions,
                        )

                        if decision["allowed"]:
                            order_id = "BUY-{}-{}".format(
                                symbol,
                                date,
                            )

                            broker.buy(
                                order_id,
                                symbol,
                                shares,
                                price,
                            )

                            risk.record_trade(date)
                            trade_count += 1

                        else:
                            # 拒绝不改变账户，只留痕，便于审计重试行为。
                            rejected_orders.append({
                                "date": date,
                                "side": "BUY",
                                "shares": shares,
                                "order_value": round(shares * price, 2),
                                "reasons": list(decision["reasons"]),
                            })

        # 4.2 收盘估值
        equity = broker.total_equity(
            {symbol: close_prices[i]}
        )

        # 初始权益已经在回测开始前登记。
        # 后续收盘权益继续更新风控状态。
        risk.update_equity(
            equity,
            has_exposure=symbol in broker.get_positions(),
        )

        peak_equity = max(peak_equity, equity)

        drawdown = (
            (peak_equity - equity) / peak_equity
            if peak_equity > 0
            else 0.0
        )

        max_drawdown = max(max_drawdown, drawdown)

        equity_curve.append({
            "date": date,
            "equity": round(equity, 2),
            "drawdown": round(drawdown, 4),
        })

        # 4.3 收盘后生成下一交易日的信号
        if target_positions is not None:
            target = target_positions[i]

            if target is not None:
                desired_target = int(target)

            current_qty = broker.get_positions().get(
                symbol,
                {"qty": 0},
            )["qty"]

            if desired_target == 1 and current_qty == 0:
                # 若风控拒绝开仓，后续交易日仍可重新尝试。
                pending_signal = {
                    "signal": "CANDIDATE_LONG"
                }

            elif desired_target == 0 and current_qty > 0:
                pending_signal = {
                    "signal": "CANDIDATE_EXIT"
                }

            else:
                pending_signal = None

        else:
            history = initial_history + list(
                close_prices[:i + 1]
            )

            if len(history) >= long_window:
                pending_signal = generate_signal(
                    history,
                    short_window=short_window,
                    long_window=long_window,
                )
            else:
                pending_signal = None

    # 5. 期末账户核算
    final_equity = equity_curve[-1]["equity"]

    checked_equity = broker.total_equity({
        symbol: close_prices[-1]
    })

    if abs(final_equity - checked_equity) > 0.01:
        raise RuntimeError("期末资产与经纪账户核算不一致")

    return {
        "symbol": symbol,
        "initial_cash": round(initial_cash, 2),
        "final_equity": final_equity,
        "total_return": round(
            (final_equity / initial_cash - 1) * 100,
            2,
        ),
        "max_drawdown": round(max_drawdown * 100, 2),
        "trade_count": trade_count,
        "cash": round(broker.get_cash(), 2),
        "positions": broker.get_positions(),
        "trades": broker.get_trades(),
        "equity_curve": equity_curve,
        "risk_status": risk.get_status(),
        "rejected_orders": rejected_orders,
    }