from datetime import date

from sqlalchemy import select

from database.models import BudgetCycle, ExpenseDay, User
from services.weekly_service import WeekSegment, week_segments


async def current_cycle(session, user_id: int, target_date: date | None = None):
    target_date = target_date or date.today()
    result = await session.execute(
        select(BudgetCycle)
        .where(
            BudgetCycle.user_id == user_id,
            BudgetCycle.start_date <= target_date,
            BudgetCycle.end_date >= target_date,
        )
        .order_by(BudgetCycle.created_at.desc())
    )
    return result.scalars().first()


async def cycle_expenses(session, user_id: int, cycle_id: int):
    result = await session.execute(
        select(ExpenseDay).where(
            ExpenseDay.user_id == user_id,
            ExpenseDay.cycle_id == cycle_id,
        )
    )
    return result.scalars().all()


def segment_for_date(segments: list[WeekSegment], target_date: date):
    return next(
        (
            segment
            for segment in segments
            if segment.start_date <= target_date <= segment.end_date
        ),
        None,
    )


async def cycle_for_expense_date(session, user: User, target_date: date):
    cycle_result = await session.execute(
        select(BudgetCycle)
        .where(
            BudgetCycle.user_id == user.id,
            BudgetCycle.start_date <= target_date,
            BudgetCycle.end_date >= target_date,
        )
        .order_by(BudgetCycle.created_at.desc())
    )
    cycle = cycle_result.scalars().first()
    if cycle is not None:
        return cycle

    earliest_result = await session.execute(
        select(BudgetCycle)
        .where(BudgetCycle.user_id == user.id)
        .order_by(BudgetCycle.start_date.asc())
    )
    earliest = earliest_result.scalars().first()
    if (
        earliest is None
        or target_date != earliest.start_date.fromordinal(
            earliest.start_date.toordinal() - 1
        )
        or user.budget_start_day is None
    ):
        return None

    previous_start = _previous_cycle_start(earliest.start_date, user.budget_start_day)
    previous_cycle = BudgetCycle(
        user_id=user.id,
        start_date=previous_start,
        end_date=earliest.start_date.fromordinal(
            earliest.start_date.toordinal() - 1
        ),
        budget_amount_cents=earliest.budget_amount_cents,
        status="archived",
    )
    session.add(previous_cycle)
    await session.flush()
    return previous_cycle


def _previous_cycle_start(cycle_start: date, start_day: int) -> date:
    year, month = cycle_start.year, cycle_start.month - 1
    if month == 0:
        year, month = year - 1, 12
    import calendar

    return date(year, month, min(start_day, calendar.monthrange(year, month)[1]))