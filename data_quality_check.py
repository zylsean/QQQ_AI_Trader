
import csv
from pathlib import Path
from datetime import datetime
from math import isfinite

folder = Path(__file__).parent
file_path = folder / "QQQ_yahoo_10y.csv"


def parse_date(value):
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y/%m/%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(value.strip(), fmt).date()
        except (ValueError, AttributeError):
            pass
    return None


def parse_number(value):
    try:
        number = float(value.strip().replace(",", ""))
        return number if isfinite(number) else None
    except (ValueError, AttributeError):
        return None


def main():
    if not file_path.exists():
        print("找不到文件：", file_path)
        return

    with open(file_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        headers = reader.fieldnames or []

    print("=" * 50)
    print("QQQ 行情数据深度审计")
    print("=" * 50)
    print("数据行数：", len(rows))
    print("字段：", headers)

    if not rows:
        print("没有数据，停止检查。")
        return

    columns = {h.strip().lower(): h for h in headers if h}

    required = ["date", "open", "high", "low", "close", "volume"]
    missing_columns = [name for name in required if name not in columns]

    if missing_columns:
        print("缺少必要字段：", missing_columns)
        return

    date_col = columns["date"]
    open_col = columns["open"]
    high_col = columns["high"]
    low_col = columns["low"]
    close_col = columns["close"]
    volume_col = columns["volume"]

    dates = []
    invalid_dates = []

    for i, row in enumerate(rows, start=2):
        d = parse_date(row.get(date_col, ""))
        if d is None:
            invalid_dates.append(i)
        else:
            dates.append(d)

    print("\n===== 日期检查 =====")
    print("无法识别的日期数：", len(invalid_dates))
    print("重复日期数：", len(dates) - len(set(dates)))
    print(
        "日期严格递增：",
        all(dates[i] < dates[i + 1] for i in range(len(dates) - 1))
        if len(dates) > 1 else True
    )

    if dates:
        print("最早日期：", min(dates))
        print("最晚日期：", max(dates))

    numeric_errors = []
    ohlc_errors = []
    invalid_volumes = []
    large_moves = []
    previous_close = None

    for i, row in enumerate(rows, start=2):
        values = {
            "Open": parse_number(row.get(open_col, "")),
            "High": parse_number(row.get(high_col, "")),
            "Low": parse_number(row.get(low_col, "")),
            "Close": parse_number(row.get(close_col, "")),
            "Volume": parse_number(row.get(volume_col, "")),
        }

        if any(v is None for v in values.values()):
            numeric_errors.append((i, values))
            previous_close = values["Close"]
            continue

        o = values["Open"]
        h = values["High"]
        l = values["Low"]
        c = values["Close"]
        volume = values["Volume"]

        if min(o, h, l, c) <= 0:
            ohlc_errors.append((i, "存在非正价格", values))
        elif l > min(o, c) or h < max(o, c) or l > h:
            ohlc_errors.append((i, "OHLC 价格关系异常", values))

        if volume < 0:
            invalid_volumes.append((i, volume))

        # 大幅日涨跌仅作为人工复核提示，不直接判定为错误。
        if previous_close is not None and previous_close > 0:
            change = c / previous_close - 1
            if abs(change) >= 0.20:
                large_moves.append((row.get(date_col), round(change * 100, 2)))

        previous_close = c

    print("\n===== 数值与价格关系 =====")
    print("无法解析的数值行数：", len(numeric_errors))
    print("OHLC 关系异常行数：", len(ohlc_errors))
    print("负成交量行数：", len(invalid_volumes))

    if numeric_errors[:5]:
        print("数值异常示例：", numeric_errors[:5])

    if ohlc_errors[:5]:
        print("OHLC 异常示例：", ohlc_errors[:5])

    if invalid_volumes[:5]:
        print("负成交量示例：", invalid_volumes[:5])

    print("\n===== 单日大幅价格变化 =====")
    print("绝对涨跌幅达到 20% 的记录数：", len(large_moves))
    for item in large_moves[:20]:
        print("日期、涨跌幅：", item)

    print("\n===== Adj Close 检查 =====")
    adj_col = columns.get("adj close")

    if adj_col:
        invalid_adj = []
        ratios = []

        for i, row in enumerate(rows, start=2):
            close = parse_number(row.get(close_col, ""))
            adj = parse_number(row.get(adj_col, ""))

            if close is None or adj is None or close <= 0 or adj <= 0:
                invalid_adj.append(i)
            else:
                ratios.append(adj / close)

        print("Adj Close 无效记录数：", len(invalid_adj))
        if ratios:
            print("Adj Close / Close 最小值：", round(min(ratios), 6))
            print("Adj Close / Close 最大值：", round(max(ratios), 6))
    else:
        print("没有 Adj Close 字段。")

    print("\n审计完成。")
    print("异常提示需要结合原始数据来源和公司行动记录复核，不能直接视为数据错误。")


if __name__ == "__main__":
    main()
