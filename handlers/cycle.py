from telegram import Update
from telegram.ext import ContextTypes


async def cycle_keep_budget(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.callback_query is None:
        return
    await update.callback_query.answer()
    await update.callback_query.edit_message_text(
        "✅ Bu cycle üçün əvvəlki büdcəni saxladıq. Uğurlu olsun!"
    )


async def cycle_later(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.callback_query is None:
        return
    await update.callback_query.answer()
    await update.callback_query.edit_message_text(
        "⏰ Oldu, büdcəni sonra dəyişə bilərsən."
    )