from io import BytesIO

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt

from database.models import BudgetCycle, ExpenseDay
from services.weekly_service import week_segments


def weekly_chart(cycle: BudgetCycle, expenses: list[ExpenseDay]) -> BytesIO:
    segments = week_segments(cycle)
    actuals = [
        sum(
            expense.amount_cents or 0
            for expense in expenses
            if segment.start_date <= expense.date <= segment.end_date
            and expense.status == "recorded"
        )
        / 100
        for segment in segments
    ]
    targets = [segment.target_cents / 100 for segment in segments]
    labels = [f"{segment.number}-ci həftə" for segment in segments]

    figure, axis = plt.subplots(figsize=(8.5, 5), facecolor="#0f172a")
    axis.set_facecolor("#0f172a")
    positions = list(range(len(labels)))
    width = 0.52
    axis.bar(
        positions,
        targets,
        width,
        color="#334155",
        edgecolor="#64748b",
        linewidth=1,
        label="Hədəf",
    )
    axis.bar(
        positions,
        actuals,
        width * 0.62,
        color="#2dd4bf",
        edgecolor="#99f6e4",
        linewidth=1,
        label="Xərc",
        zorder=3,
    )
    axis.set_ylabel("AZN", color="#cbd5e1")
    axis.set_xticks(positions, labels)
    axis.set_title(
        "Bu cycle-da xərcləmə tempin",
        color="#f8fafc",
        fontsize=16,
        loc="left",
        pad=20,
        fontweight="bold",
    )
    axis.tick_params(axis="x", colors="#cbd5e1")
    axis.tick_params(axis="y", colors="#94a3b8")
    axis.grid(axis="y", color="#334155", alpha=0.55, linewidth=0.8)
    axis.set_axisbelow(True)
    for spine in axis.spines.values():
        spine.set_visible(False)
    axis.legend(
        facecolor="#1e293b",
        edgecolor="#475569",
        labelcolor="#f8fafc",
        framealpha=1,
        loc="upper right",
    )
    total_spent = sum(actuals)
    total_budget = cycle.budget_amount_cents / 100
    progress = total_spent / total_budget * 100 if total_budget else 0
    figure.text(
        0.125,
        0.92,
        f"{total_spent:.2f} AZN xərclənib  ·  büdcənin {progress:.1f}%-i",
        color="#94a3b8",
        fontsize=10,
    )
    figure.tight_layout(rect=(0, 0, 1, 0.9))
    return _as_png(figure)


def daily_chart(cycle: BudgetCycle, expenses: list[ExpenseDay]) -> BytesIO:
    by_date = {
        expense.date: (expense.amount_cents or 0) / 100
        for expense in expenses
        if expense.status == "recorded"
    }
    days = []
    values = []
    current = cycle.start_date
    while current <= cycle.end_date:
        days.append(current.strftime("%d.%m"))
        values.append(by_date.get(current, 0))
        current = current.fromordinal(current.toordinal() + 1)

    figure, axis = plt.subplots(figsize=(10, 4.8), facecolor="#0f172a")
    axis.set_facecolor("#0f172a")
    axis.plot(days, values, color="#2dd4bf", linewidth=2.5, marker="o", markersize=5)
    axis.fill_between(range(len(values)), values, color="#2dd4bf", alpha=0.14)
    axis.set_ylabel("AZN", color="#cbd5e1")
    axis.set_title(
        "Gün-gün xərcləmə ritmin",
        color="#f8fafc",
        fontsize=16,
        loc="left",
        pad=20,
        fontweight="bold",
    )
    axis.tick_params(axis="x", colors="#cbd5e1", rotation=45)
    axis.tick_params(axis="y", colors="#94a3b8")
    axis.grid(axis="y", color="#334155", alpha=0.55, linewidth=0.8)
    axis.set_axisbelow(True)
    for spine in axis.spines.values():
        spine.set_visible(False)
    figure.tight_layout()
    return _as_png(figure)


def _as_png(figure) -> BytesIO:
    image = BytesIO()
    figure.savefig(image, format="png", dpi=140)
    plt.close(figure)
    image.seek(0)
    return image