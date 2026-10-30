


import unittest

from strategy import moving_average, generate_signal


class TestStrategy(unittest.TestCase):

    def test_moving_average(self):
        self.assertAlmostEqual(
            moving_average([10, 20, 30], 2),
            25.0,
        )

    def test_insufficient_data(self):
        self.assertIsNone(
            moving_average([10, 20], 3)
        )

    def test_invalid_window(self):
        with self.assertRaises(ValueError):
            moving_average([10, 20, 30], 0)

    def test_candidate_long_signal(self):
        prices = list(range(1, 61))
        result = generate_signal(
            prices,
            short_window=5,
            long_window=10,
        )
        self.assertEqual(
            result["signal"],
            "CANDIDATE_LONG",
        )

    def test_candidate_exit_signal(self):
        prices = list(range(60, 0, -1))
        result = generate_signal(
            prices,
            short_window=5,
            long_window=10,
        )
        self.assertEqual(
            result["signal"],
            "CANDIDATE_EXIT",
        )

    def test_insufficient_signal_data(self):
        result = generate_signal(
            [100, 101, 102],
            short_window=5,
            long_window=10,
        )
        self.assertEqual(
            result["signal"],
            "NO_SIGNAL",
        )


if __name__ == "__main__":
    suite = unittest.TestLoader().loadTestsFromTestCase(
        TestStrategy
    )
    result = unittest.TestResult()
    suite.run(result)

    print("策略测试总数：", result.testsRun)
    print("失败数量：", len(result.failures))
    print("错误数量：", len(result.errors))

    for test, message in result.failures + result.errors:
        lines = message.strip().splitlines()
        print("失败项目：", test)
        print("原因：", lines[-1] if lines else "未知错误")

    print(
        "最终结果：",
        "全部通过" if result.wasSuccessful() else "存在失败",
    )
