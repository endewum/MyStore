"""Admin user and administrator management."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot.callbacks import AdminUserCB
from app.bot.filters import IsAdmin
from app.bot.handlers.helpers import answer_callback, render
from app.bot.keyboards.admin.users import (
    admin_detail_keyboard,
    admins_keyboard,
    role_picker_keyboard,
    user_detail_keyboard,
    users_keyboard,
)
from app.bot.keyboards.common import navigation_keyboard
from app.bot.states import UserAdminStates
from app.bot.texts import admin as texts
from app.config import Settings
from app.database.models import Admin, AdminRole
from app.services.exceptions import NotFoundError, ValidationError
from app.services.registry import Services

router = Router(name="admin-users")
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())


async def _show_users(
    event: Message | CallbackQuery,
    services: Services,
    settings: Settings,
    page: int,
) -> None:
    result = await services.users.paginate(page, settings.store.admin_list_page_size)
    await render(event, texts.users_list(result), users_keyboard(result))


async def _show_user(
    event: Message | CallbackQuery, services: Services, user_id: int, page: int = 1
) -> None:
    target = await services.users.require_by_id(user_id)
    stats = await services.users.user_stats(target)
    admin_row = await services.users.get_admin(target.telegram_id)
    await render(
        event,
        texts.user_detail(target, stats, admin_row),
        user_detail_keyboard(target, page=page),
    )


@router.callback_query(AdminUserCB.filter(F.action == "list"))
async def list_users(
    callback: CallbackQuery,
    callback_data: AdminUserCB,
    state: FSMContext,
    services: Services,
    settings: Settings,
) -> None:
    await state.clear()
    await _show_users(callback, services, settings, callback_data.page)


@router.callback_query(AdminUserCB.filter(F.action == "view"))
async def view_user(
    callback: CallbackQuery,
    callback_data: AdminUserCB,
    state: FSMContext,
    services: Services,
) -> None:
    await state.clear()
    await _show_user(callback, services, callback_data.user_id, callback_data.page)


@router.callback_query(AdminUserCB.filter(F.action == "search"))
async def ask_search(
    callback: CallbackQuery, state: FSMContext
) -> None:
    await state.set_state(UserAdminStates.waiting_search)
    await render(
        callback,
        "🔎 Send a username or Telegram ID to look up.",
        navigation_keyboard(AdminUserCB(action="list", page=1).pack()),
    )


@router.message(UserAdminStates.waiting_search, F.text)
async def run_search(
    message: Message, state: FSMContext, services: Services, settings: Settings
) -> None:
    query = (message.text or "").strip()
    try:
        result = await services.users.search(
            query, 1, settings.store.admin_list_page_size
        )
    except ValidationError as error:
        await message.answer(f"⚠️ {error.message}")
        return
    await state.clear()
    await message.answer(
        texts.users_list(result, query=query),
        reply_markup=users_keyboard(result, query=query),
    )


# ---------------------------------------------------------------------- blocking
@router.callback_query(AdminUserCB.filter(F.action == "block"), IsAdmin(AdminRole.ADMIN))
async def ask_block_reason(
    callback: CallbackQuery,
    callback_data: AdminUserCB,
    state: FSMContext,
    services: Services,
) -> None:
    target = await services.users.require_by_id(callback_data.user_id)
    await state.set_state(UserAdminStates.waiting_block_reason)
    await state.update_data(user_id=target.id, page=callback_data.page)
    await render(
        callback,
        f"🚫 Block <b>{target.display_name}</b>?\n\n"
        "Send a short reason, or <code>-</code> to block without one.",
        navigation_keyboard(
            AdminUserCB(action="view", user_id=target.id, page=callback_data.page).pack()
        ),
    )


@router.message(UserAdminStates.waiting_block_reason, F.text)
async def apply_block(
    message: Message, state: FSMContext, admin: Admin, services: Services
) -> None:
    data = await state.get_data()
    target = await services.users.require_by_id(int(data["user_id"]))
    raw = (message.text or "").strip()
    reason = None if raw == "-" else raw[:255]
    await services.users.set_blocked(target, True, admin=admin, reason=reason)
    await state.clear()
    await message.answer(f"🚫 {target.display_name} is now blocked.")
    await _show_user(message, services, target.id, int(data.get("page", 1)))


@router.callback_query(
    AdminUserCB.filter(F.action == "unblock"), IsAdmin(AdminRole.ADMIN)
)
async def unblock_user(
    callback: CallbackQuery,
    callback_data: AdminUserCB,
    admin: Admin,
    services: Services,
) -> None:
    target = await services.users.require_by_id(callback_data.user_id)
    await services.users.set_blocked(target, False, admin=admin, reason=None)
    await _show_user(callback, services, target.id, callback_data.page)


# ------------------------------------------------------------------ admin roles
@router.callback_query(AdminUserCB.filter(F.action == "admins"))
async def list_admins(
    callback: CallbackQuery, state: FSMContext, services: Services
) -> None:
    await state.clear()
    admins = await services.users.list_admins()
    await render(callback, texts.admins_list(admins), admins_keyboard(admins))


@router.callback_query(AdminUserCB.filter(F.action == "admin_view"))
async def view_admin(
    callback: CallbackQuery, callback_data: AdminUserCB, services: Services
) -> None:
    admins = await services.users.list_admins()
    target = next((item for item in admins if item.id == callback_data.user_id), None)
    if target is None:
        await answer_callback(callback, "That administrator was not found.", alert=True)
        return
    name = target.display_name
    await render(
        callback,
        f"🛡 <b>{name}</b>\n\n"
        f"Role: <b>{target.role.value}</b>\n"
        f"Telegram ID: <code>{target.telegram_id}</code>",
        admin_detail_keyboard(target),
    )


@router.callback_query(
    AdminUserCB.filter(F.action == "grant"), IsAdmin(AdminRole.SUPER_ADMIN)
)
async def ask_admin_id(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(UserAdminStates.waiting_admin_id)
    await render(
        callback,
        "➕ Send the Telegram <b>user ID</b> of the new administrator.\n\n"
        "The user can find their ID by sending /account to this bot.",
        navigation_keyboard(AdminUserCB(action="admins").pack()),
    )


@router.message(UserAdminStates.waiting_admin_id, F.text)
async def pick_admin_role(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip()
    if not raw.isdigit():
        await message.answer("⚠️ Send a numeric Telegram user ID.")
        return
    await state.clear()
    await message.answer(
        f"🛡 Choose the role for <code>{raw}</code>.",
        reply_markup=role_picker_keyboard(int(raw)),
    )


@router.callback_query(
    AdminUserCB.filter(F.action == "grant_role"), IsAdmin(AdminRole.SUPER_ADMIN)
)
async def grant_role(
    callback: CallbackQuery,
    callback_data: AdminUserCB,
    admin: Admin,
    services: Services,
) -> None:
    await services.users.grant_admin(
        callback_data.user_id,
        AdminRole(callback_data.value),
        granted_by=admin.telegram_id,
    )
    admins = await services.users.list_admins()
    await render(
        callback,
        texts.admins_list(admins),
        admins_keyboard(admins),
        answer_text="✅ Administrator added.",
    )


@router.callback_query(
    AdminUserCB.filter(F.action == "set_role"), IsAdmin(AdminRole.SUPER_ADMIN)
)
async def set_role(
    callback: CallbackQuery,
    callback_data: AdminUserCB,
    admin: Admin,
    services: Services,
) -> None:
    admins = await services.users.list_admins()
    target = next((item for item in admins if item.id == callback_data.user_id), None)
    if target is None:
        await answer_callback(callback, "That administrator was not found.", alert=True)
        return
    await services.users.grant_admin(
        target.telegram_id,
        AdminRole(callback_data.value),
        granted_by=admin.telegram_id,
    )
    refreshed = await services.users.list_admins()
    await render(
        callback,
        texts.admins_list(refreshed),
        admins_keyboard(refreshed),
        answer_text="✅ Role updated.",
    )


@router.callback_query(
    AdminUserCB.filter(F.action == "revoke"), IsAdmin(AdminRole.SUPER_ADMIN)
)
async def revoke_admin(
    callback: CallbackQuery,
    callback_data: AdminUserCB,
    admin: Admin,
    services: Services,
) -> None:
    admins = await services.users.list_admins()
    target = next((item for item in admins if item.id == callback_data.user_id), None)
    if target is None:
        await answer_callback(callback, "That administrator was not found.", alert=True)
        return
    if target.telegram_id == admin.telegram_id:
        await answer_callback(
            callback, "You cannot revoke your own access.", alert=True
        )
        return
    try:
        await services.users.revoke_admin(target.telegram_id)
    except NotFoundError as error:
        await answer_callback(callback, error.message, alert=True)
        return
    refreshed = await services.users.list_admins()
    await render(
        callback,
        texts.admins_list(refreshed),
        admins_keyboard(refreshed),
        answer_text="🗑 Access revoked.",
    )
