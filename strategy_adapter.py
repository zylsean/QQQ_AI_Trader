
"""研究策略适配器：将外部策略转换为 backtester 可用的目标仓位信号。"""


def generate_trend_50_200_targets(close_prices):
    """
    生成 50/200 趋势策略目标仓位。

    返回列表中：
        1 = 持仓
        0 = 空仓
        None = 尚无足够数据，或目标状态不变

    每个目标仅使用当日及此前的收盘价。
    实际交易由 backtester 在下一交易日开盘执行。
    """
    if not isinstance(close_prices, (list, tuple)):
        raise ValueError("收盘价必须是列表或元组")

    for price in close_prices:
        if (
            isinstance(price, bool)
            or not isinstance(price, (int, float))
            or price <= 0
        ):
            raise ValueError("收盘价必须为正数")

    targets = []
    current_target = 0

    for i in range(len(close_prices)):
        if i + 1 < 200:
            targets.append(None)
            continue

        short_ma = sum(close_prices[i - 49:i + 1]) / 50
        long_ma = sum(close_prices[i - 199:i + 1]) / 200

        new_target = 1 if short_ma > long_ma else 0

        if new_target != current_target:
            targets.append(new_target)
            current_target = new_target
        else:
            targets.append(None)

    return targets

