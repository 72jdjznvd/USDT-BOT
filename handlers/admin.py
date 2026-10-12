import os
from html import escape

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

ADMIN_IDS = {
int(value.strip())
for value in os.getenv("ADMIN_IDS", "").split(",")
if value.strip().isdigit()
}

def is_admin(user_id: int) -> bool:
return user_id in ADMIN_IDS

def order_keyboard(order_ref: str) -> InlineKeyboardMarkup:
return InlineKeyboardMarkup(
inline_keyboard=[
[
InlineKeyboardButton(
text="✅ Təsdiqlə",
callback_data=f"admin:approve:{order_ref}",
),
InlineKeyboardButton(
text="❌ Rədd et",
callback_data=f"admin:reject:{order_ref}",
),
],
[
InlineKeyboardButton(
text="🔄 Yenilə",
callback_data=f"admin:view:{order_ref}",
)
],
]
)

def format_order(order: dict) -> str:
username = order.get("username")
username_text = f"@{username}" if username else "yoxdur"

first_name = order.get("first_name") or ""
last_name = order.get("last_name") or ""
full_name = escape(f"{first_name} {last_name}".strip() or "—")

kind = order.get("kind", "—")
kind_text = "USDT alış" if kind == "buy" else "USDT satış"

return (
    f"🧾 <b>Sifariş:</b> <code>{escape(str(order.get('order_ref', '—')))}</code>\n"
    f"👤 <b>Müştəri:</b> {full_name}\n"
    f"🔗 <b>Username:</b> {escape(username_text)}\n"
    f"🆔 <b>Telegram ID:</b> <code>{order.get('telegram_id', '—')}</code>\n"
    f"📌 <b>Növ:</b> {kind_text}\n"
    f"💵 <b>Məbləğ:</b> {escape(str(order.get('amount', '—')))} USDT\n"
    f"💱 <b>Məzənnə:</b> {escape(str(order.get('rate', '—')))} AZN\n"
    f"💰 <b>AZN:</b> {escape(str(order.get('total', '—')))}\n"
    f"🏦 <b>Ödəniş üsulu:</b> {escape(str(order.get('payment_method', '—')))}\n"
    f"📍 <b>Status:</b> {escape(str(order.get('status', '—')))}\n"
    f"🧾 <b>TXID:</b> <code>{escape(str(order.get('txid') or 'yoxdur'))}</code>"
)

@router.message(Command("admin"))
async def admin_panel(message: Message):
if not message.from_user or not is_admin(message.from_user.id):
await message.answer("⛔ Bu bölmə yalnız administrator üçündür.")
return

keyboard = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(
                text="🕒 Yoxlanılmamış sifarişlər",
                callback_data="admin:list:review",
            )
        ],
        [
            InlineKeyboardButton(
                text="📋 Son sifarişlər",
                callback_data="admin:list:all",
            )
        ],
    ]
)

await message.answer(
    "🛠 <b>USDT P2P AZ — Admin paneli</b>\n\n"
    "Sifarişləri seçmək üçün aşağıdakı düymələrdən istifadə et.",
    reply_markup=keyboard,
    parse_mode="HTML",
)

@router.callback_query(F.data.startswith("admin:list:"))
async def list_orders_handler(callback: CallbackQuery):
if not is_admin(callback.from_user.id):
await callback.answer("İcazə yoxdur.", show_alert=True)
return

selection = callback.data.rsplit(":", 1)[-1]

try:
    if selection == "review":
        orders = await list_orders(status="review", limit=20)
    else:
        orders = await list_orders(limit=20)
except Exception:
    await callback.answer("Sifarişlər yüklənmədi.", show_alert=True)
    return

await callback.answer()

if not orders:
    if callback.message:
        await callback.message.answer("📭 Sifariş tapılmadı.")
    return

if callback.message:
    await callback.message.answer(
        f"📋 Tapılan sifarişlər: {len(orders)}"
    )

for order in orders:
    order_ref = order.get("order_ref")
    if not order_ref:
        continue

    text = format_order(order)
    keyboard = order_keyboard(order_ref) if order.get("status") == "review" else None

    if callback.message:
        await callback.message.answer(
            text,
            reply_markup=keyboard,
            parse_mode="HTML",
        )

        # Qəbz foto və ya sənəd kimi saxlanılıbsa, onu da göstər.
        receipt_file_id = order.get("receipt_file_id")
        if receipt_file_id and order.get("kind") == "buy":
            try:
                await callback.message.bot.send_document(
                    callback.from_user.id,
                    receipt_file_id,
                    caption=f"Qəbz: {order_ref}",
                )
            except Exception:
                pass

@router.callback_query(F.data.startswith("admin:view:"))
async def view_order_handler(callback: CallbackQuery):
if not is_admin(callback.from_user.id):
await callback.answer("İcazə yoxdur.", show_alert=True)
return

order_ref = callback.data.split(":", 2)[2]

try:
    order = await get_order(order_ref)
except Exception:
    order = None

if not order:
    await callback.answer("Sifariş tapılmadı.", show_alert=True)
    return

keyboard = order_keyboard(order_ref) if order.get("status") == "review" else None

await callback.answer()

if callback.message:
    await callback.message.answer(
        format_order(order),
        reply_markup=keyboard,
        parse_mode="HTML",
    )

    receipt_file_id = order.get("receipt_file_id")
    if receipt_file_id and order.get("kind") == "buy":
        await callback.message.bot.send_document(
            callback.from_user.id,
            receipt_file_id,
            caption=f"Qəbz: {order_ref}",
        )

@router.callback_query(F.data.startswith("admin:approve:"))
async def approve_order_handler(callback: CallbackQuery):
if not is_admin(callback.from_user.id):
await callback.answer("İcazə yoxdur.", show_alert=True)
return

order_ref = callback.data.split(":", 2)[2]

try:
    order = await get_order(order_ref)
    if not order or order.get("status") != "review":
        await callback.answer(
            "Sifariş tapılmadı və ya artıq işlənib.",
            show_alert=True,
        )
        return

    if order.get("kind") == "sell":
        await callback.answer(
            "Əvvəl TXID-ni blokçeyndə yoxla. Sonra qərar ver.",
            show_alert=True,
        )
        return

    success = await admin_decide(
        order_ref=order_ref,
        admin_id=callback.from_user.id,
        decision="approve",
        reason=None,
    )
except Exception:
    success = False
    order = None

if not success:
    await callback.answer(
        "Sifariş yenilənmədi. Verilənlər bazasını yoxla.",
        show_alert=True,
    )
    return

await callback.answer("Sifariş təsdiqləndi.")

if callback.message:
    await callback.message.answer(
        f"✅ {order_ref} sifarişinin qəbzi administrator tərəfindən təsdiqləndi.\n"
        "Bu, USDT-nin müştəriyə göndərildiyini bildirmir."
    )

if order:
    try:
        await callback.bot.send_message(
            int(order["telegram_id"]),
            f"✅ {order_ref} sifarişinizin ödənişi yoxlanıldı.\n"
            "USDT köçürməsinin tamamlanmasını gözləyin.",
        )
    except Exception:
        pass

@router.callback_query(F.data.startswith("admin:reject:"))
async def reject_order_handler(callback: CallbackQuery):
if not is_admin(callback.from_user.id):
await callback.answer("İcazə yoxdur.", show_alert=True)
return

order_ref = callback.data.split(":", 2)[2]

try:
    order = await get_order(order_ref)
except Exception:
    order = None

if not order or order.get("status") != "review":
    await callback.answer(
        "Sifariş tapılmadı və ya artıq işlənib.",
        show_alert=True,
    )
    return

keyboard = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(
                text="❌ Qəbz/TXID uyğun deyil",
                callback_data=f"admin:reject_reason:{order_ref}:invalid",
            )
        ],
        [
            InlineKeyboardButton(
                text="❌ Ödəniş tapılmadı",
                callback_data=f"admin:reject_reason:{order_ref}:missing",
            )
        ],
        [
            InlineKeyboardButton(
                text="⬅️ Geri",
                callback_data=f"admin:view:{order_ref}",
            )
        ],
    ]
)

await callback.answer()

if callback.message:
    await callback.message.answer(
        f"❌ <b>{escape(order_ref)}</b> sifarişi üçün rədd səbəbini seç:",
        reply_markup=keyboard,
        parse_mode="HTML",
    )

@router.callback_query(F.data.startswith("admin:reject_reason:"))
async def reject_reason_handler(callback: CallbackQuery):
if not is_admin(callback.from_user.id):
await callback.answer("İcazə yoxdur.", show_alert=True)
return

parts = callback.data.split(":")
if len(parts) != 4:
    await callback.answer("Yanlış seçim.", show_alert=True)
    return

order_ref, reason_code = parts[2], parts[3]

reasons = {
    "invalid": "Qəbz və ya TXID uyğun deyil.",
    "missing": "Ödəniş hesabda aşkarlanmadı.",
}
reason = reasons.get(reason_code)

if not reason:
    await callback.answer("Yanlış səbəb.", show_alert=True)
    return

try:
    order = await get_order(order_ref)
    if not order or order.get("status") != "review":
        await callback.answer(
            "Sifariş artıq işlənib.",
            show_alert=True,
        )
        return

    success = await admin_decide(
        order_ref=order_ref,
        admin_id=callback.from_user.id,
        decision="reject",
        reason=reason,
    )
except Exception:
    success = False
    order = None

if not success:
    await callback.answer("Sifariş yenilənmədi.", show_alert=True)
    return

await callback.answer("Sifariş rədd edildi.")

if callback.message:
    await callback.message.answer(
        f"❌ {order_ref} sifarişi rədd edildi.\nSəbəb: {reason}"
    )

if order:
    try:
        await callback.bot.send_message(
            int(order["telegram_id"]),
            f"❌ Sifarişiniz rədd edildi.\n"
            f"Sifariş: {order_ref}\n"
            f"Səbəb: {reason}",
        )
    except Exception:
        pass
