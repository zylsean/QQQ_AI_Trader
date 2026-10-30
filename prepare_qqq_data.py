

import csv
from datetime import datetime
from pathlib import Path

folder = Path(__file__).parent
source = folder / "QQQ_history_raw.csv"
target = folder / "QQQ_history.csv"

with open(source, "r", newline="", encoding="utf-8-sig") as f:
    reader = csv.DictReader(f)

    rows = []
    for row in reader:
        date = datetime.strptime(
            row["Date"].strip(), "%m/%d/%Y"
        ).strftime("%Y-%m-%d")

        rows.append({
            "Date": date,
            "Open": float(row["Open"]),
            "Close": float(
                row["Close/Last"].replace("$", "").strip()
            ),
        })

rows.sort(key=lambda row: row["Date"])

if len(rows) < 2:
    raise ValueError("有效行情数据不足两行")

dates = [row["Date"] for row in rows]
if len(dates) != len(set(dates)):
    raise ValueError("存在重复交易日期，请检查原始文件")

with open(target, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(
        f, fieldnames=["Date", "Open", "Close"]
    )
    writer.writeheader()
    writer.writerows(rows)

print("QQQ 行情整理完成")
print("数据条数：", len(rows))
print("最早日期：", rows[0]["Date"])
print("最新日期：", rows[-1]["Date"])
print("输出文件：QQQ_history.csv")
