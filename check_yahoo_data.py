

import csv
import json
import urllib.request
from datetime import datetime, timezone

# 获取约十年历史数据
start = int(datetime(
    2016, 10, 20, tzinfo=timezone.utc
).timestamp())

end = int(datetime.now(timezone.utc).timestamp()) + 86400

url = (
    "https://query1.finance.yahoo.com/v8/finance/chart/QQQ"
    f"?period1={start}&period2={end}&interval=1d"
)

try:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0"}
    )

    with urllib.request.urlopen(req, timeout=30) as response:
        data = json.loads(response.read().decode("utf-8"))

    chart = data["chart"]

    if chart.get("error"):
        raise RuntimeError(chart["error"])

    result = chart["result"][0]
    timestamps = result["timestamp"]
    quote = result["indicators"]["quote"][0]

    adj_items = result["indicators"].get("adjclose", [])
    adj_prices = adj_items[0].get("adjclose", []) if adj_items else []

    rows = []

    for i, timestamp in enumerate(timestamps):
        open_price = quote["open"][i]
        high_price = quote["high"][i]
        low_price = quote["low"][i]
        close_price = quote["close"][i]
        volume = quote["volume"][i]
        adj_close = adj_prices[i] if i < len(adj_prices) else None

        if any(v is None for v in (
            open_price, high_price, low_price,
            close_price, adj_close
        )):
            continue

        date = datetime.fromtimestamp(
            timestamp, timezone.utc
        ).strftime("%Y-%m-%d")

        rows.append({
            "Date": date,
            "Open": open_price,
            "High": high_price,
            "Low": low_price,
            "Close": close_price,
            "Adj Close": adj_close,
            "Volume": volume
        })

    if not rows:
        raise RuntimeError("没有获取到有效行情数据")

    filename = "QQQ_yahoo_10y.csv"

    with open(filename, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "Date", "Open", "High", "Low",
                "Close", "Adj Close", "Volume"
            ]
        )
        writer.writeheader()
        writer.writerows(rows)

    print("下载成功")
    print("文件：", filename)
    print("有效数据条数：", len(rows))
    print("最早日期：", rows[0]["Date"])
    print("最新日期：", rows[-1]["Date"])
    print("第一条数据：", rows[0])
    print("最后一条数据：", rows[-1])

except Exception as e:
    print("下载失败：", repr(e))
    
import csv

with open(
    "QQQ_yahoo_10y.csv",
    "r",
    newline="",
    encoding="utf-8-sig"
) as f:
    rows = list(csv.DictReader(f))

first = rows[0]
last = rows[-1]

first_close = float(first["Close"])
last_close = float(last["Close"])
first_adj = float(first["Adj Close"])
last_adj = float(last["Adj Close"])

close_return = (last_close / first_close - 1) * 100
adj_return = (last_adj / first_adj - 1) * 100

print("\n===== 长期价格口径检查 =====")
print("数据条数：", len(rows))
print("普通收盘价累计涨幅：", round(close_return, 2), "%")
print("调整收盘价累计涨幅：", round(adj_return, 2), "%")
print("首日普通收盘价：", first_close)
print("首日调整收盘价：", first_adj)
print("末日普通收盘价：", last_close)
print("末日调整收盘价：", last_adj)

from benchmark import buy_and_hold_adjusted_result

with open(
    "QQQ_yahoo_10y.csv",
    "r",
    newline="",
    encoding="utf-8-sig"
) as f:
    rows = list(csv.DictReader(f))

adj_close_prices = [
    float(row["Adj Close"]) for row in rows
]

result = buy_and_hold_adjusted_result(
    adj_close_prices,
    initial_cash=10000.0,
    fee_rate=0.001,
)

print("\n===== 调整收盘价基准测试 =====")
for key, value in result.items():
    print(key, ":", value)

from pathlib import Path
from csv_data import load_adjusted_price_csv

folder = Path(__file__).parent

data = load_adjusted_price_csv(
    str(folder / "QQQ_yahoo_10y.csv")
)

print("\n===== 新数据读取检查 =====")
print("数据条数：", len(data["dates"]))
print("最早日期：", data["dates"][0])
print("最新日期：", data["dates"][-1])
print("开盘价：", data["open_prices"][-1])
print("普通收盘价：", data["close_prices"][-1])
print("调整收盘价：", data["adj_close_prices"][-1])
print(
    "各字段长度一致：",
    len(data["dates"])
    == len(data["open_prices"])
    == len(data["close_prices"])
    == len(data["adj_close_prices"])
)

