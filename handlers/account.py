from sqlalchemy import delete, select
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes, ConversationHandler

from database.db import Database
from database.models import (
    BudgetCycle,
    ExpenseDay,
    Reminder,
    ThresholdEvent,
    User,
)
from services.export_service import expense_csv


def _database(context: ContextTypes.DEFAULT_TYPE) -> Database:
    return context.application.bot_data["database"]


async def export_data(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None or update.effective_user is None:
        return
    database = _database(context)
    async for session in database.session():
        file = await expense_csv(session, update.effective_user.id)
    if file is None:
        await update.message.reply_text("Əvvəlcə /start yaz 🙂")
        return
    await update.message.reply_document(
        document=file, caption="📤 Xərc tarixçən burada.")


async def delete_me(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return
    await update.message.reply_text(
        "⚠️ Bu əməliyyat bütün büdcə və xərc tarixçəni həmişəlik siləcək.\n\n"
        "Davam etmək istəyirsən?",
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("🗑 Davam et", callback_data="delete:first"),
                    InlineKeyboardButton("Ləğv et", callback_data="delete:cancel"),
                ]
            ]
        ),
    )


async def delete_confirmation(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if update.callback_query is None or update.callback_query.data is None:
        return
    await update.callback_query.answer()
    action = update.callback_query.data.split(":", maxsplit=1)[1]
    if action == "cancel":
        await update.callback_query.edit_message_text("Silinmə ləğv edildi.")
        return
    if action == "first":
        await update.callback_query.edit_message_text(
            "Son təsdiq:\n\nBütün Pulİz məlumatların silinsin?",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "Bəli, həmişəlik sil", callback_data="delete:confirm"
                        ),
                        InlineKeyboardButton("Xeyr", callback_data="delete:cancel"),
                    ]
                ]
            ),
        )
        return

    telegram_user = update.effective_user
    if telegram_user is None:
        return
    database = _database(context)
    async for session in database.session():
        user = (
            await session.execute(
                select(User).where(
                    User.telegram_user_id == telegram_user.id
                )
            )
        ).scalar_one_or_none()
        if user is not None:
            await session.execute(delete(ThresholdEvent).where(ThresholdEvent.user_id == user.id))
            await session.execute(delete(Reminder).where(Reminder.user_id == user.id))
            await session.execute(delete(ExpenseDay).where(ExpenseDay.user_id == user.id))
            await session.execute(delete(BudgetCycle).where(BudgetCycle.user_id == user.id))
            await session.delete(user)
            await session.commit()
    await update.callback_query.edit_message_text(
        "✅ Bütün Pulİz məlumatların silindi. Yenidən başlamaq üçün /start yaz."
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return
    await update.message.reply_text(
        "ℹ️ Pulİz necə işləyir?\n\n"
        "Günün sonunda ümumi xərclədiyin məbləği qeyd et. Pulİz həftəlik və "
        "büdcə dövrü vəziyyətini avtomatik hesablayır.\n\n"
        "/status — cari vəziyyət\n"
        "/history — tarixçə\n"
        "/export — CSV export\n"
        "/delete_me — bütün məlumatları sil\n"
        "/cancel — cari əməliyyatı ləğv et",
    )


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    if update.message is not None:
        await update.message.reply_text("Əməliyyat ləğv edildi.")
    return ConversationHandler.END