"""Customer FSM states."""

from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class SearchStates(StatesGroup):
    """🔎 Search flow."""

    waiting_query = State()


class PaymentStates(StatesGroup):
    """Manual payment evidence submission."""

    waiting_evidence = State()


class CouponStates(StatesGroup):
    """Optional coupon entry during order confirmation."""

    waiting_code = State()


class SupportStates(StatesGroup):
    """Free-form message forwarded to the admin team."""

    waiting_message = State()
