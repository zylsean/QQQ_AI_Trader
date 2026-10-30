

import inspect
import risk_manager
from risk_manager import RiskManager

print("===== 1. 实际加载的文件 =====")
print(risk_manager.__file__)

print("\n===== 2. 实际执行的 check_open 代码 =====")
print(inspect.getsource(RiskManager.check_open))

print("\n===== 3. 重新测试暂停原因 =====")
risk = RiskManager()
risk.set_trading_day("2026-10-21")
risk.update_equity(10000)
status = risk.update_equity(9000)

print("暂停状态：", status)
print("paused：", repr(risk.paused))
print("pause_reason：", repr(risk.pause_reason))

decision = risk.check_open(
    symbol="QQQ",
    order_value=1000,
    equity=9000,
    positions_value={}
)

print("开仓检查结果：", repr(decision))
