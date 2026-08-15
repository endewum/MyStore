"""Manual payment service.

Payments are **never** verified automatically. The customer picks a channel,
transfers funds outside Telegram, submits evidence, and an administrator
approves or rejects it by hand.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import StoreSettings
from app.database.models import (
    Admin,
    AdminAction,
    Order,
    OrderStatus,
    Payment,
    PaymentMethod,
    PaymentStatus,
    User,
)
from app.database.repositories import (
    AdminLogRepository,
    PaymentMethodRepository,
    PaymentRepository,
)
from app.services.exceptions import (
    NotFoundError,
    PaymentMethodUnavailable,
    PermissionDeniedError,
    ValidationError,
)
from app.services.order_service import OrderService
from app.utils.logging import get_logger
from app.utils.pagination import Page
from app.utils.time import utcnow

logger = get_logger(__name__)


class PaymentService:
    def __init__(
        self, session: AsyncSession, store: StoreSettings, orders: OrderService
    ) -> None:
        self.session = session
        self.store = store
        self.orders = orders
        self.payments = PaymentRepository(session)
        self.methods = PaymentMethodRepository(session)
        self.logs = AdminLogRepository(session)

    # ---------------------------------------------------------------- methods
    async def enabled_methods(self) -> Sequence[PaymentMethod]:
        return await self.methods.list_enabled()

    async def all_methods(self) -> Sequence[PaymentMethod]:
        return await self.methods.list_all_ordered()

    async def get_method(self, method_id: int) -> PaymentMethod:
        method = await self.methods.get(method_id)
        if method is None:
            raise NotFoundError("This payment method no longer exists.")
        return method

    async def get_usable_method(self, method_id: int) -> PaymentMethod:
        method = await self.get_method(method_id)
        if not method.is_enabled or not method.is_configured:
            raise PaymentMethodUnavailable()
        return method

    async def update_method(
        self,
        method: PaymentMethod,
        *,
        admin: Admin | None = None,
        **fields: object,
    ) -> PaymentMethod:
        allowed = {
            "name",
            "emoji",
            "account_identifier",
            "network",
            "instructions",
            "is_enabled",
            "requires_screenshot",
            "min_amount",
            "sort_order",
        }
        unknown = set(fields) - allowed
        if unknown:
            raise ValidationError(f"Unsupported field: {', '.join(sorted(unknown))}")
        for key, value in fields.items():
            setattr(method, key, value)
        await self.session.flush()
        if admin is not None:
            await self.logs.log(
                admin.telegram_id,
                AdminAction.ADMIN_UPDATED_PAYMENT_METHOD,
                admin_username=admin.user.username if admin.user else None,
                target_type="payment_method",
                target_id=method.id,
                description=f"{method.name}: {', '.join(sorted(fields))}",
            )
        return method

    async def toggle_method(
        self, method: PaymentMethod, admin: Admin | None = None
    ) -> PaymentMethod:
        return await self.update_method(
            method, is_enabled=not method.is_enabled, admin=admin
        )

    # ---------------------------------------------------------------- payments
    async def get(self, payment_id: int) -> Payment:
        payment = await self.payments.get_full(payment_id)
        if payment is None:
            raise NotFoundError("This payment record no longer exists.")
        return payment

    async def latest_for_order(self, order_id: int) -> Payment | None:
        return await self.payments.latest_for_order(order_id)

    async def select_method(
        self, order: Order, user: User, method: PaymentMethod
    ) -> Payment:
        """Create or update the pending payment for a chosen channel."""
        if order.user_id != user.id:
            raise PermissionDeniedError("This order does not belong to you.")
        if order.status not in {
            OrderStatus.PENDING_PAYMENT,
            OrderStatus.PAYMENT_REJECTED,
        }:
            raise ValidationError("This order is not awaiting a payment.")
        if Decimal(order.total) < method.min_amount:
            raise ValidationError(
                f"{method.name} requires a minimum of ${method.min_amount:,.2f}."
            )

        payment = await self.payments.latest_for_order(order.id)
        if payment is None or payment.status in {
            PaymentStatus.CONFIRMED,
            PaymentStatus.REJECTED,
        }:
            payment = Payment(
                order_id=order.id,
                user_id=user.id,
                amount=order.total,
                currency=order.currency,
            )
            await self.payments.add(payment)

        payment.method_id = method.id
        payment.method_code = method.code
        payment.method_name = method.name
        payment.status = PaymentStatus.PENDING
        payment.amount = order.total
        await self.session.flush()
        return payment

    async def submit_evidence(
        self,
        order: Order,
        user: User,
        *,
        reference: str | None = None,
        proof_file_id: str | None = None,
        proof_file_unique_id: str | None = None,
        note: str | None = None,
    ) -> Payment:
        """Record customer-submitted evidence and queue the order for review."""
        if order.user_id != user.id:
            raise PermissionDeniedError("This order does not belong to you.")
        if order.status not in {
            OrderStatus.PENDING_PAYMENT,
            OrderStatus.PAYMENT_REJECTED,
        }:
            raise ValidationError("This order is not awaiting a payment.")

        payment = await self.payments.latest_for_order(order.id)
        if payment is None:
            raise ValidationError("Please choose a payment method first.")
        if not reference and not proof_file_id:
            raise ValidationError(
                "Send a transaction ID or a screenshot of your transfer."
            )
        method = await self.methods.get(payment.method_id) if payment.method_id else None
        if method and method.requires_screenshot and not proof_file_id:
            raise ValidationError(
                f"{method.name} requires a payment screenshot. Please send the image."
            )

        if reference:
            payment.reference = reference[:255]
        if proof_file_id:
            payment.proof_file_id = proof_file_id
            payment.proof_file_unique_id = proof_file_unique_id
        if note:
            payment.customer_note = note
        payment.status = PaymentStatus.SUBMITTED
        payment.submitted_at = utcnow()
        payment.rejection_reason = None
        await self.session.flush()

        await self.orders.transition(
            order,
            OrderStatus.PAYMENT_SUBMITTED,
            actor_telegram_id=user.telegram_id,
            reason="Customer submitted payment evidence",
        )
        logger.info(
            "payment.submitted",
            order_id=order.id,
            payment_id=payment.id,
            method=payment.method_code,
        )
        return payment

    async def confirm(self, payment: Payment, admin: Admin) -> Order:
        """Approve a submitted payment; the order becomes PAID."""
        if payment.status is PaymentStatus.CONFIRMED:
            raise ValidationError("This payment was already confirmed.")
        if payment.status is not PaymentStatus.SUBMITTED:
            raise ValidationError("Only submitted payments can be confirmed.")

        order = await self.orders.get(payment.order_id)
        payment.status = PaymentStatus.CONFIRMED
        payment.reviewed_at = utcnow()
        payment.reviewed_by_telegram_id = admin.telegram_id
        await self.session.flush()

        order = await self.orders.transition(
            order,
            OrderStatus.PAID,
            actor_telegram_id=admin.telegram_id,
            reason="Payment confirmed by admin",
        )
        await self.logs.log(
            admin.telegram_id,
            AdminAction.ADMIN_CONFIRMED_PAYMENT,
            admin_username=admin.user.username if admin.user else None,
            target_type="payment",
            target_id=payment.id,
            description=f"Order #{order.order_number} — {payment.amount_display}",
        )
        logger.info("payment.confirmed", order_id=order.id, payment_id=payment.id)
        return order

    async def reject(
        self, payment: Payment, admin: Admin, reason: str | None = None
    ) -> Order:
        """Reject a submitted payment; the customer may submit again."""
        if payment.status is not PaymentStatus.SUBMITTED:
            raise ValidationError("Only submitted payments can be rejected.")

        order = await self.orders.get(payment.order_id)
        payment.status = PaymentStatus.REJECTED
        payment.reviewed_at = utcnow()
        payment.reviewed_by_telegram_id = admin.telegram_id
        payment.rejection_reason = (reason or "")[:255] or None
        await self.session.flush()

        order = await self.orders.transition(
            order,
            OrderStatus.PAYMENT_REJECTED,
            actor_telegram_id=admin.telegram_id,
            reason=reason or "Payment rejected by admin",
        )
        await self.logs.log(
            admin.telegram_id,
            AdminAction.ADMIN_REJECTED_PAYMENT,
            admin_username=admin.user.username if admin.user else None,
            target_type="payment",
            target_id=payment.id,
            description=f"Order #{order.order_number}: {reason or 'no reason given'}",
        )
        logger.info("payment.rejected", order_id=order.id, payment_id=payment.id)
        return order

    async def paginate_review_queue(self, page: int, per_page: int) -> Page[Payment]:
        return await self.payments.paginate_pending_review(page, per_page)

    async def count_review_queue(self) -> int:
        return await self.payments.count_pending_review()
