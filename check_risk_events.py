
from risk_manager import RiskManager

risk = RiskManager()

risk.update_equity(10000)

# 连续多次更新净值，始终保持 5% 回撤
for equity in [9500, 9500, 9500, 9500]:
    risk.update_equity(equity)

print("===== 5% 回撤事件检查 =====")
print("当前风险状态：", risk.get_status())

events = risk.get_status()["events"]
warning_count = sum(
    event["type"] == "DRAWDOWN_WARNING"
    for event in events
)

print("预警事件数量：", warning_count)

# 再测试 10% 回撤
risk.update_equity(9000)

print("\n===== 10% 回撤事件检查 =====")
print("当前风险状态：", risk.get_status())

events = risk.get_status()["events"]
pause_count = sum(
    event["type"] == "TRADING_PAUSED"
    for event in events
)

print("暂停事件数量：", pause_count)
