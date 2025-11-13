import asyncio
import logging
import datetime
import hashlib
from typing import Optional, List
import json
from pathlib import Path
import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from openai import AsyncOpenAI
from contextlib import suppress

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

# ========== Константы и настройки ==========
QUOTES_FILE = Path("quotes.json")
ADMIN_IDS = {536451470}

BOT_TOKEN = os.getenv(
    "BOT_TOKEN",
    "7737583178:AAGv4gBqf_DP2ZjQqrCLWZtIGmiKYYk-LsY"
)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
client = AsyncOpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None
TG_LIMIT = 4096

DOC_URL = "https://docs.google.com/spreadsheets/d/1YmUKSPDKvB8PWE2t2dC-dGy4vk4-9Jl-sWu8pRjknSo/edit?usp=sharing"
DOC2_URL = "https://docs.google.com/spreadsheets/d/1HfuY20ysxFNBdfhfkBAFy9ULhH68oQtSKMB-Ljp5xgo/edit?usp=sharing"
DOC3_URL = "https://officeflexispace.ru/app/company/80/office/"

BUTTON_TEXT = "Марафон посещений офиса"
BUTTON2_TEXT = "Таблица навикоинов"
BUTTON3_TEXT = "Система бронирования"
BUTTON5_TEXT = "Цитата дня"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

BOT_USERNAME_LOWER: Optional[str] = None

# ========== Простой HTTP-сервер для Render ==========

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        # можно сделать простую проверку /health
        self.send_response(200)
        self.send_header("Content-type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"OK")

    # чтобы не засорять логи Render'а
    def log_message(self, format, *args):
        return


def start_http_server():
    """
    Запускаем самый простой HTTP-сервер, чтобы Render видел открытый порт.
    Порт возьмём из переменной PORT (Render её подставляет), иначе 10000.
    """
    port = int(os.getenv("PORT", "10000"))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    logging.info(f"🌐 HTTP health server started on 0.0.0.0:{port}")
    server.serve_forever()


# ========== Работа с цитатами ==========

def load_quotes() -> List[str]:
    if not QUOTES_FILE.exists():
        return []
    with QUOTES_FILE.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("quotes", [])


def save_quotes(quotes: List[str]) -> None:
    with QUOTES_FILE.open("w", encoding="utf-8") as f:
        json.dump({"quotes": quotes}, f, ensure_ascii=False, indent=2)


def get_today_quote_file_id() -> Optional[str]:
    quotes = load_quotes()
    if not quotes:
        return None
    today_str = datetime.date.today().isoformat()
    digest = hashlib.sha256(today_str.encode("utf-8")).digest()
    num = int.from_bytes(digest[:4], byteorder="big")
    idx = num % len(quotes)
    return quotes[idx]

# ========== Команды ==========
async def send_long_text(update_or_message, text: str):
    msg = update_or_message.message if hasattr(update_or_message, "message") else update_or_message
    for i in range(0, len(text), TG_LIMIT):
        with suppress(Exception):
            await msg.reply_text(text[i:i+TG_LIMIT])

async def ask_gipi(prompt: str, sys: str = "You are Gipi, a concise and friendly assistant. Answer in Russian by default.") -> str:
    if not client:
        return "❗️ OpenAI ключ не настроен на сервере."
    try:
        resp = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role":"system","content":sys},{"role":"user","content":prompt}],
            temperature=0.3,
            max_tokens=1200,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        return f"⚠️ Ошибка при обращении к модели: {e}"
async def ask_cmd(update, context):
    parts = (update.message.text or "").split(maxsplit=1)
    if len(parts) > 1:
        await update.message.chat.send_action("typing")
        answer = await ask_gipi(parts[1])
        await send_long_text(update, answer)
        return
    context.user_data["awaiting_ask_text"] = True
    await update.message.reply_text("Окей, напиши вопрос одним следующим сообщением.")

async def ask_followup_text(update, context):
    if context.user_data.get("awaiting_ask_text"):
        context.user_data["awaiting_ask_text"] = False
        q = (update.message.text or "").strip()
        if not q:
            await update.message.reply_text("Пустой вопрос. Попробуй ещё раз: /ask")
            return
        await update.message.chat.send_action("typing")
        answer = await ask_gipi(q)
        await send_long_text(update, answer)


async def addquote_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("У тебя нет прав добавлять цитаты 🙅")
        return
    context.user_data["waiting_for_quote_photo"] = True
    await update.message.reply_text("Ок 👍 Пришли мне картинку (фото) с цитатой, я её сохраню.")


async def quote_photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        return
    if not context.user_data.get("waiting_for_quote_photo"):
        await update.message.reply_text("Чтобы добавить цитату, сначала напиши /addquote.")
        return

    photos = update.message.photo
    if not photos:
        await update.message.reply_text("Мне нужна именно КАРТИНКА как фото, не документ и не стикер 🙂")
        return

    file_id = photos[-1].file_id
    quotes = load_quotes()

    if file_id in quotes:
        await update.message.reply_text("Эта цитата уже есть в базе 👌")
        context.user_data["waiting_for_quote_photo"] = False
        return

    quotes.append(file_id)
    save_quotes(quotes)
    context.user_data["waiting_for_quote_photo"] = False
    new_index = len(quotes) - 1
    await update.message.reply_text(f"Готово ✅ Я сохранил цитату как #{new_index}.\nfile_id = {file_id}")


def make_menu_keyboard() -> InlineKeyboardMarkup:
    kb = [
        [InlineKeyboardButton(BUTTON_TEXT, callback_data="list")],
        [InlineKeyboardButton(BUTTON2_TEXT, callback_data="list2")],
        [InlineKeyboardButton(BUTTON3_TEXT, callback_data="Reserve")],
        [InlineKeyboardButton(BUTTON5_TEXT, callback_data="quote")],
    ]
    return InlineKeyboardMarkup(kb)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Выбери команду", reply_markup=make_menu_keyboard())


async def list_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(DOC_URL)


async def list2_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(DOC2_URL)


async def whoami_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    await update.message.reply_text(f"Твой Telegram ID: {user.id}\nИмя: {user.full_name}")


# ========== Обработка кнопок ==========

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
        if not file_id:
            await q.message.reply_text("Цитаты пока не загружены 🤷")
            return
        await q.message.reply_photo(photo=file_id)
    else:
        await q.message.reply_text("Я пока не знаю, что делать с этой кнопкой 🤔")


# ========== Упоминания ==========

def _mentioned_me(update: Update, bot_username_lower: Optional[str]) -> bool:
    if not update.message or not bot_username_lower:
        return False

    if update.message.entities:
        text = update.message.text or ""
        for ent in update.message.entities:
            if ent.type in (MessageEntityType.MENTION, MessageEntityType.TEXT_MENTION):
                mention_text = text[ent.offset: ent.offset + ent.length].lower()
                if mention_text in (f"@{bot_username_lower}", bot_username_lower):
                    return True

    text_lower = (update.message.text or "").lower()
    return f"@{bot_username_lower}" in text_lower or bot_username_lower in text_lower


async def mention_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if _mentioned_me(update, BOT_USERNAME_LOWER):
        await update.message.reply_text("Привет!", reply_markup=make_menu_keyboard())


# ========== Создание и запуск приложения ==========

async def prepare_app():
    global BOT_USERNAME_LOWER

    app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .build()
    )

    # Команды

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("list", list_cmd))
    app.add_handler(CommandHandler("list2", list2_cmd))
    app.add_handler(CommandHandler("whoami", whoami_cmd))
    app.add_handler(CommandHandler("addquote", addquote_cmd))
    app.add_handler(CommandHandler("ask", ask_cmd))

    # Упоминания — обрабатываем ВСЕ текстовые сообщения без команд,
    # а внутри _mentioned_me уже решаем, есть ли имя бота
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, mention_handler),
        group=0,
    )

    # Текст для /ask — идёт вторым слоем
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, ask_followup_text),
        group=1,
    )

    # Фото после /addquote
    app.add_handler(MessageHandler(filters.PHOTO, quote_photo_handler))

    # Callback-кнопки
    app.add_handler(CallbackQueryHandler(on_button))

    me = await app.bot.get_me()
    BOT_USERNAME_LOWER = me.username.lower() if me and me.username else None
    logging.info(f"Bot username: @{me.username}")
    logging.info("✅ Бот запускается. Жду апдейтов...")

    return app


def main():
    # 1. поднимем http-сервер в отдельном потоке
    t = threading.Thread(target=start_http_server, daemon=True)
    t.start()

    # 2. подготовим телеграм-приложение
    loop = asyncio.get_event_loop()
    app = loop.run_until_complete(prepare_app())

    # 3. запустим polling (блокирующий)
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
