import unittest
from datetime import date

from database.db import Database
from database.models import Base, BudgetCycle, User
from services.cycle_service import cycle_for_expense_date


class PreviousCycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_day_before_current_cycle_gets_archived_cycle(self) -> None:
        database = Database("sqlite+aiosqlite:///:memory:")
        await database.create_tables()
        async for session in database.session():
            user = User(
                telegram_user_id=123,
                first_name="Test",
                budget_start_day=29,
                onboarding_completed=True,
            )
            session.add(user)
            await session.flush()
            session.add(
                BudgetCycle(
                    user_id=user.id,
                    start_date=date(2026, 9, 29),
                    end_date=date(2026, 10, 28),
                    budget_amount_cents=24000,
                )
            )
            await session.commit()
            cycle = await cycle_for_expense_date(session, user, date(2026, 9, 28))
            self.assertEqual(cycle.status, "archived")
            self.assertEqual(cycle.start_date, date(2026, 8, 29))
            self.assertEqual(cycle.end_date, date(2026, 9, 28))
        await database.close()