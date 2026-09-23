"""内置工具：时间类（占位，用来验证"模型→调工具"这条链路是通的）。

后面做记账时，会在这里换成/加上「记账工具」「查账工具」。
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from langchain.tools import tool


@tool
def get_current_time(timezone: str = "Asia/Shanghai") -> str:
    """获取当前日期和时间。

    Args:
        timezone: IANA 时区名，默认北京时间 Asia/Shanghai。
    """
    try:
        tz = ZoneInfo(timezone)
    except Exception:
        return f"无效时区：{timezone}。示例：Asia/Shanghai、UTC"
    return datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S %A")


@tool
def days_between(start_date: str, end_date: str) -> str:
    """计算两个日期相差多少天。

    Args:
        start_date: 起始日期，格式 YYYY-MM-DD。
        end_date: 结束日期，格式 YYYY-MM-DD。
    """
    try:
        d1 = datetime.strptime(start_date, "%Y-%m-%d").date()
        d2 = datetime.strptime(end_date, "%Y-%m-%d").date()
    except ValueError:
        return "日期格式错误，请用 YYYY-MM-DD"
    return f"从 {start_date} 到 {end_date} 相差 {(d2 - d1).days} 天"
