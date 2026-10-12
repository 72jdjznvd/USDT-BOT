import os
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
Message,
CallbackQuery,
InlineKeyboardMarkup,
InlineKeyboardButton,
)

from database import create_order, get_user, set_txid, set_bank
from services.i18n import get_text

router = Router()

SELL_RATE = Decimal(os.getenv("SELL_RATE", "1.69"))
SELL_TRC20_ADDRESS = os.getenv("SELL_TRC20_ADDRESS", "")
ADMIN_IDS = {
int(value.strip())
for value in os.getenv("ADMIN_IDS", "").split(",")
if value.strip().isdigit()
}

class SellStates(StatesGroup):
waiting_amount = State()
waiting_txid = State()
waiting_payout_method = State()

def cancel_keyboard(language: str):
label = "❌ Отмена" if language == "ru" else "❌ Ləğv et"
return InlineKeyboardMarkup(
inline_keyboard=[
[InlineKeyboardButton(text=label, callback_data="sell:cancel")]
]
)

def payout_keyboard(language: str):
if language == "ru":
bank_label = "🏦 Банковская карта"
m10_label = "📱 m10"
else:
bank_label = "🏦 Bank kartı"
m10_label = "📱 m10"

return InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(
                text=bank_label,
                callback_data="sell:payout:bank",
            ),
            InlineKeyboardButton(
                text=m10_label,
                callback_data="sell:payout:m10",
            ),
        ],
        [
            InlineKeyboardButton(
                text="❌ Отмена" if language == "ru" else "❌ Ləğv et",
                callback_data="sell:cancel",
            )
        ],
    ]
)

@router.message(F.text.in_({"🔵 USDT SAT", "🔵 ПРОДАТЬ USDT"}))
async def start_sell(message: Message, state: FSMContext):
user = message.from_user
if not user:
return

profile = await get_user(user.id)
language = (
    profile["language"]
    if profile and profile.get("language") in ("az", "ru")
    else "az"
)

await state.clear()
await state.set_state(SellStates.waiting_amount)

prompt = (
    "💵 Введите количество USDT для продажи. Например: 100"
    if language == "ru"
    else "💵 Satmaq istədiyiniz USDT məbləğini daxil edin. Məsələn: 100"
)
await message.answer(prompt, reply_markup=cancel_keyboard(language))

@router.message(SellStates.waiting_amount)
async def receive_sell_amount(message: Message, state: FSMContext):
user = message.from_user
if not user or not message.text:
return

profile = await get_user(user.id)
language = (
    profile["language"]
    if profile and profile.get("language") in ("az", "ru")
    else "az"
)

try:
    amount = Decimal(message.text.strip().replace(",", "."))
    if not amount.is_finite() or amount <= 0 or amount > Decimal("1000000"):
        raise InvalidOperation
    amount = amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
except (InvalidOperation, ValueError):
    text = (
        "⚠️ Введите корректную сумму больше нуля."
        if language == "ru"
        else "⚠️ Sıfırdan böyük düzgün məbləğ daxil edin."
    )
    await message.answer(text, reply_markup=cancel_keyboard(language))
    return

total = (amount * SELL_RATE).quantize(
    Decimal("0.01"),
    rounding=ROUND_HALF_UP,
)

await state.update_data(amount=str(amount), total=str(total))
await state.set_state(SellStates.waiting_txid)

if not SELL_TRC20_ADDRESS:
    await message.answer(
        "⚠️ TRC20 ünvanı administrator tərəfindən təyin edilməyib."
        if language == "az"
        else "⚠️ Администратор ещё не указал TRC20-адрес."
    )
    await state.clear()
    return

if language == "ru":
    text = (
        "🔵 Продажа USDT\n\n"
        f"💵 Количество: {amount} USDT\n"
        f"💱 Курс: {SELL_RATE} AZN\n"
        f"💰 Ожидаемая сумма: {total} AZN\n\n"
        "Отправьте USDT в сети TRON (TRC20) на адрес ниже:\n"
        f"`{SELL_TRC20_ADDRESS}`\n\n"
        "После отправки пришлите TXID транзакции.\n"
        "⚠️ Сначала проверьте адрес и сеть. TXID сам по себе не подтверждает оплату."
    )
else:
    text = (
        "🔵 USDT satış sifarişi\n\n"
        f"💵 Miqdar: {amount} USDT\n"
        f"💱 Məzənnə: {SELL_RATE} AZN\n"
        f"💰 Gözlənilən məbləğ: {total} AZN\n\n"
        "USDT-ni TRON (TRC20) şəbəkəsində aşağıdakı ünvana göndərin:\n"
        f"`{SELL_TRC20_ADDRESS}`\n\n"
        "Köçürmədən sonra tranzaksiyanın TXID-sini göndərin.\n"
        "⚠️ Ünvanı və şəbəkəni əvvəlcədən yoxlayın. TXID təkbaşına ödənişi təsdiqləmir."
    )

await message.answer(
    text,
    parse_mode="Markdown",
    reply_markup=cancel_keyboard(language),
)

@router.message(SellStates.waiting_txid)
async def receive_sell_txid(message: Message, state: FSMContext):
user = message.from_user
if not user or not message.text:
return

txid = message.text.strip()
if len(txid) < 20 or len(txid) > 150 or any(ch.isspace() for ch in txid):
    profile = await get_user(user.id)
    language = (
        profile["language"]
        if profile and profile.get("language") in ("az", "ru")
        else "az"
    )
    await message.answer(
        "⚠️ Отправьте корректный TXID без пробелов."
        if language == "ru"
        else "⚠️ Düzgün TXID göndərin, boşluq olmamalıdır.",
        reply_markup=cancel_keyboard(language),
    )
    return

data = await state.get_data()
amount = Decimal(data["amount"])
total = Decimal(data["total"])
order_ref = data.get("order_ref")

if not order_ref:
    import secrets
    order_ref = f"SELL-{secrets.token_hex(4).upper()}"

    try:
        await create_order(
            order_ref=order_ref,
            telegram_id=user.id,
            kind="sell",
            amount=amount,
            rate=SELL_RATE,
            total=total,
            currency="AZN",
            payment_method="pending_payout_method",
        )
    except Exception:
        await message.answer(
            "Sifariş yaradıla bilmədi. Bir az sonra yenidən cəhd edin."
        )
        return

    await state.update_data(order_ref=order_ref)

try:
    updated = await set_txid(order_ref, txid)
except Exception:
    updated = False

if not updated:
    await message.answer(
        "TXID qeydə alınmadı. Bu TXID daha əvvəl istifadə edilmiş ola bilər. "
        "Administratorla əlaqə saxlayın."
    )
    return

await state.update_data(txid=txid)
await state.set_state(SellStates.waiting_payout_method)

profile = await get_user(user.id)
language = (
    profile["language"]
    if profile and profile.get("language") in ("az", "ru")
    else "az"
)

text = (
    "Выберите способ получения AZN:"
    if language == "ru"
    else "AZN məbləğini almaq üçün üsulu seçin:"
)
await message.answer(text, reply_markup=payout_keyboard(language))

@router.callback_query(F.data.startswith("sell:payout:"))
async def choose_payout_method(callback: CallbackQuery, state: FSMContext):
user = callback.from_user
data = await state.get_data()

if await state.get_state() != SellStates.waiting_payout_method.state:
    await callback.answer("Aktiv sifariş tapılmadı.", show_alert=True)
    return

order_ref = data.get("order_ref")
method = callback.data.rsplit(":", 1)[-1]

if method not in ("bank", "m10") or not order_ref:
    await callback.answer("Seçim etibarsızdır.", show_alert=True)
    return

try:
    updated = await set_bank(order_ref, method)
except Exception:
    updated = False

if not updated:
    await callback.answer(
        "Məlumat saxlanılmadı. Administratorla əlaqə saxlayın.",
        show_alert=True,
    )
    return

await callback.answer()

profile = await get_user(user.id)
language = (
    profile["language"]
    if profile and profile.get("language") in ("az", "ru")
    else "az"
)

if language == "ru":
    text = (
        f"✅ Заказ {order_ref} отправлен на проверку.\n"
        "Администратор проверит транзакцию в блокчейне и сообщит результат.\n"
        "TXID и скриншот не являются подтверждением получения USDT."
    )
else:
    text = (
        f"✅ {order_ref} sifarişi yoxlamaya göndərildi.\n"
        "Administrator tranzaksiyanı blokçeyndə yoxlayıb nəticəni bildirəcək.\n"
        "TXID və ekran görüntüsü USDT-nin daxil olduğunu təsdiqləmir."
    )

if callback.message:
    await callback.message.answer(text)

for admin_id in ADMIN_IDS:
    try:
        await callback.bot.send_message(
            admin_id,
            "🔵 Yeni USDT satış sifarişi — yoxlama tələb olunur.\n"
            f"Sifariş: {order_ref}\n"
            f"İstifadəçi: {user.full_name}\n"
            f"Username: @{user.username if user.username else 'yoxdur'}\n"
            f"Telegram ID: {user.id}\n"
            f"Miqdar: {data.get('amount')} USDT\n"
            f"Gözlənilən AZN: {data.get('total')}\n"
            f"TXID: {data.get('txid')}\n"
            f"Ödəniş üsulu: {method}",
            disable_web_page_preview=True,
        )
    except Exception:
        pass

await state.clear()

@router.callback_query(F.data == "sell:cancel")
async def cancel_sell(callback: CallbackQuery, state: FSMContext):
await state.clear()
await callback.answer()

profile = await get_user(callback.from_user.id)
language = (
    profile["language"]
    if profile and profile.get("language") in ("az", "ru")
    else "az"
)

text = "❌ Заказ отменён." if language == "ru" else "❌ Sifariş ləğv edildi."
if callback.message:
    await callback.message.answer(text)
