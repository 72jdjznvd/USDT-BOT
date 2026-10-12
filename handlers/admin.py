import os
import logging
from decimal import Decimal, InvalidOperation

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

from database import (
    list_orders,
    get_order,
    admin_decide,
)

router = Router()
logger = logging.getLogger(__name__)

ADMIN_IDS = {
    int(value.strip())
    for value in os.getenv("ADMIN_IDS", "").split(",")
    if value.strip().isdigit()
}


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def format_order(order: dict) -> str:
    username = order.get("username") or "Yoxdur"
    first_name = order.get("first_name") or ""
    last_name = order.get("last_name") or ""
    full_name = f"{first_name} {last_name}".strip() or "Ad yoxdur"

    return (
        f"🧾 <b>Sifariş:</b> <code>{order.get('order_ref', '-')}</code>\n"
        f"👤 <b>İstifadəçi:</b> {full_name}\n"
        f"🔗 <b>Username:</b> @{username}\n"
        f"🆔 <b>Telegram ID:</b> <code>{order.get('telegram_id', '-')}</code>\n"
        f"📌 <b>Növ:</b> {order.get('kind', '-')}\n"
        f"💰 <b>USDT:</b> {order.get('amount', '-')}\n"
        f"💱 <b>Məzənnə:</b> {order.get('rate', '-')}\n"
        f"💵 <b>AZN:</b> {order.get('total', '-')}\n"
        f"🏦 <b>Ödəniş:</b> {order.get('payment_method') or '-'}\n"
        f"📍 <b>Status:</b> {order.get('status', '-')}\n"
        f"🔎 <b>TXID:</b> <code>{order.get('txid') or '-'}</code>\n"
        f"📝 <b>İmtina səbəbi:</b> {order.get('rejection_reason') or '-'}"
    )


def order_keyboard(order: dict) -> InlineKeyboardMarkup:
    order_ref = order["order_ref"]

    buttons = [
        [
            InlineKeyboardButton(
                text="🔄 Yenilə",
                callback_data=f"admin:view:{order_ref}",
            )
        ]
    ]

    if order.get("status") == "review":
        buttons.append([
            InlineKeyboardButton(
                text="✅ Təsdiqlə",
                callback_data=f"admin:approve:{order_ref}",
            ),
            InlineKeyboardButton(
                text="❌ İmtina et",
                callback_data=f"admin:reject:{order_ref}",
            ),
        ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


@router.message(Command("admin"))
async def admin_panel(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Bu bölmə yalnız administrator üçündür.")
        return

    orders = await list_orders(limit=20)

    if not orders:
        await message.answer("Hələ sifariş yoxdur.")
        return

    await message.answer(
        f"🛠 <b>Administrator paneli</b>\n"
        f"Son {len(orders)} sifariş göstərilir."
    )

    for order in orders:
        try:
            await message.answer(
                format_order(order),
                reply_markup=order_keyboard(order),
            )
        except Exception:
            logger.exception("Sifariş göstərilmədi: %s", order.get("order_ref"))


@router.message(Command("review"))
async def review_orders(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ İcazən yoxdur.")
        return

    orders = await list_orders(status="review", limit=30)

    if not orders:
        await message.answer("Yoxlanılma gözləyən sifariş yoxdur.")
        return

    await message.answer(
        f"🔎 <b>Yoxlanılmalı sifarişlər:</b> {len(orders)}"
    )

    for order in orders:
        await message.answer(
            format_order(order),
            reply_markup=order_keyboard(order),
        )

        # Qəbz varsa, onun foto/sənəd növünə uyğun göndər.
        file_id = order.get("receipt_file_id")
        file_type = order.get("receipt_type") or "document"

        if order.get("kind") == "buy" and file_id:
            try:
                if file_type == "photo":
                    await message.bot.send_photo(
                        chat_id=message.chat.id,
                        photo=file_id,
                        caption=f"📎 Qəbz: {order['order_ref']}",
                    )
                else:
                    await message.bot.send_document(
                        chat_id=message.chat.id,
                        document=file_id,
                        caption=f"📎 Qəbz: {order['order_ref']}",
                    )
            except Exception:
                logger.exception(
                    "Qəbz göstərilmədi: %s",
                    order.get("order_ref"),
                )
                await message.answer(
                    "⚠️ Qəbz göstərilə bilmədi. "
                    "İlkin bildirişdəki qəbzi yoxla."
                )


@router.callback_query(F.data.startswith("admin:view:"))
async def view_order(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("İcazən yoxdur.", show_alert=True)
        return

    order_ref = callback.data.split(":", 2)[2]
    order = await get_order(order_ref)

    if not order:
        await callback.answer("Sifariş tapılmadı.", show_alert=True)
        return

    await callback.answer("Sifariş yeniləndi.")

    if callback.message:
        await callback.message.edit_text(
            format_order(order),
            reply_markup=order_keyboard(order),
        )


@router.callback_query(F.data.startswith("admin:approve:"))
async def approve_order_handler(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("İcazən yoxdur.", show_alert=True)
        return

    order_ref = callback.data.split(":", 2)[2]
    order = await get_order(order_ref)

    if not order:
        await callback.answer("Sifariş tapılmadı.", show_alert=True)
        return

    if order.get("status") != "review":
        await callback.answer(
            "Bu sifariş artıq yoxlanılıb və ya statusu dəyişib.",
            show_alert=True,
        )
        return

    if order.get("kind") == "sell":
        await callback.answer(
            "Satış sifarişini təsdiqləməzdən əvvəl TXID-ni blokçeyndə yoxla.",
            show_alert=True,
        )
        return

    if order.get("kind") != "buy":
        await callback.answer("Naməlum sifariş növü.", show_alert=True)
        return

    success = await admin_decide(
        order_ref=order_ref,
        admin_id=callback.from_user.id,
        decision="approve",
    )

    if not success:
        await callback.answer(
            "Status dəyişdirilmədi. Sifarişi yenilə.",
            show_alert=True,
        )
        return

    await callback.answer("Sifariş təsdiqləndi.")

    if callback.message:
        await callback.message.edit_text(
            format_order(await get_order(order_ref))
        )

    try:
        await callback.bot.send_message(
            chat_id=order["telegram_id"],
            text=(
                "✅ <b>Ödəniş qəbzin təsdiqləndi.</b>\n\n"
                f"Sifariş: <code>{order_ref}</code>\n"
                "Bu bildiriş USDT-nin göndərildiyini təsdiqləmir. "
                "Köçürmə tamamlandıqdan sonra ayrıca TXID və ya "
                "təsdiq təqdim edilməlidir."
            ),
        )
    except Exception:
        logger.exception("İstifadəçiyə bildiriş göndərilmədi.")


@router.callback_query(F.data.startswith("admin:reject:"))
async def reject_order_handler(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("İcazən yoxdur.", show_alert=True)
        return

    order_ref = callback.data.split(":", 2)[2]
    order = await get_order(order_ref)

    if not order:
        await callback.answer("Sifariş tapılmadı.", show_alert=True)
        return

    if order.get("status") != "review":
        await callback.answer(
            "Sifariş artıq yoxlanılıb və ya statusu dəyişib.",
            show_alert=True,
        )
        return

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Qəbz aydın deyil",
                    callback_data=f"admin:reason:{order_ref}:receipt",
                )
            ],
            [
                InlineKeyboardButton(
                    text="Ödəniş təsdiqlənməyib",
                    callback_data=f"admin:reason:{order_ref}:unpaid",
                )
            ],
            [
                InlineKeyboardButton(
                    text="Yanlış məlumat",
                    callback_data=f"admin:reason:{order_ref}:invalid",
                )
            ],
        ]
    )

    await callback.answer()

    if callback.message:
        await callback.message.answer(
            f"❌ <b>{order_ref}</b> üçün imtina səbəbini seç:",
            reply_markup=keyboard,
        )


@router.callback_query(F.data.startswith("admin:reason:"))
async def reject_reason_handler(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("İcazən yoxdur.", show_alert=True)
        return

    parts = callback.data.split(":")

    if len(parts) != 4:
        await callback.answer("Yanlış sorğu.", show_alert=True)
        return

    _, _, order_ref, reason_code = parts

    reasons = {
        "receipt": "Qəbz aydın deyil",
        "unpaid": "Ödəniş təsdiqlənməyib",
        "invalid": "Yanlış məlumat",
    }

    reason = reasons.get(reason_code)

    if reason is None:
        await callback.answer("İmtina səbəbi tapılmadı.", show_alert=True)
        return

    order = await get_order(order_ref)

    if not order or order.get("status") != "review":
        await callback.answer(
            "Sifariş tapılmadı və ya artıq yoxlanılıb.",
            show_alert=True,
        )
        return

    success = await admin_decide(
        order_ref=order_ref,
        admin_id=callback.from_user.id,
        decision="reject",
        reason=reason,
    )

    if not success:
        await callback.answer(
            "Sifarişin statusu dəyişdirilmədi.",
            show_alert=True,
        )
        return

    await callback.answer("Sifariş rədd edildi.")

    if callback.message:
        await callback.message.edit_text(
            f"❌ <b>Sifariş rədd edildi</b>\n"
            f"Sifariş: <code>{order_ref}</code>\n"
            f"Səbəb: {reason}"
        )

    try:
        await callback.bot.send_message(
            chat_id=order["telegram_id"],
            text=(
                "❌ <b>Sifariş qəbul edilmədi.</b>\n\n"
                f"Sifariş: <code>{order_ref}</code>\n"
                f"Səbəb: {reason}\n\n"
                "Məlumatları yoxlayıb administratorla əlaqə saxla."
            ),
        )
    except Exception:
        logger.exception("İstifadəçiyə imtina bildirişi göndərilmədi.")
