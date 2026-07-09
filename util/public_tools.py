from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Optional


DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"


def ensure_directory(path: str | Path) -> None:
    target = Path(path)
    directory = target if target.suffix == "" else target.parent
    if directory:
        os.makedirs(directory, exist_ok=True)


def now_text() -> str:
    return datetime.now().strftime(DATETIME_FORMAT)


def parse_datetime(value: str) -> datetime:
    return datetime.strptime(value, DATETIME_FORMAT)


def format_duration(seconds: Optional[int]) -> str:
    if seconds is None:
        return "未离馆"
    seconds = max(0, int(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}小时{minutes}分钟{secs}秒"
    if minutes:
        return f"{minutes}分钟{secs}秒"
    return f"{secs}秒"


def prompt_required(label: str) -> str:
    while True:
        value = input(f"{label}: ").strip()
        if value:
            return value
        print(f"{label}不能为空。")


def prompt_optional(label: str, default: str = "") -> str:
    value = input(f"{label}: ").strip()
    return value or default
