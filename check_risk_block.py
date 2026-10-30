

from risk_manager import RiskManager
import risk_manager

print("实际加载的 risk_manager 文件：")
print(risk_manager.__file__)
risk = RiskManager()

# 先设置交易日期
risk.set_trading_day("2026-10-21")

# 建立账户峰值
risk.update_equity(10000)

# 模拟账户回撤达到 10%
status = risk.update_equity(9000)
print("触发暂停后的状态：", status)

# 检查暂停后是否允许新增买入
decision = risk.check_open(
    symbol="QQQ",
    order_value=1000,
    equity=9000,
    positions_value={}
)

print("\n===== 暂停后买入检查 =====")
print("是否允许新增买入：", decision)

print("\n===== 最终风险状态 =====")
print(risk.get_status())
