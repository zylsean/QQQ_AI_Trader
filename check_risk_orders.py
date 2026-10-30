

from risk_manager import RiskManager

risk = RiskManager()
risk.set_trading_day("2026-10-21")
risk.update_equity(10000)

print("===== 测试一：正常买单 =====")
result = risk.check_open(
    symbol="QQQ",
    order_value=2000,
    equity=10000,
    positions_value={}
)
print(result)

assert result["allowed"] is True, "正常买单应当通过"
print("测试一：通过")

print("\n===== 测试二：触发暂停后买单 =====")
risk.update_equity(9000)

result = risk.check_open(
    symbol="QQQ",
    order_value=2000,
    equity=9000,
    positions_value={}
)
print(result)

assert result["allowed"] is False, "暂停状态下不应允许新增买单"
assert any("暂停" in reason for reason in result["reasons"]), \
    "拒绝原因应包含暂停信息"
print("测试二：通过")

print("\n===== 全部测试通过 =====")
