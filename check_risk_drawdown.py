

from risk_manager import RiskManager

risk = RiskManager()

print("===== 风险管理回撤测试 =====")

# 初始资产 10000
print("\n测试 1：初始资产 10000")
print(risk.update_equity(10000))

# 下跌 5%
print("\n测试 2：资产降至 9500（回撤 5%）")
print(risk.update_equity(9500))

# 下跌 10%
print("\n测试 3：资产降至 9000（回撤 10%）")
print(risk.update_equity(9000))

# 下跌 15%
print("\n测试 4：资产降至 8500（相对峰值回撤 15%）")
print(risk.update_equity(8500))

print("\n测试 5：最终风险状态")
print(risk.get_status())
