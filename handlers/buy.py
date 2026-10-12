import os
import secrets
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

from database import create_order, get_order, set_receipt
from services.i18n import get_text

router = Router()

BUY_RATE = Decimal(os.getenv("BUY_RATE", "1.70"))
PAYMENT_MINUTES = int(os.getenv("PAYMENT_MINUTES", "15"))
BANK_DETAILS = os.getenv("BANK_DETAILS", "")
M10_DETAILS = os.getenv("M10_DETAILS", "")
ADMIN_IDS = {
int(value.strip())
for value in os.getenv("ADMIN_IDS", "").split(",")
if value.strip().isdigit()
}

class BuyStates(StatesGroup):
waiting_amount = State()
waiting_confirmation = State()
waiting_receipt = State()

def amount_keyboard(language: str) -> InlineKeyboardMarkup:
label = "❌ Отмена" if language == "ru" else "❌ Ləğv et"
return InlineKeyboardMarkup(
inline_keyboard=[
[InlineKeyboardButton(text=label, callback_data="buy:cancel")]
]
)

def confirm_keyboard(language: str) -> InlineKeyboardMarkup:
yes = "✅ Подтвердить" if language == "ru" else "✅ Təsdiqlə"
no = "❌ Отмена" if language == "ru" else "❌ Ləğv et"

return InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(
                text=yes,
                callback_data="buy:confirm",
            ),
            InlineKeyboardButton(
                text=no,
                callback_data="buy:cancel",
            ),
        ]
    ]
)

def payment_text(language: str) -> str:
if language == "ru":
text = (
"💳 Реквизиты для оплаты\n\n"
"Переведите точную сумму, указанную в заказе.\n"
)
if BANK_DETAILS:
text += f"\n🏦 Банк:\n{BANK_DETAILS}\n"
if M10_DETAILS:
text += f"\n📱 m10:\n{M10_DETAILS}\n"
text += (
f"\n⏳ Время на оплату: {PAYMENT_MINUTES} мин.\n"
"После оплаты отправьте чек фотографией или документом.\n"
"Не отправляйте PIN-код, CVV или SMS-коды."
)
return text

text = (
    "💳 Ödəniş məlumatları\n\n"
    "Sifarişdə göstərilən dəqiq məbləği köçürün.\n"
)
if BANK_DETAILS:
    text += f"\n🏦 Bank məlumatları:\n{BANK_DETAILS}\n"
if M10_DETAILS:
    text += f"\n📱 m10 məlumatları:\n{M10_DETAILS}\n"
text += (
    f"\n⏳ Ödəniş üçün vaxt: {PAYMENT_MINUTES} dəqiqə\n"
    "Ödənişdən sonra qəbzi şəkil və ya sənəd kimi göndərin.\n"
    "PIN, CVV və SMS kodlarını göndərməyin."
)
return text

@router.message(F.text.in_({"🟢 USDT AL", "🟢 КУПИТЬ USDT"}))
async def start_buy(message: Message, state: FSMContext):
user = message.from_user
if not user:
return

db_user = await get_order("__language_lookup_not_an_order__")
# Language is read from the users table by the helper below.
from database import get_user
profile = await get_user(user.id)
language = profile["language"] if profile and profile.get("language") in ("az", "ru") else "az"

await state.clear()
await state.set_state(BuyStates.waiting_amount)
prompt = (
    "💵 Введите сумму USDT для покупки. Например: 100"
    if language == "ru"
    else "💵 Almaq istədiyiniz USDT məbləğini daxil edin. Məsələn: 100"
)
await message.answer(prompt, reply_markup=amount_keyboard(language))

@router.message(BuyStates.waiting_amount)
async def receive_buy_amount(message: Message, state: FSMContext):
user = message.from_user
if not user or not message.text:
return

from database import get_user
profile = await get_user(user.id)
language = profile["language"] if profile and profile.get("language") in ("az", "ru") else "az"

try:
    raw = message.text.strip().replace(",", ".")
    amount = Decimal(raw)
    if not amount.is_finite() or amount <= 0 or amount > Decimal("1000000"):
        raise InvalidOperation
    amount = amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
except (InvalidOperation, ValueError):
    text = (
        "⚠️ Введите корректную сумму больше нуля."
        if language == "ru"
        else "⚠️ Sıfırdan böyük düzgün məbləğ daxil edin."
    )
    await message.answer(text, reply_markup=amount_keyboard(language))
    return

total = (amount * BUY_RATE).quantize(
    Decimal("0.01"),
    rounding=ROUND_HALF_UP,
)

await state.update_data(amount=str(amount), total=str(total))
await state.set_state(BuyStates.waiting_confirmation)

if language == "ru":
    text = (
        "🧾 Проверьте заказ:\n\n"
        f"💵 Количество: {amount} USDT\n"
        f"💱 Курс: {BUY_RATE} AZN\n"
        f"💰 К оплате: {total} AZN\n\n"
        "Создать заказ?"
    )
else:
    text = (
        "🧾 Sifarişi yoxlayın:\n\n"
        f"💵 Miqdar: {amount} USDT\n"
        f"💱 Məzənnə: {BUY_RATE} AZN\n"
        f"💰 Ödəniləcək məbləğ: {total} AZN\n\n"
        "Sifariş yaradılsın?"
    )

await message.answer(text, reply_markup=confirm_keyboard(language))

@router.callback_query(F.data == "buy:confirm")
async def confirm_buy(callback: CallbackQuery, state: FSMContext):
user = callback.from_user
data = await state.get_data()

if await state.get_state() != BuyStates.waiting_confirmation.state:
    await callback.answer("Bu sifariş artıq aktiv deyil.", show_alert=True)
    return

if not data.get("amount") or not data.get("total"):
    await callback.answer("Məlumat tapılmadı. Yenidən başlayın.", show_alert=True)
    await state.clear()
    return

amount = Decimal(data["amount"])
total = Decimal(data["total"])
order_ref = f"BUY-{secrets.token_hex(4).upper()}"

try:
    await create_order(
        order_ref=order_ref,
        telegram_id=user.id,
        kind="buy",
        amount=amount,
        rate=BUY_RATE,
        total=total,
        currency="AZN",
        payment_method="bank_or_m10",
    )
except Exception:
    await callback.answer(
        "Sifariş yaradıla bilmədi. Bir az sonra yenidən cəhd edin.",
        show_alert=True,
    )
    return

await state.update_data(order_ref=order_ref)
await state.set_state(BuyStates.waiting_receipt)
await callback.answer()

language = "az"
from database import get_user
profile = await get_user(user.id)
if profile and profile.get("language") in ("az", "ru"):
    language = profile["language"]

if callback.message:
    await callback.message.answer(
        get_text(language, "order_created", order_ref=order_ref)
        + "\n\n"
        + payment_text(language)
    )

@router.message(BuyStates.waiting_receipt, F.photo)
async def receive_buy_photo(message: Message, state: FSMContext):
photo = message.photo[-1]
await process_receipt(message, state, photo.file_id)

@router.message(BuyStates.waiting_receipt, F.document)
async def receive_buy_document(message: Message, state: FSMContext):
document = message.document
if not document:
return
await process_receipt(message, state, document.file_id)

async def process_receipt(message: Message, state: FSMContext, file_id: str):
user = message.from_user
data = await state.get_data()
order_ref = data.get("order_ref")

if not user or not order_ref:
    await message.answer("Aktiv sifariş tapılmadı. /start yazın.")
    await state.clear()
    return

try:
    updated = await set_receipt(order_ref, file_id)
except Exception:
    updated = False

if not updated:
    await message.answer(
        "Qəbz qeydə alınmadı. Sifariş statusunu administrator yoxlamalıdır."
    )
    return

from database import get_user
profile = await get_user(user.id)
language = profile["language"] if profile and profile.get("language") in ("az", "ru") else "az"

await message.answer(
    "📩 Чек отправлен на проверку администратору."
    if language == "ru"
    else "📩 Qəbz administratorun yoxlamasına göndərildi."
)

for admin_id in ADMIN_IDS:
    try:
        await message.bot.send_message(
            admin_id,
            "🧾 Новая покупка USDT — проверьте заказ."
            if language == "ru"
            else "🧾 Yeni USDT alış sifarişi — qəbzi yoxlayın."
        )
        await message.bot.send_message(
            admin_id,
            f"Заказ / Sifariş: {order_ref}\n"
            f"Ad / Имя: {user.full_name}\n"
            f"Username: @{user.username if user.username else 'yoxdur'}\n"
            f"Telegram ID: {user.id}"
        )
        await message.bot.send_document(
            admin_id,
            file_id,
            caption=f"Qəbz / Чек: {order_ref}",
        )
    except Exception:
        pass

await state.clear()

@router.callback_query(F.data == "buy:cancel")
async def cancel_buy(callback: CallbackQuery, state: FSMContext):
await state.clear()
await callback.answer()

language = "az"
from database import get_user
profile = await get_user(callback.from_user.id)
if profile and profile.get("language") in ("az", "ru"):
    language = profile["language"]

text = "❌ Заказ отменён." if language == "ru" else "❌ Sifariş ləğv edildi."
if callback.message:
    await callback.message.answer(text)
