from datetime import date, datetime, timedelta

from sqlalchemy import select
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes, ConversationHandler

from database.db import Database
from database.models import BudgetCycle, ExpenseDay, User
from services.cycle_service import cycle_for_expense_date
from utils.money import format_amount, parse_amount


SELECT_DATE, CUSTOM_DATE, AMOUNT, EXISTING = range(4)


def _database(context: ContextTypes.DEFAULT_TYPE) -> Database:
    return context.application.bot_data["database"]


def _date_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Bu gün", callback_data="expense_date:today"),
                InlineKeyboardButton("Dünən", callback_data="expense_date:yesterday"),
            ],
            [
                InlineKeyboardButton(
                    "📅 Başqa tarix", callback_data="expense_date:custom"
                )
            ],
        ]
    )


async def begin_expense(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    if update.message is None:
        return ConversationHandler.END
    await update.message.reply_text(
        "💸 Hansı günün xərcini qeyd etmək istəyirsən?",
        reply_markup=_date_keyboard(),
    )
    return SELECT_DATE


async def select_date(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    if update.callback_query is None or update.callback_query.data is None:
        return SELECT_DATE

    await update.callback_query.answer()
    value = update.callback_query.data.split(":", maxsplit=1)[1]
    if value == "custom":
        await update.callback_query.edit_message_text(
            "📅 Tarixi GG.AA.İİİİ formatında yaz.\n\nMəsələn: 25.09.2026"
        )
        return CUSTOM_DATE

    target_date = date.today()
    if value == "yesterday":
        target_date = date.today() - timedelta(days=1)
    return await _prepare_expense(update, context, target_date)


async def custom_date(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    if update.message is None or update.message.text is None:
        return CUSTOM_DATE
    try:
        target_date = datetime.strptime(update.message.text.strip(), "%d.%m.%Y").date()
    except ValueError:
        await update.message.reply_text(
            "Tarixi GG.AA.İİİİ formatında yaz 🙂\n\nMəsələn: 25.09.2026"
        )
        return CUSTOM_DATE

    return await _prepare_expense(update, context, target_date)


async def _prepare_expense(
    update: Update, context: ContextTypes.DEFAULT_TYPE, target_date: date
) -> int:
    if target_date > date.today():
        await _reply(update, "Gələcək tarix üçün xərc qeyd etmək mümkün deyil. 🙂")
        return ConversationHandler.END

    telegram_user = update.effective_user
    if telegram_user is None:
        return ConversationHandler.END

    database = _database(context)
    async for session in database.session():
        user_result = await session.execute(
            select(User).where(User.telegram_user_id == telegram_user.id)
        )
        user = user_result.scalar_one_or_none()
        if user is None:
            await _reply(update, "Əvvəlcə /start ilə qeydiyyatdan keç 🙂")
            return ConversationHandler.END

        cycle = await cycle_for_expense_date(session, user, target_date)
        if cycle is None:
            await _reply(update, "Bu tarix üçün aktiv büdcə dövrü tapılmadı.")
            return ConversationHandler.END

        expense_result = await session.execute(
            select(ExpenseDay).where(
                ExpenseDay.user_id == user.id,
                ExpenseDay.date == target_date,
            )
        )
        expense = expense_result.scalar_one_or_none()

    context.user_data["expense_date"] = target_date
    if expense is not None and expense.status == "recorded":
        context.user_data["expense_existing_cents"] = expense.amount_cents
        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("✏️ Dəyiş", callback_data="expense:edit"),
                    InlineKeyboardButton("🗑 Sil", callback_data="expense:delete"),
                ],
                [InlineKeyboardButton("⬅️ Geri", callback_data="expense:back")],
            ]
        )
        await _reply(
            update,
            f"{target_date:%d.%m.%Y} üçün hazırda **{format_amount(expense.amount_cents or 0)} AZN** qeyd edilib.",
            keyboard,
        )
        return EXISTING

    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton("✅ Bu gün xərc olmadı", callback_data="expense:zero")]]
    )
    await _reply(
        update,
        f"💸 {target_date:%d.%m.%Y} üçün ümumi xərci yaz.",
        keyboard,
    )
    return AMOUNT


async def expense_amount(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    if update.message is None or update.message.text is None:
        return AMOUNT
    amount_cents = parse_amount(update.message.text)
    if amount_cents is None:
        await update.message.reply_text("Məbləği rəqəmlə yaz 🙂\n\nMəsələn: 8.50")
        return AMOUNT
    return await _save_expense(update, context, amount_cents)


async def expense_action(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    if update.callback_query is None or update.callback_query.data is None:
        return EXISTING
    await update.callback_query.answer()
    action = update.callback_query.data.split(":", maxsplit=1)[1]
    if action == "back":
        await update.callback_query.edit_message_text("Xərc qeydiyyatı ləğv edildi.")
        return ConversationHandler.END
    if action == "edit":
        await update.callback_query.edit_message_text("Yeni məbləği yaz.")
        return AMOUNT
    if action == "zero":
        return await _save_expense(update, context, 0)
    if action == "delete":
        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("Bəli, sil", callback_data="expense:confirm_delete"),
                    InlineKeyboardButton("Xeyr", callback_data="expense:back"),
                ]
            ]
        )
        await update.callback_query.edit_message_text(
            "Bu xərc qeydini silmək istəyirsən?", reply_markup=keyboard
        )
        return EXISTING
    if action == "confirm_delete":
        return await _delete_expense(update, context)
    return EXISTING


async def _save_expense(
    update: Update, context: ContextTypes.DEFAULT_TYPE, amount_cents: int
) -> int:
    telegram_user = update.effective_user
    target_date = context.user_data.get("expense_date")
    if telegram_user is None or not isinstance(target_date, date):
        return ConversationHandler.END

    database = _database(context)
    async for session in database.session():
        user_result = await session.execute(
            select(User).where(User.telegram_user_id == telegram_user.id)
        )
        user = user_result.scalar_one()
        cycle = await cycle_for_expense_date(session, user, target_date)
        if cycle is None:
            await _reply(update, "Bu tarix üçün aktiv büdcə dövrü tapılmadı.")
            return ConversationHandler.END
        expense_result = await session.execute(
            select(ExpenseDay).where(
                ExpenseDay.user_id == user.id, ExpenseDay.date == target_date
            )
        )
        expense = expense_result.scalar_one_or_none()
        if expense is None:
            expense = ExpenseDay(
                user_id=user.id,
                cycle_id=cycle.id,
                date=target_date,
                amount_cents=amount_cents,
                status="recorded",
            )
            session.add(expense)
        else:
            expense.amount_cents = amount_cents
            expense.status = "recorded"
        await session.commit()

    await _reply(
        update,
        f"✅ **{format_amount(amount_cents)} AZN** qeyd edildi.",
    )
    context.user_data.clear()
    return ConversationHandler.END


async def _delete_expense(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    telegram_user = update.effective_user
    target_date = context.user_data.get("expense_date")
    if telegram_user is None or not isinstance(target_date, date):
        return ConversationHandler.END
    database = _database(context)
    async for session in database.session():
        result = await session.execute(
            select(User).where(User.telegram_user_id == telegram_user.id)
        )
        user = result.scalar_one()
        expense_result = await session.execute(
            select(ExpenseDay).where(
                ExpenseDay.user_id == user.id, ExpenseDay.date == target_date
            )
        )
        expense = expense_result.scalar_one_or_none()
        if expense is not None:
            await session.delete(expense)
            await session.commit()
    await _reply(update, "✅ Xərc qeydi silindi.")
    context.user_data.clear()
    return ConversationHandler.END


async def _reply(
    update: Update,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    if update.callback_query is not None:
        await update.callback_query.edit_message_text(
            text, reply_markup=reply_markup, parse_mode="Markdown"
        )
    elif update.message is not None:
        await update.message.reply_text(
            text, reply_markup=reply_markup, parse_mode="Markdown"
        )