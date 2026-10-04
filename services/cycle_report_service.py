from datetime import date, datetime

from sqlalchemy import select
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application

from database.models import BudgetCycle, ExpenseDay, Reminder, User
from services.weekly_service import _spent, week_segments
from services.ai_service import generate_commentary
from utils.dates import cycle_dates
from utils.money import format_amount


async def process_cycle_reports(application: Application) -> None:
    database = application.bot_data["database"]
    async for session in database.session():
        cycles = (
            await session.execute(
                select(BudgetCycle).where(
                    BudgetCycle.status == "active",
                    BudgetCycle.end_date < date.today(),
                )
            )
        ).scalars().all()
        for cycle in cycles:
            await _send_cycle_report(application, session, cycle)
        await session.commit()


async def _send_cycle_report(application, session, cycle: BudgetCycle) -> None:
    user = (
        await session.execute(select(User).where(User.id == cycle.user_id))
    ).scalar_one()
    existing = (
        await session.execute(
            select(Reminder).where(
                Reminder.user_id == user.id,
                Reminder.target_date == cycle.end_date,
                Reminder.reminder_type == "cycle_report",
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        cycle.status = "closed"
        return

    expenses = (
        await session.execute(
            select(ExpenseDay).where(
                ExpenseDay.user_id == user.id,
                ExpenseDay.cycle_id == cycle.id,
            )
        )
    ).scalars().all()
    recorded = [expense for expense in expenses if expense.status == "recorded"]
    spent_cents = sum(expense.amount_cents or 0 for expense in recorded)
    total_days = (cycle.end_date - cycle.start_date).days + 1
    missing_days = total_days - len(recorded)
    segments = week_segments(cycle)
    weekly_spent = [await _spent(session, user.id, cycle.id, segment) for segment in segments]
    highest_index = max(range(len(weekly_spent)), key=weekly_spent.__getitem__)
    lowest_index = min(range(len(weekly_spent)), key=weekly_spent.__getitem__)

    previous = (
        await session.execute(
            select(BudgetCycle)
            .where(
                BudgetCycle.user_id == user.id,
                BudgetCycle.end_date < cycle.start_date,
            )
            .order_by(BudgetCycle.end_date.desc())
        )
    ).scalars().first()
    comparison = ""
    if previous is not None:
        previous_spent = (
            await session.execute(
                select(ExpenseDay).where(
                    ExpenseDay.user_id == user.id,
                    ExpenseDay.cycle_id == previous.id,
                    ExpenseDay.status == "recorded",
                )
            )
        ).scalars().all()
        previous_total = sum(expense.amount_cents or 0 for expense in previous_spent)
        difference = spent_cents - previous_total
        direction = "çox" if difference > 0 else "az"
        comparison = (
            f"\nKeçən cycle ilə müqayisədə "
            f"{format_amount(abs(difference))} AZN daha {direction} xərcləmisən."
        )

    await application.bot.send_message(
        chat_id=user.telegram_user_id,
        text=(
            f"📊 **Bu cycle belə keçdi**\n\n"
            f"Büdcə: **{format_amount(cycle.budget_amount_cents)} AZN**\n"
            f"Xərc: **{format_amount(spent_cents)} AZN**\n"
            f"Qalıb: **{format_amount(cycle.budget_amount_cents - spent_cents)} AZN**\n\n"
            f"📈 Ən çox xərc: **{highest_index + 1}-ci həftə — {format_amount(weekly_spent[highest_index])} AZN**\n"
            f"📉 Ən az xərc: **{lowest_index + 1}-ci həftə — {format_amount(weekly_spent[lowest_index])} AZN**\n"
            f"📝 Qeyd etdiyin günlər: **{len(recorded)} / {total_days}**\n"
            f"⚠️ Boş qalan günlər: **{missing_days}**"
            f"{comparison}"
        ),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "🔁 Eyni büdcəni saxla", callback_data="cycle_budget:keep"
                    )
                ],
                [
                    InlineKeyboardButton(
                        "✏️ Yeni məbləğ", callback_data="settings:budget"
                    ),
                    InlineKeyboardButton(
                        "⏰ Sonra", callback_data="cycle_budget:later"
                    ),
                ],
            ]
        ),
    )
    settings = application.bot_data["settings"]
    if user.ai_enabled:
        commentary = await generate_commentary(
            enabled=settings.ai_enabled,
            api_key=settings.gemini_api_key,
            budget_cents=cycle.budget_amount_cents,
            spent_cents=spent_cents,
            remaining_cents=cycle.budget_amount_cents - spent_cents,
            average_daily_cents=spent_cents / len(recorded) if recorded else 0,
            tracked_days=len(recorded),
            total_days=total_days,
            highest_week_cents=weekly_spent[highest_index],
            lowest_week_cents=weekly_spent[lowest_index],
        )
        await application.bot.send_message(
            chat_id=user.telegram_user_id,
            text=f"🤖 {commentary}",
        )
    cycle.status = "closed"
    await _create_next_cycle(application, session, user, cycle)
    session.add(
        Reminder(
            user_id=user.id,
            target_date=cycle.end_date,
            reminder_type="cycle_report",
            scheduled_at=datetime.utcnow(),
            sent_at=datetime.utcnow(),
            status="sent",
        )
    )


async def _create_next_cycle(application, session, user: User, cycle: BudgetCycle) -> None:
    if user.budget_start_day is None:
        return
    next_start, next_end = cycle_dates(
        user.budget_start_day,
        today=cycle.end_date.fromordinal(cycle.end_date.toordinal() + 1),
    )
    existing = (
        await session.execute(
            select(BudgetCycle).where(
                BudgetCycle.user_id == user.id,
                BudgetCycle.start_date == next_start,
                BudgetCycle.end_date == next_end,
            )
        )
    ).scalars().first()
    if existing is not None:
        return
    next_cycle = BudgetCycle(
        user_id=user.id,
        start_date=next_start,
        end_date=next_end,
        budget_amount_cents=cycle.budget_amount_cents,
        status="active",
    )
    session.add(next_cycle)
    await application.bot.send_message(
        chat_id=user.telegram_user_id,
        text=(
            "🌱 Yeni büdcə cycle-ın başladı!\n\n"
            f"Keçən cycle-da büdcən **{format_amount(cycle.budget_amount_cents)} AZN** idi.\n"
            "İndilik eyni məbləği saxladım. İstəsən, bunu Ayarlar bölməsindən dəyişə bilərsən."
        ),
        parse_mode="Markdown",
    )