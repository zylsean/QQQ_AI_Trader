

from pathlib import Path
from csv_data import load_price_csv

file_path = Path(__file__).parent / "QQQ_history.csv"

data = load_price_csv(str(file_path))

print("===== QQQ 行情数据检查 =====")
print("数据条数：", len(data["dates"]))
print("最早日期：", data["dates"][0])
print("最新日期：", data["dates"][-1])
print("第一条开盘价：", data["open_prices"][0])
print("第一条收盘价：", data["close_prices"][0])
print("最后一条开盘价：", data["open_prices"][-1])
print("最后一条收盘价：", data["close_prices"][-1])

print("日期顺序：", "正常" if data["dates"] == sorted(data["dates"]) else "异常")
print("价格检查：", "通过" if all(
    price > 0
    for price in data["open_prices"] + data["close_prices"]
) else "异常")

print("最终结果：数据读取成功")
print("\n===== 原始行情文件列名检查 =====")

with open("QQQ_history_raw.csv", "r", encoding="utf-8-sig") as f:
    header = f.readline().strip()

print("原始 CSV 表头：", header)
print("清洗后 CSV 表头：")

with open("QQQ_history.csv", "r", encoding="utf-8-sig") as f:
    print(f.readline().strip())
