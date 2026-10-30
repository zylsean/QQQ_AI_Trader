

from pathlib import Path
from csv_data import load_price_csv, load_adjusted_price_csv

folder = Path(__file__).parent

old_data = load_price_csv(str(folder / "QQQ_history.csv"))
new_data = load_adjusted_price_csv(str(folder / "QQQ_yahoo_10y.csv"))

# 按日期建立索引，只比较两份数据共同拥有的日期
old_index = {
    date: i for i, date in enumerate(old_data["dates"])
}
new_index = {
    date: i for i, date in enumerate(new_data["dates"])
}

common_dates = sorted(set(old_index) & set(new_index))

open_diffs = []
close_diffs = []

for date in common_dates:
    oi = old_index[date]
    ni = new_index[date]

    old_open = old_data["open_prices"][oi]
    new_open = new_data["open_prices"][ni]

    old_close = old_data["close_prices"][oi]
    new_close = new_data["close_prices"][ni]

    open_diffs.append(abs(old_open - new_open))
    close_diffs.append(abs(old_close - new_close))

print("===== 新旧行情数据对照 =====")
print("旧数据条数：", len(old_data["dates"]))
print("新数据条数：", len(new_data["dates"]))
print("共同交易日期数：", len(common_dates))

print("旧数据最早日期：", old_data["dates"][0])
print("新数据最早日期：", new_data["dates"][0])
print("共同日期范围：", common_dates[0], "至", common_dates[-1])

print("开盘价最大绝对差异：", round(max(open_diffs), 6))
print("收盘价最大绝对差异：", round(max(close_diffs), 6))

# 找出收盘价相差超过 1% 的日期
large_differences = []

for date in common_dates:
    oi = old_index[date]
    ni = new_index[date]

    old_close = old_data["close_prices"][oi]
    new_close = new_data["close_prices"][ni]

    difference_pct = abs(old_close - new_close) / new_close * 100

    if difference_pct > 1:
        large_differences.append(
            (date, old_close, new_close, difference_pct)
        )

print("收盘价相差超过 1% 的日期数：", len(large_differences))

for item in large_differences[:10]:
    print(
        item[0],
        "旧收盘价：", round(item[1], 4),
        "新收盘价：", round(item[2], 4),
        "差异：", round(item[3], 2), "%"
    )
    
print("\n===== 开盘价差异最大的 10 个日期 =====")

open_differences = []

for date in common_dates:
    oi = old_index[date]
    ni = new_index[date]

    old_open = old_data["open_prices"][oi]
    new_open = new_data["open_prices"][ni]

    difference = abs(old_open - new_open)

    open_differences.append(
        (date, old_open, new_open, difference)
    )

open_differences.sort(key=lambda item: item[3], reverse=True)

for date, old_open, new_open, difference in open_differences[:10]:
    print(
        date,
        "旧开盘价：", round(old_open, 4),
        "新开盘价：", round(new_open, 4),
        "绝对差异：", round(difference, 6)
    )

