from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_user_id: Mapped[int] = mapped_column(
        BigInteger, unique=True, index=True
    )
    first_name: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    reminder_time: Mapped[str] = mapped_column(
        String(5), default="23:00", server_default="23:00"
    )
    timezone: Mapped[str] = mapped_column(
        String(64), default="Asia/Baku", server_default="Asia/Baku"
    )
    ai_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="1"
    )
    morning_summary_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="0"
    )
    budget_start_day: Mapped[int | None] = mapped_column(Integer, nullable=True)
    onboarding_completed: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="0"
    )


class BudgetCycle(Base):
    __tablename__ = "budget_cycles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    budget_amount_cents: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    status: Mapped[str] = mapped_column(
        String(16), default="active", server_default="active"
    )


class BudgetChange(Base):
    __tablename__ = "budget_changes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cycle_id: Mapped[int] = mapped_column(Integer, index=True)
    old_amount_cents: Mapped[int] = mapped_column(Integer)
    new_amount_cents: Mapped[int] = mapped_column(Integer)
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ExpenseDay(Base):
    __tablename__ = "expense_days"
    __table_args__ = (UniqueConstraint("user_id", "date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    cycle_id: Mapped[int] = mapped_column(Integer, index=True)
    date: Mapped[date] = mapped_column(Date)
    amount_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Reminder(Base):
    __tablename__ = "reminders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    target_date: Mapped[date] = mapped_column(Date)
    reminder_type: Mapped[str] = mapped_column(String(16))
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(16), default="pending", server_default="pending"
    )


class ThresholdEvent(Base):
    __tablename__ = "threshold_events"
    __table_args__ = (
        UniqueConstraint("user_id", "cycle_id", "week_number", "threshold"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    cycle_id: Mapped[int] = mapped_column(Integer, index=True)
    week_number: Mapped[int] = mapped_column(Integer)
    threshold: Mapped[int] = mapped_column(Integer)
    triggered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )