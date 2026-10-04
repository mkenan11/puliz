from datetime import date

from sqlalchemy import select
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes, ConversationHandler

from database.db import Database
from database.models import BudgetCycle, User
from utils.dates import cycle_dates
from utils.money import format_amount, parse_amount


BUDGET, START_DAY, CUSTOM_START_DAY, REMINDER_TIME = range(4)


def _database(context: ContextTypes.DEFAULT_TYPE) -> Database:
    return context.application.bot_data["database"]


async def begin_onboarding(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    if update.callback_query is None:
        return ConversationHandler.END

    await update.callback_query.answer()
    await update.callback_query.edit_message_text(
        "💰 Bu cycle üçün nə qədər xərcləmək istəyirsən?\n\n"
        "Məsələn: 160"
    )
    return BUDGET


async def budget_amount(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    if update.message is None or update.message.text is None:
        return BUDGET

    amount_cents = parse_amount(update.message.text)
    if amount_cents is None or amount_cents <= 0:
        await update.message.reply_text(
            "Məbləği rəqəmlə yaz 🙂\n\nMəsələn: 160 və ya 160,50"
        )
        return BUDGET

    context.user_data["budget_amount_cents"] = amount_cents
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("1️⃣ Ayın 1-i", callback_data="start_day:1"),
                InlineKeyboardButton("📅 Bu gün", callback_data="start_day:today"),
            ],
            [InlineKeyboardButton("✏️ Başqa gün", callback_data="start_day:custom")],
        ]
    )
    await update.message.reply_text(
        f"✅ Büdcə: **{format_amount(amount_cents)} AZN**\n\n"
        "İndi büdcənin hansı gün yeniləndiyini seçək.\n\n"
        "Adətən pulun ayın hansı günü gəlir?",
        reply_markup=keyboard,
        parse_mode="Markdown",
    )
    return START_DAY


async def start_day(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    if update.callback_query is None or update.callback_query.data is None:
        return START_DAY

    await update.callback_query.answer()
    value = update.callback_query.data.split(":", maxsplit=1)[1]
    if value == "custom":
        await update.callback_query.edit_message_text(
            "📅 Büdcə dövrünün başladığı günü yaz (1-31)."
        )
        return CUSTOM_START_DAY

    start_day_value = date.today().day if value == "today" else int(value)
    context.user_data["budget_start_day"] = start_day_value
    await update.callback_query.edit_message_text(
        "⏰ Günlük xərclərini sənə saat neçədə xatırladım?",
        reply_markup=_reminder_keyboard(),
    )
    return REMINDER_TIME


async def custom_start_day(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    if update.message is None or update.message.text is None:
        return CUSTOM_START_DAY

    try:
        start_day_value = int(update.message.text.strip())
    except ValueError:
        start_day_value = 0

    if not 1 <= start_day_value <= 31:
        await update.message.reply_text("Günü 1-31 aralığında yaz 🙂")
        return CUSTOM_START_DAY

    context.user_data["budget_start_day"] = start_day_value
    await update.message.reply_text(
        "⏰ Günlük xərclərini sənə saat neçədə xatırladım?",
        reply_markup=_reminder_keyboard(),
    )
    return REMINDER_TIME


def _reminder_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("22:00", callback_data="reminder:22:00"),
                InlineKeyboardButton("23:00", callback_data="reminder:23:00"),
            ],
            [InlineKeyboardButton("✏️ Başqa vaxt", callback_data="reminder:custom")],
        ]
    )


async def reminder_time(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    if update.callback_query is None or update.callback_query.data is None:
        return REMINDER_TIME

    await update.callback_query.answer()
    value = update.callback_query.data.split(":", maxsplit=1)[1]
    if value == "custom":
        await update.callback_query.edit_message_text(
            "⏰ Reminder saatını HH:MM formatında yaz.\n\nMəsələn: 21:30"
        )
        return REMINDER_TIME

    return await _finish_onboarding(update, context, value)


async def custom_reminder_time(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    if update.message is None or update.message.text is None:
        return REMINDER_TIME

    value = update.message.text.strip()
    parts = value.split(":")
    if len(parts) != 2:
        await update.message.reply_text("Vaxtı HH:MM formatında yaz 🙂")
        return REMINDER_TIME

    try:
        hour, minute = int(parts[0]), int(parts[1])
    except ValueError:
        hour, minute = -1, -1

    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        await update.message.reply_text("Düzgün vaxt yaz, məsələn: 21:30")
        return REMINDER_TIME

    return await _finish_onboarding(update, context, f"{hour:02d}:{minute:02d}")


async def _finish_onboarding(
    update: Update, context: ContextTypes.DEFAULT_TYPE, reminder_time: str
) -> int:
    telegram_user = update.effective_user
    if telegram_user is None:
        return ConversationHandler.END

    amount_cents = context.user_data["budget_amount_cents"]
    start_day_value = context.user_data["budget_start_day"]
    start_date, end_date = cycle_dates(start_day_value)
    database = _database(context)

    async for session in database.session():
        result = await session.execute(
            select(User).where(User.telegram_user_id == telegram_user.id)
        )
        user = result.scalar_one()
        user.reminder_time = reminder_time
        user.budget_start_day = start_day_value
        user.onboarding_completed = True
        cycle_result = await session.execute(
            select(BudgetCycle).where(
                BudgetCycle.user_id == user.id,
                BudgetCycle.status == "active",
                BudgetCycle.start_date == start_date,
                BudgetCycle.end_date == end_date,
            )
        )
        cycle = cycle_result.scalars().first()
        if cycle is None:
            session.add(
                BudgetCycle(
                    user_id=user.id,
                    start_date=start_date,
                    end_date=end_date,
                    budget_amount_cents=amount_cents,
                )
            )
        else:
            cycle.budget_amount_cents = amount_cents
        await session.commit()

    number_of_days = (end_date - start_date).days + 1
    daily_average = amount_cents / number_of_days
    message = (
        "🎉 Hazırsan!\n\n"
        f"**Büdcən:** {format_amount(amount_cents)} AZN\n"
        f"**Büdcə dövrü:** {start_date:%d.%m.%Y} – {end_date:%d.%m.%Y}\n"
        f"**Gündəlik orta:** {daily_average / 100:.2f} AZN\n"
        f"**Gündəlik reminder:** {reminder_time}\n\n"
        "Bundan sonra hər gün xərclərini birlikdə izləyəcəyik."
    )
    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton("🏠 Əsas menyu", callback_data="main_menu")]]
    )
    if update.callback_query is not None:
        await update.callback_query.edit_message_text(
            message, reply_markup=keyboard, parse_mode="Markdown"
        )
    elif update.message is not None:
        await update.message.reply_text(
            message, reply_markup=keyboard, parse_mode="Markdown"
        )
    context.user_data.clear()
    return ConversationHandler.END