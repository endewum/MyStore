"""Customer-facing callback data factories.

Telegram limits callback payloads to 64 bytes, so every factory keeps a short
prefix and only carries identifiers — never display text.
"""

from __future__ import annotations

from aiogram.filters.callback_data import CallbackData


class MenuCB(CallbackData, prefix="m"):
    """Top level navigation: ``m:home``, ``m:store`` ..."""

    action: str


class StoreCB(CallbackData, prefix="st"):
    """Storefront grid navigation with optional category filter."""

    page: int = 1
    category: int = 0


class CategoryCB(CallbackData, prefix="cat"):
    page: int = 1


class ProductCB(CallbackData, prefix="p"):
    """Product screen actions: ``view``, ``notify`` and ``unnotify``."""

    product_id: int
    action: str = "view"
    page: int = 1


class PlanCB(CallbackData, prefix="pl"):
    """Plan actions: ``view``, ``buy``, ``notify``, ``unnotify``."""

    action: str
    plan_id: int
    page: int = 1


class OrderCB(CallbackData, prefix="o"):
    """Customer order actions: ``view``, ``cancel``, ``pay``, ``list``."""

    action: str
    order_id: int = 0
    page: int = 1


class PayCB(CallbackData, prefix="pay"):
    """Payment flow: ``choose``, ``method``, ``paid``, ``cancel``."""

    action: str
    order_id: int
    method_id: int = 0


class AccountCB(CallbackData, prefix="acc"):
    """Account screens: ``home``, ``settings``, ``alerts``, ``toggle_notify``."""

    action: str
    page: int = 1


class NotifyCB(CallbackData, prefix="nt"):
    """Notification inbox: ``list``, ``read_all``, ``alerts``, ``drop``."""

    action: str
    page: int = 1
    target_id: int = 0


class SearchCB(CallbackData, prefix="sr"):
    """Search result pagination; the term itself lives in the FSM state."""

    action: str
    page: int = 1


class ConfirmCB(CallbackData, prefix="cf"):
    """Generic confirmation: ``scope`` identifies what is being confirmed."""

    scope: str
    action: str
    target_id: int = 0


class NoopCB(CallbackData, prefix="noop"):
    """Inert button (page indicators, section headers)."""

    tag: str = "x"
