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
    get_user,
    create_order,
    get_order,
    set_txid,
    set_bank,
)

router = Router()
logger = logging.getLogger(__name__)

ADMIN_IDS = {
    int(value.strip())
    for value in os.getenv("ADMIN_IDS", "").split(",")
    if value.strip().isdigit()
}

SELL_RATE = Decimal(os.getenv("SELL_RATE", "1.65"))


class SellStates(StatesGroup):
    waiting_amount = State()
    waiting_txid = State()
    waiting_method = State()
    waiting_details = State()
    waiting_confirmation = State()


def money(value: Decimal) -> str:
    return str(
        value.quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )
    )


def payment_method_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🏦 Bank kartı",
                    callback_data="sell:method:bank",
                )
            ],
            [
                InlineKeyboardButton(
                    text="📱 M10",
                    callback_data="sell:method:m10",
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ Ləğv et",
                    callback_data="sell:cancel",
                )
            ],
        ]
    )


def confirm_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Təsdiqlə",
                    callback_data="sell:confirm",
                ),
                InlineKeyboardButton(
                    text="❌ Ləğv et",
                    callback_data="sell:cancel",
                ),
            ]
        ]
    )


@router.message(Command("sell"))
async def start_sell(message: Message, state: FSMContext):
    user = await get_user(message.from_user.id)

    if user is None:
        await message.answer(
            "Əvvəlcə /start yazaraq botda qeydiyyatdan keç."
        )
        return

    await state.clear()
    await state.set_state(SellStates.waiting_amount)

    await message.answer(
        "🔵 <b>USDT satışı</b>\n\n"
        f"Satış məzənnəsi: 1 USDT = {SELL_RATE} AZN\n\n"
        "Satmaq istədiyin USDT miqdarını yaz.\n"
        "Məsələn: <code>100</code>"
    )


@router.message(SellStates.waiting_amount)
async def process_sell_amount(
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
            "USDT miqdarı sıfırdan böyük olmalıdır."
        )
        return

    if amount > Decimal("1000000"):
        await message.answer(
            "Məbləğ çox böyükdür. Administratorla əlaqə saxla."
        )
        return

    total = (amount * SELL_RATE).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )

    await state.update_data(
        amount=str(amount),
        rate=str(SELL_RATE),
        total=str(total),
    )

    await state.set_state(SellStates.waiting_txid)

    await message.answer(
        "🔗 <b>USDT köçürməsini yoxlamaq</b>\n\n"
        f"Satış miqdarı: <b>{amount} USDT</b>\n"
        f"Təxmini ödəniş: <b>{money(total)} AZN</b>\n\n"
        "USDT-ni göndərmisənsə, əməliyyatın TXID-ni göndər.\n"
        "TXID blokçeyndəki əməliyyat identifikatorudur.\n\n"
        "⚠️ TXID təkbaşına ödənişin uğurlu olduğunu sübut etmir. "
        "Şəbəkə, ünvan və məbləğ ayrıca yoxlanmalıdır."
    )


@router.message(SellStates.waiting_txid)
async def process_sell_txid(
    message: Message,
    state: FSMContext,
):
    txid = (message.text or "").strip()

    if not txid or len(txid) > 200:
        await message.answer(
            "TXID formatını yoxla və yenidən göndər."
        )
        return

    if any(character.isspace() for character in txid):
        await message.answer(
            "TXID daxilində boşluq olmamalıdır."
        )
        return

    await state.update_data(txid=txid)
    await state.set_state(SellStates.waiting_method)

    await message.answer(
        "💳 <b>Pulu hansı üsulla almaq istəyirsən?</b>",
        reply_markup=payment_method_keyboard(),
    )


@router.callback_query(F.data == "sell:cancel")
async def cancel_sell(
    callback: CallbackQuery,
    state: FSMContext,
):
    await state.clear()
    await callback.answer("Satış prosesi ləğv edildi.")

    if callback.message:
        await callback.message.edit_text(
            "❌ Satış prosesi dayandırıldı.\n"
            "Yenidən başlamaq üçün /sell yaz."
        )


@router.callback_query(
    F.data.startswith("sell:method:"),
    SellStates.waiting_method,
)
async def select_sell_method(
    callback: CallbackQuery,
    state: FSMContext,
):
    if callback.message is None:
        await callback.answer()
        return

    method_code = callback.data.rsplit(":", 1)[-1]

    methods = {
        "bank": "Bank kartı",
        "m10": "M10",
    }

    method = methods.get(method_code)

    if method is None:
        await callback.answer("Ödəniş üsulu düzgün deyil.", show_alert=True)
        return

    await state.update_data(payment_method=method)
    await state.set_state(SellStates.waiting_details)

    await callback.answer()

    await callback.message.edit_text(
        f"💳 Seçilən üsul: <b>{method}</b>\n\n"
        "Pul qəbul etmək üçün məlumatını göndər.\n"
        "Bank seçmisənsə, kart sahibinin adını və kart məlumatını; "
        "M10 seçmisənsə, uyğun hesab məlumatını daxil et.\n\n"
        "⚠️ PIN, CVV, SMS kodu və bank şifrəsini göndərmə."
    )


@router.message(SellStates.waiting_details)
async def process_sell_details(
    message: Message,
    state: FSMContext,
):
    details = (message.text or "").strip()

    if len(details) < 3 or len(details) > 500:
        await message.answer(
            "Məlumat 3–500 simvol arasında olmalıdır."
        )
        return

    await state.update_data(payout_details=details)
    data = await state.get_data()

    await state.set_state(SellStates.waiting_confirmation)

    await message.answer(
        "📋 <b>Satış sifarişini yoxla</b>\n\n"
        f"USDT: <b>{data['amount']}</b>\n"
        f"Məzənnə: <b>{data['rate']} AZN</b>\n"
        f"Təxmini ödəniş: <b>{data['total']} AZN</b>\n"
        f"Ödəniş üsulu: <b>{data['payment_method']}</b>\n\n"
        "Məlumatların düzgün olduğuna əmin ol. "
        "Davam etdikdə sifariş administrator yoxlamasına göndəriləcək.\n\n"
        "Kart məlumatlarını qrupda paylaşma.",
        reply_markup=confirm_keyboard(),
    )


@router.callback_query(
    F.data == "sell:confirm",
    SellStates.waiting_confirmation,
)
async def confirm_sell(
    callback: CallbackQuery,
    state: FSMContext,
):
    if callback.message is None:
        await callback.answer()
        return

    data = await state.get_data()

    required = (
        "amount",
        "rate",
        "total",
        "txid",
        "payment_method",
        "payout_details",
    )

    if not all(key in data for key in required):
        await state.clear()
        await callback.answer(
            "Sifariş məlumatları natamamdır. Yenidən başla.",
            show_alert=True,
        )
        return

    order_ref = f"SELL-{uuid.uuid4().hex[:8].upper()}"

    try:
        await create_order(
            order_ref=order_ref,
            telegram_id=callback.from_user.id,
            kind="sell",
            amount=Decimal(data["amount"]),
            rate=Decimal(data["rate"]),
            total=Decimal(data["total"]),
            currency="AZN",
            payment_method=data["payment_method"],
        )

        txid_saved = await set_txid(
            order_ref,
            data["txid"],
        )

        if not txid_saved:
            await callback.answer(
                "TXID saxlanmadı. Eyni TXID artıq istifadə edilmiş ola bilər.",
                show_alert=True,
            )
            await state.clear()
            return

        bank_saved = await set_bank(
            order_ref,
            data["payout_details"],
        )

        if not bank_saved:
            logger.error(
                "Satış sifarişinin ödəniş məlumatı saxlanmadı: %s",
                order_ref,
            )
            await callback.answer(
                "Ödəniş məlumatları saxlanmadı. Administratorla əlaqə saxla.",
                show_alert=True,
            )
            await state.clear()
            return

    except Exception:
        logger.exception("Satış sifarişi yaradılmadı.")
        await callback.answer(
            "Sifariş yaradılarkən xəta baş verdi.",
            show_alert=True,
        )
        await state.clear()
        return

    order = await get_order(order_ref)

    await callback.answer("Sifariş yaradıldı.")
    await callback.message.edit_text(
        "✅ <b>Satış sifarişin qəbul edildi.</b>\n\n"
        f"Sifariş: <code>{order_ref}</code>\n"
        f"USDT: <b>{data['amount']}</b>\n"
        f"Təxmini ödəniş: <b>{data['total']} AZN</b>\n"
        "Status: <b>Yoxlanılır</b>\n\n"
        "Bu, pulun göndərildiyi və ya sifarişin təsdiqləndiyi demək deyil. "
        "Administrator TXID-ni və əməliyyat məlumatlarını yoxlamalıdır."
    )

    for admin_id in ADMIN_IDS:
        try:
            await callback.bot.send_message(
                chat_id=admin_id,
                text=(
                    "🔔 <b>Yeni satış sifarişi</b>\n\n"
                    f"Sifariş: <code>{order_ref}</code>\n"
                    f"İstifadəçi ID: <code>{callback.from_user.id}</code>\n"
                    f"USDT: <b>{data['amount']}</b>\n"
                    f"Təxmini AZN: <b>{data['total']}</b>\n"
                    f"TXID: <code>{data['txid']}</code>\n"
                    f"Ödəniş üsulu: <b>{data['payment_method']}</b>\n"
                    f"Ödəniş məlumatı: <code>{data['payout_details']}</code>\n\n"
                    "⚠️ TXID-ni blokçeyndə yoxlamadan sifarişi təsdiqləmə."
                ),
            )
        except Exception:
            logger.exception(
                "Satış bildirişi göndərilmədi: admin_id=%s",
                admin_id,
            )

    await state.clear()
