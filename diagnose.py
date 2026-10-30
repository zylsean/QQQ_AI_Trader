
import os
import re
import hashlib

files_to_check = [
    "run_all_tests.py",
    "risk_manager.py",
    "backtester.py",
    "risk_edge_test.py",
    "signal_backtest_test.py",
    "strategy_adapter_test.py",
]

for name in files_to_check:
    if not os.path.isfile(name):
        print("\n缺少文件:", name)
        continue

    with open(name, "rb") as f:
        digest = hashlib.sha256(f.read()).hexdigest()

    print("\n" + "=" * 40)
    print("文件:", name)
    print("SHA256:", digest)

    if name.endswith("_test.py"):
        with open(name, encoding="utf-8") as f:
            source = f.read()

        print("测试方法:")
        for method in re.findall(
            r"^\s+def (test_\w+)\(",
            source,
            re.M
        ):
            print(" ", method)

print("\n检查完成：没有修改项目文件。")
