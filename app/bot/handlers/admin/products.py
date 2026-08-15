"""Admin product management."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot.callbacks import AdminProductCB, ConfirmCB
from app.bot.filters import IsAdmin
from app.bot.handlers.helpers import answer_callback, render
from app.bot.keyboards.admin.catalog import (
    category_picker_keyboard,
    product_detail_keyboard,
    products_keyboard,
)
from app.bot.keyboards.common import confirm_keyboard, navigation_keyboard
from app.bot.states import ProductStates
from app.bot.texts import admin as texts
from app.config import Settings
from app.database.models import Admin, AdminRole
from app.services.registry import Services
from app.utils.text import clean_emoji, clean_multiline, clean_text

router = Router(name="admin-products")
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())

DELETE_SCOPE = "admin_product_delete"

#: Editable single fields and how to validate them.
FIELD_PROMPTS: dict[str, str] = {
    "name": "✏️ Send the new product name.",
    "description": "📝 Send the new description.",
    "emoji": "😀 Send a single emoji for this product.",
}


async def _show_list(
    event: Message | CallbackQuery, services: Services, settings: Settings, page: int
) -> None:
    result = await services.products.admin_page(page, settings.store.admin_list_page_size)
    await render(event, texts.products_list(result), products_keyboard(result))


async def _show_product(
    event: Message | CallbackQuery,
    services: Services,
    product_id: int,
    page: int = 1,
) -> None:
    product = await services.products.get_with_plans(product_id)
    stock = sum(plan.available_quantity for plan in product.plans)
    await render(
        event,
        texts.product_detail(product, plan_count=len(product.plans), stock=stock),
        product_detail_keyboard(product, page=page),
    )


@router.callback_query(AdminProductCB.filter(F.action == "list"))
async def list_products(
    callback: CallbackQuery,
    callback_data: AdminProductCB,
    state: FSMContext,
    services: Services,
    settings: Settings,
) -> None:
    await state.clear()
    await _show_list(callback, services, settings, callback_data.page)


@router.callback_query(AdminProductCB.filter(F.action == "view"))
async def view_product(
    callback: CallbackQuery,
    callback_data: AdminProductCB,
    state: FSMContext,
    services: Services,
) -> None:
    await state.clear()
    await _show_product(callback, services, callback_data.product_id, callback_data.page)


@router.callback_query(AdminProductCB.filter(F.action == "toggle"))
async def toggle_product(
    callback: CallbackQuery,
    callback_data: AdminProductCB,
    admin: Admin,
    services: Services,
) -> None:
    product = await services.products.get(callback_data.product_id)
    await services.products.toggle_product(product, admin)
    await _show_product(callback, services, product.id, callback_data.page)


@router.callback_query(AdminProductCB.filter(F.action == "feature"))
async def feature_product(
    callback: CallbackQuery,
    callback_data: AdminProductCB,
    admin: Admin,
    services: Services,
) -> None:
    product = await services.products.get(callback_data.product_id)
    await services.products.toggle_featured(product, admin)
    await _show_product(callback, services, product.id, callback_data.page)


@router.callback_query(AdminProductCB.filter(F.action == "move"))
async def move_product(
    callback: CallbackQuery,
    callback_data: AdminProductCB,
    admin: Admin,
    services: Services,
) -> None:
    product = await services.products.get(callback_data.product_id)
    await services.products.move_product(
        product, -1 if callback_data.value == "up" else 1, admin
    )
    await _show_product(callback, services, product.id, callback_data.page)


# ------------------------------------------------------------------ single field
@router.callback_query(AdminProductCB.filter(F.action == "field"))
async def edit_field(
    callback: CallbackQuery,
    callback_data: AdminProductCB,
    state: FSMContext,
    services: Services,
) -> None:
    product = await services.products.get(callback_data.product_id)
    field = callback_data.value
    back = AdminProductCB(
        action="view", product_id=product.id, page=callback_data.page
    ).pack()

    if field == "category":
        categories = await services.products.all_categories()
        await render(
            callback,
            "🗂 Choose a category for this product.",
            category_picker_keyboard(
                categories,
                callback=AdminProductCB(
                    action="set_category", product_id=product.id, value="{id}"
                ).pack(),
            ),
        )
        return

    prompt = FIELD_PROMPTS.get(field)
    if prompt is None:
        await answer_callback(callback, "Unsupported field.", alert=True)
        return
    await state.set_state(ProductStates.waiting_field_value)
    await state.update_data(product_id=product.id, field=field, page=callback_data.page)
    await render(callback, prompt, navigation_keyboard(back))


@router.message(ProductStates.waiting_field_value, F.text)
async def save_field(
    message: Message,
    state: FSMContext,
    admin: Admin,
    services: Services,
) -> None:
    data = await state.get_data()
    product = await services.products.get(int(data["product_id"]))
    field = str(data["field"])
    try:
        value = _validate_field(field, message.text or "")
    except ValueError as error:
        await message.answer(f"⚠️ {error}")
        return
    await services.products.update_product(product, admin=admin, **{field: value})
    await state.clear()
    await message.answer("✅ Product updated.")
    await _show_product(message, services, product.id, int(data.get("page", 1)))


def _validate_field(field: str, raw: str) -> str:
    if field == "name":
        return clean_text(raw, max_length=120, field="name")
    if field == "description":
        return clean_multiline(raw, max_length=1000, field="description")
    if field == "emoji":
        return clean_emoji(raw)
    raise ValueError("Unsupported field.")


@router.callback_query(AdminProductCB.filter(F.action == "set_category"))
async def set_category(
    callback: CallbackQuery,
    callback_data: AdminProductCB,
    admin: Admin,
    services: Services,
) -> None:
    product = await services.products.get(callback_data.product_id)
    category_id = int(callback_data.value or 0) or None
    await services.products.update_product(product, admin=admin, category_id=category_id)
    await _show_product(callback, services, product.id, callback_data.page)


# -------------------------------------------------------------------- new product
@router.callback_query(AdminProductCB.filter(F.action == "new"))
async def new_product(
    callback: CallbackQuery, state: FSMContext, services: Services
) -> None:
    await state.set_state(ProductStates.waiting_name)
    await state.update_data(new_product={})
    await render(
        callback,
        "➕ <b>New product</b>\n\nSend the product name.\n\n"
        "Send /cancel at any time to stop.",
        navigation_keyboard(AdminProductCB(action="list", page=1).pack()),
    )


@router.message(ProductStates.waiting_name, F.text)
async def wizard_name(message: Message, state: FSMContext) -> None:
    try:
        name = clean_text(message.text or "", max_length=120, field="name")
    except ValueError as error:
        await message.answer(f"⚠️ {error}")
        return
    await state.update_data(name=name)
    await state.set_state(ProductStates.waiting_emoji)
    await message.answer(
        "😀 Send an emoji for this product (or send <code>-</code> to use 🛍)."
    )


@router.message(ProductStates.waiting_emoji, F.text)
async def wizard_emoji(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip()
    emoji = "🛍"
    if raw != "-":
        try:
            emoji = clean_emoji(raw)
        except ValueError as error:
            await message.answer(f"⚠️ {error}")
            return
    await state.update_data(emoji=emoji)
    await state.set_state(ProductStates.waiting_description)
    await message.answer(
        "📝 Send a short description (or <code>-</code> to skip)."
    )


@router.message(ProductStates.waiting_description, F.text)
async def wizard_description(
    message: Message, state: FSMContext, services: Services
) -> None:
    raw = (message.text or "").strip()
    description = None
    if raw != "-":
        try:
            description = clean_multiline(raw, max_length=1000, field="description")
        except ValueError as error:
            await message.answer(f"⚠️ {error}")
            return
    await state.update_data(description=description)
    await state.set_state(ProductStates.waiting_category)
    categories = await services.products.all_categories()
    await message.answer(
        "🗂 Choose a category.",
        reply_markup=category_picker_keyboard(
            categories,
            callback=AdminProductCB(action="wizard_category", value="{id}").pack(),
        ),
    )


@router.callback_query(
    ProductStates.waiting_category, AdminProductCB.filter(F.action == "wizard_category")
)
async def wizard_category(
    callback: CallbackQuery,
    callback_data: AdminProductCB,
    state: FSMContext,
    admin: Admin,
    services: Services,
) -> None:
    data = await state.get_data()
    product = await services.products.create_product(
        name=str(data["name"]),
        description=data.get("description"),
        emoji=str(data.get("emoji", "🛍")),
        category_id=int(callback_data.value or 0) or None,
        admin=admin,
    )
    await state.clear()
    await answer_callback(callback, "✅ Product created.")
    await _show_product(callback, services, product.id)


# ----------------------------------------------------------------------- delete
@router.callback_query(AdminProductCB.filter(F.action == "delete"), IsAdmin(AdminRole.ADMIN))
async def ask_delete(
    callback: CallbackQuery, callback_data: AdminProductCB, services: Services
) -> None:
    product = await services.products.get_with_plans(callback_data.product_id)
    await render(
        callback,
        f"🗑 Delete <b>{product.name}</b>?\n\n"
        f"This also deletes {len(product.plans)} plan(s) and their inventory.\n"
        "This cannot be undone.",
        confirm_keyboard(
            DELETE_SCOPE,
            product.id,
            confirm_text="🗑 Yes, delete it",
            back_callback=AdminProductCB(
                action="view", product_id=product.id, page=callback_data.page
            ).pack(),
        ),
    )


@router.callback_query(
    ConfirmCB.filter(F.scope == DELETE_SCOPE), IsAdmin(AdminRole.ADMIN)
)
async def confirm_delete(
    callback: CallbackQuery,
    callback_data: ConfirmCB,
    admin: Admin,
    services: Services,
    settings: Settings,
) -> None:
    if callback_data.action == "yes":
        product = await services.products.get(callback_data.target_id)
        await services.products.delete_product(product, admin)
        await answer_callback(callback, "🗑 Product deleted.")
        await _show_list(callback, services, settings, 1)
        return
    await _show_product(callback, services, callback_data.target_id)
