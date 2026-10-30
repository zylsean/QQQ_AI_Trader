
import sys
import os
import traceback
import importlib.util
from pathlib import Path

print("=" * 45)
print("Pyto 模块导入诊断")
print("=" * 45)

print("\n[1] Python 版本")
print(sys.version)

print("\n[2] 当前工作目录")
print(os.getcwd())

print("\n[3] 当前诊断文件位置")
print(Path(__file__).resolve())

print("\n[4] Python 模块搜索路径 sys.path")
for i, path in enumerate(sys.path):
    print(f"{i}: {path}")

print("\n[5] 诊断文件所在目录中的相关文件")
folder = Path(__file__).resolve().parent
for name in [
    "strategy.py",
    "strategy_test.py",
    "run_all_tests.py",
    "risk_manager.py",
    "backtester.py",
    "__init__.py",
]:
    path = folder / name
    print(f"{name}: {'存在' if path.is_file() else '不存在'}")

print("\n[6] Python 能否找到strategy 模块")
try:
    spec = importlib.util.find_spec("strategy")
    print("find_spec('strategy') =", spec)
    if spec is not None:
        print("模块文件位置 =", spec.origin)
except Exception:
    traceback.print_exc()

print("\n[7] 尝试导入 strategy")
try:
    import strategy
    print("导入成功")
    print("实际加载位置 =", getattr(strategy, "__file__", "未知"))
except Exception:
    print("导入失败，完整错误如下：")
    traceback.print_exc()

print("\n" + "=" * 45)
print("诊断结束，请保留全部输出")
print("=" * 45)



