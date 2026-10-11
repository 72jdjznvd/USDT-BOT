import asyncio
import logging
import os
import time
import uuid
from decimal import Decimal, InvalidOperation

from aiohttp import web
from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton,
)
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
BUY_RATE = Decimal(os.getenv("BUY_RATE", "1.70"))
SELL_RATE = Decimal(os.getenv("SELL_RATE", "1.69"))
PAYMENT_MINUTES = int(os.getenv("PAYMENT_MINUTES", "3"))
BANK_DETAILS = os.getenv(
    "BANK_DETAILS",
    "Ödəniş rekvizitləri operator tərəfindən əlavə edilməyib.",
)
SELL_TRC20_ADDRESS = os.getenv("SELL_TRC20_ADDRESS", "").strip()
OPERATOR_CHAT_ID = os.getenv("OPERATOR_CHAT_ID", "").strip()

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN Render Environment-də təyin edilməyib.")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

bot = Bot(
    BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)
dp = Dispatcher()


class Trade(StatesGroup):
    waiting_buy_amount = State()
    waiting_sell_amount = State()
    waiting_trc20 = State()
    waiting_buy_receipt = State()
    waiting_sell_tx = State()
    waiting_bank = State()
    waiting_card = State()


BANKS = [
    ("m10", "📱 m10"),
    ("kapital", "🏦 Kapital Bank"),
    ("leo", "🟣 Leo Bank"),
    ("abb", "🏛 ABB"),
    ("xalq", "🏦 Xalq Bank"),
    ("yelo", "💛 Yelo Bank"),
    ("other", "➕ Digər bank"),
]


def main_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="🟢 USDT AL"),
                KeyboardButton(text="🔵 USDT SAT"),
            ],
            [
                KeyboardButton(text="📊 Məzənnələr"),
                KeyboardButton(text="ℹ️ Kömək"),
            ],
        ],
        resize_keyboard=True,
        input_field_placeholder="Əməliyyat seçin…",
    )


def confirm_kb(kind: str):
    return InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(
                text="✅ Təsdiqlə",
                callback_data=f"confirm:{kind}",
            ),
            InlineKeyboardButton(
                text="❌ Ləğv et",
                callback_data="cancel",
            ),
        ]]
    )


def banks_kb():
    rows = []
    for i in range(0, len(BANKS), 2):
        row = [
            InlineKeyboardButton(
                text=BANKS[i][1],
                callback_data=f"bank:{BANKS[i][0]}",
            )
        ]
        if i + 1 < len(BANKS):
            row.append(
                InlineKeyboardButton(
                    text=BANKS[i + 1][1],
                    callback_data=f"bank:{BANKS[i + 1][0]}",
                )
            )
        rows.append(row)

    rows.append([
        InlineKeyboardButton(text="❌ Ləğv et", callback_data="cancel")
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def valid_amount(raw: str) -> Decimal | None:
    try:
        amount = Decimal(raw.strip().replace(",", "."))
        if not amount.is_finite() or amount <= 0:
            return None
        if amount > Decimal("1000000"):
            return None
        if amount.as_tuple().exponent < -6:
            return None
        return amount
    except (InvalidOperation, ValueError):
        return None


def money(value: Decimal) -> str:
    return f"{value.quantize(Decimal('0.01')):,.2f}".replace(",", " ")


async def notify_operator(text: str, message: Message | None = None):
    if not OPERATOR_CHAT_ID:
        return

    try:
        # Rəqəmli Telegram chat ID tələb olunur, @username yox.
        operator_id = int(OPERATOR_CHAT_ID)
        await bot.send_message(operator_id, text)

        if message and message.photo:
            await bot.send_photo(
                operator_id,
                message.photo[-1].file_id,
                caption="📎 Müştəri qəbzi — avtomatik təsdiq deyil.",
            )
        elif message and message.document:
            await bot.send_document(
                operator_id,
                message.document.file_id,
                caption="📎 Müştəri faylı — avtomatik təsdiq deyil.",
            )

    except (ValueError, TypeError):
        logging.error(
            "OPERATOR_CHAT_ID rəqəmli Telegram chat ID olmalıdır."
        )
    except Exception:
        logging.exception("Operator bildirişi göndərilmədi")


@dp.message(CommandStart())
async def start(message: Message, state: FSMContext):
    await state.clear()
    name = message.from_user.first_name or "dostum"

    await message.answer(
        f"👋 Salam, <b>{name}</b>!\n\n"
        "🇦🇿 <b>USDT P2P AZ</b> botuna xoş gəlmisiniz.\n"
        "💱 Əməliyyat növünü seçin:\n\n"
        f"🟢 USDT AL — <b>1 USDT = {money(BUY_RATE)} AZN</b>\n"
        f"🔵 USDT SAT — <b>1 USDT = {money(SELL_RATE)} AZN</b>\n\n"
        "⚠️ Ödəniş və kripto köçürməsi faktiki yoxlamadan sonra tamamlanır.",
        reply_markup=main_menu(),
    )


@dp.message(Command("cancel"))
@dp.message(F.text == "❌ Ləğv et")
async def cancel_command(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "❌ Əməliyyat ləğv edildi.",
        reply_markup=main_menu(),
    )


@dp.callback_query(F.data == "cancel")
async def cancel_callback(call: CallbackQuery, state: FSMContext):
    await state.clear()
    if call.message:
        await call.message.answer(
            "❌ Əməliyyat ləğv edildi.",
            reply_markup=main_menu(),
        )
    await call.answer("Ləğv edildi")


@dp.message(F.text == "📊 Məzənnələr")
async def rates(message: Message):
    await message.answer(
        "📊 <b>Cari məzənnələr</b>\n\n"
        f"🟢 Alış: 1 USDT = {money(BUY_RATE)} AZN\n"
        f"🔵 Satış: 1 USDT = {money(SELL_RATE)} AZN\n\n"
        "Məzənnələr Render Environment dəyişənlərindən idarə olunur.",
        reply_markup=main_menu(),
    )


@dp.message(F.text == "ℹ️ Kömək")
async def help_message(message: Message):
    await message.answer(
        "ℹ️ <b>Necə işləyir?</b>\n"
        "1️⃣ Alış və ya satış seçin.\n"
        "2️⃣ USDT miqdarını daxil edin.\n"
        "3️⃣ Məbləği yoxlayıb təsdiqləyin.\n"
        "4️⃣ Ödəniş və köçürmə faktiki yoxlanmalıdır.\n\n"
        "🛡 Telegram kodunuzu, şifrənizi, CVV və PIN kodunuzu paylaşmayın.",
        reply_markup=main_menu(),
    )


@dp.message(F.text == "🟢 USDT AL")
async def buy_start(message: Message, state: FSMContext):
    await state.set_state(Trade.waiting_buy_amount)
    await message.answer(
        f"🟢 <b>USDT AL</b>\n"
        f"Məzənnə: 1 USDT = {money(BUY_RATE)} AZN\n\n"
        "Neçə USDT almaq istəyirsiniz? Məsələn: <code>100</code>"
    )


@dp.message(Trade.waiting_buy_amount)
async def buy_amount(message: Message, state: FSMContext):
    amount = valid_amount(message.text or "")
    if amount is None:
        await message.answer("⚠️ Düzgün müsbət məbləğ yazın.")
        return

    total = amount * BUY_RATE
    await state.update_data(
        kind="buy",
        amount=str(amount),
        total=str(total),
    )
    await message.answer(
        "🧾 <b>Əməliyyat xülasəsi</b>\n\n"
        f"💵 USDT: <b>{amount.normalize()} USDT</b>\n"
        f"💱 Məzənnə: {money(BUY_RATE)} AZN\n"
        f"💳 Ödəniləcək: <b>{money(total)} AZN</b>\n\n"
        "Əməliyyatı təsdiqləyirsiniz?",
        reply_markup=confirm_kb("buy"),
    )


@dp.message(F.text == "🔵 USDT SAT")
async def sell_start(message: Message, state: FSMContext):
    await state.set_state(Trade.waiting_sell_amount)
    await message.answer(
        f"🔵 <b>USDT SAT</b>\n"
        f"Məzənnə: 1 USDT = {money(SELL_RATE)} AZN\n\n"
        "Neçə USDT satmaq istəyirsiniz? Məsələn: <code>100</code>"
    )


@dp.message(Trade.waiting_sell_amount)
async def sell_amount(message: Message, state: FSMContext):
    amount = valid_amount(message.text or "")
    if amount is None:
        await message.answer("⚠️ Düzgün müsbət məbləğ yazın.")
        return

    total = amount * SELL_RATE
    await state.update_data(
        kind="sell",
        amount=str(amount),
        total=str(total),
    )
    await message.answer(
        "🧾 <b>Əməliyyat xülasəsi</b>\n\n"
        f"💵 USDT: <b>{amount.normalize()} USDT</b>\n"
        f"💱 Məzənnə: {money(SELL_RATE)} AZN\n"
        f"💰 Alacağınız: <b>{money(total)} AZN</b>\n\n"
        "Əməliyyatı təsdiqləyirsiniz?",
        reply_markup=confirm_kb("sell"),
    )


@dp.callback_query(F.data.startswith("confirm:"))
async def confirm_trade(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    kind = call.data.split(":", 1)[1]

    if data.get("kind") != kind or not data.get("amount"):
        await call.answer(
            "Əməliyyat tapılmadı. Yenidən başlayın.",
            show_alert=True,
        )
        return

    ref = uuid.uuid4().hex[:10].upper()
    deadline = int(time.time()) + PAYMENT_MINUTES * 60
    await state.update_data(ref=ref, deadline=deadline)

    amount = Decimal(data["amount"])
    total = Decimal(data["total"])

    if kind == "buy":
        await state.set_state(Trade.waiting_buy_receipt)
        await call.message.answer(
            f"🧾 <b>Əməliyyat № {ref}</b>\n\n"
            f"💳 Ödəniləcək: <b>{money(total)} AZN</b>\n"
            f"🏦 Bank məlumatları:\n<code>{BANK_DETAILS}</code>\n\n"
            f"⏳ Ödəniş üçün {PAYMENT_MINUTES} dəqiqə ayrılıb.\n"
            "Ödənişdən sonra qəbzi şəkil və ya fayl kimi göndərin.\n"
            "⚠️ Qəbz avtomatik ödəniş təsdiqi deyil."
        )
    else:
        if not SELL_TRC20_ADDRESS:
            await state.clear()
            await call.message.answer(
                "⚠️ SELL_TRC20_ADDRESS təyin edilməyib. "
                "Bot sahibi Render Environment-də ünvanı əlavə etməlidir.",
                reply_markup=main_menu(),
            )
        else:
            await state.set_state(Trade.waiting_sell_tx)
            await call.message.answer(
                f"🧾 <b>Əməliyyat № {ref}</b>\n\n"
                f"💵 Köçürüləcək: <b>{amount.normalize()} USDT</b>\n"
                "🔗 Şəbəkə: <b>TRON (TRC20)</b>\n"
                f"📥 Ünvan:\n<code>{SELL_TRC20_ADDRESS}</code>\n\n"
                "Köçürmədən sonra TXID göndərin. TXID ayrıca yoxlanmalıdır."
            )

    await notify_operator(
        f"🆕 Yeni {kind.upper()} əməliyyatı #{ref}\n"
        f"User ID: {call.from_user.id}\n"
        f"Məbləğ: {amount} USDT / {money(total)} AZN"
    )
    await call.answer("Əməliyyat yaradıldı")


@dp.message(Trade.waiting_buy_receipt, F.photo | F.document)
async def buy_receipt(message: Message, state: FSMContext):
    data = await state.get_data()
    if not data.get("deadline") or time.time() > data["deadline"]:
        await state.clear()
        await message.answer(
            "⌛ Ödəniş vaxtı bitib. Yeni əməliyyat başlada bilərsiniz.",
            reply_markup=main_menu(),
        )
        return

    ref = data.get("ref", "N/A")
    await notify_operator(
        f"📎 Alış əməliyyatı #{ref} üçün qəbz göndərildi.\n"
        f"User ID: {message.from_user.id}\n"
        "Status: yoxlama gözləyir; avtomatik təsdiq edilməyib.",
        message,
    )
    await message.answer(
        f"📩 Qəbz qəbul edildi. Əməliyyat № <code>{ref}</code>\n\n"
        "Ödənişin bank hesabına faktiki daxil olması yoxlanmalıdır."
    )


@dp.message(Trade.waiting_sell_tx)
async def sell_tx(message: Message, state: FSMContext):
    txid = (message.text or "").strip()
    if len(txid) < 20 or len(txid) > 150 or any(c.isspace() for c in txid):
        await message.answer("🔎 Düzgün TXID/hash məlumatını göndərin.")
        return

    data = await state.get_data()
    ref = data.get("ref", "N/A")
    await state.update_data(txid=txid)
    await notify_operator(
        f"🔗 Satış əməliyyatı #{ref} üçün TXID alındı.\n"
        f"User ID: {message.from_user.id}\nTXID: {txid}\n"
        "Status: blokçeyndə yoxlanmalıdır."
    )
    await state.set_state(Trade.waiting_bank)
    await message.answer(
        "🔎 TXID qəbul edildi, lakin avtomatik blokçeyn təsdiqi aktiv deyil.\n"
        "🏦 AZN ödənişi üçün bankınızı seçin:",
        reply_markup=banks_kb(),
    )


@dp.callback_query(F.data.startswith("bank:"))
async def choose_bank(call: CallbackQuery, state: FSMContext):
    bank_key = call.data.split(":", 1)[1]
    bank_name = dict(BANKS).get(bank_key, "Digər bank")
    await state.update_data(bank=bank_name)
    await state.set_state(Trade.waiting_card)
    await call.message.answer(
        f"🏦 Seçilən bank: <b>{bank_name}</b>\n\n"
        "💳 Kart nömrənizi daxil edin.\n"
        "🔐 CVV, PIN, SMS kodu və bank tətbiqi şifrəsini göndərməyin."
    )
    await call.answer()


@dp.message(Trade.waiting_card)
async def receive_card(message: Message, state: FSMContext):
    raw = (message.text or "").replace(" ", "").replace("-", "")
    if not raw.isdigit() or not 12 <= len(raw) <= 19:
        await message.answer("⚠️ Kart nömrəsinin formatını yoxlayın.")
        return

    data = await state.get_data()
    ref = data.get("ref", "N/A")
    await notify_operator(
        f"💳 Satış əməliyyatı #{ref}: bank rekviziti daxil edildi.\n"
        f"User ID: {message.from_user.id}\n"
        f"Bank: {data.get('bank', 'N/A')}\n"
        f"Kart nömrəsi: **** **** **** {raw[-4:]}\n"
        f"Məbləğ: {money(Decimal(data.get('total', '0')))} AZN\n"
        "Status: TXID və ödəniş yoxlanmalıdır."
    )
    await state.clear()
    await message.answer(
        f"📨 Məlumat qəbul edildi. Əməliyyat № <code>{ref}</code>\n\n"
        "Köçürmə yalnız USDT daxil olması təsdiqləndikdən sonra həyata keçirilə bilər.",
        reply_markup=main_menu(),
    )


@dp.message()
async def fallback(message: Message):
    await message.answer(
        "🙂 Zəhmət olmasa, menyudakı düymələrdən birini seçin.",
        reply_markup=main_menu(),
    )


async def health(request: web.Request):
    return web.Response(text="USDT P2P AZ bot is running", status=200)


async def main():
    # Render Web Service-in PORT dəyişənində verdiyi portu açırıq.
    app = web.Application()
    app.router.add_get("/", health)
    app.router.add_get("/health", health)

    runner = web.AppRunner(app)
    await runner.setup()

    port = int(os.getenv("PORT", "10000"))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logging.info("HTTP server started on port %s", port)

    try:
        await dp.start_polling(bot)
    finally:
        await runner.cleanup()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())

