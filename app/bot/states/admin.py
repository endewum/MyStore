"""Admin FSM states."""

from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class ProductStates(StatesGroup):
    """➕ Add product wizard and single-field edits."""

    waiting_name = State()
    waiting_description = State()
    waiting_emoji = State()
    waiting_category = State()
    waiting_image = State()
    waiting_field_value = State()


class PlanStates(StatesGroup):
    """➕ Add plan wizard and single-field edits."""

    waiting_name = State()
    waiting_price = State()
    waiting_duration = State()
    waiting_description = State()
    waiting_delivery_type = State()
    waiting_stock = State()
    waiting_field_value = State()


class StockStates(StatesGroup):
    """Stock adjustments and bulk code imports."""

    waiting_quantity = State()
    waiting_codes = State()


class OrderStates(StatesGroup):
    """Manual fulfilment and order moderation."""

    waiting_delivery_content = State()
    waiting_cancel_reason = State()
    waiting_order_search = State()


class PaymentReviewStates(StatesGroup):
    """Payment rejection reason."""

    waiting_rejection_reason = State()


class PaymentMethodStates(StatesGroup):
    """Payment channel configuration."""

    waiting_field_value = State()


class BroadcastStates(StatesGroup):
    """📢 Broadcast composer."""

    waiting_content = State()
    waiting_audience = State()
    waiting_button_text = State()


class UserAdminStates(StatesGroup):
    """User lookup and moderation."""

    waiting_search = State()
    waiting_block_reason = State()
    waiting_admin_id = State()


class CategoryStates(StatesGroup):
    waiting_name = State()
    waiting_emoji = State()
    waiting_field_value = State()


class CouponAdminStates(StatesGroup):
    waiting_code = State()
    waiting_value = State()
    waiting_max_uses = State()


class SettingStates(StatesGroup):
    waiting_value = State()
