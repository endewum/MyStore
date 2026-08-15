"""Admin settings, categories, coupons and audit log."""

from __future__ import annotations

from decimal import Decimal

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot.callbacks import AdminSettingCB
from app.bot.filters import IsAdmin
from app.bot.handlers.helpers import answer_callback, render
from app.bot.keyboards.admin.settings import (
    categories_keyboard,
    category_detail_keyboard,
    coupon_detail_keyboard,
    coupon_type_keyboard,
    coupons_keyboard,
    logs_keyboard,
    settings_menu_keyboard,
    toggle_setting_keyboard,
)
from app.bot.keyboards.common import navigation_keyboard
from app.bot.states import CategoryStates, CouponAdminStates, SettingStates
from app.bot.texts import admin as texts
from app.config import Settings
from app.database.models import Admin, AdminRole, CouponType
from app.services.exceptions import ValidationError
from app.services.registry import Services
from app.services.settings_service import SETTING_MAP
from app.utils.text import clean_emoji, clean_multiline, clean_text, parse_money

router = Router(name="admin-settings")
router.message.filter(IsAdmin(AdminRole.ADMIN))
router.callback_query.filter(IsAdmin(AdminRole.ADMIN))

#: Settings rendered as simple on/off switches.
BOOLEAN_KEYS = {"auto_notify_stock", "store_open"}


async def _show_menu(event: Message | CallbackQuery, services: Services) -> None:
    values = await services.store_settings.all_values()
    await render(event, texts.settings_menu(values), settings_menu_keyboard())


@router.callback_query(AdminSettingCB.filter(F.action == "menu"))
async def open_menu(
    callback: CallbackQuery, state: FSMContext, services: Services
) -> None:
    await state.clear()
    await _show_menu(callback, services)


@router.callback_query(AdminSettingCB.filter(F.action == "edit"))
async def edit_setting(
    callback: CallbackQuery,
    callback_data: AdminSettingCB,
    state: FSMContext,
    services: Services,
) -> None:
    key = callback_data.value
    definition = SETTING_MAP.get(key)
    if definition is None:
        await answer_callback(callback, "Unknown setting.", alert=True)
        return
    current = await services.store_settings.get(key)
    if key in BOOLEAN_KEYS:
        await render(
            callback,
            f"⚙️ <b>{definition.label}</b>\n\n{definition.description}\n\n"
            f"Current value: <b>{current or 'off'}</b>",
            toggle_setting_keyboard(key),
        )
        return
    await state.set_state(SettingStates.waiting_value)
    await state.update_data(key=key)
    await render(
        callback,
        f"⚙️ <b>{definition.label}</b>\n\n{definition.description}\n\n"
        f"Current value:\n<code>{current or '—'}</code>\n\n"
        "Send the new value.",
        navigation_keyboard(AdminSettingCB(action="menu").pack()),
    )


@router.message(SettingStates.waiting_value, F.text)
async def save_setting(
    message: Message, state: FSMContext, admin: Admin, services: Services
) -> None:
    data = await state.get_data()
    key = str(data["key"])
    raw = (message.text or "").strip()
    if key == "payment_timeout_minutes" and not raw.isdigit():
        await message.answer("⚠️ Send a whole number of minutes, for example 60.")
        return
    try:
        value = clean_multiline(raw, max_length=1000, field="value")
    except ValueError as error:
        await message.answer(f"⚠️ {error}")
        return
    await services.store_settings.set(key, value, admin=admin)
    await state.clear()
    await message.answer("✅ Setting saved.")
    await _show_menu(message, services)


@router.callback_query(AdminSettingCB.filter(F.action == "set_bool"))
async def set_bool(
    callback: CallbackQuery,
    callback_data: AdminSettingCB,
    admin: Admin,
    services: Services,
) -> None:
    key, _, value = callback_data.value.partition(":")
    await services.store_settings.set(key, value, admin=admin)
    await _show_menu(callback, services)


# --------------------------------------------------------------------- categories
@router.callback_query(AdminSettingCB.filter(F.action == "categories"))
async def list_categories(
    callback: CallbackQuery, state: FSMContext, services: Services
) -> None:
    await state.clear()
    categories = await services.products.all_categories()
    await render(
        callback, texts.categories_list(categories), categories_keyboard(categories)
    )


@router.callback_query(AdminSettingCB.filter(F.action == "category"))
async def view_category(
    callback: CallbackQuery, callback_data: AdminSettingCB, services: Services
) -> None:
    category = await services.products.get_category(callback_data.target_id)
    await render(
        callback, texts.category_detail(category), category_detail_keyboard(category)
    )


@router.callback_query(AdminSettingCB.filter(F.action == "category_new"))
async def new_category(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(CategoryStates.waiting_name)
    await render(
        callback,
        "➕ Send the new category name.",
        navigation_keyboard(AdminSettingCB(action="categories", page=1).pack()),
    )


@router.message(CategoryStates.waiting_name, F.text)
async def category_name(message: Message, state: FSMContext) -> None:
    try:
        name = clean_text(message.text or "", max_length=80, field="name")
    except ValueError as error:
        await message.answer(f"⚠️ {error}")
        return
    await state.update_data(name=name)
    await state.set_state(CategoryStates.waiting_emoji)
    await message.answer("😀 Send an emoji for this category (or <code>-</code> for 📦).")


@router.message(CategoryStates.waiting_emoji, F.text)
async def category_emoji(
    message: Message, state: FSMContext, admin: Admin, services: Services
) -> None:
    raw = (message.text or "").strip()
    emoji = "📦"
    if raw != "-":
        try:
            emoji = clean_emoji(raw)
        except ValueError as error:
            await message.answer(f"⚠️ {error}")
            return
    data = await state.get_data()
    try:
        await services.products.create_category(
            name=str(data["name"]), emoji=emoji, admin=admin
        )
    except ValidationError as error:
        await state.clear()
        await message.answer(f"⚠️ {error.message}")
        return
    await state.clear()
    categories = await services.products.all_categories()
    await message.answer(
        texts.categories_list(categories), reply_markup=categories_keyboard(categories)
    )


@router.callback_query(AdminSettingCB.filter(F.action == "category_field"))
async def edit_category_field(
    callback: CallbackQuery,
    callback_data: AdminSettingCB,
    state: FSMContext,
    services: Services,
) -> None:
    category = await services.products.get_category(callback_data.target_id)
    await state.set_state(CategoryStates.waiting_field_value)
    await state.update_data(category_id=category.id, field=callback_data.value)
    prompt = (
        "✏️ Send the new category name."
        if callback_data.value == "name"
        else "😀 Send the new emoji."
    )
    await render(
        callback,
        prompt,
        navigation_keyboard(
            AdminSettingCB(action="category", target_id=category.id).pack()
        ),
    )


@router.message(CategoryStates.waiting_field_value, F.text)
async def save_category_field(
    message: Message, state: FSMContext, admin: Admin, services: Services
) -> None:
    data = await state.get_data()
    category = await services.products.get_category(int(data["category_id"]))
    field = str(data["field"])
    try:
        if field == "name":
            value = clean_text(message.text or "", max_length=80, field="name")
            await services.products.update_category(category, name=value, admin=admin)
        else:
            value = clean_emoji(message.text or "")
            await services.products.update_category(category, emoji=value, admin=admin)
    except (ValueError, ValidationError) as error:
        await message.answer(f"⚠️ {error}")
        return
    await state.clear()
    await message.answer("✅ Category updated.")
    await message.answer(
        texts.category_detail(category),
        reply_markup=category_detail_keyboard(category),
    )


@router.callback_query(AdminSettingCB.filter(F.action == "category_toggle"))
async def toggle_category(
    callback: CallbackQuery,
    callback_data: AdminSettingCB,
    admin: Admin,
    services: Services,
) -> None:
    category = await services.products.get_category(callback_data.target_id)
    await services.products.update_category(
        category, is_active=not category.is_active, admin=admin
    )
    await render(
        callback, texts.category_detail(category), category_detail_keyboard(category)
    )


@router.callback_query(
    AdminSettingCB.filter(F.action == "category_delete"),
    IsAdmin(AdminRole.SUPER_ADMIN),
)
async def delete_category(
    callback: CallbackQuery,
    callback_data: AdminSettingCB,
    admin: Admin,
    services: Services,
) -> None:
    category = await services.products.get_category(callback_data.target_id)
    await services.products.delete_category(category, admin)
    categories = await services.products.all_categories()
    await render(
        callback,
        texts.categories_list(categories),
        categories_keyboard(categories),
        answer_text="🗑 Category deleted. Its products are now uncategorised.",
    )


# ------------------------------------------------------------------------ coupons
@router.callback_query(AdminSettingCB.filter(F.action == "coupons"))
async def list_coupons(
    callback: CallbackQuery,
    callback_data: AdminSettingCB,
    state: FSMContext,
    services: Services,
    settings: Settings,
) -> None:
    await state.clear()
    result = await services.store_settings.paginate_coupons(
        callback_data.page, settings.store.admin_list_page_size
    )
    await render(callback, texts.coupons_list(result), coupons_keyboard(result))


@router.callback_query(AdminSettingCB.filter(F.action == "coupon"))
async def view_coupon(
    callback: CallbackQuery, callback_data: AdminSettingCB, services: Services
) -> None:
    coupon = await services.store_settings.get_coupon(callback_data.target_id)
    await render(
        callback,
        texts.coupon_detail(coupon),
        coupon_detail_keyboard(coupon, page=callback_data.page),
    )


@router.callback_query(AdminSettingCB.filter(F.action == "coupon_new"))
async def new_coupon(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(CouponAdminStates.waiting_code)
    await render(
        callback,
        "🎟 Send the coupon code, for example <code>WELCOME10</code>.",
        navigation_keyboard(AdminSettingCB(action="coupons", page=1).pack()),
    )


@router.message(CouponAdminStates.waiting_code, F.text)
async def coupon_code(message: Message, state: FSMContext) -> None:
    try:
        code = clean_text(message.text or "", max_length=48, field="code")
    except ValueError as error:
        await message.answer(f"⚠️ {error}")
        return
    await state.update_data(code=code.upper())
    await message.answer(
        "Choose the discount type.", reply_markup=coupon_type_keyboard()
    )


@router.callback_query(AdminSettingCB.filter(F.action == "coupon_type"))
async def coupon_type(
    callback: CallbackQuery, callback_data: AdminSettingCB, state: FSMContext
) -> None:
    await state.update_data(coupon_type=callback_data.value)
    await state.set_state(CouponAdminStates.waiting_value)
    hint = (
        "Send the percentage, for example <code>10</code> for 10% off."
        if callback_data.value == CouponType.PERCENT.value
        else "Send the fixed discount, for example <code>2.50</code>."
    )
    await render(
        callback,
        hint,
        navigation_keyboard(AdminSettingCB(action="coupons", page=1).pack()),
    )


@router.message(CouponAdminStates.waiting_value, F.text)
async def coupon_value(
    message: Message, state: FSMContext, admin: Admin, services: Services
) -> None:
    data = await state.get_data()
    try:
        value = parse_money(message.text or "")
    except ValueError as error:
        await message.answer(f"⚠️ {error}")
        return
    try:
        coupon = await services.store_settings.create_coupon(
            code=str(data["code"]),
            type=CouponType(str(data["coupon_type"])),
            value=Decimal(value),
            admin=admin,
        )
    except ValidationError as error:
        await state.clear()
        await message.answer(f"⚠️ {error.message}")
        return
    await state.clear()
    await message.answer(
        texts.coupon_detail(coupon), reply_markup=coupon_detail_keyboard(coupon)
    )


@router.callback_query(AdminSettingCB.filter(F.action == "coupon_toggle"))
async def toggle_coupon(
    callback: CallbackQuery,
    callback_data: AdminSettingCB,
    admin: Admin,
    services: Services,
) -> None:
    coupon = await services.store_settings.get_coupon(callback_data.target_id)
    await services.store_settings.toggle_coupon(coupon, admin)
    await render(
        callback,
        texts.coupon_detail(coupon),
        coupon_detail_keyboard(coupon, page=callback_data.page),
    )


@router.callback_query(
    AdminSettingCB.filter(F.action == "coupon_delete"), IsAdmin(AdminRole.SUPER_ADMIN)
)
async def delete_coupon(
    callback: CallbackQuery,
    callback_data: AdminSettingCB,
    services: Services,
    settings: Settings,
) -> None:
    coupon = await services.store_settings.get_coupon(callback_data.target_id)
    await services.store_settings.delete_coupon(coupon)
    result = await services.store_settings.paginate_coupons(
        1, settings.store.admin_list_page_size
    )
    await render(
        callback,
        texts.coupons_list(result),
        coupons_keyboard(result),
        answer_text="🗑 Coupon deleted.",
    )


# ---------------------------------------------------------------------- audit log
@router.callback_query(AdminSettingCB.filter(F.action == "logs"))
async def view_logs(
    callback: CallbackQuery,
    callback_data: AdminSettingCB,
    services: Services,
    settings: Settings,
) -> None:
    result = await services.store_settings.paginate_logs(
        callback_data.page, settings.store.admin_list_page_size
    )
    await render(callback, texts.audit_log(result), logs_keyboard(result))  # type: ignore[arg-type]
