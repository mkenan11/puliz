from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from telegram.ext import Application

from database.db import Database
from database.models import BudgetCycle, ExpenseDay, Reminder, User
from utils.money import format_amount


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def to_utc(local_time: datetime, timezone_name: str) -> datetime:
    return local_time.replace(tzinfo=ZoneInfo(timezone_name)).astimezone(
        timezone.utc
    ).replace(tzinfo=None)


async def send_due_reminders(application: Application) -> None:
    database: Database = application.bot_data["database"]
    now = utc_now()
    async for session in database.session():
        users = (
            await session.execute(
                select(User).where(User.onboarding_completed.is_(True))
            )
        ).scalars().all()

        for user in users:
            try:
                local_now = datetime.now(ZoneInfo(user.timezone))
            except Exception:
                local_now = datetime.now(ZoneInfo("Asia/Baku"))
            today = local_now.date()
            await _send_daily_reminder(application, session, user, today, local_now)
            await _send_follow_up(application, session, user, today, now)
            await _send_snoozed(application, session, user, today, now)
            await _send_missing_reminder(application, session, user, today, local_now)
            await _send_morning_summary(application, session, user, today, local_now)

        await session.commit()


async def _send_morning_summary(
    application: Application, session, user: User, target_date: date, local_now: datetime
) -> None:
    if not user.morning_summary_enabled or local_now.hour != 8:
        return
    existing = await _reminder(session, user.id, target_date, "morning_summary")
    if existing is not None:
        return
    cycle = (
        await session.execute(
            select(BudgetCycle).where(
                BudgetCycle.user_id == user.id,
                BudgetCycle.start_date <= target_date,
                BudgetCycle.end_date >= target_date,
            )
        )
    ).scalars().first()
    if cycle is None:
        return
    expenses = (
        await session.execute(
            select(ExpenseDay).where(
                ExpenseDay.user_id == user.id,
                ExpenseDay.cycle_id == cycle.id,
                ExpenseDay.status == "recorded",
            )
        )
    ).scalars().all()
    spent_cents = sum(expense.amount_cents or 0 for expense in expenses)
    remaining_days = max((cycle.end_date - target_date).days + 1, 0)
    daily_average = (
        (cycle.budget_amount_cents - spent_cents) / remaining_days
        if remaining_days
        else 0
    )
    await application.bot.send_message(
        chat_id=user.telegram_user_id,
        text=(
            "☀️ Bu gün üçün büdcə tempin\n\n"
            f"Qalan büdcə: {format_amount(cycle.budget_amount_cents - spent_cents)} AZN\n"
            f"Gündəlik mümkün orta: {daily_average / 100:.2f} AZN"
        ),
    )
    now = utc_now()
    session.add(
        Reminder(
            user_id=user.id,
            target_date=target_date,
            reminder_type="morning_summary",
            scheduled_at=now,
            sent_at=now,
            status="sent",
        )
    )


async def _send_daily_reminder(
    application: Application, session, user: User, target_date: date, local_now: datetime
) -> None:
    expense = await _expense(session, user.id, target_date)
    if expense is not None and expense.status == "recorded":
        return
    try:
        hour, minute = (int(part) for part in user.reminder_time.split(":"))
    except ValueError:
        hour, minute = 23, 0
    local_scheduled = local_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    scheduled_at = to_utc(local_scheduled, user.timezone)
    existing = await _reminder(session, user.id, target_date, "daily")
    if existing is None and utc_now() >= scheduled_at:
        await application.bot.send_message(
            chat_id=user.telegram_user_id,
            text="🌙 Günün xərcini qeyd edək.\n\nBu gün ümumilikdə nə qədər xərclədin?",
            reply_markup=_reminder_keyboard(),
        )
        session.add(
            Reminder(
                user_id=user.id,
                target_date=target_date,
                reminder_type="daily",
                scheduled_at=scheduled_at,
                sent_at=utc_now(),
                status="sent",
            )
        )


async def _send_follow_up(
    application: Application, session, user: User, target_date: date, now: datetime
) -> None:
    daily = await _reminder(session, user.id, target_date, "daily")
    if daily is None or daily.sent_at is None or now < daily.sent_at + timedelta(hours=1):
        return
    if await _expense(session, user.id, target_date) is not None:
        return
    if await _reminder(session, user.id, target_date, "follow_up") is not None:
        return
    await application.bot.send_message(
        chat_id=user.telegram_user_id,
        text="🔔 Bugünkü xərc qeydin hələ daxil edilməyib.\n\nVaxtın varsa, günün ümumi xərcini yaza bilərsən.",
        reply_markup=_reminder_keyboard(),
    )
    session.add(
        Reminder(
            user_id=user.id,
            target_date=target_date,
            reminder_type="follow_up",
            scheduled_at=now,
            sent_at=now,
            status="sent",
        )
    )


async def _send_snoozed(
    application: Application, session, user: User, target_date: date, now: datetime
) -> None:
    result = await session.execute(
        select(Reminder).where(
            Reminder.user_id == user.id,
            Reminder.target_date == target_date,
            Reminder.reminder_type == "snooze",
            Reminder.status == "pending",
            Reminder.scheduled_at <= now,
        )
    )
    for reminder in result.scalars().all():
        if await _expense(session, user.id, target_date) is not None:
            reminder.status = "cancelled"
            continue
        await application.bot.send_message(
            chat_id=user.telegram_user_id,
            text="⏰ Günün xərcini qeyd etmək vaxtıdır. Nə qədər xərclədin?",
            reply_markup=_reminder_keyboard(),
        )
        reminder.status = "sent"
        reminder.sent_at = now


async def _send_missing_reminder(
    application: Application, session, user: User, today: date, local_now: datetime
) -> None:
    target_date = today - timedelta(days=1)
    if local_now.hour < 9 or await _expense(session, user.id, target_date) is not None:
        return
    cycle = (
        await session.execute(
            select(BudgetCycle).where(
                BudgetCycle.user_id == user.id,
                BudgetCycle.start_date <= target_date,
                BudgetCycle.end_date >= target_date,
            )
        )
    ).scalars().first()
    if cycle is None or await _reminder(session, user.id, target_date, "missing"):
        return
    now = utc_now()
    await application.bot.send_message(
        chat_id=user.telegram_user_id,
        text="📅 Dünənin xərc qeydi çatışmır.\n\nDünən nə qədər xərclədiyini xatırlayırsansa, indi əlavə edə bilərsən.",
        reply_markup=_missing_keyboard(),
    )
    session.add(
        Reminder(
            user_id=user.id,
            target_date=target_date,
            reminder_type="missing",
            scheduled_at=now,
            sent_at=now,
            status="sent",
        )
    )


async def _expense(session, user_id: int, target_date: date):
    return (
        await session.execute(
            select(ExpenseDay).where(
                ExpenseDay.user_id == user_id, ExpenseDay.date == target_date
            )
        )
    ).scalar_one_or_none()


async def _reminder(session, user_id: int, target_date: date, reminder_type: str):
    return (
        await session.execute(
            select(Reminder).where(
                Reminder.user_id == user_id,
                Reminder.target_date == target_date,
                Reminder.reminder_type == reminder_type,
            )
        )
    ).scalar_one_or_none()


def _reminder_keyboard():
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("✅ Bu gün xərc olmadı", callback_data="reminder:zero")],
            [InlineKeyboardButton("⏰ Sonra xatırlat", callback_data="reminder:snooze")],
        ]
    )


def _missing_keyboard():
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("✏️ Əlavə et", callback_data="missing:add")],
            [
                InlineKeyboardButton("✅ 0 AZN idi", callback_data="missing:zero"),
                InlineKeyboardButton("⏭ Keç", callback_data="missing:skip"),
            ],
        ]
    )