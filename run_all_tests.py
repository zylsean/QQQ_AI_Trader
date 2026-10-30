
import unittest
import io
from contextlib import redirect_stdout

import strategy_test
import paper_broker_test
import risk_manager_test
import backtester_test
import backtester_risk_test
import performance_test
import adaptive_accounting_test
import adaptive_execution_test
import adaptive_strategy_test

def run_all_tests():
    modules = [
        ("策略模块", strategy_test),
        ("模拟交易模块", paper_broker_test),
        ("风控模块", risk_manager_test),
        ("回测模块", backtester_test),
        ("回测风控模块", backtester_risk_test),
        ("性能指标模块", performance_test),
        ("自适应策略账本模块", adaptive_accounting_test),
        ("自适应策略执行模块", adaptive_execution_test),
        ("自适应策略研究模块", adaptive_strategy_test),
    ]

    total_tests = 0
    total_failures = 0
    total_errors = 0

    print("=" * 40)
    print("AI Quant Trader - 全部测试")
    print("=" * 40)

    for name, module in modules:
        print("\n[" + name + "]")

        suite = unittest.defaultTestLoader.loadTestsFromModule(
            module
        )

        stream = io.StringIO()

        with redirect_stdout(stream):
            runner = unittest.TextTestRunner(
                stream=stream,
                verbosity=2,
            )
            result = runner.run(suite)

        print(stream.getvalue())

        total_tests += result.testsRun
        total_failures += len(result.failures)
        total_errors += len(result.errors)

    print("=" * 40)
    print("测试总数：", total_tests)
    print("失败数量：", total_failures)
    print("错误数量：", total_errors)

    if total_failures == 0 and total_errors == 0:
        print("结果：全部通过")
    else:
        print("结果：存在失败，请检查上方错误信息")


if __name__ == "__main__":
    run_all_tests()

