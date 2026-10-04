import csv
from io import BytesIO, StringIO

from sqlalchemy import select

from database.models import BudgetCycle, ExpenseDay, User
from services.weekly_service import week_segments


async def expense_csv(session, telegram_user_id: int) -> BytesIO | None:
    user = (
        await session.execute(
            select(User).where(User.telegram_user_id == telegram_user_id)
        )
    ).scalar_one_or_none()
    if user is None:
        return None
    result = await session.execute(
        select(ExpenseDay, BudgetCycle)
        .join(BudgetCycle, ExpenseDay.cycle_id == BudgetCycle.id)
        .where(ExpenseDay.user_id == user.id)
        .order_by(ExpenseDay.date)
    )
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["date", "expense", "cycle", "week", "status"])
    for expense, cycle in result.all():
        week_number = next(
            (
                segment.number
                for segment in week_segments(cycle)
                if segment.start_date <= expense.date <= segment.end_date
            ),
            "",
        )
        writer.writerow(
            [
                expense.date.isoformat(),
                f"{(expense.amount_cents or 0) / 100:.2f}",
                f"{cycle.start_date.isoformat()} - {cycle.end_date.isoformat()}",
                week_number,
                expense.status,
            ]
        )
    file = BytesIO(output.getvalue().encode("utf-8-sig"))
    file.name = "puliz_expenses.csv"
    file.seek(0)
    return file