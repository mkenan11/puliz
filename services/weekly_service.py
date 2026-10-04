from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from telegram.ext import Application

from database.models import BudgetCycle, ExpenseDay, Reminder, ThresholdEvent, User
from utils.money import format_amount


@dataclass(frozen=True)
class WeekSegment:
    number: int
    start_date: date
    end_date: date
    target_cents: int


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def week_segments(cycle: BudgetCycle) -> list[WeekSegment]:
    total_days = (cycle.end_date - cycle.start_date).days + 1
    segments: list[tuple[date, date]] = []
    current = cycle.start_date
    while current <= cycle.end_date:
        end = min(current + timedelta(days=6), cycle.end_date)
        segments.append((current, end))
        current = end + timedelta(days=1)

    targets: list[int] = []
    allocated = 0
    for index, (start, end) in enumerate(segments):
        days = (end - start).days + 1
        if index == len(segments) - 1:
            target = cycle.budget_amount_cents - allocated
        else:
            target = cycle.budget_amount_cents * days // total_days
        targets.append(target)
        allocated += target

    return [
        WeekSegment(number=index + 1, start_date=start, end_date=end, target_cents=targets[index])
        for index, (start, end) in enumerate(segments)
    ]


async def process_weekly_updates(application: Application) -> None:
    database = application.bot_data["database"]
    today = date.today()
    async for session in database.session():
        users = (
            await session.execute(
                select(User).where(User.onboarding_completed.is_(True))
            )
        ).scalars().all()
        for user in users:
            cycles = (
                await session.execute(
                    select(BudgetCycle).where(
                        BudgetCycle.user_id == user.id,
                        BudgetCycle.status == "active",
                    )
                )
            ).scalars().all()
            for cycle in cycles:
                segments = week_segments(cycle)
                for segment in segments:
                    if segment.start_date <= today <= segment.end_date:
                        await _thresholds(
                            application, session, user, cycle, segment
                        )
                    elif today > segment.end_date:
                        await _weekly_report(
                            application, session, user, cycle, segment
                        )
        await session.commit()


async def _thresholds(application, session, user, cycle, segment) -> None:
    spent_cents = await _spent(session, user.id, cycle.id, segment)
    if segment.target_cents <= 0:
        return
    for threshold in (75, 90, 100, 110):
        if spent_cents * 100 < segment.target_cents * threshold:
            continue
        event = (
            await session.execute(
                select(ThresholdEvent).where(
                    ThresholdEvent.user_id == user.id,
                    ThresholdEvent.cycle_id == cycle.id,
                    ThresholdEvent.week_number == segment.number,
                    ThresholdEvent.threshold == threshold,
                )
            )
        ).scalar_one_or_none()
        if event is not None:
            continue
        await application.bot.send_message(
            chat_id=user.telegram_user_id,
            text=_threshold_text(threshold, spent_cents, segment.target_cents),
            parse_mode="Markdown",
        )
        session.add(
            ThresholdEvent(
                user_id=user.id,
                cycle_id=cycle.id,
                week_number=segment.number,
                threshold=threshold,
            )
        )


async def _weekly_report(application, session, user, cycle, segment) -> None:
    existing = (
        await session.execute(
            select(Reminder).where(
                Reminder.user_id == user.id,
                Reminder.target_date == segment.end_date,
                Reminder.reminder_type == "weekly_report",
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return
    spent_cents = await _spent(session, user.id, cycle.id, segment)
    tracked_days = (
        await session.execute(
            select(ExpenseDay).where(
                ExpenseDay.user_id == user.id,
                ExpenseDay.cycle_id == cycle.id,
                ExpenseDay.date >= segment.start_date,
                ExpenseDay.date <= segment.end_date,
                ExpenseDay.status == "recorded",
            )
        )
    ).scalars().all()
    days = (segment.end_date - segment.start_date).days + 1
    difference = spent_cents - segment.target_cents
    await application.bot.send_message(
        chat_id=user.telegram_user_id,
        text=(
            f"📊 **{segment.number}-ci həftə arxada qaldı**\n\n"
            f"Target: **{format_amount(segment.target_cents)} AZN**\n"
            f"Xərc: **{format_amount(spent_cents)} AZN**\n"
            f"Fərq: **{format_amount(difference)} AZN**\n"
            f"Qeyd etdiyin günlər: **{len(tracked_days)} / {days}**"
        ),
        parse_mode="Markdown",
    )
    now = utc_now()
    session.add(
        Reminder(
            user_id=user.id,
            target_date=segment.end_date,
            reminder_type="weekly_report",
            scheduled_at=now,
            sent_at=now,
            status="sent",
        )
    )


async def _spent(session, user_id: int, cycle_id: int, segment) -> int:
    expenses = (
        await session.execute(
            select(ExpenseDay).where(
                ExpenseDay.user_id == user_id,
                ExpenseDay.cycle_id == cycle_id,
                ExpenseDay.date >= segment.start_date,
                ExpenseDay.date <= segment.end_date,
                ExpenseDay.status == "recorded",
            )
        )
    ).scalars().all()
    return sum(expense.amount_cents or 0 for expense in expenses)


def _threshold_text(threshold: int, spent_cents: int, target_cents: int) -> str:
    if threshold == 75:
        return (
            f"📊 Həftəlik target-ının **75%-nə** çatmısan.\n\n"
            f"Xərc: **{format_amount(spent_cents)} AZN**\n"
            f"Target: **{format_amount(target_cents)} AZN**\n"
            f"Qalan: **{format_amount(max(target_cents - spent_cents, 0))} AZN**"
        )
    if threshold == 90:
        return (
            "⚠️ Həftəlik büdcənin **90%-i** istifadə olunub.\n\n"
            f"Qalan target: **{format_amount(max(target_cents - spent_cents, 0))} AZN**"
        )
    if threshold == 100:
        return (
            "🎯 Həftəlik target-a çatdın.\n\n"
            f"Target: **{format_amount(target_cents)} AZN**\n"
            f"Cari xərc: **{format_amount(spent_cents)} AZN**"
        )
    return (
        "📌 Həftəlik target 10%-dən çox keçilib.\n\n"
        f"Target: **{format_amount(target_cents)} AZN**\n"
        f"Xərc: **{format_amount(spent_cents)} AZN**"
    )