from enum import Enum


class WidgetLayout(Enum):
    COMPACT = 1
    TOUCH = 2
    STANDARD = 3


def seconds_to_min_sec(seconds: int) -> str:
    return f"{seconds // 60:02}:{seconds % 60:02}"
