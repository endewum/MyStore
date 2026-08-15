"""Admin panel message templates."""

from __future__ import annotations

from datetime import timedelta
from typing import Sequence

from app.database.models import (
    Admin,
    AdminLog,
    Broadcast,
    Category,
    Coupon,
    CouponType,
    InventoryItem,
    InventoryStatus,
    Order,
    OrderStatusHistory,
    Payment,
    PaymentMethod,
    Plan,
    Product,
    User,
)
from app.services.dashboard_service import DashboardStats
from app.services.inventory_service import StockChange
from app.utils.pagination import Page
from app.utils.text import DIVIDER, esc, money, progress_bar
from app.utils.time import format_dt, format_time, humanize_timedelta


def header(title: str) -> str:
    return f"{DIVIDER}\n<b>{esc(title)}</b>\n{DIVIDER}"


def panel(admin: Admin, counts: dict[str, int]) -> str:
    lines = [
        header("⚙️ ADMIN PANEL"),
        "",
        f"Signed in as <b>{esc(admin.role.value)}</b>",
    ]
    pending = counts.get("pending_payments", 0)
    fulfil = counts.get("awaiting_fulfilment", 0)
    if pending or fulfil:
        lines += ["", "<b>Needs your attention</b>"]
        if pending:
            lines.append(f"💳 {pending} payment(s) waiting for review")
        if fulfil:
            lines.append(f"📦 {fulfil} order(s) waiting for fulfilment")
    else:
        lines += ["", "✅ Nothing is waiting for review."]
    return "\n".join(lines)


def dashboard(stats: DashboardStats) -> str:
    return "\n".join(
        [
            header("📊 DASHBOARD"),
            "",
            f"👥 Users: <b>{stats.users:,}</b> ({stats.active_users:,} active)",
            f"🧾 Orders: <b>{stats.orders:,}</b>",
            f"⏳ Pending payments: <b>{stats.pending_payments:,}</b>",
            f"✅ Completed: <b>{stats.completed_orders:,}</b>",
            f"💰 Revenue: <b>{money(stats.revenue)}</b>",
            "",
            f"🛍 Products: <b>{stats.products:,}</b>",
            f"📋 Plans: <b>{stats.plans:,}</b>",
            f"📦 Available plans: <b>{stats.available_plans:,}</b>",
            f"❌ Sold-out plans: <b>{stats.sold_out_plans:,}</b>",
            f"🔢 Units in stock: <b>{stats.available_stock:,}</b>",
        ]
    )


def products_list(page: Page[Product]) -> str:
    if page.is_empty:
        return f"{header('🛍 PRODUCTS')}\n\nNo products yet. Tap ➕ Add product."
    return "\n".join(
        [
            header("🛍 PRODUCTS"),
            "",
            f"<b>{page.total}</b> product(s) · page {esc(page.label)}",
            "",
            "🟢 active · ⚫ disabled · 🔥 featured",
        ]
    )


def product_detail(product: Product, *, plan_count: int, stock: int) -> str:
    lines = [
        header(f"{product.emoji} {product.name.upper()}"),
        "",
        f"<b>Status</b>\n{'🟢 Active' if product.is_active else '⚫ Disabled'}",
        "",
        f"<b>Featured</b>\n{'🔥 Yes' if product.is_featured else 'No'}",
        "",
        f"<b>Category</b>\n{esc(product.category.title) if product.category else '—'}",
        "",
        f"<b>Plans</b>\n{plan_count}",
        "",
        f"<b>Units in stock</b>\n{stock}",
        "",
        f"<b>Sort order</b>\n{product.sort_order}",
    ]
    if product.description:
        lines += ["", "<b>Description</b>", esc(product.description)]
    lines += ["", f"<i>Created {format_dt(product.created_at)}</i>"]
    return "\n".join(lines)


def plans_list(product: Product, page: Page[Plan]) -> str:
    if page.is_empty:
        return (
            f"{header(f'📋 {product.name.upper()} PLANS')}\n\n"
            "No plans yet. Tap ➕ Add plan."
        )
    return "\n".join(
        [
            header(f"📋 {product.name.upper()} PLANS"),
            "",
            f"<b>{page.total}</b> plan(s) · page {esc(page.label)}",
            "",
            "Format: status · name · price · available",
        ]
    )


def plan_detail(plan: Plan, *, waiting: int, breakdown: dict[InventoryStatus, int]) -> str:
    lines = [
        header(f"📋 {plan.name.upper()}"),
        "",
        f"<b>Product</b>\n{esc(plan.product.name)}",
        "",
        f"<b>Price</b>\n{money(plan.price, plan.currency)}",
        "",
        f"<b>Duration</b>\n{esc(plan.duration) if plan.duration else '—'}",
        "",
        f"<b>Status</b>\n{'🟢 ACTIVE' if plan.is_active else '⚫ DISABLED'}"
        + (" · 🔥 Featured" if plan.is_featured else ""),
        "",
        f"<b>Delivery</b>\n{plan.delivery_type.label}",
        "",
        "<b>Stock</b>",
        f"📦 Available: {plan.available_quantity}",
        f"🟡 Reserved: {plan.reserved_quantity}",
        f"🔵 Sold: {plan.sold_quantity}",
        f"🔢 Total: {plan.stock_quantity}",
    ]
    items_total = sum(breakdown.values())
    if items_total:
        lines += [
            "",
            "<b>Inventory items</b>",
            f"🟢 {breakdown.get(InventoryStatus.AVAILABLE, 0)} available · "
            f"🟡 {breakdown.get(InventoryStatus.RESERVED, 0)} reserved · "
            f"🔵 {breakdown.get(InventoryStatus.SOLD, 0)} sold · "
            f"⚫ {breakdown.get(InventoryStatus.DISABLED, 0)} disabled",
        ]
    if waiting:
        lines += ["", f"🔔 <b>{waiting}</b> user(s) waiting for restock"]
    if plan.description:
        lines += ["", "<b>Description</b>", esc(plan.description)]
    return "\n".join(lines)


def stock_screen(plan: Plan, breakdown: dict[InventoryStatus, int], waiting: int) -> str:
    lines = [
        header("📦 STOCK MANAGEMENT"),
        "",
        f"<b>{esc(plan.product.name)}</b>",
        esc(plan.name),
        "",
        f"📦 Available: <b>{plan.available_quantity}</b>",
        f"🟡 Reserved: <b>{plan.reserved_quantity}</b>",
        f"🔵 Sold: <b>{plan.sold_quantity}</b>",
        f"🔢 Total stock: <b>{plan.stock_quantity}</b>",
        "",
        f"<b>Delivery type</b>\n{plan.delivery_type.label}",
    ]
    items_total = sum(breakdown.values())
    if items_total:
        lines += [
            "",
            f"<b>Inventory rows</b>\n{items_total} item(s) stored",
        ]
    if waiting:
        lines += ["", f"🔔 <b>{waiting}</b> user(s) on the waiting list"]
    return "\n".join(lines)


def stock_change_result(change: StockChange, waiting: int, all_users: int) -> str:
    """Confirmation shown after a stock mutation, before any notification."""
    plan = change.plan
    lines = [
        header("✅ STOCK UPDATED"),
        "",
        f"<b>Product</b>\n{esc(plan.product.name)}",
        "",
        f"<b>Plan</b>\n{esc(plan.name)}",
        "",
        f"<b>Previous stock</b>\n{change.previous_stock}",
        "",
        f"<b>New stock</b>\n{change.new_stock}",
    ]
    if change.created_items:
        lines += ["", f"<b>Items imported</b>\n{change.created_items}"]
    if change.duplicates:
        lines += ["", f"⚠️ Skipped {change.duplicates} duplicate value(s)"]
    if change.back_in_stock:
        lines += [
            "",
            DIVIDER,
            "",
            "🔥 <b>This plan is back in stock.</b>",
            "",
            f"🔔 Waiting list: <b>{waiting}</b> user(s)",
            f"📢 All users: <b>{all_users}</b> user(s)",
            "",
            "Nothing has been sent yet — choose who to notify.",
        ]
    elif change.became_sold_out:
        lines += ["", "🔴 This plan is now sold out."]
    return "\n".join(lines)


def inventory_items(plan: Plan, page: Page[InventoryItem]) -> str:
    if page.is_empty:
        return (
            f"{header('📋 INVENTORY ITEMS')}\n\n"
            f"{esc(plan.name)} has no stored items.\n\n"
            "Use 📥 Import codes to add deliverables."
        )
    return "\n".join(
        [
            header("📋 INVENTORY ITEMS"),
            "",
            f"<b>{esc(plan.name)}</b>",
            f"{page.total} item(s) · page {esc(page.label)}",
            "",
            "Values are masked here and only revealed on delivery.",
        ]
    )


def inventory_item_detail(item: InventoryItem) -> str:
    lines = [
        header("📦 INVENTORY ITEM"),
        "",
        f"<b>Status</b>\n{item.status.label}",
        "",
        f"<b>Value</b>\n<code>{esc(item.value)}</code>",
    ]
    if item.note:
        lines += ["", f"<b>Note</b>\n{esc(item.note)}"]
    if item.order_id:
        lines += ["", f"<b>Order</b>\n#{item.order_id}"]
    lines += [
        "",
        f"<i>Added {format_dt(item.created_at)}</i>",
    ]
    if item.sold_at:
        lines.append(f"<i>Sold {format_dt(item.sold_at)}</i>")
    return "\n".join(lines)


def low_stock(page: Page[Plan]) -> str:
    if page.is_empty:
        return f"{header('📦 SOLD-OUT PLANS')}\n\n✅ Every active plan has stock."
    return "\n".join(
        [
            header("📦 SOLD-OUT PLANS"),
            "",
            f"<b>{page.total}</b> active plan(s) with no available stock",
            f"📄 Page {esc(page.label)}",
            "",
            "Tap a plan to restock it.",
        ]
    )


def orders_list(page: Page[Order], filter_label: str) -> str:
    if page.is_empty:
        return f"{header('🧾 ORDERS')}\n\n{esc(filter_label)}\n\nNo orders here."
    return "\n".join(
        [
            header("🧾 ORDERS"),
            "",
            f"<b>{esc(filter_label)}</b>",
            f"{page.total} order(s) · page {esc(page.label)}",
        ]
    )


def order_detail(order: Order, user: User | None, payment: Payment | None) -> str:
    item = order.item
    lines = [
        header(f"🧾 ORDER #{order.order_number}"),
        "",
        f"<b>Status</b>\n{order.status.label}",
        "",
        f"<b>Customer</b>\n{esc(user.display_name) if user else '—'}",
        f"<code>{user.telegram_id if user else order.telegram_id}</code>",
        "",
        f"<b>Product</b>\n{esc(item.product_name if item else '—')}",
        "",
        f"<b>Plan</b>\n{esc(item.plan_name if item else '—')}",
        "",
        f"<b>Amount</b>\n{money(order.total, order.currency)}",
    ]
    if order.coupon_code:
        lines.append(f"🎟 {esc(order.coupon_code)} (−{money(order.discount)})")
    if payment is not None:
        lines += [
            "",
            DIVIDER,
            "",
            f"<b>Payment</b>\n{payment.status.label}",
            f"Method: {esc(payment.method_name or '—')}",
        ]
        if payment.reference:
            lines.append(f"Reference: <code>{esc(payment.reference)}</code>")
        if payment.submitted_at:
            lines.append(f"Submitted: {format_dt(payment.submitted_at)}")
        if payment.rejection_reason:
            lines.append(f"Rejected: {esc(payment.rejection_reason)}")
    if order.delivery_content:
        lines += ["", "<b>Delivered content</b>", f"<pre>{esc(order.delivery_content)}</pre>"]
    lines += ["", f"<i>Created {format_dt(order.created_at)}</i>"]
    return "\n".join(lines)


def order_history(order: Order, history: Sequence[OrderStatusHistory]) -> str:
    lines = [header(f"🕘 ORDER #{order.order_number} HISTORY"), ""]
    if not history:
        lines.append("No transitions recorded.")
        return "\n".join(lines)
    for entry in history:
        arrow = (
            f"{entry.from_status.value} → {entry.to_status.value}"
            if entry.from_status
            else entry.to_status.value
        )
        lines.append(f"• <b>{esc(arrow)}</b>")
        detail = [format_dt(entry.created_at)]
        if entry.changed_by_telegram_id:
            detail.append(f"by <code>{entry.changed_by_telegram_id}</code>")
        lines.append("  " + " · ".join(detail))
        if entry.reason:
            lines.append(f"  <i>{esc(entry.reason)}</i>")
    return "\n".join(lines)


def payment_queue(page: Page[Payment]) -> str:
    if page.is_empty:
        return f"{header('💳 PAYMENT REVIEW')}\n\n✅ No payments are waiting for review."
    return "\n".join(
        [
            header("💳 PAYMENT REVIEW"),
            "",
            f"<b>{page.total}</b> payment(s) awaiting manual review",
            f"📄 Page {esc(page.label)}",
            "",
            "Every payment must be verified by hand.",
        ]
    )


def payment_review(payment: Payment, order: Order, user: User | None) -> str:
    item = order.item
    lines = [
        header("💰 PAYMENT REVIEW"),
        "",
        f"<b>Order</b>\n#{esc(order.order_number)}",
        "",
        f"<b>Customer</b>\n{esc(user.display_name) if user else '—'}",
        f"<code>{user.telegram_id if user else order.telegram_id}</code>",
        "",
        f"<b>Product</b>\n{esc(item.product_name if item else '—')}",
        "",
        f"<b>Plan</b>\n{esc(item.plan_name if item else '—')}",
        "",
        f"<b>Amount</b>\n{money(payment.amount, payment.currency)}",
        "",
        f"<b>Payment method</b>\n{esc(payment.method_name or '—')}",
        "",
        f"<b>Transaction reference</b>\n"
        f"{f'<code>{esc(payment.reference)}</code>' if payment.reference else '—'}",
    ]
    if payment.customer_note:
        lines += ["", f"<b>Customer note</b>\n{esc(payment.customer_note)}"]
    lines += [
        "",
        f"<b>Submitted</b>\n{format_time(payment.submitted_at)} · "
        f"{format_dt(payment.submitted_at, '%Y-%m-%d')}",
    ]
    if payment.proof_file_id:
        lines += ["", "📸 A screenshot was attached."]
    else:
        lines += ["", "⚠️ No screenshot was attached."]
    lines += [
        "",
        DIVIDER,
        "",
        "Verify the transfer in your own account before confirming.",
    ]
    return "\n".join(lines)


def payment_methods(methods: Sequence[PaymentMethod]) -> str:
    lines = [header("💳 PAYMENT METHODS"), ""]
    if not methods:
        lines.append("No payment methods are configured.")
        return "\n".join(lines)
    for method in methods:
        state = "🟢 ENABLED" if method.is_enabled else "⚫ DISABLED"
        if method.is_enabled and not method.is_configured:
            state = "⚠️ NOT CONFIGURED"
        lines.append(f"{method.emoji} <b>{esc(method.name)}</b>")
        lines.append(f"Status: {state}")
        if method.account_identifier:
            lines.append(f"ID: <code>{esc(method.account_identifier)}</code>")
        if method.network:
            lines.append(f"Network: {esc(method.network)}")
        lines.append("")
    lines.append(DIVIDER)
    lines.append("Credentials are stored in the database, never in the code.")
    return "\n".join(lines)


def payment_method_detail(method: PaymentMethod) -> str:
    return "\n".join(
        [
            header(f"{method.emoji} {method.name.upper()}"),
            "",
            f"<b>Code</b>\n<code>{esc(method.code)}</code>",
            "",
            f"<b>Status</b>\n{'🟢 Enabled' if method.is_enabled else '⚫ Disabled'}",
            "",
            f"<b>Account / wallet</b>\n"
            f"{f'<code>{esc(method.account_identifier)}</code>' if method.account_identifier else '⚠️ not set'}",
            "",
            f"<b>Network</b>\n{esc(method.network) if method.network else '—'}",
            "",
            f"<b>Minimum amount</b>\n{money(method.min_amount)}",
            "",
            f"<b>Screenshot</b>\n"
            f"{'required' if method.requires_screenshot else 'optional'}",
            "",
            f"<b>Instructions</b>\n{esc(method.instructions) if method.instructions else '—'}",
        ]
    )


def fulfillment_prompt(order: Order, suggestion: str | None) -> str:
    item = order.item
    lines = [
        header("📦 FULFILL ORDER"),
        "",
        f"<b>Order</b>\n#{esc(order.order_number)}",
        "",
        f"<b>Product</b>\n{esc(item.product_name if item else '—')}",
        "",
        f"<b>Plan</b>\n{esc(item.plan_name if item else '—')}",
        "",
        DIVIDER,
        "",
        "Send the delivery details for this customer.",
        "",
        "For example: account credentials, licence key, redeem code or setup "
        "instructions.",
    ]
    if suggestion:
        lines += [
            "",
            "<b>Reserved inventory for this order</b>",
            f"<pre>{esc(suggestion)}</pre>",
            "",
            "Send <code>/use</code> to deliver exactly this content.",
        ]
    return "\n".join(lines)


def users_list(page: Page[User], *, query: str = "") -> str:
    if page.is_empty:
        return f"{header('👥 USERS')}\n\nNo users matched." if query else (
            f"{header('👥 USERS')}\n\nNo users yet."
        )
    scope = f"Search: <b>{esc(query)}</b>\n" if query else ""
    return "\n".join(
        [
            header("👥 USERS"),
            "",
            f"{scope}<b>{page.total}</b> user(s) · page {esc(page.label)}",
            "",
            "🟢 active · ⚫ inactive · 🚫 blocked",
        ]
    )


def user_detail(user: User, stats: dict[str, int], admin: Admin | None) -> str:
    lines = [
        header("👤 USER"),
        "",
        f"<b>Name</b>\n{esc(user.full_name)}",
        "",
        f"<b>Username</b>\n{f'@{esc(user.username)}' if user.username else '—'}",
        "",
        f"<b>Telegram ID</b>\n<code>{user.telegram_id}</code>",
        "",
        f"<b>Status</b>\n"
        + (
            "🚫 Blocked"
            if user.is_blocked
            else ("🟢 Active" if user.can_receive_messages else "⚫ Unreachable")
        ),
    ]
    if user.block_reason:
        lines.append(f"Reason: {esc(user.block_reason)}")
    if admin is not None:
        lines += ["", f"<b>Role</b>\n🛡 {esc(admin.role.value)}"]
    lines += [
        "",
        f"<b>Orders</b>\n{stats.get('orders', 0)}",
        "",
        f"<b>Joined</b>\n{format_dt(user.joined_at)}",
        "",
        f"<b>Last activity</b>\n{format_dt(user.last_activity_at)}",
        "",
        f"<b>Notifications</b>\n{'on' if user.notifications_enabled else 'off'}",
    ]
    return "\n".join(lines)


def admins_list(admins: Sequence[Admin]) -> str:
    lines = [header("🛡 ADMINISTRATORS"), ""]
    if not admins:
        lines.append("No administrators configured.")
        return "\n".join(lines)
    for admin in admins:
        name = admin.user.display_name if admin.user else str(admin.telegram_id)
        lines.append(f"🛡 <b>{esc(name)}</b> — {esc(admin.role.value)}")
        lines.append(f"<code>{admin.telegram_id}</code>")
        lines.append("")
    lines.append(DIVIDER)
    lines.append("Access is granted by Telegram ID and verified against the database.")
    return "\n".join(lines)


def broadcast_menu() -> str:
    return "\n".join(
        [
            header("📢 BROADCAST"),
            "",
            "Send an announcement to your users.",
            "",
            "Every broadcast is previewed with its recipient count before it is "
            "sent, and delivery is rate-limited to respect Telegram's limits.",
        ]
    )


def broadcast_compose() -> str:
    return "\n".join(
        [
            header("✍️ NEW BROADCAST"),
            "",
            "Send the announcement content now.",
            "",
            "• Plain text, or",
            "• A photo with a caption",
            "",
            "HTML formatting such as <b>bold</b> is supported.",
        ]
    )


def broadcast_preview(broadcast: Broadcast, estimate_seconds: int) -> str:
    return "\n".join(
        [
            header("👁 PREVIEW"),
            "",
            broadcast.body,
            "",
            DIVIDER,
            "",
            f"<b>Audience</b>\n{broadcast.audience.label}",
            "",
            f"<b>Recipients</b>\n{broadcast.total_recipients:,} user(s)",
            "",
            f"<b>Estimated delivery</b>\n"
            f"{humanize_timedelta(timedelta(seconds=estimate_seconds))}",
            "",
            "Nothing has been sent yet.",
        ]
    )


def broadcast_progress(broadcast: Broadcast) -> str:
    percent = broadcast.progress_percent
    return "\n".join(
        [
            header("📢 BROADCAST"),
            "",
            f"<b>Status</b>\n{broadcast.status.label}",
            "",
            f"<b>Recipients</b>\n{broadcast.total_recipients:,}",
            "",
            f"<b>Successful</b>\n{broadcast.sent_count:,}",
            "",
            f"<b>Failed</b>\n{broadcast.failed_count:,}",
            "",
            f"<b>Progress</b>\n{progress_bar(percent)} {percent}%",
        ]
    )


def broadcast_history(page: Page[Broadcast]) -> str:
    if page.is_empty:
        return f"{header('🕘 BROADCAST HISTORY')}\n\nNo broadcasts have been sent yet."
    return "\n".join(
        [
            header("🕘 BROADCAST HISTORY"),
            "",
            f"<b>{page.total}</b> campaign(s) · page {esc(page.label)}",
        ]
    )


def settings_menu(values: dict[str, str]) -> str:
    lines = [header("⚙️ SETTINGS"), ""]
    for key, value in values.items():
        shown = value if len(value) <= 40 else f"{value[:37]}…"
        lines.append(f"• <b>{esc(key)}</b>: {esc(shown) if shown else '—'}")
    lines += ["", DIVIDER, "", "Tap a setting to change it."]
    return "\n".join(lines)


def categories_list(categories: Sequence[Category]) -> str:
    lines = [header("🗂 CATEGORIES"), ""]
    if not categories:
        lines.append("No categories yet. Tap ➕ Add category.")
        return "\n".join(lines)
    for category in categories:
        state = "🟢" if category.is_active else "⚫"
        lines.append(f"{state} {esc(category.title)} — {len(category.products)} product(s)")
    return "\n".join(lines)


def category_detail(category: Category) -> str:
    return "\n".join(
        [
            header(f"🗂 {category.name.upper()}"),
            "",
            f"<b>Emoji</b>\n{esc(category.emoji)}",
            "",
            f"<b>Status</b>\n{'🟢 Active' if category.is_active else '⚫ Disabled'}",
            "",
            f"<b>Slug</b>\n<code>{esc(category.slug)}</code>",
            "",
            f"<b>Sort order</b>\n{category.sort_order}",
        ]
    )


def coupons_list(page: Page[Coupon]) -> str:
    if page.is_empty:
        return f"{header('🎟 COUPONS')}\n\nNo coupons yet. Tap ➕ Add coupon."
    return "\n".join(
        [
            header("🎟 COUPONS"),
            "",
            f"<b>{page.total}</b> coupon(s) · page {esc(page.label)}",
        ]
    )


def coupon_detail(coupon: Coupon) -> str:
    value = (
        f"{coupon.value:g}%"
        if coupon.type is CouponType.PERCENT
        else money(coupon.value)
    )
    return "\n".join(
        [
            header(f"🎟 {coupon.code}"),
            "",
            f"<b>Discount</b>\n{value}",
            "",
            f"<b>Status</b>\n{'🟢 Usable' if coupon.is_usable else '⚫ Not usable'}",
            "",
            f"<b>Used</b>\n{coupon.used_count}"
            + (f" / {coupon.max_uses}" if coupon.max_uses else " (unlimited)"),
            "",
            f"<b>Minimum order</b>\n{money(coupon.min_order_total)}",
            "",
            f"<b>Expires</b>\n{format_dt(coupon.expires_at)}",
        ]
    )


def audit_log(page: Page[AdminLog]) -> str:
    if page.is_empty:
        return f"{header('📜 AUDIT LOG')}\n\nNo admin actions recorded yet."
    lines = [header("📜 AUDIT LOG"), ""]
    for entry in page.items:
        lines.append(f"• <b>{esc(entry.action.value)}</b>")
        who = entry.admin_username or entry.admin_telegram_id
        lines.append(f"  {esc(who)} · {format_dt(entry.created_at)}")
        if entry.description:
            lines.append(f"  <i>{esc(entry.description)}</i>")
    lines += ["", DIVIDER, f"📄 Page {esc(page.label)} · {page.total} entries"]
    return "\n".join(lines)
