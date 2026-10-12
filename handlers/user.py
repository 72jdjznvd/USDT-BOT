import os
import logging
from decimal import Decimal, InvalidOperation

from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

from database import (
    save_user,
    get_user,
    list_user_orders,
)

router = Router()
logger = logging.getLogger(__name__)

BUY_RATE = os.getenv("BUY_RATE", "1.70")
SELL_RATE = os.getenv("SELL_RATE", "1.65")

SUPPORT_USERNAME = os.getenv(
    "SUPPORT_USERNAME",
    "",
).strip().lstrip("@")

TEXTS = {
    "az": {
        "welcome": (
            "👋 <b>USDT P2P AZ</b> botuna xoş gəlmisən!\n\n"
            "Buradan USDT alış və satış sifarişləri yarada bilərsən.\n\n"
            "⚠️ Köçürmə etməzdən əvvəl məbləği, ünvanı və "
            "ödəniş məlumatlarını diqqətlə yoxla."
        ),
        "buy": "🟢 USDT al",
        "sell": "🔵 USDT sat",
        "rates": "💱 Məzənnələr",
        "profile": "👤 Profilim",
        "orders": "📋 Sifarişlərim",
        "language": "🌐 Dil",
        "support": "🆘 Dəstək",
        "help": "ℹ️ Kömək",
        "language_saved": "Dil Azərbaycan dili seçildi.",
        "profile_title": "👤 <b>Profil məlumatların</b>",
        "orders_empty": "Hələ sifarişin yoxdur.",
        "orders_title": "📋 <b>Son sifarişlərin</b>",
        "support_missing": (
            "Dəstək ünvanı hələ əlavə edilməyib. "
            "Administratorla əlaqə saxla."
        ),
        "help_text": (
            "ℹ️ <b>Botdan istifadə</b>\n\n"
            "/start — əsas menyu\n"
            "/buy — USDT almaq\n"
            "/sell — USDT satmaq\n"
            "/rates — məzənnələr\n"
            "/profile — profil\n"
            "/orders — sifariş tarixçəsi\n"
            "/language — dil seçimi\n"
            "/support — dəstək\n\n"
            "Sifariş təsdiqlənənədək vəsaitin göndərildiyini "
            "fərz etmə. TXID və ödəniş məlumatları ayrıca yoxlanmalıdır."
        ),
    },
    "ru": {
        "welcome": (
            "👋 Добро пожаловать в <b>USDT P2P AZ</b>!\n\n"
            "Здесь можно создать заявку на покупку или продажу USDT.\n\n"
            "⚠️ Перед переводом внимательно проверь сумму, "
            "адрес и платёжные реквизиты."
        ),
        "buy": "🟢 Купить USDT",
        "sell": "🔵 Продать USDT",
        "rates": "💱 Курсы",
        "profile": "👤 Мой профиль",
        "orders": "📋 Мои заявки",
        "language": "🌐 Язык",
        "support": "🆘 Поддержка",
        "help": "ℹ️ Помощь",
        "language_saved": "Выбран русский язык.",
        "profile_title": "👤 <b>Данные профиля</b>",
        "orders_empty": "У вас пока нет заявок.",
        "orders_title": "📋 <b>Последние заявки</b>",
        "support_missing": (
            "Контакт поддержки ещё не добавлен. "
            "Свяжитесь с администратором."
        ),
        "help_text": (
            "ℹ️ <b>Помощь</b>\n\n"
            "/start — главное меню\n"
            "/buy — купить USDT\n"
            "/sell — продать USDT\n"
            "/rates — курсы\n"
            "/profile — профиль\n"
            "/orders — история заявок\n"
            "/language — выбор языка\n"
            "/support — поддержка\n\n"
            "Не считайте перевод выполненным до проверки. "
            "TXID и платёжные данные нужно проверять отдельно."
        ),
    },
}


def get_language(user: dict | None) -> str:
    language = user.get("language", "az") if user else "az"
    return language if language in TEXTS else "az"


def t(language: str, key: str) -> str:
    language = language if language in TEXTS else "az"
    return TEXTS[language].get(key, TEXTS["az"].get(key, key))


def main_keyboard(language: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t(language, "buy"),
                    callback_data="menu:buy",
                ),
                InlineKeyboardButton(
                    text=t(language, "sell"),
                    callback_data="menu:sell",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=t(language, "rates"),
                    callback_data="menu:rates",
                ),
                InlineKeyboardButton(
                    text=t(language, "profile"),
                    callback_data="menu:profile",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=t(language, "orders"),
                    callback_data="menu:orders",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=t(language, "language"),
                    callback_data="menu:language",
                ),
                InlineKeyboardButton(
                    text=t(language, "support"),
                    callback_data="menu:support",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=t(language, "help"),
                    callback_data="menu:help",
                ),
            ],
        ]
    )


def language_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🇦🇿 Azərbaycan dili",
                    callback_data="language:az",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🇷🇺 Русский",
                    callback_data="language:ru",
                ),
            ],
        ]
    )


async def register_user(message: Message, language: str = "az"):
    user = message.from_user
    if user is None:
        return None

    await save_user(
        telegram_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
        language=language,
    )
    return await get_user(user.id)


@router.message(CommandStart())
async def start_handler(message: Message):
    if message.from_user is None:
        return

    user = await get_user(message.from_user.id)

    if user:
        language = get_language(user)
        await save_user(
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            last_name=message.from_user.last_name,
            language=language,
        )
    else:
        language = "az"
        await register_user(message, language)

    await message.answer(
        t(language, "welcome"),
        reply_markup=main_keyboard(language),
    )


@router.message(Command("language"))
async def language_command(message: Message):
    await message.answer(
        "Dil seç / Выберите язык:",
        reply_markup=language_keyboard(),
    )


@router.callback_query(F.data.startswith("language:"))
async def language_callback(callback: CallbackQuery):
    if callback.from_user is None:
        await callback.answer()
        return

    language = callback.data.split(":", 1)[1]

    if language not in ("az", "ru"):
        await callback.answer("Dil seçimi düzgün deyil.", show_alert=True)
        return

    await save_user(
        telegram_id=callback.from_user.id,
        username=callback.from_user.username,
        first_name=callback.from_user.first_name,
        last_name=callback.from_user.last_name,
        language=language,
    )

    await callback.answer(t(language, "language_saved"))

    if callback.message:
        await callback.message.edit_text(
            t(language, "welcome"),
            reply_markup=main_keyboard(language),
        )


async def show_rates(message: Message, language: str):
    await message.answer(
        "💱 <b>USDT P2P AZ</b>\n\n"
        f"🟢 Alış: <b>{BUY_RATE} AZN</b> / USDT\n"
        f"🔵 Satış: <b>{SELL_RATE} AZN</b> / USDT\n\n"
        "Məzənnələr nümunə deyil, Render Environment Variables "
        "bölməsində təyin olunan qiymətlərdən götürülür.\n"
        "Sifarişi təsdiqləməzdən əvvəl yekun məbləği yoxla."
    )


@router.message(Command("rates"))
async def rates_command(message: Message):
    user = await get_user(message.from_user.id)
    await show_rates(message, get_language(user))


@router.callback_query(F.data == "menu:rates")
async def rates_callback(callback: CallbackQuery):
    user = await get_user(callback.from_user.id)
    language = get_language(user)

    await callback.answer()

    if callback.message:
        await show_rates(callback.message, language)


@router.message(Command("profile"))
async def profile_command(message: Message):
    user = await get_user(message.from_user.id)

    if not user:
        await message.answer("Əvvəlcə /start yaz.")
        return

    language = get_language(user)
    username = (
        f"@{user['username']}"
        if user.get("username")
        else "Yoxdur"
    )

    await message.answer(
        f"{t(language, 'profile_title')}\n\n"
        f"🆔 Telegram ID: <code>{user['telegram_id']}</code>\n"
        f"👤 Ad: {user.get('first_name') or '-'}\n"
        f"🔗 Username: {username}\n"
        f"🌐 Dil: {language.upper()}"
    )


@router.callback_query(F.data == "menu:profile")
async def profile_callback(callback: CallbackQuery):
    if callback.from_user is None:
        await callback.answer()
        return

    user = await get_user(callback.from_user.id)
    if not user:
        await callback.answer(
            "Əvvəlcə /start yaz.",
            show_alert=True,
        )
        return

    language = get_language(user)
    username = (
        f"@{user['username']}"
        if user.get("username")
        else "Yoxdur"
    )

    await callback.answer()

    if callback.message:
        await callback.message.answer(
            f"{t(language, 'profile_title')}\n\n"
            f"🆔 Telegram ID: <code>{user['telegram_id']}</code>\n"
            f"👤 Ad: {user.get('first_name') or '-'}\n"
            f"🔗 Username: {username}\n"
            f"🌐 Dil: {language.upper()}"
        )


def format_order(order: dict, language: str) -> str:
    if language == "ru":
        return (
            f"🧾 Заявка: <code>{order.get('order_ref', '-')}</code>\n"
            f"Тип: {order.get('kind', '-')}\n"
            f"USDT: {order.get('amount', '-')}\n"
            f"Сумма: {order.get('total', '-')} AZN\n"
            f"Статус: {order.get('status', '-')}"
        )

    return (
        f"🧾 Sifariş: <code>{order.get('order_ref', '-')}</code>\n"
        f"Tip: {order.get('kind', '-')}\n"
        f"USDT: {order.get('amount', '-')}\n"
        f"Məbləğ: {order.get('total', '-')} AZN\n"
        f"Status: {order.get('status', '-')}"
    )


async def show_orders(message: Message, telegram_id: int):
    user = await get_user(telegram_id)

    if not user:
        await message.answer("Əvvəlcə /start yaz.")
        return

    language = get_language(user)
    orders = await list_user_orders(telegram_id, limit=10)

    if not orders:
        await message.answer(t(language, "orders_empty"))
        return

    await message.answer(t(language, "orders_title"))

    for order in orders:
        await message.answer(format_order(order, language))


@router.message(Command("orders"))
async def orders_command(message: Message):
    await show_orders(message, message.from_user.id)


@router.callback_query(F.data == "menu:orders")
async def orders_callback(callback: CallbackQuery):
    await callback.answer()

    if callback.message:
        await show_orders(
            callback.message,
            callback.from_user.id,
        )


@router.callback_query(F.data == "menu:language")
async def language_menu_callback(callback: CallbackQuery):
    await callback.answer()

    if callback.message:
        await callback.message.answer(
            "Dil seç / Выберите язык:",
            reply_markup=language_keyboard(),
        )


@router.message(Command("support"))
async def support_command(message: Message):
    user = await get_user(message.from_user.id)
    language = get_language(user)

    if not SUPPORT_USERNAME:
        await message.answer(t(language, "support_missing"))
        return

    await message.answer(
        f"🆘 Dəstək: @{SUPPORT_USERNAME}"
        if language == "az"
        else f"🆘 Поддержка: @{SUPPORT_USERNAME}"
    )


@router.callback_query(F.data == "menu:support")
async def support_callback(callback: CallbackQuery):
    user = await get_user(callback.from_user.id)
    language = get_language(user)

    await callback.answer()

    if callback.message:
        if SUPPORT_USERNAME:
            text = (
                f"🆘 Dəstək: @{SUPPORT_USERNAME}"
                if language == "az"
                else f"🆘 Поддержка: @{SUPPORT_USERNAME}"
            )
        else:
            text = t(language, "support_missing")

        await callback.message.answer(text)


@router.message(Command("help"))
async def help_command(message: Message):
    user = await get_user(message.from_user.id)
    language = get_language(user)
    await message.answer(t(language, "help_text"))


@router.callback_query(F.data == "menu:help")
async def help_callback(callback: CallbackQuery):
    user = await get_user(callback.from_user.id)
    language = get_language(user)

    await callback.answer()

    if callback.message:
        await callback.message.answer(t(language, "help_text"))


@router.callback_query(F.data == "menu:buy")
async def menu_buy_callback(callback: CallbackQuery):
    await callback.answer()

    if callback.message:
        await callback.message.answer(
            "USDT almaq üçün /buy yaz."
            if get_language(await get_user(callback.from_user.id)) == "az"
            else "Для покупки USDT введи /buy."
        )


@router.callback_query(F.data == "menu:sell")
async def menu_sell_callback(callback: CallbackQuery):
    await callback.answer()

    if callback.message:
        await callback.message.answer(
            "USDT satmaq üçün /sell yaz."
            if get_language(await get_user(callback.from_user.id)) == "az"
            else "Для продажи USDT введи /sell."
            )
