import os

from aiogram import Router, F
from aiogram.filters import Command, CommandStart
from aiogram.types import (
Message,
CallbackQuery,
ReplyKeyboardMarkup,
KeyboardButton,
InlineKeyboardMarkup,
InlineKeyboardButton,
)

from database import save_user, get_user, list_user_orders
from services.i18n import get_text

router = Router()

BUY_RATE = os.getenv("BUY_RATE", "1.70")
SELL_RATE = os.getenv("SELL_RATE", "1.69")
SUPPORT_USERNAME = os.getenv("SUPPORT_USERNAME", "")

def main_menu(language: str = "az") -> ReplyKeyboardMarkup:
if language == "ru":
rows = [
[
KeyboardButton(text="🟢 КУПИТЬ USDT"),
KeyboardButton(text="🔵 ПРОДАТЬ USDT"),
],
[
KeyboardButton(text="📊 Курсы"),
KeyboardButton(text="📋 Мои заказы"),
],
[
KeyboardButton(text="👤 Мой профиль"),
KeyboardButton(text="🌐 Язык / Dil"),
],
[KeyboardButton(text="🆘 Поддержка")],
]
else:
rows = [
[
KeyboardButton(text="🟢 USDT AL"),
KeyboardButton(text="🔵 USDT SAT"),
],
[
KeyboardButton(text="📊 Məzənnələr"),
KeyboardButton(text="📋 Sifarişlərim"),
],
[
KeyboardButton(text="👤 Profilim"),
KeyboardButton(text="🌐 Dil / Язык"),
],
[KeyboardButton(text="🆘 Dəstək")],
]

return ReplyKeyboardMarkup(
    keyboard=rows,
    resize_keyboard=True,
    input_field_placeholder=(
        "Menyu seçin" if language == "az" else "Выберите меню"
    ),
)

def language_keyboard() -> InlineKeyboardMarkup:
return InlineKeyboardMarkup(
inline_keyboard=[
[
InlineKeyboardButton(
text="🇦🇿 Azərbaycan dili",
callback_data="language:az",
),
InlineKeyboardButton(
text="🇷🇺 Русский",
callback_data="language:ru",
),
]
]
)

async def get_language(telegram_id: int) -> str:
user = await get_user(telegram_id)
if user and user.get("language") in ("az", "ru"):
return user["language"]
return "az"

async def register_user(message: Message, language: str = "az"):
user = message.from_user
if not user:
return

await save_user(
    telegram_id=user.id,
    username=user.username,
    first_name=user.first_name,
    last_name=user.last_name,
    language=language,
)

@router.message(CommandStart())
async def start_handler(message: Message):
user = message.from_user
if not user:
return

await register_user(message)
language = await get_language(user.id)

await message.answer(
    get_text(
        language,
        "welcome",
        name=user.first_name or "dost",
    ),
    reply_markup=main_menu(language),
)

@router.message(Command("language"))
@router.message(
F.text.in_({"🌐 Dil / Язык", "🌐 Язык / Dil"})
)
async def language_handler(message: Message):
language = await get_language(message.from_user.id)

await message.answer(
    get_text(language, "choose_language"),
    reply_markup=language_keyboard(),
)

@router.callback_query(F.data.startswith("language:"))
async def language_callback(callback: CallbackQuery):
user = callback.from_user
language = callback.data.split(":", 1)[1]

if language not in ("az", "ru"):
    await callback.answer("Invalid language", show_alert=True)
    return

await save_user(
    telegram_id=user.id,
    username=user.username,
    first_name=user.first_name,
    last_name=user.last_name,
    language=language,
)

await callback.answer()

if callback.message:
    await callback.message.answer(
        get_text(language, "language_saved"),
        reply_markup=main_menu(language),
    )

@router.message(
F.text.in_({"📊 Məzənnələr", "📊 Курсы"})
)
async def rates_handler(message: Message):
language = await get_language(message.from_user.id)

if language == "ru":
    text = (
        "📊 Курсы USDT P2P AZ\n\n"
        f"🟢 Покупка USDT: {BUY_RATE} AZN\n"
        f"🔵 Продажа USDT: {SELL_RATE} AZN\n\n"
        "⚠️ Перед созданием заказа уточните актуальный курс."
    )
else:
    text = (
        "📊 USDT P2P AZ məzənnələri\n\n"
        f"🟢 USDT alış: {BUY_RATE} AZN\n"
        f"🔵 USDT satış: {SELL_RATE} AZN\n\n"
        "⚠️ Sifariş yaratmazdan əvvəl aktual məzənnəni yoxlayın."
    )

await message.answer(text, reply_markup=main_menu(language))

@router.message(
F.text.in_({"👤 Profilim", "👤 Мой профиль"})
)
async def profile_handler(message: Message):
user = message.from_user
language = await get_language(user.id)
db_user = await get_user(user.id)
orders = await list_user_orders(user.id, limit=100)

name = user.full_name or "—"
username = f"@{user.username}" if user.username else "—"

text = get_text(
    language,
    "profile_info",
    name=name,
    username=username,
    telegram_id=user.id,
    orders_count=len(orders),
)

await message.answer(text, reply_markup=main_menu(language))

@router.message(
F.text.in_({"📋 Sifarişlərim", "📋 Мои заказы"})
)
async def orders_handler(message: Message):
language = await get_language(message.from_user.id)
orders = await list_user_orders(message.from_user.id, limit=10)

if not orders:
    await message.answer(
        get_text(language, "no_orders"),
        reply_markup=main_menu(language),
    )
    return

if language == "ru":
    lines = ["📋 Ваши последние заказы:\n"]
    kind_names = {"buy": "Покупка", "sell": "Продажа"}
else:
    lines = ["📋 Son sifarişləriniz:\n"]
    kind_names = {"buy": "Alış", "sell": "Satış"}

for order in orders:
    order_ref = order.get("order_ref", "—")
    kind = kind_names.get(order.get("kind"), order.get("kind", "—"))
    amount = order.get("amount", "—")
    status = order.get("status", "—")

    lines.append(
        f"№ {order_ref}\n"
        f"{kind} | {amount} USDT\n"
        f"Status: {status}\n"
    )

await message.answer(
    "\n".join(lines),
    reply_markup=main_menu(language),
)

@router.message(
F.text.in_({"🆘 Dəstək", "🆘 Поддержка"})
)
async def support_handler(message: Message):
language = await get_language(message.from_user.id)

if SUPPORT_USERNAME:
    support = SUPPORT_USERNAME
    if not support.startswith("@"):
        support = f"@{support}"

    text = (
        f"🆘 Поддержка: {support}"
        if language == "ru"
        else f"🆘 Dəstək: {support}"
    )
else:
    text = (
        "🆘 Напишите администратору для получения помощи."
        if language == "ru"
        else "🆘 Kömək üçün administratorla əlaqə saxlayın."
    )

await message.answer(text, reply_markup=main_menu(language))

@router.message(
F.text.in_({"ℹ️ Kömək", "ℹ️ Помощь"})
)
async def help_handler(message: Message):
language = await get_language(message.from_user.id)

await message.answer(
    get_text(language, "help"),
    reply_markup=main_menu(language),
)
