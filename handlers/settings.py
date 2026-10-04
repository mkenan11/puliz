from datetime import date

from sqlalchemy import select
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes, ConversationHandler

from database.db import Database
from database.models import BudgetChange, BudgetCycle, User
from utils.money import format_amount, parse_amount


SETTINGS_BUDGET, SETTINGS_REMINDER = range(2)


def _database(context: ContextTypes.DEFAULT_TYPE) -> Database:
    return context.application.bot_data["database"]


async def settings_menu(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    if update.message is None:
        return ConversationHandler.END
    database = _database(context)
    async for session in database.session():
        user = (
            await session.execute(
                select(User).where(User.telegram_user_id == update.effective_user.id)
            )
        ).scalar_one()
        ai_label = "Açıq" if user.ai_enabled else "Bağlı"
        morning_label = "Açıq" if user.morning_summary_enabled else "Bağlı"
    await update.message.reply_text(
        "⚙️ Ayarlar",
        reply_markup=_settings_keyboard(ai_label, morning_label),
    )
    return ConversationHandler.END


def _settings_keyboard(ai_label: str, morning_label: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("💰 Cari büdcə", callback_data="settings:budget")],
            [InlineKeyboardButton("⏰ Reminder saatı", callback_data="settings:reminder")],
            [InlineKeyboardButton(f"🤖 AI şərhləri: {ai_label}", callback_data="settings:ai")],
            [InlineKeyboardButton(f"☀️ Səhər xülasəsi: {morning_label}", callback_data="settings:morning")],
        ]
    )


def _cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("❌ Ləğv et", callback_data="settings:cancel")]]
    )


async def setting_action(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    if update.callback_query is None or update.callback_query.data is None:
        return ConversationHandler.END
    await update.callback_query.answer()
    action = update.callback_query.data.split(":", maxsplit=1)[1]
    if action == "cancel":
        await update.callback_query.edit_message_text("Ayar dəyişikliyi ləğv edildi.")
        return ConversationHandler.END
    if action == "morning":
        telegram_user = update.effective_user
        if telegram_user is None:
            return ConversationHandler.END
        database = _database(context)
        async for session in database.session():
            user = (
                await session.execute(
                    select(User).where(User.telegram_user_id == telegram_user.id)
                )
            ).scalar_one()
            user.morning_summary_enabled = not user.morning_summary_enabled
            await session.commit()
            morning_label = "Açıq" if user.morning_summary_enabled else "Bağlı"
            ai_label = "Açıq" if user.ai_enabled else "Bağlı"
        await update.callback_query.edit_message_text(
            f"☀️ Səhər xülasəsi indi {morning_label}.",
            reply_markup=_settings_keyboard(ai_label, morning_label),
        )
        return ConversationHandler.END
    if action == "budget":
        await update.callback_query.edit_message_text(
            "💰 Yeni cari büdcəni yaz.", reply_markup=_cancel_keyboard()
        )
        return SETTINGS_BUDGET
    if action == "reminder":
        await update.callback_query.edit_message_text(
            "⏰ Yeni reminder saatını HH:MM formatında yaz.\n\nMəsələn: 22:30",
            reply_markup=_cancel_keyboard(),
        )
        return SETTINGS_REMINDER

    telegram_user = update.effective_user
    if telegram_user is None:
        return ConversationHandler.END
    database = _database(context)
    async for session in database.session():
        user = (
            await session.execute(
                select(User).where(User.telegram_user_id == telegram_user.id)
            )
        ).scalar_one()
        user.ai_enabled = not user.ai_enabled
        await session.commit()
        state = "aktivdir" if user.ai_enabled else "deaktivdir"
        ai_label = "Açıq" if user.ai_enabled else "Bağlı"
    await update.callback_query.edit_message_text(
        f"🤖 AI şərhləri indi {state}.",
        reply_markup=_settings_keyboard(ai_label, "Açıq" if user.morning_summary_enabled else "Bağlı"),
    )
    return ConversationHandler.END


async def setting_budget(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    if update.message is None or update.message.text is None:
        return SETTINGS_BUDGET
    amount_cents = parse_amount(update.message.text)
    if amount_cents is None or amount_cents <= 0:
        await update.message.reply_text("Müsbət məbləğ yaz 🙂")
        return SETTINGS_BUDGET
    telegram_user = update.effective_user
    if telegram_user is None:
        return ConversationHandler.END
    database = _database(context)
    async for session in database.session():
        user = (
            await session.execute(
                select(User).where(User.telegram_user_id == telegram_user.id)
            )
        ).scalar_one()
        cycle = (
            await session.execute(
                select(BudgetCycle)
                .where(
                    BudgetCycle.user_id == user.id,
                    BudgetCycle.status == "active",
                    BudgetCycle.start_date <= date.today(),
                    BudgetCycle.end_date >= date.today(),
                )
                .order_by(BudgetCycle.created_at.desc())
            )
        ).scalars().first()
        if cycle is None:
            await update.message.reply_text("Aktiv büdcə dövrü tapılmadı.")
            return ConversationHandler.END
        old_amount = cycle.budget_amount_cents
        cycle.budget_amount_cents = amount_cents
        session.add(
            BudgetChange(
                cycle_id=cycle.id,
                old_amount_cents=old_amount,
                new_amount_cents=amount_cents,
            )
        )
        await session.commit()
    await update.message.reply_text(
        f"✅ Büdcə **{format_amount(old_amount)} AZN → {format_amount(amount_cents)} AZN** oldu.",
        parse_mode="Markdown",
    )
    return ConversationHandler.END


async def setting_reminder(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    if update.message is None or update.message.text is None:
        return SETTINGS_REMINDER
    value = update.message.text.strip()
    parts = value.split(":")
    try:
        hour, minute = int(parts[0]), int(parts[1])
    except (ValueError, IndexError):
        hour, minute = -1, -1
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        await update.message.reply_text("Vaxtı HH:MM formatında yaz 🙂")
        return SETTINGS_REMINDER
    telegram_user = update.effective_user
    if telegram_user is None:
        return ConversationHandler.END
    database = _database(context)
    async for session in database.session():
        user = (
            await session.execute(
                select(User).where(User.telegram_user_id == telegram_user.id)
            )
        ).scalar_one()
        user.reminder_time = f"{hour:02d}:{minute:02d}"
        await session.commit()
    await update.message.reply_text(
        f"✅ Reminder saatı **{hour:02d}:{minute:02d}** olaraq təyin edildi.",
        parse_mode="Markdown",
    )
    return ConversationHandler.END


async def cancel_settings(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    context.user_data.clear()
    if update.message is not None:
        await update.message.reply_text(
            "Ayar dəyişikliyi ləğv edildi. İndi əsas menyudan seçim edə bilərsən."
        )
    return ConversationHandler.END