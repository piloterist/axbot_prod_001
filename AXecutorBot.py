import asyncio
import logging
import datetime
import hashlib
from typing import Optional, List
import json
from pathlib import Path
import os

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import MessageEntityType
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ================== КОНСТАНТЫ / НАСТРОЙКИ ==================

# Файл с цитатами (file_id картинок)
QUOTES_FILE = Path("quotes.json")

# Админы, которым можно использовать /addquote
ADMIN_IDS = {536451470}

# Токен бота. На Render лучше хранить в переменной окружения BOT_TOKEN,
# но я оставляю твою логику: если переменной нет, использовать хардкод.
BOT_TOKEN = os.getenv(
    "BOT_TOKEN",
    "7737583178:AAGv4gBqf_DP2ZjQqrCLWZtIGmiKYYk-LsY"
)

DOC_URL = "https://docs.google.com/spreadsheets/d/1YmUKSPDKvB8PWE2t2dC-dGy4vk4-9Jl-sWu8pRjknSo/edit?usp=sharing"
DOC2_URL = "https://docs.google.com/spreadsheets/d/1HfuY20ysxFNBdfhfkBAFy9ULhH68oQtSKMB-Ljp5xgo/edit?usp=sharing"
DOC3_URL = "https://officeflexispace.ru/app/company/80/office/"

BUTTON_TEXT = "Марафон посещений офиса"
BUTTON2_TEXT = "Таблица навикоинов"
BUTTON3_TEXT = "Система бронирования"
BUTTON5_TEXT = "Цитата дня"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

# Кешируем username бота после старта (в нижнем регистре)
BOT_USERNAME_LOWER: Optional[str] = None

# ================== УТИЛИТЫ ДЛЯ ЦИТАТ ==================


def load_quotes() -> List[str]:
    """
    Читает quotes.json и возвращает список сохранённых file_id картинок.
    Если файла ещё нет — вернёт пустой список.
    """
    if not QUOTES_FILE.exists():
        return []

    with QUOTES_FILE.open("r", encoding="utf-8") as f:
        data = json.load(f)

    return data.get("quotes", [])


def save_quotes(quotes: List[str]) -> None:
    """
    Сохраняет список file_id обратно в quotes.json.
    """
    with QUOTES_FILE.open("w", encoding="utf-8") as f:
        json.dump(
            {"quotes": quotes},
            f,
            ensure_ascii=False,
            indent=2
        )


def get_today_quote_file_id() -> Optional[str]:
    """
    Возвращает file_id "цитаты дня" по сегодняшней дате.
    Одна и та же цитата для всех в течение суток.
    """
    quotes = load_quotes()
    if not quotes:
        return None

    today_str = datetime.date.today().isoformat()
    digest = hashlib.sha256(today_str.encode("utf-8")).digest()
    num = int.from_bytes(digest[:4], byteorder="big")
    idx = num % len(quotes)
    return quotes[idx]


# ================== ХЕНДЛЕРЫ КОМАНД ==================


async def addquote_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /addquote:
    - только для админов
    - ставим флаг "жду фото"
    """
    user_id = update.effective_user.id

    if user_id not in ADMIN_IDS:
        await update.message.reply_text("У тебя нет прав добавлять цитаты 🙅")
        return

    context.user_data["waiting_for_quote_photo"] = True

    await update.message.reply_text(
        "Ок 👍 Пришли мне картинку (фото) с цитатой, я её сохраню."
    )


async def quote_photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Принимает фото после /addquote, сохраняет его file_id в quotes.json
    """
    user_id = update.effective_user.id

    # только админ может добавлять
    if user_id not in ADMIN_IDS:
        # тихо игнорируем, чтобы не палить админку
        return

    # мы вообще ждали фото?
    if not context.user_data.get("waiting_for_quote_photo"):
        await update.message.reply_text(
            "Чтобы добавить цитату, сначала напиши /addquote."
        )
        return

    photos = update.message.photo
    if not photos:
        await update.message.reply_text(
            "Мне нужна именно КАРТИНКА как фото, не документ и не стикер 🙂"
        )
        return

    file_id = photos[-1].file_id

    quotes = load_quotes()

    if file_id in quotes:
        await update.message.reply_text(
            "Эта цитата уже есть в базе 👌"
        )
        context.user_data["waiting_for_quote_photo"] = False
        return

    quotes.append(file_id)
    save_quotes(quotes)

    context.user_data["waiting_for_quote_photo"] = False

    new_index = len(quotes) - 1
    await update.message.reply_text(
        f"Готово ✅ Я сохранил цитату как #{new_index}.\n"
        f"file_id = {file_id}"
    )


def make_menu_keyboard() -> InlineKeyboardMarkup:
    kb = [
        [InlineKeyboardButton(BUTTON_TEXT, callback_data="list")],
        [InlineKeyboardButton(BUTTON2_TEXT, callback_data="list2")],
        [InlineKeyboardButton(BUTTON3_TEXT, callback_data="Reserve")],
        [InlineKeyboardButton(BUTTON5_TEXT, callback_data="quote")],
    ]
    return InlineKeyboardMarkup(kb)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /start — показать меню
    """
    await update.message.reply_text(
        "Выбери команду",
        reply_markup=make_menu_keyboard(),
    )


async def list_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /list — отправить первую ссылку
    """
    await update.message.reply_text(DOC_URL)


async def list2_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /list2 — отправить вторую ссылку
    """
    await update.message.reply_text(DOC2_URL)


async def whoami_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /whoami — показать твой Telegram ID (для ADMIN_IDS)
    """
    user = update.effective_user
    await update.message.reply_text(
        f"Твой Telegram ID: {user.id}\nИмя: {user.full_name}"
    )


# ================== КНОПКИ / CALLBACK DATA ==================


async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()

    data = q.data

    if data == "list":
        await q.message.reply_text(DOC_URL)

    elif data == "list2":
        await q.message.reply_text(DOC2_URL)

    elif data == "Reserve":
        await q.message.reply_text(DOC3_URL)

    elif data == "quote":
        file_id = get_today_quote_file_id()

        if file_id is None:
            await q.message.reply_text("Цитаты пока не загружены 🤷")
            return

        await q.message.reply_photo(
            photo=file_id,
            # caption="Цитата дня ✨",
        )

    else:
        await q.message.reply_text("Я пока не знаю, что делать с этой кнопкой 🤔")


# ================== УПОМИНАНИЕ БОТА ==================


def _mentioned_me(update: Update, bot_username_lower: Optional[str]) -> bool:
    if not update.message or not bot_username_lower:
        return False

    # (1) Через entities (нормально работает в группах)
    if update.message.entities:
        text = update.message.text or ""
        for ent in update.message.entities:
            if ent.type in (
                MessageEntityType.MENTION,
                MessageEntityType.TEXT_MENTION,
            ):
                mention_text = text[ent.offset: ent.offset + ent.length].lower()
                if mention_text in (
                    f"@{bot_username_lower}",
                    bot_username_lower,
                ):
                    return True

    # (2) fallback — просто ищем в тексте
    text_lower = (update.message.text or "").lower()
    return (
        f"@{bot_username_lower}" in text_lower
        or bot_username_lower in text_lower
    )


async def mention_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if _mentioned_me(update, BOT_USERNAME_LOWER):
        await update.message.reply_text(
            "Привет!",
            reply_markup=make_menu_keyboard(),
        )


# ================== MAIN ==================


async def main() -> None:
    global BOT_USERNAME_LOWER

    # создаём Application через ApplicationBuilder (PTB 20.x стиль)
    app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .build()
    )

    # команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("list", list_cmd))
    app.add_handler(CommandHandler("list2", list2_cmd))
    app.add_handler(CommandHandler("whoami", whoami_cmd))
    app.add_handler(CommandHandler("addquote", addquote_cmd))

    # фото после /addquote
    app.add_handler(MessageHandler(filters.PHOTO, quote_photo_handler))

    # callback-кнопки
    app.add_handler(CallbackQueryHandler(on_button))

    # сообщения с упоминанием бота
    app.add_handler(
        MessageHandler(
            (filters.TEXT & ~filters.COMMAND)
            | filters.Entity(MessageEntityType.MENTION)
            | filters.Entity(MessageEntityType.TEXT_MENTION),
            mention_handler,
        )
    )

    # Получаем username бота один раз, сохраним в BOT_USERNAME_LOWER
    me = await app.bot.get_me()
    BOT_USERNAME_LOWER = me.username.lower() if me and me.username else None
    logging.info("Bot username: @%s", me.username if me else "<?>")

    logging.info("✅ Бот запускается. Жду апдейтов...")

    # ВАЖНО:
    # run_polling сам:
    # - снимет вебхук
    # - запустит long polling
    # - будет держать процесс живым
    # никаких app.initialize(), app.start(), app.updater.* не нужно
    await app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
