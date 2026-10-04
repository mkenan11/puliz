from datetime import date

from sqlalchemy import select
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from database.db import Database
from database.models import BudgetCycle, ExpenseDay, User
from services.cycle_service import cycle_expenses, current_cycle
from services.chart_service import daily_chart, weekly_chart
from services.ai_service import generate_commentary
from services.weekly_service import _spent, week_segments
from utils.money import format_amount


def _database(context: ContextTypes.DEFAULT_TYPE) -> Database:
    return context.application.bot_data["database"]


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None or update.effective_user is None:
        return
    database = _database(context)
    async for session in database.session():
        user = (
            await session.execute(
                select(User).where(
                    User.telegram_user_id == update.effective_user.id
                )
            )
        ).scalar_one_or_none()
        cycle = await current_cycle(session, user.id) if user else None
        if user is None or cycle is None:
            await update.message.reply_text("Əvvəlcə onboarding-i tamamla 🙂")
            return
        expenses = await cycle_expenses(session, user.id, cycle.id)
        spent_cents = sum(
            expense.amount_cents or 0
            for expense in expenses
            if expense.status == "recorded"
        )
        segments = week_segments(cycle)
        current_segment = next(
            (
                segment
                for segment in segments
                if segment.start_date <= date.today() <= segment.end_date
            ),
            segments[-1],
        )
        weekly_spent = await _spent(session, user.id, cycle.id, current_segment)

    remaining_cents = cycle.budget_amount_cents - spent_cents
    remaining_days = max((cycle.end_date - date.today()).days + 1, 0)
    remaining_daily = remaining_cents / remaining_days if remaining_days else 0
    await update.message.reply_text(
        "📊 **Bu cycle-da vəziyyətin**\n\n"
        f"💰 Büdcə: **{format_amount(cycle.budget_amount_cents)} AZN**\n"
        f"💸 İndiyə qədər: **{format_amount(spent_cents)} AZN**\n"
        f"🟢 Qalıb: **{format_amount(remaining_cents)} AZN**\n\n"
        f"**Bu həftə**\n"
        f"Target: **{format_amount(current_segment.target_cents)} AZN**\n"
        f"Xərc: **{format_amount(weekly_spent)} AZN**\n\n"
        f"📅 Cycle-ın bitməsinə: **{remaining_days} gün**\n"
        f"📉 Qalan günlər üçün gündəlik orta: **{remaining_daily / 100:.2f} AZN**",
        reply_markup=InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("📈 Qrafik", callback_data="status:chart")],
                [InlineKeyboardButton("🤖 AI şərhi", callback_data="status:ai")],
            ]
        ),
        parse_mode="Markdown",
    )


async def history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None or update.effective_user is None:
        return
    database = _database(context)
    async for session in database.session():
        user = (
            await session.execute(
                select(User).where(
                    User.telegram_user_id == update.effective_user.id
                )
            )
        ).scalar_one_or_none()
        if user is None:
            await update.message.reply_text("Əvvəlcə /start yaz 🙂")
            return
        cycles = (
            await session.execute(
                select(BudgetCycle)
                .where(BudgetCycle.user_id == user.id)
                .order_by(BudgetCycle.start_date.desc())
            )
        ).scalars().all()
    if not cycles:
        await update.message.reply_text("Hələ tarixçə yoxdur.")
        return
    keyboard = [
        [
            InlineKeyboardButton(
                f"{cycle.start_date:%d.%m.%Y} – {cycle.end_date:%d.%m.%Y}",
                callback_data=f"cycle:{cycle.id}",
            )
        ]
        for cycle in cycles
    ]
    await update.message.reply_text(
        "📅 **Tarixçə**\n\nBir büdcə dövrü seç:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown",
    )


async def cycle_detail(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.callback_query is None or update.callback_query.data is None:
        return
    await update.callback_query.answer()
    cycle_id = int(update.callback_query.data.split(":", maxsplit=1)[1])
    database = _database(context)
    async for session in database.session():
        user = await _user(session, update)
        cycle = (
            await session.execute(
                select(BudgetCycle).where(
                    BudgetCycle.id == cycle_id,
                    BudgetCycle.user_id == user.id,
                )
            )
        ).scalar_one()
        expenses = await cycle_expenses(session, user.id, cycle.id)
    spent_cents = sum(
        expense.amount_cents or 0
        for expense in expenses
        if expense.status == "recorded"
    )
    segments = week_segments(cycle)
    keyboard = [
        [
            InlineKeyboardButton(
                f"{segment.number}-ci həftə · {segment.start_date:%d.%m}–{segment.end_date:%d.%m}",
                callback_data=f"week:{cycle.id}:{segment.number}",
            )
        ]
        for segment in segments
    ]
    keyboard.append(
        [InlineKeyboardButton("📈 Qrafik", callback_data=f"cycle_chart:{cycle.id}")]
    )
    keyboard.append(
        [InlineKeyboardButton("📉 Gündəlik qrafik", callback_data=f"cycle_daily_chart:{cycle.id}")]
    )
    await update.callback_query.edit_message_text(
        f"📅 **{cycle.start_date:%d.%m.%Y} – {cycle.end_date:%d.%m.%Y}**\n\n"
        f"Büdcə: **{format_amount(cycle.budget_amount_cents)} AZN**\n"
        f"Xərc: **{format_amount(spent_cents)} AZN**\n"
        f"Qalıb: **{format_amount(cycle.budget_amount_cents - spent_cents)} AZN**",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown",
    )


async def week_detail(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.callback_query is None or update.callback_query.data is None:
        return
    await update.callback_query.answer()
    _, cycle_id_text, week_number_text = update.callback_query.data.split(":")
    cycle_id, week_number = int(cycle_id_text), int(week_number_text)
    database = _database(context)
    async for session in database.session():
        user = await _user(session, update)
        cycle = (
            await session.execute(
                select(BudgetCycle).where(
                    BudgetCycle.id == cycle_id, BudgetCycle.user_id == user.id
                )
            )
        ).scalar_one()
        expenses = await cycle_expenses(session, user.id, cycle.id)
    segment = week_segments(cycle)[week_number - 1]
    by_date = {expense.date: expense for expense in expenses}
    lines = [f"📊 **{week_number}-ci həftə**", ""]
    current = segment.start_date
    while current <= segment.end_date:
        expense = by_date.get(current)
        if expense is None:
            value = "məlumat yoxdur"
        else:
            value = f"{format_amount(expense.amount_cents or 0)} AZN"
        lines.append(f"{current:%d.%m.%Y} — {value}")
        current = date.fromordinal(current.toordinal() + 1)
    spent_cents = sum(
        expense.amount_cents or 0
        for expense in expenses
        if segment.start_date <= expense.date <= segment.end_date
        and expense.status == "recorded"
    )
    lines.append("")
    lines.append(f"Cəmi: **{format_amount(spent_cents)} AZN**")
    await update.callback_query.edit_message_text(
        "\n".join(lines), parse_mode="Markdown"
    )


async def status_placeholder(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.callback_query is None:
        return
    await update.callback_query.answer()
    await update.callback_query.edit_message_text(
        "Bu funksiya növbəti mərhələdə aktiv ediləcək."
    )


async def status_ai(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.callback_query is None or update.effective_user is None:
        return
    await update.callback_query.answer()
    database = _database(context)
    async for session in database.session():
        user = await _user(session, update)
        cycle = await current_cycle(session, user.id)
        if cycle is None:
            return
        expenses = await cycle_expenses(session, user.id, cycle.id)
        recorded = [expense for expense in expenses if expense.status == "recorded"]
        spent_cents = sum(expense.amount_cents or 0 for expense in recorded)
        segments = week_segments(cycle)
        weekly_spent = [
            await _spent(session, user.id, cycle.id, segment)
            for segment in segments
        ]
    settings = context.application.bot_data["settings"]
    text = await generate_commentary(
        enabled=settings.ai_enabled,
        api_key=settings.gemini_api_key,
        budget_cents=cycle.budget_amount_cents,
        spent_cents=spent_cents,
        remaining_cents=cycle.budget_amount_cents - spent_cents,
        average_daily_cents=spent_cents / len(recorded) if recorded else 0,
        tracked_days=len(recorded),
        total_days=(cycle.end_date - cycle.start_date).days + 1,
        highest_week_cents=max(weekly_spent, default=0),
        lowest_week_cents=min(weekly_spent, default=0),
    )
    await update.callback_query.message.reply_text(f"🤖 {text}")


async def status_chart(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.callback_query is None or update.effective_user is None:
        return
    await update.callback_query.answer()
    database = _database(context)
    async for session in database.session():
        user = await _user(session, update)
        cycle = await current_cycle(session, user.id)
        if cycle is None:
            return
        expenses = await cycle_expenses(session, user.id, cycle.id)
    await update.callback_query.message.reply_photo(
        photo=weekly_chart(cycle, expenses),
        caption="📈 Həftəlik target və faktiki xərc",
    )


async def cycle_chart(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.callback_query is None or update.effective_user is None:
        return
    await update.callback_query.answer()
    cycle_id = int(update.callback_query.data.split(":", maxsplit=1)[1])
    database = _database(context)
    async for session in database.session():
        user = await _user(session, update)
        cycle = (
            await session.execute(
                select(BudgetCycle).where(
                    BudgetCycle.id == cycle_id, BudgetCycle.user_id == user.id
                )
            )
        ).scalar_one()
        expenses = await cycle_expenses(session, user.id, cycle.id)
    await update.callback_query.message.reply_photo(
        photo=weekly_chart(cycle, expenses),
        caption="📈 Büdcə dövrü üzrə həftəlik qrafik",
    )


async def cycle_daily_chart(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.callback_query is None or update.effective_user is None:
        return
    await update.callback_query.answer()
    cycle_id = int(update.callback_query.data.split(":", maxsplit=1)[1])
    database = _database(context)
    async for session in database.session():
        user = await _user(session, update)
        cycle = (
            await session.execute(
                select(BudgetCycle).where(
                    BudgetCycle.id == cycle_id, BudgetCycle.user_id == user.id
                )
            )
        ).scalar_one()
        expenses = await cycle_expenses(session, user.id, cycle.id)
    await update.callback_query.message.reply_photo(
        photo=daily_chart(cycle, expenses),
        caption="📉 Büdcə dövrü üzrə gündəlik qrafik",
    )
    await update.callback_query.message.reply_photo(
        photo=daily_chart(cycle, expenses),
        caption="📈 Büdcə dövrü üzrə gündəlik qrafik",
    )


async def _user(session, update: Update):
    return (
        await session.execute(
            select(User).where(User.telegram_user_id == update.effective_user.id)
        )
    ).scalar_one()