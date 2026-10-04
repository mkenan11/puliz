import asyncio
import logging

from telegram import BotCommand
from telegram.error import NetworkError
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    filters,
)

from config import load_settings
from database.db import Database
from handlers.onboarding import (
    BUDGET,
    CUSTOM_START_DAY,
    REMINDER_TIME,
    START_DAY,
    begin_onboarding,
    budget_amount,
    custom_reminder_time,
    custom_start_day,
    reminder_time,
    start_day,
)
from handlers.expense import (
    AMOUNT,
    CUSTOM_DATE,
    EXISTING,
    SELECT_DATE,
    begin_expense,
    custom_date,
    expense_action,
    expense_amount,
    select_date,
)
from handlers.reminder import (
    handle_reminder_amount,
    missing_action,
    reminder_snooze,
    reminder_snooze_menu,
    reminder_zero,
)
from handlers.account import cancel, delete_confirmation, delete_me, export_data, help_command
from handlers.cycle import cycle_keep_budget, cycle_later
from handlers.status import (
    cycle_chart,
    cycle_daily_chart,
    cycle_detail,
    history,
    status,
    status_ai,
    status_chart,
    status_placeholder,
    week_detail,
)
from handlers.settings import (
    SETTINGS_BUDGET,
    SETTINGS_REMINDER,
    cancel_settings,
    setting_action,
    setting_budget,
    setting_reminder,
    settings_menu,
)
from keyboards.main_menu import main_menu_keyboard
from handlers.start import start
from scheduler.scheduler import reminder_loop


logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.WARNING)


def build_application() -> tuple[Application, Database]:
    settings = load_settings()
    database = Database(settings.database_url)
    application = Application.builder().token(settings.telegram_bot_token).build()
    application.bot_data["database"] = database
    application.bot_data["settings"] = settings
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("export", export_data))
    application.add_handler(CommandHandler("delete_me", delete_me))
    application.add_handler(CommandHandler("cancel", cancel))
    application.add_handler(CommandHandler("settings", settings_menu))
    application.add_handler(
        CallbackQueryHandler(cycle_keep_budget, pattern="^cycle_budget:keep$")
    )
    application.add_handler(
        CallbackQueryHandler(cycle_later, pattern="^cycle_budget:later$")
    )
    application.add_handler(
        ConversationHandler(
            entry_points=[
                MessageHandler(filters.Regex("^⚙️ Ayarlar$"), settings_menu),
                CallbackQueryHandler(setting_action, pattern="^settings:"),
            ],
            states={
                SETTINGS_BUDGET: [
                    CallbackQueryHandler(setting_action, pattern="^settings:cancel$"),
                    MessageHandler(
                        filters.TEXT
                        & ~filters.COMMAND
                        & ~filters.Regex("^(💸 Xərc qeyd et|📊 Vəziyyətim|📅 Tarixçə|⚙️ Ayarlar)$"),
                        setting_budget,
                    ),
                ],
                SETTINGS_REMINDER: [
                    CallbackQueryHandler(setting_action, pattern="^settings:cancel$"),
                    MessageHandler(
                        filters.TEXT
                        & ~filters.COMMAND
                        & ~filters.Regex("^(💸 Xərc qeyd et|📊 Vəziyyətim|📅 Tarixçə|⚙️ Ayarlar)$"),
                        setting_reminder,
                    ),
                ],
            },
            fallbacks=[
                CommandHandler("cancel", cancel),
                MessageHandler(
                    filters.Regex("^(💸 Xərc qeyd et|📊 Vəziyyətim|📅 Tarixçə|⚙️ Ayarlar)$"),
                    cancel_settings,
                ),
            ],
        )
    )
    application.add_handler(
        ConversationHandler(
            entry_points=[
                CallbackQueryHandler(begin_onboarding, pattern="^begin_onboarding$")
            ],
            states={
                BUDGET: [MessageHandler(filters.TEXT & ~filters.COMMAND, budget_amount)],
                START_DAY: [CallbackQueryHandler(start_day, pattern="^start_day:")],
                CUSTOM_START_DAY: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, custom_start_day)
                ],
                REMINDER_TIME: [
                    CallbackQueryHandler(reminder_time, pattern="^reminder:"),
                    MessageHandler(
                        filters.TEXT & ~filters.COMMAND, custom_reminder_time
                    ),
                ],
            },
            fallbacks=[],
        )
    )
    application.add_handler(
        CallbackQueryHandler(main_menu_placeholder, pattern="^main_menu$")
    )
    application.add_handler(CommandHandler("menu", main_menu_placeholder))
    application.add_handler(CommandHandler("status", status))
    application.add_handler(CommandHandler("history", history))
    application.add_handler(
        MessageHandler(filters.Regex("^📊 Vəziyyətim$"), status)
    )
    application.add_handler(
        MessageHandler(filters.Regex("^📅 Tarixçə$"), history)
    )
    application.add_handler(
        CallbackQueryHandler(cycle_detail, pattern="^cycle:")
    )
    application.add_handler(CallbackQueryHandler(week_detail, pattern="^week:"))
    application.add_handler(
        CallbackQueryHandler(status_chart, pattern="^status:chart$")
    )
    application.add_handler(
        CallbackQueryHandler(status_ai, pattern="^status:ai$")
    )
    application.add_handler(
        CallbackQueryHandler(status_placeholder, pattern="^status:")
    )
    application.add_handler(
        CallbackQueryHandler(cycle_chart, pattern="^cycle_chart:")
    )
    application.add_handler(
        CallbackQueryHandler(cycle_daily_chart, pattern="^cycle_daily_chart:")
    )
    application.add_handler(
        CallbackQueryHandler(delete_confirmation, pattern="^delete:")
    )
    application.add_handler(
        ConversationHandler(
            entry_points=[
                MessageHandler(filters.Regex("^💸 Xərc qeyd et$"), begin_expense)
            ],
            states={
                SELECT_DATE: [
                    CallbackQueryHandler(select_date, pattern="^expense_date:")
                ],
                CUSTOM_DATE: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, custom_date)
                ],
                AMOUNT: [
                    CallbackQueryHandler(expense_action, pattern="^expense:zero$"),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, expense_amount),
                ],
                EXISTING: [
                    CallbackQueryHandler(expense_action, pattern="^expense:")
                ],
            },
            fallbacks=[],
        )
    )
    application.add_handler(
        CallbackQueryHandler(reminder_snooze_menu, pattern="^reminder:snooze$")
    )
    application.add_handler(
        CallbackQueryHandler(reminder_zero, pattern="^reminder:zero$")
    )
    application.add_handler(
        CallbackQueryHandler(reminder_snooze, pattern="^snooze:")
    )
    application.add_handler(
        CallbackQueryHandler(missing_action, pattern="^missing:")
    )
    application.add_handler(
        MessageHandler(
            filters.Regex(r"^\s*\d+(?:[.,]\d+)?\s*(?:AZN)?\s*$"),
            handle_reminder_amount,
        )
    )
    application.add_error_handler(error_handler)
    return application, database


async def post_init(application: Application) -> None:
    database: Database = application.bot_data["database"]
    await database.create_tables()
    await application.bot.set_my_commands(
        [
            BotCommand("start", "Pulİz-i başlat"),
            BotCommand("menu", "Əsas menyunu göstər"),
            BotCommand("status", "Cari vəziyyət"),
            BotCommand("history", "Büdcə tarixçəsi"),
            BotCommand("settings", "Ayarlar"),
            BotCommand("help", "Pulİz necə işləyir?"),
            BotCommand("export", "CSV export"),
            BotCommand("delete_me", "Məlumatlarımı sil"),
            BotCommand("cancel", "Cari əməliyyatı ləğv et"),
        ]
    )
    application.bot_data["reminder_task"] = asyncio.create_task(
        reminder_loop(application)
    )


async def post_shutdown(application: Application) -> None:
    reminder_task = application.bot_data.get("reminder_task")
    if reminder_task is not None:
        reminder_task.cancel()
        await asyncio.gather(reminder_task, return_exceptions=True)
    database: Database = application.bot_data["database"]
    await database.close()


async def main_menu_placeholder(
    update: object, context: object
) -> None:
    message = getattr(update, "message", None)
    callback_query = getattr(update, "callback_query", None)
    if message is not None:
        await message.reply_text(
            "🏠 Əsas menyu", reply_markup=main_menu_keyboard()
        )
        return
    if callback_query is None:
        return
    await callback_query.answer()
    await callback_query.edit_message_text(
        "🏠 Əsas menyu", reply_markup=None
    )
    await callback_query.message.reply_text(
        "Seçim et:", reply_markup=main_menu_keyboard()
    )


async def error_handler(update: object, context: object) -> None:
    error = getattr(context, "error", None)
    if isinstance(error, NetworkError):
        logging.getLogger(__name__).warning(
            "Telegram network unavailable; polling will retry."
        )
        return
    logging.getLogger(__name__).exception("Unhandled bot error", exc_info=error)
    message = getattr(update, "effective_message", None)
    if message is not None:
        await message.reply_text(
            "Texniki problem yarandı. Bir az sonra yenidən yoxla."
        )


def main() -> None:
    application, _ = build_application()
    application.post_init = post_init
    application.post_shutdown = post_shutdown
    application.run_polling()


if __name__ == "__main__":
    main()