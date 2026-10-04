from telegram import ReplyKeyboardMarkup


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            ["💸 Xərc qeyd et", "📊 Vəziyyətim"],
            ["📅 Tarixçə", "⚙️ Ayarlar"],
        ],
        resize_keyboard=True,
    )