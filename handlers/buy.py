import os
import logging
import uuid
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

from database import (
    create_order,
    get_order,
    set_receipt,
    get_user,
)
from services.i18n import get_text

router = Router()
logger = logging.getLogger(__name__)

ADMIN_IDS = {
    int(value.strip())
    for value in os.getenv("ADMIN_IDS", "").split(",")
    if value.strip().isdigit()
}

BUY_RATE = Decimal(os.getenv("BUY_RATE", "1.70"))
PAYMENT_MINUTES = int(os.getenv("PAYMENT_MINUTES", "15"))

BANK_DETAILS = os.getenv(
    "BANK_DETAILS",
    "Ödəniş rekvizitləri administrator tərəfindən əlavə edilməlidir.",
)
M10_DETAILS = os.getenv(
    "M10_DETAILS",
    "M10 rekvizitləri administrator tərəfindən əlavə edilməlidir.",
)


class BuyStates(StatesGroup):
    waiting_amount = State()
    waiting_confirmation = State()
    waiting_receipt = State()


def money(value: Decimal) -> str:
    return str(
        value.quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )
    )


def buy_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Təsdiqlə",
                    callback_data="buy:confirm",
                ),
                InlineKeyboardButton(
                    text="❌ Ləğv et",
                    callback_data="buy:cancel",
                ),
            ]
        ]
    )


def receipt_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="❌ Sifarişi ləğv et",
                    callback_data="buy:cancel",
                )
            ]
        ]
    )


def payment_text(total: Decimal) -> str:
    return (
        "💳 <b>Ödəniş məlumatları</b>\n\n"
        f"Ödəniləcək məbləğ: <b>{money(total)} AZN</b>\n\n"
        "<b>Bank köçürməsi:</b>\n"
        f"{BANK_DETAILS}\n\n"
        "<b>M10:</b>\n"
        f"{M10_DETAILS}\n\n"
        f"⏳ Ödəniş üçün ayrılmış vaxt: {PAYMENT_MINUTES} dəqiqə.\n\n"
        "Ödəniş etdikdən sonra qəbzin şəklini və ya sənədini "
        "bu söhbətə göndər."
    )


@router.message(Command("buy"))
async def start_buy(message: Message, state: FSMContext):
    user = await get_user(message.from_user.id)

    if user is None:
        await message.answer(
            "Əvvəlcə /start yazaraq botda qeydiyyatdan keç."
        )
        return

    await state.clear()
    await state.set_state(BuyStates.waiting_amount)

    await message.answer(
        "🟢 <b>USDT almaq</b>\n\n"
        f"Alış məzənnəsi: 1 USDT = {BUY_RATE} AZN\n\n"
        "Almaq istədiyin USDT miqdarını rəqəmlə göndər.\n"
        "Məsələn: <code>100</code>"
    )


@router.message(BuyStates.waiting_amount)
async def process_buy_amount(
    message: Message,
    state: FSMContext,
):
    raw_amount = (message.text or "").strip().replace(",", ".")

    try:
        amount = Decimal(raw_amount)
    except InvalidOperation:
        await message.answer(
            "Məbləği düzgün yaz. Məsələn: 100 və ya 50.5"
        )
        return

    if not amount.is_finite() or amount <= 0:
        await message.answer(
            "Məbləğ sıfırdan böyük olmalıdır."
        )
        return

    if amount > Decimal("1000000"):
        await message.answer(
            "Məbləğ çox böyükdür. Administratorla əlaqə saxla."
        )
        return

    total = (amount * BUY_RATE).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )

    await state.update_data(
        amount=str(amount),
        rate=str(BUY_RATE),
        total=str(total),
    )

    await state.set_state(BuyStates.waiting_confirmation)

    await message.answer(
        "📋 <b>Sifariş məlumatları</b>\n\n"
        f"USDT miqdarı: <b>{amount} USDT</b>\n"
        f"Alış məzənnəsi: <b>{BUY_RATE} AZN</b>\n"
        f"Ümumi ödəniş: <b>{money(total)} AZN</b>\n\n"
        "Davam etmək istəyirsən?",
        reply_markup=buy_keyboard(),
    )


@router.callback_query(F.data == "buy:cancel")
async def cancel_buy(
    callback: CallbackQuery,
    state: FSMContext,
):
    await state.clear()

    await callback.answer("Sifariş ləğv edildi.")

    if callback.message:
        await callback.message.edit_text(
            "❌ Sifariş prosesi dayandırıldı.\n"
            "Yeni sifariş üçün /buy yaz."
        )


@router.callback_query(
    F.data == "buy:confirm",
    BuyStates.waiting_confirmation,
)
async def confirm_buy(
    callback: CallbackQuery,
    state: FSMContext,
):
    if callback.from_user is None or callback.message is None:
        await callback.answer()
        return

    data = await state.get_data()

    if not all(key in data for key in ("amount", "rate", "total")):
        await state.clear()
        await callback.answer(
            "Sifariş məlumatları tapılmadı. Yenidən başla.",
            show_alert=True,
        )
        return

    amount = Decimal(data["amount"])
    rate = Decimal(data["rate"])
    total = Decimal(data["total"])

    order_ref = f"BUY-{uuid.uuid4().hex[:8].upper()}"

    try:
        await create_order(
            order_ref=order_ref,
            telegram_id=callback.from_user.id,
            kind="buy",
            amount=amount,
            rate=rate,
            total=total,
            currency="AZN",
            payment_method="bank_or_m10",
        )
    except Exception:
        logger.exception("Alış sifarişi yaradılmadı.")
        await callback.answer(
            "Sifariş yaradıla bilmədi. Bir az sonra yenidən yoxla.",
            show_alert=True,
        )
        return

    await state.update_data(order_ref=order_ref)
    await state.set_state(BuyStates.waiting_receipt)

    await callback.answer("Sifariş yaradıldı.")

    await callback.message.edit_text(
        f"🧾 Sifariş nömrəsi: <code>{order_ref}</code>\n\n"
        + payment_text(total),
        reply_markup=receipt_keyboard(),
    )


@router.message(BuyStates.waiting_receipt, F.photo)
async def process_receipt_photo(
    message: Message,
    state: FSMContext,
):
    file_id = message.photo[-1].file_id
    await save_and_notify_receipt(
        message=message,
        state=state,
        file_id=file_id,
        file_type="photo",
    )


@router.message(BuyStates.waiting_receipt, F.document)
async def process_receipt_document(
    message: Message,
    state: FSMContext,
):
    file_id = message.document.file_id

    await save_and_notify_receipt(
        message=message,
        state=state,
        file_id=file_id,
        file_type="document",
    )


async def save_and_notify_receipt(
    message: Message,
    state: FSMContext,
    file_id: str,
    file_type: str,
):
    data = await state.get_data()
    order_ref = data.get("order_ref")

    if not order_ref:
        await state.clear()
        await message.answer(
            "Sifariş nömrəsi tapılmadı. Yeni sifariş üçün /buy yaz."
        )
        return

    order = await get_order(order_ref)

    if not order or order.get("telegram_id") != message.from_user.id:
        await message.answer(
            "Sifariş tapılmadı və ya bu sifariş sənə aid deyil."
        )
        await state.clear()
        return

    saved = await set_receipt(
        order_ref,
        file_id,
        file_type=file_type,
    )

    if not saved:
        await message.answer(
            "Qəbz saxlanmadı. Sifariş artıq işlənmiş ola bilər. "
            "Administratorla əlaqə saxla."
        )
        await state.clear()
        return

    await message.answer(
        "✅ Qəbz qəbul edildi.\n\n"
        f"Sifariş: <code>{order_ref}</code>\n"
        "Status: <b>Yoxlanılır</b>\n\n"
        "Administrator ödənişi yoxladıqdan sonra məlumat veriləcək."
    )

    # Qəbzi administratorlara ilkin bildirişdə düzgün növdə göndər.
    for admin_id in ADMIN_IDS:
        try:
            await message.bot.send_message(
                admin_id,
                "🔔 <b>Yeni alış qəbzi</b>\n\n"
                f"Sifariş: <code>{order_ref}</code>\n"
                f"İstifadəçi ID: <code>{message.from_user.id}</code>\n"
                f"USDT: <b>{order.get('amount', data.get('amount'))}</b>\n"
                f"Məbləğ: <b>{order.get('total', data.get('total'))} AZN</b>\n"
                f"Qəbz növü: <b>{file_type}</b>\n\n"
                "Qəbzi aşağıdakı mesajda yoxla.",
            )

            await message.bot.copy_message(
                chat_id=admin_id,
                from_chat_id=message.chat.id,
                message_id=message.message_id,
            )

        except Exception:
            logger.exception(
                "Qəbz administratora göndərilmədi: admin_id=%s",
                admin_id,
            )

    await state.clear()


@router.message(BuyStates.waiting_receipt)
async def receipt_required(message: Message):
    await message.answer(
        "Sifarişi davam etdirmək üçün ödəniş qəbzini "
        "foto və ya sənəd kimi göndər."
)
