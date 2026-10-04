import asyncio

from telegram.ext import Application

from services.reminder_service import send_due_reminders
from services.weekly_service import process_weekly_updates
from services.cycle_report_service import process_cycle_reports


async def reminder_loop(application: Application) -> None:
    while True:
        try:
            await send_due_reminders(application)
            await process_weekly_updates(application)
            await process_cycle_reports(application)
        except asyncio.CancelledError:
            raise
        except Exception:
            application.logger.exception("Reminder scheduler failed")
        await asyncio.sleep(60)