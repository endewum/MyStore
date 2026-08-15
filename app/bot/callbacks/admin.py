"""Admin callback data factories."""

from __future__ import annotations

from aiogram.filters.callback_data import CallbackData


class AdminCB(CallbackData, prefix="a"):
    """Admin panel sections: ``home``, ``dashboard``, ``products`` ..."""

    section: str
    page: int = 1


class AdminProductCB(CallbackData, prefix="ap"):
    """Product administration.

    ``action`` values: ``list``, ``view``, ``new``, ``edit``, ``field``,
    ``toggle``, ``feature``, ``move``, ``delete``, ``confirm_delete``, ``plans``.
    """

    action: str
    product_id: int = 0
    page: int = 1
    value: str = ""


class AdminPlanCB(CallbackData, prefix="apl"):
    """Plan administration.

    ``action`` values: ``list``, ``view``, ``new``, ``field``, ``price``,
    ``toggle``, ``feature``, ``move``, ``delete``, ``confirm_delete``, ``stock``.
    """

    action: str
    plan_id: int = 0
    product_id: int = 0
    page: int = 1
    value: str = ""


class AdminStockCB(CallbackData, prefix="ast"):
    """Stock and inventory operations.

    ``action`` values: ``view``, ``add``, ``remove``, ``set``, ``import``,
    ``items``, ``item_toggle``, ``item_delete``, ``low``.
    """

    action: str
    plan_id: int = 0
    page: int = 1
    item_id: int = 0


class AdminStockNotifyCB(CallbackData, prefix="asn"):
    """Restock notification decisions.

    ``action`` values: ``menu``, ``preview``, ``interested``, ``all``, ``skip``.
    """

    action: str
    plan_id: int


class AdminOrderCB(CallbackData, prefix="ao"):
    """Order administration.

    ``action`` values: ``list``, ``view``, ``filter``, ``process``, ``fulfill``,
    ``cancel``, ``refund``, ``history``, ``proof``.
    """

    action: str
    order_id: int = 0
    page: int = 1
    value: str = ""


class AdminPaymentCB(CallbackData, prefix="apay"):
    """Payment review and payment-method settings.

    ``action`` values: ``queue``, ``view``, ``confirm``, ``reject``, ``proof``,
    ``methods``, ``method``, ``toggle``, ``field``.
    """

    action: str
    payment_id: int = 0
    method_id: int = 0
    page: int = 1
    value: str = ""


class AdminUserCB(CallbackData, prefix="au"):
    """User administration: ``list``, ``view``, ``block``, ``unblock``,
    ``search``, ``orders``, ``admins``, ``grant``, ``revoke``."""

    action: str
    user_id: int = 0
    page: int = 1
    value: str = ""


class AdminBroadcastCB(CallbackData, prefix="ab"):
    """Broadcast composer: ``menu``, ``new``, ``audience``, ``preview``,
    ``send``, ``cancel``, ``history``, ``view``."""

    action: str
    broadcast_id: int = 0
    page: int = 1
    value: str = ""


class AdminSettingCB(CallbackData, prefix="as"):
    """Settings, categories, coupons and audit log.

    ``action`` values: ``menu``, ``edit``, ``categories``, ``category``,
    ``category_new``, ``category_toggle``, ``category_delete``, ``coupons``,
    ``coupon``, ``coupon_new``, ``coupon_toggle``, ``logs``.
    """

    action: str
    target_id: int = 0
    page: int = 1
    value: str = ""
