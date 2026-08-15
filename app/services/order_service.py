"""Order lifecycle service.

All order status changes funnel through :meth:`OrderService.transition`, which
enforces the state machine below. Handlers never assign ``order.status``
directly.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import StoreSettings
from app.database.models import (
    Admin,
    AdminAction,
    Coupon,
    Order,
    OrderItem,
    OrderStatus,
    Plan,
    User,
)
from app.database.repositories import (
    AdminLogRepository,
    CouponRepository,
    OrderHistoryRepository,
    OrderRepository,
    UserRepository,
)
from app.services.exceptions import (
    InvalidStateTransition,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from app.services.inventory_service import InventoryService
from app.utils.logging import get_logger
from app.utils.pagination import Page
from app.utils.time import in_minutes, utcnow

logger = get_logger(__name__)

#: Allowed order state transitions. Anything not listed is rejected.
ALLOWED_TRANSITIONS: dict[OrderStatus, frozenset[OrderStatus]] = {
    OrderStatus.PENDING_PAYMENT: frozenset(
        {OrderStatus.PAYMENT_SUBMITTED, OrderStatus.CANCELLED}
    ),
    OrderStatus.PAYMENT_SUBMITTED: frozenset(
        {OrderStatus.PAID, OrderStatus.PAYMENT_REJECTED, OrderStatus.CANCELLED}
    ),
    OrderStatus.PAYMENT_REJECTED: frozenset(
        {OrderStatus.PAYMENT_SUBMITTED, OrderStatus.CANCELLED}
    ),
    OrderStatus.PAID: frozenset(
        {
            OrderStatus.PROCESSING,
            OrderStatus.READY,
            OrderStatus.DELIVERED,
            OrderStatus.CANCELLED,
            OrderStatus.REFUNDED,
        }
    ),
    OrderStatus.PROCESSING: frozenset(
        {
            OrderStatus.READY,
            OrderStatus.DELIVERED,
            OrderStatus.CANCELLED,
            OrderStatus.REFUNDED,
        }
    ),
    OrderStatus.READY: frozenset(
        {OrderStatus.DELIVERED, OrderStatus.CANCELLED, OrderStatus.REFUNDED}
    ),
    OrderStatus.DELIVERED: frozenset({OrderStatus.REFUNDED}),
    OrderStatus.CANCELLED: frozenset(),
    OrderStatus.REFUNDED: frozenset(),
}

#: Statuses in which reserved stock must be handed back to the pool.
_RELEASING_STATUSES = frozenset({OrderStatus.CANCELLED, OrderStatus.REFUNDED})


def can_transition(current: OrderStatus, target: OrderStatus) -> bool:
    return target in ALLOWED_TRANSITIONS.get(current, frozenset())


class OrderService:
    def __init__(self, session: AsyncSession, store: StoreSettings) -> None:
        self.session = session
        self.store = store
        self.orders = OrderRepository(session)
        self.history = OrderHistoryRepository(session)
        self.coupons = CouponRepository(session)
        self.users = UserRepository(session)
        self.logs = AdminLogRepository(session)
        self.inventory = InventoryService(session)

    # ----------------------------------------------------------------- reading
    async def get(self, order_id: int) -> Order:
        order = await self.orders.get_full(order_id)
        if order is None:
            raise NotFoundError("This order no longer exists.")
        return order

    async def get_for_user(self, order_id: int, user: User) -> Order:
        """Fetch an order, enforcing ownership so IDs cannot be enumerated."""
        order = await self.get(order_id)
        if order.user_id != user.id:
            logger.warning(
                "order.ownership_violation",
                order_id=order_id,
                telegram_id=user.telegram_id,
            )
            raise PermissionDeniedError("This order does not belong to you.")
        return order

    async def history_for_order(self, order_id: int) -> Sequence[object]:
        return await self.history.list_for_order(order_id)

    async def paginate_for_user(
        self, user: User, page: int, per_page: int | None = None
    ) -> Page[Order]:
        return await self.orders.paginate_for_user(
            user.id, page, per_page or self.store.orders_per_page
        )

    async def paginate_admin(
        self, statuses: Sequence[OrderStatus] | None, page: int, per_page: int
    ) -> Page[Order]:
        return await self.orders.paginate_by_status(statuses, page, per_page)

    async def count_open_for_user(self, user: User) -> int:
        """Orders where the customer still has something to do."""
        return await self.orders.count_for_user(
            user.id,
            [
                OrderStatus.PENDING_PAYMENT,
                OrderStatus.PAYMENT_SUBMITTED,
                OrderStatus.PAYMENT_REJECTED,
            ],
        )

    # ---------------------------------------------------------------- creation
    async def create_order(
        self,
        user: User,
        plan: Plan,
        *,
        coupon_code: str | None = None,
        expires_in_minutes: int | None = None,
    ) -> Order:
        """Create a PENDING_PAYMENT order and reserve one unit of stock.

        ``expires_in_minutes`` lets the caller apply the admin-configured
        payment window; it falls back to the value from the environment.
        """
        if user.is_blocked:
            raise PermissionDeniedError("Your account cannot place orders.")
        if not plan.is_active or not plan.product.is_active:
            raise ValidationError("This plan is not on sale right now.")

        subtotal = Decimal(plan.price)
        coupon: Coupon | None = None
        discount = Decimal("0.00")
        if coupon_code:
            coupon = await self._validate_coupon(coupon_code, subtotal)
            discount = coupon.discount_for(subtotal)

        order = Order(
            order_number=await self.orders.next_order_number(),
            user_id=user.id,
            telegram_id=user.telegram_id,
            status=OrderStatus.PENDING_PAYMENT,
            subtotal=subtotal,
            discount=discount,
            total=subtotal - discount,
            currency=plan.currency,
            coupon_id=coupon.id if coupon else None,
            coupon_code=coupon.code if coupon else None,
            expires_at=in_minutes(
                expires_in_minutes or self.store.payment_timeout_minutes
            ),
        )
        # Build the line item while the order is still transient: appending to
        # a pending collection avoids a lazy load, and the insert cascades.
        order.items.append(
            OrderItem(
                plan_id=plan.id,
                product_id=plan.product_id,
                product_name=plan.product.name,
                plan_name=plan.name,
                duration=plan.duration,
                unit_price=plan.price,
                quantity=1,
                delivery_type=plan.delivery_type.value,
            )
        )
        await self.orders.add(order)

        # Reserve after the order exists so inventory rows can reference it.
        await self.inventory.reserve_for_order(plan, order)

        if coupon is not None:
            coupon.used_count += 1

        await self._record_history(order, None, OrderStatus.PENDING_PAYMENT, user.telegram_id)
        logger.info(
            "order.created",
            order_id=order.id,
            order_number=order.order_number,
            plan_id=plan.id,
            telegram_id=user.telegram_id,
        )
        return order

    async def _validate_coupon(self, code: str, subtotal: Decimal) -> Coupon:
        coupon = await self.coupons.get_by_code(code)
        if coupon is None or not coupon.is_usable:
            raise ValidationError("That coupon code is not valid.")
        if subtotal < coupon.min_order_total:
            raise ValidationError(
                f"This coupon requires a minimum order of ${coupon.min_order_total:,.2f}."
            )
        return coupon

    # -------------------------------------------------------------- transitions
    async def transition(
        self,
        order: Order,
        target: OrderStatus,
        *,
        actor_telegram_id: int | None = None,
        reason: str | None = None,
    ) -> Order:
        """Move an order to ``target``, enforcing the state machine."""
        current = order.status
        if current is target:
            return order
        if not can_transition(current, target):
            raise InvalidStateTransition(current.value, target.value)

        order.status = target
        if target is OrderStatus.PAID:
            order.paid_at = utcnow()
        elif target is OrderStatus.DELIVERED:
            order.delivered_at = utcnow()
        elif target in _RELEASING_STATUSES:
            order.cancel_reason = reason or order.cancel_reason
            await self.inventory.release_for_order(order)

        await self._record_history(order, current, target, actor_telegram_id, reason)
        await self.session.flush()
        logger.info(
            "order.transition",
            order_id=order.id,
            from_status=current.value,
            to_status=target.value,
        )
        return order

    async def cancel_by_customer(self, order: Order, user: User) -> Order:
        """Let a customer abandon an order that has not been paid yet."""
        if order.user_id != user.id:
            raise PermissionDeniedError("This order does not belong to you.")
        if order.status is not OrderStatus.PENDING_PAYMENT:
            raise ValidationError(
                "This order can no longer be cancelled. Please contact support."
            )
        return await self.transition(
            order,
            OrderStatus.CANCELLED,
            actor_telegram_id=user.telegram_id,
            reason="Cancelled by customer",
        )

    async def cancel_by_admin(
        self, order: Order, admin: Admin, reason: str | None = None
    ) -> Order:
        order = await self.transition(
            order,
            OrderStatus.CANCELLED,
            actor_telegram_id=admin.telegram_id,
            reason=reason or "Cancelled by admin",
        )
        await self._log(admin, AdminAction.ADMIN_CANCELLED_ORDER, order, reason)
        return order

    async def refund(self, order: Order, admin: Admin, reason: str | None = None) -> Order:
        order = await self.transition(
            order,
            OrderStatus.REFUNDED,
            actor_telegram_id=admin.telegram_id,
            reason=reason or "Refunded by admin",
        )
        await self._log(admin, AdminAction.ADMIN_REFUNDED_ORDER, order, reason)
        return order

    async def start_processing(self, order: Order, admin: Admin) -> Order:
        return await self.transition(
            order, OrderStatus.PROCESSING, actor_telegram_id=admin.telegram_id
        )

    async def fulfill(
        self, order: Order, admin: Admin, delivery_content: str
    ) -> Order:
        """Attach the delivery payload and mark the order DELIVERED."""
        if order.status not in {
            OrderStatus.PAID,
            OrderStatus.PROCESSING,
            OrderStatus.READY,
        }:
            raise InvalidStateTransition(order.status.value, OrderStatus.DELIVERED.value)
        content = delivery_content.strip()
        if not content:
            raise ValidationError("Delivery details cannot be empty.")

        order.delivery_content = content
        await self.inventory.consume_for_order(order)
        order = await self.transition(
            order,
            OrderStatus.DELIVERED,
            actor_telegram_id=admin.telegram_id,
            reason="Fulfilled by admin",
        )
        user = await self.users.get(order.user_id)
        if user is not None:
            user.total_orders += 1
        await self._log(admin, AdminAction.ADMIN_FULFILLED_ORDER, order, None)
        return order

    async def auto_delivery_preview(self, order: Order) -> str | None:
        """Inventory values reserved for this order, to pre-fill fulfilment."""
        items = await self.inventory.items_for_order(order.id)
        if not items:
            return None
        return "\n".join(item.value for item in items)

    async def expire_stale_orders(self, limit: int = 50) -> list[Order]:
        """Cancel unpaid orders past their payment window, freeing stock."""
        expired: list[Order] = []
        for order in await self.orders.list_expired_pending(limit):
            await self.transition(
                order, OrderStatus.CANCELLED, reason="Payment window expired"
            )
            expired.append(order)
        return expired

    # ---------------------------------------------------------------- internals
    async def _record_history(
        self,
        order: Order,
        from_status: OrderStatus | None,
        to_status: OrderStatus,
        actor_telegram_id: int | None,
        reason: str | None = None,
    ) -> None:
        await self.history.create(
            order_id=order.id,
            from_status=from_status,
            to_status=to_status,
            changed_by_telegram_id=actor_telegram_id,
            reason=reason,
        )

    async def _log(
        self,
        admin: Admin,
        action: AdminAction,
        order: Order,
        description: str | None,
    ) -> None:
        await self.logs.log(
            admin.telegram_id,
            action,
            admin_username=admin.username,
            target_type="order",
            target_id=order.id,
            description=description or f"Order #{order.order_number}",
        )
