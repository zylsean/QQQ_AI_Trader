

"""
AI Quant Trader
第一阶段：均线策略核心
仅用于研究和模拟，不执行真实交易。
"""

SHORT_WINDOW = 20
LONG_WINDOW = 50


def moving_average(prices, window):
    """计算最近 window 个收盘价的简单移动平均。"""
    if window <= 0:
        raise ValueError("均线周期必须大于 0")

    if len(prices) < window:
        return None

    values = prices[-window:]

    if any(
        not isinstance(p, (int, float))
        or isinstance(p, bool)
        or p <= 0
        for p in values
    ):
        raise ValueError("价格必须是有效的正数")

    return sum(values) / window


def generate_signal(
    prices,
    short_window=SHORT_WINDOW,
    long_window=LONG_WINDOW,
):
    """
    根据截至当前收盘的历史价格生成候选信号。

    注意：
    1. 数据不足时返回 NO_SIGNAL。
    2. 本函数不执行交易。
    3. 回测应在下一交易日成交，不能按当前收盘价成交。
    """
    if short_window <= 0 or long_window <= 0:
        raise ValueError("均线周期必须大于 0")

    if short_window >= long_window:
        raise ValueError("短期均线周期必须小于长期均线周期")

    # 检查全部输入，避免隐藏无效数据
    if any(
        not isinstance(p, (int, float))
        or isinstance(p, bool)
        or p <= 0
        for p in prices
    ):
        raise ValueError("价格必须是有效的正数")

    short_ma = moving_average(prices, short_window)
    long_ma = moving_average(prices, long_window)

    if short_ma is None or long_ma is None:
        return {
            "signal": "NO_SIGNAL",
            "short_ma": short_ma,
            "long_ma": long_ma,
            "reason": "数据不足",
        }

    if short_ma > long_ma:
        signal = "CANDIDATE_LONG"
    elif short_ma < long_ma:
        signal = "CANDIDATE_EXIT"
    else:
        signal = "NO_SIGNAL"

    return {
        "signal": signal,
        "short_ma": short_ma,
        "long_ma": long_ma,
        "reason": "均线比较完成",
    }


def run_tests():
    """使用 Python 自带的 assert 进行基础单元测试。"""

    # 测试 1：均线计算
    assert moving_average([10, 20, 30], 2) == 25

    # 测试 2：数据不足，不得产生信号
    result = generate_signal([100] * 49)
    assert result["signal"] == "NO_SIGNAL"
    assert result["reason"] == "数据不足"

    # 测试 3：持续上涨，短期均线高于长期均线
    rising = list(range(100, 160))
    result = generate_signal(rising)
    assert result["signal"] == "CANDIDATE_LONG"

    # 测试 4：持续下跌，短期均线低于长期均线
    falling = list(range(160, 100, -1))
    result = generate_signal(falling)
    assert result["signal"] == "CANDIDATE_EXIT"

    # 测试 5：非法价格应当报错
    try:
        generate_signal([100, -1, 102])
    except ValueError:
        pass
    else:
        raise AssertionError("非法价格未被拒绝")

    # 测试 6：非法均线参数应当报错
    try:
        generate_signal([100] * 60, 50, 20)
    except ValueError:
        pass
    else:
        raise AssertionError("非法均线周期未被拒绝")

    print("测试 1：均线计算 PASS")
    print("测试 2：数据不足 PASS")
    print("测试 3：上涨趋势 PASS")
    print("测试 4：下跌趋势 PASS")
    print("测试 5：非法价格 PASS")
    print("测试 6：非法周期 PASS")
    print("全部 6 项测试通过。")


if __name__ == "__main__":
    run_tests()
