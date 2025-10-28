# AXecutorBot.py — финальная чистая версия
# Функции:
#  • /start — показать меню с кнопкой «Марафон посещений офиса»
#  • /list  — выслать ссылку на документ
#  • Упоминание @ИмяБота в группе — показать то же меню
# Совместимо с python-telegram-bot 21.x и Python 3.11–3.14 (Windows OK)

import asyncio
import logging
import datetime
import hashlib
from typing import Optional
import json
from pathlib import Path
from typing import List

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import MessageEntityType
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# Путь к файлу, где будут лежать ID картинок с цитатами
QUOTES_FILE = Path("quotes.json")
ADMIN_IDS = {536451470}

def load_quotes() -> List[str]:
    """
    Читает quotes.json и возвращает список сохранённых file_id картинок.
    Если файла ещё нет — вернёт пустой список.
    """
    if not QUOTES_FILE.exists():
        return []

    with QUOTES_FILE.open("r", encoding="utf-8") as f:
        data = json.load(f)

    # ожидаем структуру {"quotes": ["file_id1", "file_id2", ...]}
    return data.get("quotes", [])


def save_quotes(quotes: List[str]) -> None:
    """
    Принимает список строк (file_idшки картинок)
    и записывает их в quotes.json.
    """
    with QUOTES_FILE.open("w", encoding="utf-8") as f:
        json.dump(
            {"quotes": quotes},
            f,
            ensure_ascii=False,
            indent=2
        )

def get_today_quote_file_id() -> str:
    """
    Берём список цитат из quotes.json,
    выбираем одну на основе сегодняшней даты,
    и возвращаем её file_id.
    """
    quotes = load_quotes()
    if not quotes:
        return None  # если нет ни одной цитаты

    # сегодняшняя дата как строка "2025-10-24"
    today_str = datetime.date.today().isoformat()

    # делаем стабильный хэш этой строки
    digest = hashlib.sha256(today_str.encode("utf-8")).digest()

    # превращаем первые 4 байта хэша в число
    num = int.from_bytes(digest[:4], byteorder="big")

    # берём индекс по модулю длины массива цитат
    idx = num % len(quotes)

    return quotes[idx]

# ----------------- НАСТРОЙКИ -----------------
BOT_TOKEN = "7737583178:AAGv4gBqf_DP2ZjQqrCLWZtIGmiKYYk-LsY"
DOC_URL = "https://docs.google.com/spreadsheets/d/1YmUKSPDKvB8PWE2t2dC-dGy4vk4-9Jl-sWu8pRjknSo/edit?usp=sharing"  # ← твоя ссылка
DOC2_URL = "https://docs.google.com/spreadsheets/d/1HfuY20ysxFNBdfhfkBAFy9ULhH68oQtSKMB-Ljp5xgo/edit?usp=sharing"  # ← твоя ссылка
DOC3_URL = "https://officeflexispace.ru/app/company/80/office/"  # ← твоя ссылка
BUTTON_TEXT = "Марафон посещений офиса"
BUTTON2_TEXT = "Таблица навикоинов"
BUTTON3_TEXT = "Система бронирования"
BUTTON5_TEXT = "Цитата дня"
# ---------------------------------------------

logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")

# Кешируем username бота после старта (в нижнем регистре)
BOT_USERNAME_LOWER: Optional[str] = None

async def addquote_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Команда /addquote:
    - проверяем, что это админ
    - включаем режим "я жду от тебя картинку"
    - просим скинуть фото
    """
    user_id = update.effective_user.id

    # проверяем права
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("У тебя нет прав добавлять цитаты 🙅")
        return

    # ставим флаг в user_data, что от этого пользователя ждём фото
    context.user_data["waiting_for_quote_photo"] = True

    await update.message.reply_text(
        "Ок 👍 Пришли мне картинку (фото) с цитатой, я её сохраню."
    )

async def quote_photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Этот хэндлер ловит входящее фото и,
    если до этого был /addquote, забирает file_id и сохраняет.
    """
    user_id = update.effective_user.id

    # Только админы могут добавлять
    if user_id not in ADMIN_IDS:
       # await update.message.reply_text(
       #     "Это фото я не могу сохранить как цитату."
       # )
        return

    # Проверяем, ждём ли мы сейчас фото от этого пользователя
    if not context.user_data.get("waiting_for_quote_photo"):
        await update.message.reply_text(
            "Чтобы добавить цитату, сначала напиши /addquote."
        )
        return

    # Проверяем, что вообще пришло фото
    photos = update.message.photo
    if not photos:
        await update.message.reply_text(
            "Мне нужна именно КАРТИНКА как фото, не документ и не стикер 🙂"
        )
        return

    # Берём самую большую версию картинки = последний элемент
    file_id = photos[-1].file_id

    # Загружаем текущий список цитат из файла
    quotes = load_quotes()

    # Проверяем на дубликат (не обязательно, но удобно)
    if file_id in quotes:
        await update.message.reply_text(
            "Эта цитата уже есть в базе 👌"
        )
        # флаг больше не нужен
        context.user_data["waiting_for_quote_photo"] = False
        return

    # Добавляем новую цитату
    quotes.append(file_id)

    # Сохраняем обратно в quotes.json
    save_quotes(quotes)

    # Сбрасываем флаг ожидания
    context.user_data["waiting_for_quote_photo"] = False

    # Для удобства скажем индекс новой цитаты
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


# /start — показать меню
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Выбери команду",
        reply_markup=make_menu_keyboard(),
    )


# /list — выслать ссылку
async def list_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(DOC_URL)

# /list2 — выслать ссылку на второй документ
async def list2_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(DOC_URL_2)

# Нажатие инлайн‑кнопки
async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    data = q.data
    if q.data == "list":
        await q.message.reply_text(DOC_URL)
    elif q.data == "list2":
        await q.message.reply_text(DOC2_URL)
    elif q.data == "Reserve":
        await q.message.reply_text(DOC3_URL)
    
    
    elif data == "quote":
        # здесь мы отправляем картинку "цитата дня"

        file_id = get_today_quote_file_id()

        if file_id is None:
            # На случай, если в quotes.json почему-то пусто
            await q.message.reply_text("Цитаты пока не загружены 🤷")
            return

        # отправляем фото по file_id
        await q.message.reply_photo(
            photo=file_id
            #caption="Цитата дня ✨"
        )

    else:
        # неизвестная кнопка (на будущее)
        await q.message.reply_text("Я пока не знаю, что делать с этой кнопкой 🤔")

# Проверяем, упомянут ли бот в сообщении
def _mentioned_me(update: Update, bot_username_lower: Optional[str]) -> bool:
    if not update.message or not bot_username_lower:
        return False

    # 1) Через entities (надёжнее для групп)
    if update.message.entities:
        text = update.message.text or ""
        for ent in update.message.entities:
            if ent.type in (MessageEntityType.MENTION, MessageEntityType.TEXT_MENTION):
                mention_text = text[ent.offset : ent.offset + ent.length].lower()
                if mention_text in (f"@{bot_username_lower}", bot_username_lower):
                    return True

    # 2) Запасной путь — поиск по тексту
    text_lower = (update.message.text or "").lower()
    return (f"@{bot_username_lower}" in text_lower) or (bot_username_lower in text_lower)


# Реагируем на упоминание бота: показываем меню
async def mention_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if _mentioned_me(update, BOT_USERNAME_LOWER):
        await update.message.reply_text(
            "Привет!", reply_markup=make_menu_keyboard()
        )

async def whoami_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает Telegram ID пользователя (чтобы добавить его в ADMIN_IDS)."""
    user = update.effective_user
    await update.message.reply_text(
        f"Твой Telegram ID: {user.id}\n"
        f"Имя: {user.full_name}"
    )


async def main() -> None:
    global BOT_USERNAME_LOWER

    app = Application.builder().token(BOT_TOKEN).build()

    # Команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("list", list_cmd))
    app.add_handler(CommandHandler("whoami", whoami_cmd))
    app.add_handler(CallbackQueryHandler(on_button))

    app.add_handler(CommandHandler("addquote", addquote_cmd))

    # НОВОЕ: приём фото после /addquote
    app.add_handler(MessageHandler(
        filters.PHOTO,
        quote_photo_handler
    ))

    # Кнопка
    app.add_handler(CallbackQueryHandler(on_button))

    # Сообщения: ловим упоминания бота в тексте (в группе/супергруппе)
    from telegram.constants import MessageEntityType

    app.add_handler(
    MessageHandler(
        (filters.TEXT & ~filters.COMMAND)
        | filters.Entity(MessageEntityType.MENTION)
        | filters.Entity(MessageEntityType.TEXT_MENTION),
        mention_handler,
                  )
    )


    # Явный пошаговый запуск
    await app.initialize()

    me = await app.bot.get_me()
    BOT_USERNAME_LOWER = me.username.lower() if me and me.username else None
    logging.info("Bot username: @%s", me.username)

    await app.start()
    logging.info("✅ Бот запущен. Напиши /start в Telegram (Ctrl+C — остановка).")

    # Снимаем вебхук и запускаем polling
    await app.bot.delete_webhook(drop_pending_updates=True)
    await app.updater.start_polling()
    logging.info("📡 Polling запущен.")

    try:
        # Держим процесс живым
        await asyncio.Future()
    except asyncio.CancelledError:
        pass
    finally:
        logging.info("⏹ Остановка…")
        await app.updater.stop()
        await app.stop()
        await app.shutdown()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
