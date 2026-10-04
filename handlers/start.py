from sqlalchemy import select
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from database.db import Database
from database.models import User
from keyboards.main_menu import main_menu_keyboard


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user is None or update.message is None:
        return

    database: Database = context.application.bot_data["database"]
    async for session in database.session():
        result = await session.execute(
            select(User).where(
                User.telegram_user_id == update.effective_user.id
            )
        )
        user = result.scalar_one_or_none()

        if user is None:
            user = User(
                telegram_user_id=update.effective_user.id,
                first_name=update.effective_user.first_name or "dost",
            )
            session.add(user)
            await session.commit()

    if user.onboarding_completed:
        await update.message.reply_text(
            "Xoş gəldin 👋\n\nƏsas menyudan seçim et:",
            reply_markup=main_menu_keyboard(),
        )
        return

    first_name = update.effective_user.first_name or "dost"
    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton("🚀 Başlayaq", callback_data="begin_onboarding")]]
    )
    await update.message.reply_text(
        f"Salam, {first_name} 👋\n\n"
        "Mən **Pulİz**-əm.\n\n"
        "Gündəlik xərclərini qeyd etməyinə və aylıq büdcəni nəzarətdə "
        "saxlamağına kömək edəcəyəm.\n\n"
        "Səndən hər alış-verişi ayrıca yazmağını istəməyəcəyəm. "
        "Günün sonunda sadəcə ümumi nə qədər xərclədiyini deyəcəksən.\n\n"
        "Başlayaq?",
        reply_markup=keyboard,
        parse_mode="Markdown",
    )


async def begin_onboarding(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if update.callback_query is None:
        return

    await update.callback_query.answer()
    await update.callback_query.edit_message_text(
        "Onboarding növbəti mərhələdə aktiv ediləcək."
    )