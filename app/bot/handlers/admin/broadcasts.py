"""Admin broadcast composer.

A campaign is always previewed with its recipient count and estimated delivery
time before anything is sent, and delivery runs in the background so the panel
stays responsive.
"""

from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot.callbacks import AdminBroadcastCB
from app.bot.filters import IsAdmin
from app.bot.handlers.helpers import answer_callback, render
from app.bot.keyboards.admin.broadcast import (
    audience_keyboard,
    broadcast_detail_keyboard,
    broadcast_menu_keyboard,
    history_keyboard,
    preview_keyboard,
)
from app.bot.keyboards.common import navigation_keyboard
from app.bot.keyboards.store import open_store_keyboard
from app.bot.states import BroadcastStates
from app.bot.texts import admin as texts
from app.config import Settings
from app.database.models import Admin, AdminRole, Broadcast, BroadcastAudience
from app.database.session import Database
from app.services.broadcast_service import BroadcastRunner
from app.services.exceptions import ValidationError
from app.services.registry import Services
from app.utils.logging import get_logger

logger = get_logger(__name__)

router = Router(name="admin-broadcasts")
router.message.filter(IsAdmin(AdminRole.ADMIN))
router.callback_query.filter(IsAdmin(AdminRole.ADMIN))

MAX_BROADCAST_LENGTH = 3500


@router.callback_query(AdminBroadcastCB.filter(F.action == "menu"))
async def open_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await render(callback, texts.broadcast_menu(), broadcast_menu_keyboard())


@router.callback_query(AdminBroadcastCB.filter(F.action == "new"))
async def compose(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(BroadcastStates.waiting_content)
    await render(
        callback,
        texts.broadcast_compose(),
        navigation_keyboard(AdminBroadcastCB(action="menu").pack()),
    )


@router.message(BroadcastStates.waiting_content, F.photo)
async def capture_photo(message: Message, state: FSMContext) -> None:
    photo = message.photo[-1] if message.photo else None
    caption = (message.caption or "").strip()
    if not caption:
        await message.answer("⚠️ Send the photo again with a caption as the text.")
        return
    await state.update_data(
        body=caption[:MAX_BROADCAST_LENGTH],
        image_file_id=photo.file_id if photo else None,
    )
    await state.set_state(BroadcastStates.waiting_audience)
    await message.answer("👥 Who should receive it?", reply_markup=audience_keyboard())


@router.message(BroadcastStates.waiting_content, F.text)
async def capture_text(message: Message, state: FSMContext) -> None:
    body = (message.text or "").strip()
    if not body:
        await message.answer("⚠️ The broadcast text cannot be empty.")
        return
    await state.update_data(body=body[:MAX_BROADCAST_LENGTH], image_file_id=None)
    await state.set_state(BroadcastStates.waiting_audience)
    await message.answer("👥 Who should receive it?", reply_markup=audience_keyboard())


@router.callback_query(
    BroadcastStates.waiting_audience, AdminBroadcastCB.filter(F.action == "audience")
)
async def choose_audience(
    callback: CallbackQuery,
    callback_data: AdminBroadcastCB,
    state: FSMContext,
    admin: Admin,
    services: Services,
    settings: Settings,
) -> None:
    """Create the DRAFT campaign and show the preview."""
    data = await state.get_data()
    try:
        broadcast = await services.broadcasts.create_draft(
            body=str(data.get("body", "")),
            audience=BroadcastAudience(callback_data.value),
            admin=admin,
            image_file_id=data.get("image_file_id"),
        )
    except ValidationError as error:
        await answer_callback(callback, error.message, alert=True)
        return
    await state.clear()
    estimate = await services.broadcasts.estimated_seconds(
        broadcast.total_recipients, settings.store.broadcast_messages_per_second
    )
    await render(
        callback,
        texts.broadcast_preview(broadcast, estimate),
        preview_keyboard(broadcast),
    )


@router.callback_query(AdminBroadcastCB.filter(F.action == "send"))
async def send_broadcast(
    callback: CallbackQuery,
    callback_data: AdminBroadcastCB,
    admin: Admin,
    services: Services,
    settings: Settings,
    db: Database,
) -> None:
    """Launch the campaign in the background and report live progress."""
    broadcast = await services.broadcasts.get(callback_data.broadcast_id)
    if services.dispatcher is None:  # pragma: no cover - bot always present
        await answer_callback(callback, "Messaging is unavailable.", alert=True)
        return
    await services.broadcasts.log_sent(broadcast, admin)
    await answer_callback(callback, "📡 Broadcast started.")

    message = callback.message
    runner = BroadcastRunner(
        db, services.dispatcher, batch_size=settings.store.broadcast_batch_size
    )

    async def progress(current: Broadcast) -> None:
        if message is None:
            return
        try:
            await message.edit_text(
                texts.broadcast_progress(current),
                reply_markup=broadcast_detail_keyboard(current),
            )
        except Exception:  # pragma: no cover - progress updates are best effort
            logger.debug("broadcast.progress_edit_failed", broadcast_id=current.id)

    runner.start(broadcast.id, reply_markup=open_store_keyboard(), progress=progress)
    await render(
        callback,
        texts.broadcast_progress(broadcast),
        broadcast_detail_keyboard(broadcast),
    )


@router.callback_query(AdminBroadcastCB.filter(F.action == "cancel"))
async def cancel_broadcast(
    callback: CallbackQuery,
    callback_data: AdminBroadcastCB,
    state: FSMContext,
    services: Services,
) -> None:
    broadcast = await services.broadcasts.get(callback_data.broadcast_id)
    try:
        await services.broadcasts.cancel(broadcast)
    except ValidationError as error:
        await answer_callback(callback, error.message, alert=True)
        return
    await state.clear()
    await render(
        callback,
        texts.broadcast_menu(),
        broadcast_menu_keyboard(),
        answer_text="❌ Broadcast cancelled.",
    )


@router.callback_query(AdminBroadcastCB.filter(F.action == "history"))
async def history(
    callback: CallbackQuery,
    callback_data: AdminBroadcastCB,
    services: Services,
    settings: Settings,
) -> None:
    result = await services.broadcasts.paginate_history(
        callback_data.page, settings.store.admin_list_page_size
    )
    await render(callback, texts.broadcast_history(result), history_keyboard(result))


@router.callback_query(AdminBroadcastCB.filter(F.action == "view"))
async def view_broadcast(
    callback: CallbackQuery, callback_data: AdminBroadcastCB, services: Services
) -> None:
    broadcast = await services.broadcasts.get(callback_data.broadcast_id)
    await render(
        callback,
        texts.broadcast_progress(broadcast),
        broadcast_detail_keyboard(broadcast, page=callback_data.page),
    )
