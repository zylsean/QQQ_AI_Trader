

import csv
from math import isfinite


def load_price_csv(path):
    """读取包含 Date、Open、Close 列的日线 CSV 文件。"""

    dates = []
    opens = []
    closes = []

    with open(path, "r", newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)

        required = {"Date", "Open", "Close"}
        if not reader.fieldnames or not required.issubset(
            set(reader.fieldnames)
        ):
            raise ValueError(
                "CSV 必须包含 Date、Open、Close 三列"
            )

        for row in reader:
            try:
                date = row["Date"].strip()
                open_price = float(row["Open"])
                close_price = float(row["Close"])
            except (ValueError, AttributeError, TypeError):
                raise ValueError("日期或价格数据格式不正确")

            if not date:
                raise ValueError("日期不能为空")

            if (
                not isfinite(open_price)
                or not isfinite(close_price)
                or open_price <= 0
                or close_price <= 0
            ):
                raise ValueError("开盘价和收盘价必须是有限正数")

            dates.append(date)
            opens.append(open_price)
            closes.append(close_price)

    if len(dates) < 2:
        raise ValueError("至少需要两行行情数据")

    if dates != sorted(dates):
        raise ValueError("日期必须按从早到晚排列")

    if len(set(dates)) != len(dates):
        raise ValueError("行情日期不能重复")

    return {
        "dates": dates,
        "open_prices": opens,
        "close_prices": closes,
    }
    
def load_adjusted_price_csv(path):
    """读取包含普通行情与调整收盘价的 CSV。"""

    from math import isfinite

    dates = []
    opens = []
    closes = []
    adj_closes = []

    with open(path, "r", newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)

        required = {"Date", "Open", "Close", "Adj Close"}
        if not reader.fieldnames or not required.issubset(
            set(reader.fieldnames)
        ):
            raise ValueError(
                "CSV 必须包含 Date、Open、Close、Adj Close 四列"
            )

        for row in reader:
            try:
                date = row["Date"].strip()
                open_price = float(row["Open"])
                close_price = float(row["Close"])
                adj_close = float(row["Adj Close"])
            except (ValueError, AttributeError, TypeError):
                raise ValueError("日期或价格数据格式不正确")

            if not date:
                raise ValueError("日期不能为空")

            if any(
                not isfinite(price) or price <= 0
                for price in (open_price, close_price, adj_close)
            ):
                raise ValueError("所有价格必须是有限正数")

            dates.append(date)
            opens.append(open_price)
            closes.append(close_price)
            adj_closes.append(adj_close)

    if len(dates) < 2:
        raise ValueError("至少需要两行行情数据")

    if dates != sorted(dates):
        raise ValueError("日期必须按从早到晚排列")

    if len(set(dates)) != len(dates):
        raise ValueError("行情日期不能重复")

    return {
        "dates": dates,
        "open_prices": opens,
        "close_prices": closes,
        "adj_close_prices": adj_closes,
    }

