import calendar
from datetime import date, timedelta


def safe_month_date(year: int, month: int, day: int) -> date:
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(day, last_day))


def previous_month(year: int, month: int) -> tuple[int, int]:
    if month == 1:
        return year - 1, 12
    return year, month - 1


def next_month(year: int, month: int) -> tuple[int, int]:
    if month == 12:
        return year + 1, 1
    return year, month + 1


def cycle_dates(start_day: int, today: date | None = None) -> tuple[date, date]:
    current_date = today or date.today()
    if start_day <= current_date.day:
        start_date = safe_month_date(
            current_date.year, current_date.month, start_day
        )
    else:
        year, month = previous_month(current_date.year, current_date.month)
        start_date = safe_month_date(year, month, start_day)

    year, month = next_month(start_date.year, start_date.month)
    next_start = safe_month_date(year, month, start_day)
    return start_date, next_start - timedelta(days=1)