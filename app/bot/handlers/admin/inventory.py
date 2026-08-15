"""Admin stock and inventory management, including restock notifications.

The restock notification flow is deliberately manual: adding stock never
messages anyone by itself. The admin sees what changed, how many users are
waiting, can preview the exact message, and then chooses the audience — unless
the ``auto_notify_stock`` setting is switched on, in which case the waiting list
is notified right away.
"""

from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot.callbacks import AdminStockCB, AdminStockNotifyCB
from app.bot.filters import IsAdmin
from app.bot.handlers.helpers import answer_callback, render
from app.bot.keyboards.admin.catalog import (
    inventory_item_keyboard,
    inventory_items_keyboard,
    low_stock_keyboard,
    restock_notify_keyboard,
    stock_keyboard,
)
from app.bot.keyboards.common import navigation_keyboard
from app.bot.keyboards.store import buy_now_keyboard
from app.bot.states import StockStates
from app.bot.texts import admin as texts
from app.bot.texts import notifications as notify_texts
from app.config import Settings
from app.database.models import Admin, Plan
from app.services.inventory_service import StockChange
from app.services.registry import Services
from app.utils.logging import get_logger
from app.utils.text import parse_positive_int, split_lines

logger = get_logger(__name__)

router = Router(name="admin-inventory")
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())

#: Maximum codes accepted in a single import message.
MAX_IMPORT_LINES = 300


async def _show_stock(
    event: Message | CallbackQuery, services: Services, plan_id: int
) -> None:
    plan = await services.plans.get(plan_id)
    breakdown = await services.inventory.breakdown(plan.id)
    waiting = await services.notifications.waiting_count(plan.id)
    await render(
        event, texts.stock_screen(plan, breakdown, waiting), stock_keyboard(plan)
    )


@router.callback_query(AdminStockCB.filter(F.action == "view"))
async def open_stock(
    callback: CallbackQuery,
    callback_data: AdminStockCB,
    state: FSMContext,
    services: Services,
) -> None:
    await state.clear()
    await _show_stock(callback, services, callback_data.plan_id)


@router.callback_query(AdminStockCB.filter(F.action == "low"))
async def open_low_stock(
    callback: CallbackQuery,
    callback_data: AdminStockCB,
    services: Services,
    settings: Settings,
) -> None:
    """Every active plan with no sellable units — the restock worklist."""
    result = await services.inventory.low_stock_page(
        callback_data.page, settings.store.admin_list_page_size
    )
    await render(callback, texts.low_stock(result), low_stock_keyboard(result))


# ------------------------------------------------------------------ stock changes
@router.callback_query(AdminStockCB.filter(F.action.in_({"add", "remove", "set"})))
async def ask_quantity(
    callback: CallbackQuery,
    callback_data: AdminStockCB,
    state: FSMContext,
    services: Services,
) -> None:
    plan = await services.plans.get(callback_data.plan_id)
    prompts = {
        "add": "➕ How many units should be <b>added</b>?",
        "remove": "➖ How many units should be <b>removed</b>?",
        "set": "🔢 Send the exact total stock quantity.",
    }
    await state.set_state(StockStates.waiting_quantity)
    await state.update_data(plan_id=plan.id, mode=callback_data.action)
    await render(
        callback,
        f"{prompts[callback_data.action]}\n\n"
        f"Current stock: <b>{plan.stock_quantity}</b> "
        f"({plan.available_quantity} available)",
        navigation_keyboard(AdminStockCB(action="view", plan_id=plan.id).pack()),
    )


@router.message(StockStates.waiting_quantity, F.text)
async def apply_quantity(
    message: Message,
    state: FSMContext,
    admin: Admin,
    services: Services,
) -> None:
    data = await state.get_data()
    plan = await services.plans.get(int(data["plan_id"]))
    mode = str(data["mode"])
    raw = (message.text or "").strip()
    try:
        quantity = 0 if (mode == "set" and raw == "0") else parse_positive_int(raw)
    except ValueError as error:
        await message.answer(f"⚠️ {error}")
        return

    if mode == "add":
        change = await services.inventory.add_stock(plan, quantity, admin=admin)
    elif mode == "remove":
        change = await services.inventory.remove_stock(plan, quantity, admin=admin)
    else:
        change = await services.inventory.set_stock(plan, quantity, admin=admin)

    await state.clear()
    await _report_change(message, change, services, admin)


@router.callback_query(AdminStockCB.filter(F.action == "import"))
async def ask_codes(
    callback: CallbackQuery,
    callback_data: AdminStockCB,
    state: FSMContext,
    services: Services,
) -> None:
    plan = await services.plans.get(callback_data.plan_id)
    await state.set_state(StockStates.waiting_codes)
    await state.update_data(plan_id=plan.id)
    await render(
        callback,
        "📥 <b>Import inventory</b>\n\n"
        "Send the deliverables, <b>one per line</b>. For example:\n\n"
        "<code>CODE-001\nCODE-002\nemail:password</code>\n\n"
        f"Up to {MAX_IMPORT_LINES} lines per message. Duplicates are skipped.",
        navigation_keyboard(AdminStockCB(action="view", plan_id=plan.id).pack()),
    )


@router.message(StockStates.waiting_codes, F.text)
async def import_codes(
    message: Message,
    state: FSMContext,
    admin: Admin,
    services: Services,
) -> None:
    data = await state.get_data()
    plan = await services.plans.get(int(data["plan_id"]))
    values = split_lines(message.text or "", limit=MAX_IMPORT_LINES)
    if not values:
        await message.answer("⚠️ No usable lines found. Send one value per line.")
        return
    change = await services.inventory.import_codes(plan, values, admin=admin)
    await state.clear()
    await _report_change(message, change, services, admin)


async def _report_change(
    message: Message, change: StockChange, services: Services, admin: Admin
) -> None:
    """Confirm the mutation and, when relevant, offer the notification choices."""
    plan = change.plan
    waiting = await services.notifications.waiting_count(plan.id)
    audience = await services.notifications.notifiable_users()
    text = texts.stock_change_result(change, waiting, len(audience))

    if not change.back_in_stock:
        await message.answer(text)
        await _show_stock(message, services, plan.id)
        return

    if await services.store_settings.get_bool("auto_notify_stock") and waiting:
        report = await _notify(services, plan, admin, interested_only=True)
        await message.answer(
            f"{text}\n\n🔔 Waiting list notified automatically: "
            f"{report.sent} sent, {report.failed} failed."
        )
        await _show_stock(message, services, plan.id)
        return

    await message.answer(
        text,
        reply_markup=restock_notify_keyboard(
            plan, waiting=waiting, all_users=len(audience)
        ),
    )


# ---------------------------------------------------------- restock notifications
@router.callback_query(AdminStockNotifyCB.filter(F.action == "menu"))
async def notify_menu(
    callback: CallbackQuery, callback_data: AdminStockNotifyCB, services: Services
) -> None:
    plan = await services.plans.get(callback_data.plan_id)
    waiting = await services.notifications.waiting_count(plan.id)
    audience = await services.notifications.notifiable_users()
    if plan.is_sold_out:
        await answer_callback(
            callback, "This plan has no available stock to announce.", alert=True
        )
        return
    await render(
        callback,
        notify_texts.stock_notification_preview(plan, waiting, targeted=True),
        restock_notify_keyboard(plan, waiting=waiting, all_users=len(audience)),
    )


@router.callback_query(AdminStockNotifyCB.filter(F.action == "preview"))
async def notify_preview(
    callback: CallbackQuery, callback_data: AdminStockNotifyCB, services: Services
) -> None:
    plan = await services.plans.get(callback_data.plan_id)
    waiting = await services.notifications.waiting_count(plan.id)
    audience = await services.notifications.notifiable_users()
    await render(
        callback,
        notify_texts.stock_notification_preview(plan, waiting, targeted=False),
        restock_notify_keyboard(plan, waiting=waiting, all_users=len(audience)),
    )


@router.callback_query(AdminStockNotifyCB.filter(F.action.in_({"interested", "all"})))
async def notify_send(
    callback: CallbackQuery,
    callback_data: AdminStockNotifyCB,
    admin: Admin,
    services: Services,
) -> None:
    plan = await services.plans.get(callback_data.plan_id)
    if plan.is_sold_out:
        await answer_callback(
            callback, "This plan is sold out again — nothing was sent.", alert=True
        )
        return
    interested_only = callback_data.action == "interested"
    await answer_callback(callback, "📡 Sending…")
    report = await _notify(services, plan, admin, interested_only=interested_only)
    scope = "waiting list" if interested_only else "all users"
    await render(
        callback,
        f"{texts.header('📢 NOTIFICATION SENT')}\n\n"
        f"<b>Audience</b>\n{scope}\n\n"
        f"<b>Recipients</b>\n{report.total}\n\n"
        f"<b>Successful</b>\n{report.sent}\n\n"
        f"<b>Failed</b>\n{report.failed}",
        navigation_keyboard(AdminStockCB(action="view", plan_id=plan.id).pack()),
    )


async def _notify(
    services: Services, plan: Plan, admin: Admin, *, interested_only: bool
):
    """Send the restock announcement to the chosen audience."""
    if interested_only:
        recipients = await services.notifications.waiting_users(plan.id)
    else:
        recipients = await services.notifications.notifiable_users()
    message_text = notify_texts.back_in_stock(plan, targeted=interested_only)
    return await services.notifications.notify_back_in_stock(
        plan,
        title=f"{plan.product.name} — {plan.name} is back in stock",
        body=f"{plan.name} is available again at {plan.price_display}.",
        message_text=message_text,
        recipients=recipients,
        reply_markup=buy_now_keyboard(plan),
        admin=admin,
        interested_only=interested_only,
    )


@router.callback_query(AdminStockNotifyCB.filter(F.action == "skip"))
async def notify_skip(
    callback: CallbackQuery, callback_data: AdminStockNotifyCB, services: Services
) -> None:
    await answer_callback(callback, "No notification was sent.")
    await _show_stock(callback, services, callback_data.plan_id)


# ------------------------------------------------------------------ inventory rows
@router.callback_query(AdminStockCB.filter(F.action == "items"))
async def list_items(
    callback: CallbackQuery,
    callback_data: AdminStockCB,
    services: Services,
    settings: Settings,
) -> None:
    plan = await services.plans.get(callback_data.plan_id)
    result = await services.inventory.paginate_items(
        plan.id, callback_data.page, settings.store.admin_list_page_size
    )
    await render(
        callback, texts.inventory_items(plan, result), inventory_items_keyboard(plan, result)
    )


@router.callback_query(AdminStockCB.filter(F.action == "item"))
async def view_item(
    callback: CallbackQuery, callback_data: AdminStockCB, services: Services
) -> None:
    plan = await services.plans.get(callback_data.plan_id)
    item = await services.inventory.get_item(callback_data.item_id)
    await render(
        callback,
        texts.inventory_item_detail(item),
        inventory_item_keyboard(plan, item, page=callback_data.page),
    )


@router.callback_query(AdminStockCB.filter(F.action == "item_toggle"))
async def toggle_item(
    callback: CallbackQuery,
    callback_data: AdminStockCB,
    admin: Admin,
    services: Services,
) -> None:
    item = await services.inventory.get_item(callback_data.item_id)
    await services.inventory.toggle_item(item, admin=admin)
    plan = await services.plans.get(callback_data.plan_id)
    await render(
        callback,
        texts.inventory_item_detail(item),
        inventory_item_keyboard(plan, item, page=callback_data.page),
        answer_text="Updated.",
    )


@router.callback_query(AdminStockCB.filter(F.action == "item_delete"))
async def delete_item(
    callback: CallbackQuery,
    callback_data: AdminStockCB,
    admin: Admin,
    services: Services,
    settings: Settings,
) -> None:
    item = await services.inventory.get_item(callback_data.item_id)
    await services.inventory.delete_item(item, admin=admin)
    plan = await services.plans.get(callback_data.plan_id)
    result = await services.inventory.paginate_items(
        plan.id, callback_data.page, settings.store.admin_list_page_size
    )
    await render(
        callback,
        texts.inventory_items(plan, result),
        inventory_items_keyboard(plan, result),
        answer_text="🗑 Item deleted.",
    )
