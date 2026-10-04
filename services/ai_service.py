from google import genai


FALLBACK_TEMPLATE = (
    "💰 Büdcənin {percentage:.1f}%-ni istifadə etmisən.\n"
    "🟢 {remaining} AZN qalıb və {tracked}/{total} gün qeyd olunub."
)


async def generate_commentary(
    *,
    enabled: bool,
    api_key: str,
    budget_cents: int,
    spent_cents: int,
    remaining_cents: int,
    average_daily_cents: float,
    tracked_days: int,
    total_days: int,
    highest_week_cents: int,
    lowest_week_cents: int,
) -> str:
    percentage = spent_cents / budget_cents * 100 if budget_cents else 0
    fallback = FALLBACK_TEMPLATE.format(
        percentage=percentage,
        remaining=f"{remaining_cents / 100:.2f}",
        tracked=tracked_days,
        total=total_days,
    )
    if not enabled or not api_key:
        return fallback

    prompt = (
        "Azərbaycan dilində səmimi, insani və rahat oxunan büdcə şərhi yaz. "
        "Cavabı 2-3 qısa sətirə böl və hər sətirdən sonra yeni sətrə keç. "
        "Rəsmi və robot kimi ifadələrdən "
        "(məsələn, 'təşkil edir', 'səviyyəsindədir') istifadə etmə. "
        "Vacib rəqəmləri cümlələr arasında təbii göstər, bütün statistikaları "
        "sadəcə ard-arda sadalama. Yalnız verilmiş rəqəmlərdən istifadə et, "
        "rəqəmləri dəyişmə, istifadəçini günahlandırma və investisiya məsləhəti "
        "vermə. Məzmuna uyğun maksimum 2 emoji istifadə et; seçdiyin emojiləri "
        "sətirlərin əvvəlində yerləşdir, cümlənin sonunda yox. 💰, 💸 və 🟢 "
        "emojilərindən yalnız lazım olanları seç. Qısa və ölçülü motivasiya "
        "əlavə edə bilərsən, amma "
        "'hər şey əla olacaq' kimi əsassız vədlər və şişirtmələr yazma.\n\n"
        f"period_budget: {budget_cents / 100:.2f} AZN\n"
        f"period_spent: {spent_cents / 100:.2f} AZN\n"
        f"remaining: {remaining_cents / 100:.2f} AZN\n"
        f"average_daily_spend: {average_daily_cents / 100:.2f} AZN\n"
        f"tracked_days: {tracked_days}\n"
        f"total_days: {total_days}\n"
        f"highest_week: {highest_week_cents / 100:.2f} AZN\n"
        f"lowest_week: {lowest_week_cents / 100:.2f} AZN"
    )
    try:
        client = genai.Client(api_key=api_key)
        response = await client.aio.models.generate_content(
            model="gemini-flash-lite-latest", contents=prompt
        )
        text = (response.text or "").strip()
        return text or fallback
    except Exception:
        return fallback