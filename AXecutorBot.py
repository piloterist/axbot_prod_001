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

# ========== Константы и настройки ==========
QUOTES_FILE = Path("quotes.json")
ADMIN_IDS = {536451470}

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

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

BOT_USERNAME_LOWER: Optional[str] = None

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


# ========== У
