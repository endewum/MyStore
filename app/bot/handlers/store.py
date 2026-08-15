"""Storefront: product grid, categories and search."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot.callbacks import CategoryCB, MenuCB, SearchCB, StoreCB
from app.bot.handlers.helpers import answer_callback, render
from app.bot.keyboards.common import BTN_SEARCH, BTN_STORE, navigation_keyboard
from app.bot.keyboards.store import (
    categories_keyboard,
    flat_store_keyboard,
    search_results_keyboard,
)
from app.bot.states import SearchStates
from app.bot.texts import customer as texts
from app.config import Settings
from app.database.models import User
from app.services.exceptions import ValidationError
from app.services.registry import Services

router = Router(name="store")


async def _show_store(
    event: Message | CallbackQuery,
    state: FSMContext,
    user: User,
    services: Services,
    settings: Settings,
    *,
    page: int = 1,
    category_id: int = 0,
) -> None:
    """Render the paginated, plan-by-plan customer catalogue."""
    result = await services.plans.store_page(
        page, settings.store.plans_per_page, category_id or None
    )
    category_name = None
    if category_id:
        category = await services.products.get_category(category_id)
        category_name = category.name
    # Remember where the customer was so plan detail can return to this page.
    await state.update_data(
        store_page=result.page, store_category=category_id, store_view="flat"
    )
    subscribed = {
        plan.id
        for plan in result.items
        if plan.is_sold_out
        and await services.notifications.is_subscribed(plan.id, user)
    }
    await render(
        event,
        texts.flat_store_page(result, category_name=category_name),
        flat_store_keyboard(
            result,
            category_id=category_id,
            subscribed_plan_ids=subscribed,
        ),
    )


@router.message(Command("store"))
@router.message(F.text == BTN_STORE)
async def cmd_store(
    message: Message,
    state: FSMContext,
    user: User,
    services: Services,
    settings: Settings,
) -> None:
    await state.clear()
    await _show_store(message, state, user, services, settings)


@router.callback_query(MenuCB.filter(F.action == "store"))
async def open_store(
    callback: CallbackQuery,
    state: FSMContext,
    user: User,
    services: Services,
    settings: Settings,
) -> None:
    await state.clear()
    await _show_store(callback, state, user, services, settings)


@router.callback_query(StoreCB.filter())
async def paginate_store(
    callback: CallbackQuery,
    callback_data: StoreCB,
    state: FSMContext,
    user: User,
    services: Services,
    settings: Settings,
) -> None:
    await _show_store(
        callback,
        state,
        user,
        services,
        settings,
        page=callback_data.page,
        category_id=callback_data.category,
    )


@router.callback_query(CategoryCB.filter())
async def open_categories(callback: CallbackQuery, services: Services) -> None:
    categories = await services.products.visible_categories()
    await render(
        callback, texts.categories(len(categories)), categories_keyboard(categories)
    )


# ----------------------------------------------------------------------- search
async def _start_search(event: Message | CallbackQuery, state: FSMContext) -> None:
    await state.set_state(SearchStates.waiting_query)
    await render(
        event,
        texts.search_prompt(),
        navigation_keyboard(StoreCB(page=1, category=0).pack()),
    )


@router.message(Command("search"))
@router.message(F.text == BTN_SEARCH)
async def cmd_search(message: Message, state: FSMContext) -> None:
    await _start_search(message, state)


@router.callback_query(MenuCB.filter(F.action == "search"))
@router.callback_query(SearchCB.filter(F.action == "start"))
async def open_search(callback: CallbackQuery, state: FSMContext) -> None:
    await _start_search(callback, state)


@router.message(SearchStates.waiting_query, F.text)
async def run_search(
    message: Message, state: FSMContext, services: Services, settings: Settings
) -> None:
    query = (message.text or "").strip()
    try:
        result = await services.products.search(
            query, 1, settings.store.products_per_page
        )
    except ValidationError as error:
        await message.answer(f"⚠️ {error.message}")
        return
    # Leave the FSM state but keep the term so result pages can be re-queried.
    await state.set_state(None)
    await state.update_data(search_query=query)
    await message.answer(
        texts.search_results(query, result), reply_markup=search_results_keyboard(result)
    )


@router.callback_query(SearchCB.filter(F.action == "page"))
async def paginate_search(
    callback: CallbackQuery,
    callback_data: SearchCB,
    state: FSMContext,
    services: Services,
    settings: Settings,
) -> None:
    data = await state.get_data()
    query = data.get("search_query", "")
    if not query:
        await answer_callback(callback, "Please start a new search.", alert=True)
        await _start_search(callback, state)
        return
    result = await services.products.search(
        query, callback_data.page, settings.store.products_per_page
    )
    await render(
        callback, texts.search_results(query, result), search_results_keyboard(result)
    )
