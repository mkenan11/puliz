from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


def parse_amount(value: str) -> int | None:
    normalized = value.strip().upper().replace("AZN", "").strip()
    normalized = normalized.replace(",", ".")
    try:
        amount = Decimal(normalized)
    except InvalidOperation:
        return None

    if amount < 0:
        return None
    cents = (amount * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return int(cents)


def format_amount(cents: int) -> str:
    return f"{Decimal(cents) / 100:.2f}"