"""Stock and inventory management.

``Plan.stock_quantity`` is the single number the storefront reads, while
``inventory`` rows hold the actual deliverables for CODE/ACCOUNT/INFORMATION
plans. Both are always mutated together through this service so they can never
drift apart, and every mutation reports whether the plan just came back in
stock — that signal drives the notification system.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import (
    Admin,
    AdminAction,
    DeliveryType,
    InventoryItem,
    InventoryStatus,
    Order,
    Plan,
)
from app.database.repositories import (
    AdminLogRepository,
    InventoryRepository,
    PlanRepository,
    StockAlertRepository,
)
from app.services.exceptions import NotFoundError, OutOfStockError, ValidationError
from app.utils.logging import get_logger
from app.utils.pagination import Page
from app.utils.time import utcnow

logger = get_logger(__name__)


@dataclass(slots=True)
class StockChange:
    """Result of a stock mutation, including the back-in-stock signal."""

    plan: Plan
    previous_stock: int
    new_stock: int
    previous_available: int
    new_available: int
    #: Units actually added (positive) or removed (negative).
    delta: int
    #: Inventory rows created by this operation, if any.
    created_items: int = 0
    #: Lines rejected as duplicates during a code import.
    duplicates: int = 0
    waiting_users: int = 0

    @property
    def back_in_stock(self) -> bool:
        """True when a sold-out plan became purchasable again."""
        return self.previous_available <= 0 and self.new_available > 0

    @property
    def became_sold_out(self) -> bool:
        return self.previous_available > 0 and self.new_available <= 0


class InventoryService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.plans = PlanRepository(session)
        self.items = InventoryRepository(session)
        self.alerts = StockAlertRepository(session)
        self.logs = AdminLogRepository(session)

    # ---------------------------------------------------------------- reading
    async def breakdown(self, plan_id: int) -> dict[InventoryStatus, int]:
        return await self.items.status_breakdown(plan_id)

    async def paginate_items(
        self, plan_id: int, page: int, per_page: int
    ) -> Page[InventoryItem]:
        return await self.items.paginate_for_plan(plan_id, page, per_page)

    async def items_for_order(self, order_id: int) -> Sequence[InventoryItem]:
        return await self.items.list_for_order(order_id)

    async def get_item(self, item_id: int) -> InventoryItem:
        item = await self.items.get(item_id)
        if item is None:
            raise NotFoundError("This inventory item no longer exists.")
        return item

    # --------------------------------------------------------- admin mutation
    async def add_stock(
        self, plan: Plan, quantity: int, *, admin: Admin | None = None
    ) -> StockChange:
        """Increase the plain stock counter (used for MANUAL fulfilment)."""
        if quantity <= 0:
            raise ValidationError("Quantity must be greater than zero.")
        snapshot = self._snapshot(plan)
        plan.stock_quantity += quantity
        await self.session.flush()
        change = await self._build_change(plan, snapshot, delta=quantity)
        await self._log(
            admin,
            AdminAction.ADMIN_ADDED_STOCK,
            plan,
            f"+{quantity} (stock {change.previous_stock} -> {change.new_stock})",
        )
        return change

    async def import_codes(
        self,
        plan: Plan,
        values: Sequence[str],
        *,
        admin: Admin | None = None,
        note: str | None = None,
    ) -> StockChange:
        """Bulk-create inventory rows, skipping values already stored."""
        if not values:
            raise ValidationError("No codes were provided.")
        snapshot = self._snapshot(plan)
        created = 0
        duplicates = 0
        for raw in values:
            value = raw.strip()
            if not value:
                continue
            if await self.items.exists_value(plan.id, value):
                duplicates += 1
                continue
            self.session.add(
                InventoryItem(
                    plan_id=plan.id,
                    value=value,
                    note=note,
                    status=InventoryStatus.AVAILABLE,
                    added_by_telegram_id=admin.telegram_id if admin else None,
                )
            )
            created += 1
        plan.stock_quantity += created
        await self.session.flush()
        change = await self._build_change(
            plan, snapshot, delta=created, created_items=created, duplicates=duplicates
        )
        await self._log(
            admin,
            AdminAction.ADMIN_IMPORTED_CODES,
            plan,
            f"imported {created} item(s), {duplicates} duplicate(s)",
        )
        return change

    async def remove_stock(
        self, plan: Plan, quantity: int, *, admin: Admin | None = None
    ) -> StockChange:
        """Remove unsold units, deleting spare inventory rows first."""
        if quantity <= 0:
            raise ValidationError("Quantity must be greater than zero.")
        snapshot = self._snapshot(plan)
        removable = plan.available_quantity
        if removable <= 0:
            raise ValidationError("There is no unreserved stock left to remove.")
        quantity = min(quantity, removable)
        deleted_items = await self.items.delete_available(plan.id, quantity)
        plan.stock_quantity = max(plan.stock_quantity - quantity, plan.reserved_quantity)
        await self.session.flush()
        change = await self._build_change(plan, snapshot, delta=-quantity)
        await self._log(
            admin,
            AdminAction.ADMIN_REMOVED_STOCK,
            plan,
            f"-{quantity} ({deleted_items} item row(s) deleted)",
        )
        return change

    async def set_stock(
        self, plan: Plan, quantity: int, *, admin: Admin | None = None
    ) -> StockChange:
        """Set an absolute stock level, never below the reserved amount."""
        if quantity < 0:
            raise ValidationError("Stock cannot be negative.")
        if quantity < plan.reserved_quantity:
            raise ValidationError(
                f"{plan.reserved_quantity} unit(s) are reserved by open orders; "
                "cancel those orders first."
            )
        snapshot = self._snapshot(plan)
        delta = quantity - plan.stock_quantity
        if delta < 0:
            await self.items.delete_available(plan.id, abs(delta))
        plan.stock_quantity = quantity
        await self.session.flush()
        change = await self._build_change(plan, snapshot, delta=delta)
        await self._log(
            admin,
            AdminAction.ADMIN_ADDED_STOCK if delta >= 0 else AdminAction.ADMIN_REMOVED_STOCK,
            plan,
            f"stock set to {quantity}",
        )
        return change

    async def delete_item(
        self, item: InventoryItem, *, admin: Admin | None = None
    ) -> StockChange:
        """Delete a single unsold inventory row."""
        if item.status in {InventoryStatus.SOLD, InventoryStatus.RESERVED}:
            raise ValidationError("Sold or reserved items cannot be deleted.")
        plan = await self._require_plan(item.plan_id)
        snapshot = self._snapshot(plan)
        was_available = item.status is InventoryStatus.AVAILABLE
        await self.items.delete(item)
        if was_available:
            plan.stock_quantity = max(plan.stock_quantity - 1, plan.reserved_quantity)
        await self.session.flush()
        change = await self._build_change(plan, snapshot, delta=-1 if was_available else 0)
        await self._log(admin, AdminAction.ADMIN_REMOVED_STOCK, plan, "deleted 1 item")
        return change

    async def toggle_item(
        self, item: InventoryItem, *, admin: Admin | None = None
    ) -> StockChange:
        """Enable/disable an item without deleting it."""
        if item.status in {InventoryStatus.SOLD, InventoryStatus.RESERVED}:
            raise ValidationError("Sold or reserved items cannot be changed.")
        plan = await self._require_plan(item.plan_id)
        snapshot = self._snapshot(plan)
        if item.status is InventoryStatus.AVAILABLE:
            item.status = InventoryStatus.DISABLED
            plan.stock_quantity = max(plan.stock_quantity - 1, plan.reserved_quantity)
            delta = -1
        else:
            item.status = InventoryStatus.AVAILABLE
            plan.stock_quantity += 1
            delta = 1
        await self.session.flush()
        return await self._build_change(plan, snapshot, delta=delta)

    # ------------------------------------------------------ order integration
    async def reserve_for_order(self, plan: Plan, order: Order, quantity: int = 1) -> None:
        """Hold stock for a freshly created order.

        The plan row is re-read with ``FOR UPDATE`` so two customers checking
        out the last unit cannot both succeed.
        """
        locked = await self.plans.get_for_update(plan.id)
        if locked is None:
            raise NotFoundError("This plan no longer exists.")
        if not locked.is_active:
            raise OutOfStockError("This plan is not on sale right now.")
        if locked.available_quantity < quantity:
            raise OutOfStockError()

        locked.reserved_quantity += quantity
        if locked.delivery_type is not DeliveryType.MANUAL:
            items = await self.items.take_available(locked.id, quantity)
            for item in items:
                item.status = InventoryStatus.RESERVED
                item.order_id = order.id
                item.reserved_at = utcnow()
        await self.session.flush()
        # Keep the caller's instance consistent with the locked row.
        if locked is not plan:
            plan.reserved_quantity = locked.reserved_quantity
            plan.stock_quantity = locked.stock_quantity

    async def release_for_order(self, order: Order) -> None:
        """Return reserved stock after a cancellation or refund."""
        if order.stock_settled:
            return
        item = order.item
        quantity = item.quantity if item else 1
        for inventory_item in await self.items.list_for_order(order.id):
            if inventory_item.status is InventoryStatus.RESERVED:
                inventory_item.status = InventoryStatus.AVAILABLE
                inventory_item.order_id = None
                inventory_item.reserved_at = None
        if item and item.plan_id:
            plan = await self.plans.get(item.plan_id)
            if plan is not None:
                plan.reserved_quantity = max(plan.reserved_quantity - quantity, 0)
        order.stock_settled = True
        await self.session.flush()

    async def consume_for_order(self, order: Order) -> Sequence[InventoryItem]:
        """Convert reserved stock into a sale at delivery time."""
        item = order.item
        quantity = item.quantity if item else 1
        sold_items: list[InventoryItem] = []
        for inventory_item in await self.items.list_for_order(order.id):
            if inventory_item.status is InventoryStatus.RESERVED:
                inventory_item.status = InventoryStatus.SOLD
                inventory_item.sold_at = utcnow()
                sold_items.append(inventory_item)
        if not order.stock_settled and item and item.plan_id:
            plan = await self.plans.get(item.plan_id)
            if plan is not None:
                plan.reserved_quantity = max(plan.reserved_quantity - quantity, 0)
                plan.stock_quantity = max(plan.stock_quantity - quantity, 0)
                plan.sold_quantity += quantity
            order.stock_settled = True
        await self.session.flush()
        return sold_items

    # --------------------------------------------------------------- internals
    def _snapshot(self, plan: Plan) -> tuple[int, int]:
        return plan.stock_quantity, plan.available_quantity

    async def _build_change(
        self,
        plan: Plan,
        snapshot: tuple[int, int],
        *,
        delta: int,
        created_items: int = 0,
        duplicates: int = 0,
    ) -> StockChange:
        previous_stock, previous_available = snapshot
        change = StockChange(
            plan=plan,
            previous_stock=previous_stock,
            new_stock=plan.stock_quantity,
            previous_available=previous_available,
            new_available=plan.available_quantity,
            delta=delta,
            created_items=created_items,
            duplicates=duplicates,
        )
        if change.back_in_stock:
            change.waiting_users = await self.alerts.count_waiting(plan.id)
            logger.info(
                "stock.back_in_stock",
                plan_id=plan.id,
                new_stock=change.new_stock,
                waiting_users=change.waiting_users,
            )
        return change

    async def _require_plan(self, plan_id: int) -> Plan:
        plan = await self.plans.get(plan_id)
        if plan is None:
            raise NotFoundError("This plan no longer exists.")
        return plan

    async def _log(
        self,
        admin: Admin | None,
        action: AdminAction,
        plan: Plan,
        description: str,
    ) -> None:
        if admin is None:
            return
        await self.logs.log(
            admin.telegram_id,
            action,
            admin_username=admin.user.username if admin.user else None,
            target_type="plan",
            target_id=plan.id,
            description=f"{plan.name}: {description}",
        )
