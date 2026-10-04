from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from database.db import Database
from database.models import BudgetCycle, ExpenseDay, Reminder, User
from services.cycle_service import cycle_for_expense_date
from utils.money import format_amount, parse_amount


def _database(context: ContextTypes.DEFAULT_TYPE) -> Database:
    return context.application.bot_data["database"]


async def reminder_snooze_menu(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if update.callback_query is None:
        return
    await update.callback_query.answer()
    await update.callback_query.edit_message_text(
        "⏰ Nə vaxt yenidən xatırladım?",
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("30 dəqiqə", callback_data="snooze:30"),
                    InlineKeyboardButton("1 saat", callback_data="snooze:60"),
                ],
                [InlineKeyboardButton("Ləğv et", callback_data="snooze:cancel")],
            ]
        ),
    )


async def reminder_snooze(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if update.callback_query is None or update.callback_query.data is None:
        return
    await update.callback_query.answer()
    value = update.callback_query.data.split(":", maxsplit=1)[1]
    if value == "cancel":
        await update.callback_query.edit_message_text("Snooze ləğv edildi.")
        return

    telegram_user = update.effective_user
    if telegram_user is None:
        return
    minutes = int(value)
    database = _database(context)
    async for session in database.session():
        user = (
            await session.execute(
                select(User).where(User.telegram_user_id == telegram_user.id)
            )
        ).scalar_one()
        target_date = _local_date(user)
        session.add(
            Reminder(
                user_id=user.id,
                target_date=target_date,
                reminder_type="snooze",
                scheduled_at=datetime.utcnow() + timedelta(minutes=minutes),
                status="pending",
            )
        )
        await session.commit()
    await update.callback_query.edit_message_text(
        f"✅ Yenidən {minutes} dəqiqə sonra xatırladacağam."
    )


async def reminder_zero(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if update.callback_query is None:
        return
    await update.callback_query.answer()
    await _record_amount(update, context, await _local_target(update, context), 0)


async def missing_action(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if update.callback_query is None or update.callback_query.data is None:
        return
    await update.callback_query.answer()
    action = update.callback_query.data.split(":", maxsplit=1)[1]
    target_date = await _local_target(update, context, yesterday=True)
    if action == "skip":
        await update.callback_query.edit_message_text(
            "⏭ Dünən üçün məlumat əlavə edilmədi. Gün missing olaraq qalır."
        )
        return
    if action == "add":
        context.user_data["reminder_target_date"] = target_date
        await update.callback_query.edit_message_text(
            "✏️ Dünən üçün xərci yaz."
        )
        return
    await _record_amount(update, context, target_date, 0)


async def handle_reminder_amount(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if update.message is None or update.message.text is None:
        return
    amount_cents = parse_amount(update.message.text)
    if amount_cents is None:
        return
    target_date = context.user_data.pop("reminder_target_date", None)
    if target_date is None:
        target_date = await _pending_target_date(update, context)
    if target_date is None:
        return
    await _record_amount(update, context, target_date, amount_cents)


async def _pending_target_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_user = update.effective_user
    if telegram_user is None:
        return None
    database = _database(context)
    async for session in database.session():
        user = (
            await session.execute(
                select(User).where(User.telegram_user_id == telegram_user.id)
            )
        ).scalar_one_or_none()
        if user is None:
            return None
        result = await session.execute(
            select(Reminder)
            .where(
                Reminder.user_id == user.id,
                Reminder.status == "sent",
                Reminder.target_date <= _local_date(user),
                Reminder.reminder_type.in_(["daily", "follow_up", "snooze", "missing"]),
            )
            .order_by(Reminder.sent_at.desc())
        )
        reminder = result.scalars().first()
        return reminder.target_date if reminder else None


async def _record_amount(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    target_date: date | None,
    amount_cents: int,
) -> None:
    telegram_user = update.effective_user
    if telegram_user is None or target_date is None:
        return
    database = _database(context)
    async for session in database.session():
        user = (
            await session.execute(
                select(User).where(User.telegram_user_id == telegram_user.id)
            )
        ).scalar_one()
        cycle = await cycle_for_expense_date(session, user, target_date)
        if cycle is None:
            return
        expense = (
            await session.execute(
                select(ExpenseDay).where(
                    ExpenseDay.user_id == user.id, ExpenseDay.date == target_date
                )
            )
        ).scalar_one_or_none()
        if expense is None:
            session.add(
                ExpenseDay(
                    user_id=user.id,
                    cycle_id=cycle.id,
                    date=target_date,
                    amount_cents=amount_cents,
                    status="recorded",
                )
            )
        else:
            expense.amount_cents = amount_cents
            expense.status = "recorded"
        await session.commit()
    await _reply(update, f"✅ **{format_amount(amount_cents)} AZN** qeyd edildi.")


def _local_date(user: User, yesterday: bool = False) -> date:
    try:
        current = datetime.now(ZoneInfo(user.timezone)).date()
    except Exception:
        current = datetime.now(ZoneInfo("Asia/Baku")).date()
    return current - timedelta(days=1) if yesterday else current


async def _local_target(
    update: Update, context: ContextTypes.DEFAULT_TYPE, yesterday: bool = False
) -> date | None:
    telegram_user = update.effective_user
    if telegram_user is None:
        return None
    database = _database(context)
    async for session in database.session():
        user = (
            await session.execute(
                select(User).where(User.telegram_user_id == telegram_user.id)
            )
        ).scalar_one_or_none()
        return _local_date(user, yesterday) if user is not None else None


async def _reply(update: Update, text: str) -> None:
    if update.callback_query is not None:
        await update.callback_query.edit_message_text(text, parse_mode="Markdown")
    elif update.message is not None:
        await update.message.reply_text(text, parse_mode="Markdown")