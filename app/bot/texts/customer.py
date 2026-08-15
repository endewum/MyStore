"""Customer-facing message templates.

Every screen is short, sectioned and uses the same divider so the storefront
feels consistent. All dynamic values are HTML-escaped.
"""

from __future__ import annotations

from collections.abc import Sequence

from app.database.models import (
    InventoryItem,
    Order,
    OrderStatus,
    Payment,
    PaymentMethod,
    Plan,
    Product,
    StockAlert,
)
from app.database.models.notification import NotificationRecipient
from app.utils.pagination import Page
from app.utils.text import DIVIDER, esc, money
from app.utils.time import format_dt, humanize_timedelta, utcnow


def header(title: str) -> str:
    return f"{DIVIDER}\n<b>{esc(title)}</b>\n{DIVIDER}"


def home(store_name: str, welcome: str, *, first_name: str | None = None) -> str:
    greeting = f"👋 Hi {esc(first_name)}!" if first_name else "👋 Welcome!"
    return (
        f"{header(f'🏪 {store_name}')}\n\n"
        f"{greeting}\n\n"
        f"{esc(welcome)}\n\n"
        "Choose an option below to get started."
    )


def store_page(page: Page[Product], *, category_name: str | None = None) -> str:
    if page.is_empty:
        return (
            f"{header('🏪 STORE')}\n\n"
            "No products are available right now.\n"
            "Please check back soon."
        )
    scope = f"🗂 {esc(category_name)}" if category_name else "All products"
    return (
        f"{header('🏪 STORE')}\n\n"
        f"{scope} · <b>{page.total}</b> product(s)\n"
        f"📄 Page {esc(page.label)}\n\n"
        "Tap a product to see its plans."
    )


def categories(total: int) -> str:
    return (
        f"{header('🗂 CATEGORIES')}\n\n"
        f"Browse <b>{total}</b> categories, or open the full catalog."
    )


def product_plans(product: Product, page: Page[Plan]) -> str:
    """Plan list for a product — the "select a plan" screen."""
    lines = [header(f"{product.emoji} {product.name.upper()}")]
    if product.description:
        lines.append(f"\n{esc(product.description)}")
    if page.is_empty:
        lines.append("\nNo plans are available for this product yet.")
        return "\n".join(lines)

    lines.append("\n<b>Select a plan:</b>\n")
    for plan in page.items:
        badges = "🔥 " if plan.is_featured else ""
        lines.append(f"{plan.status_icon} {badges}<b>{esc(plan.name)}</b>")
        if plan.duration:
            lines.append(f"⏳ {esc(plan.duration)}")
        lines.append(f"💵 {money(plan.price, plan.currency)}")
        if plan.is_sold_out:
            lines.append("❌ Sold Out")
        else:
            lines.append(f"📦 {plan.available_quantity} available")
        lines.append("")
    lines.append(DIVIDER)
    if page.total_pages > 1:
        lines.append(f"📄 Page {esc(page.label)} · {page.total} plan(s)")
    return "\n".join(lines)


def plan_confirmation(plan: Plan) -> str:
    """Order confirmation screen shown before an order is created."""
    lines = [
        header("🛒 ORDER CONFIRMATION"),
        "",
        "<b>Product</b>",
        f"{plan.product.emoji} {esc(plan.product.name)}",
        "",
        "<b>Plan</b>",
        esc(plan.name),
    ]
    if plan.duration:
        lines += ["", "<b>Duration</b>", esc(plan.duration)]
    lines += [
        "",
        "<b>Price</b>",
        money(plan.price, plan.currency),
        "",
        "<b>Stock</b>",
        f"{plan.available_quantity} available",
        "",
        "<b>Delivery</b>",
        plan.delivery_type.label,
    ]
    if plan.description:
        lines += ["", esc(plan.description)]
    lines += [
        "",
        DIVIDER,
        "",
        "ℹ️ Payment is reviewed manually by our team after you submit your "
        "transaction details.",
    ]
    return "\n".join(lines)


def plan_sold_out(plan: Plan, *, subscribed: bool) -> str:
    lines = [
        header("❌ SOLD OUT"),
        "",
        f"{plan.product.emoji} <b>{esc(plan.product.name)}</b>",
        esc(plan.name),
        "",
        f"💵 {money(plan.price, plan.currency)}",
        "",
        DIVIDER,
        "",
    ]
    if subscribed:
        lines.append(
            "🔔 You are on the waiting list. We will message you the moment this "
            "plan is restocked."
        )
    else:
        lines.append(
            "Tap <b>🔔 Notify Me</b> and we will message you as soon as this plan "
            "is back in stock."
        )
    return "\n".join(lines)


def payment_methods(order: Order, *, has_methods: bool) -> str:
    item = order.item
    lines = [
        header("💳 PAYMENT"),
        "",
        f"<b>Order #{esc(order.order_number)}</b>",
        "",
        "<b>Product</b>",
        esc(item.product_name if item else "—"),
        "",
        "<b>Plan</b>",
        esc(item.plan_name if item else "—"),
        "",
        "<b>Amount</b>",
        f"{money(order.total, order.currency)}",
    ]
    if order.discount:
        lines.append(f"🎟 Discount applied: −{money(order.discount, order.currency)}")
    lines += ["", DIVIDER, ""]
    if has_methods:
        lines.append("<b>Choose a payment method:</b>")
    else:
        lines.append(
            "⚠️ No payment method is configured right now. "
            "Please contact support to complete this order."
        )
    if order.expires_at:
        remaining = order.expires_at - utcnow()
        if remaining.total_seconds() > 0:
            lines.append(
                f"\n⏳ Reserved for {humanize_timedelta(remaining)}."
            )
    return "\n".join(lines)


def payment_instructions(order: Order, method: PaymentMethod) -> str:
    """Show the admin-configured credentials for the chosen channel."""
    lines = [
        header(f"{method.emoji} {method.name.upper()} PAYMENT"),
        "",
        f"<b>Order #{esc(order.order_number)}</b>",
        "",
        "<b>Amount to send</b>",
        f"{money(order.total, order.currency)}",
        "",
    ]
    label = "Wallet address" if method.network else "Account / ID"
    lines += [f"<b>{label}</b>", f"<code>{esc(method.account_identifier)}</code>"]
    if method.network:
        lines += ["", "<b>Network</b>", esc(method.network)]
    if method.instructions:
        lines += ["", esc(method.instructions)]
    lines += [
        "",
        DIVIDER,
        "",
        f"Please send <b>exactly {money(order.total, order.currency)}</b>.",
        "",
        "When the transfer is done, tap <b>✅ I Have Paid</b> and send your "
        "transaction details.",
        "",
        "ℹ️ Payments are verified manually by our team — nothing is charged or "
        "confirmed automatically.",
    ]
    if method.requires_screenshot:
        lines.append("\n📸 A payment screenshot is required for this method.")
    return "\n".join(lines)


def payment_evidence_prompt(order: Order, method: PaymentMethod | None) -> str:
    lines = [
        header("🧾 SUBMIT PAYMENT DETAILS"),
        "",
        f"<b>Order #{esc(order.order_number)}</b>",
        "",
        "Please send your transaction information. You may send:",
        "",
        "• Transaction ID / hash",
        "• Transfer reference or note",
        "• A screenshot of the payment",
        "",
        "You can send text, a photo, or a photo with a caption.",
    ]
    if method and method.requires_screenshot:
        lines.append("\n📸 A screenshot is required for this payment method.")
    return "\n".join(lines)


def payment_submitted(order: Order, payment: Payment) -> str:
    return "\n".join(
        [
            header("✅ PAYMENT SUBMITTED"),
            "",
            f"<b>Order #{esc(order.order_number)}</b>",
            "",
            "Your payment details were received and are now <b>waiting for "
            "manual review</b> by our team.",
            "",
            "<b>Method</b>",
            esc(payment.method_name or "—"),
            "",
            "<b>Amount</b>",
            money(payment.amount, payment.currency),
            "",
            DIVIDER,
            "",
            "⏳ You will get a message as soon as the payment is confirmed.",
        ]
    )


def orders_list(page: Page[Order]) -> str:
    if page.is_empty:
        return (
            f"{header('📦 MY ORDERS')}\n\n"
            "You have not placed any orders yet.\n"
            "Open the 🏪 Store to get started."
        )
    lines = [header("📦 MY ORDERS"), ""]
    for order in page.items:
        item = order.item
        lines.append(f"<b>#{esc(order.order_number)}</b>")
        lines.append(
            f"{esc(item.product_name if item else '—')} — "
            f"{esc(item.plan_name if item else '—')}"
        )
        lines.append(f"{money(order.total, order.currency)} · {order.status.label}")
        lines.append("")
    lines.append(DIVIDER)
    lines.append(f"📄 Page {esc(page.label)} · {page.total} order(s)")
    return "\n".join(lines)


def order_detail(
    order: Order,
    *,
    payment: Payment | None = None,
    inventory_items: Sequence[InventoryItem] | None = None,
) -> str:
    item = order.item
    lines = [
        header(f"🧾 ORDER #{order.order_number}"),
        "",
        "<b>Status</b>",
        order.status.label,
        "",
        "<b>Product</b>",
        esc(item.product_name if item else "—"),
        "",
        "<b>Plan</b>",
        esc(item.plan_name if item else "—"),
    ]
    if item and item.duration:
        lines += ["", "<b>Duration</b>", esc(item.duration)]
    lines += ["", "<b>Total</b>", money(order.total, order.currency)]
    if order.discount:
        lines.append(f"🎟 Saved {money(order.discount, order.currency)}")
    lines += ["", "<b>Placed</b>", format_dt(order.created_at)]

    if payment is not None:
        lines += ["", DIVIDER, "", "<b>Payment</b>", payment.status.label]
        if payment.method_name:
            lines.append(f"Method: {esc(payment.method_name)}")
        if payment.reference:
            lines.append(f"Reference: <code>{esc(payment.reference)}</code>")
        if payment.rejection_reason:
            lines.append(f"Reason: {esc(payment.rejection_reason)}")

    if order.status is OrderStatus.DELIVERED and order.delivery_content:
        lines += [
            "",
            DIVIDER,
            "",
            "<b>🎁 Your delivery</b>",
            f"<pre>{esc(order.delivery_content)}</pre>",
        ]
    elif order.status is OrderStatus.PENDING_PAYMENT:
        lines += ["", "⏳ Complete the payment to continue."]
    elif order.status is OrderStatus.PAYMENT_SUBMITTED:
        lines += ["", "🔎 Our team is reviewing your payment."]
    elif order.status is OrderStatus.PAYMENT_REJECTED:
        lines += ["", "🚫 Your payment was rejected. You can submit it again."]
    elif order.status in {OrderStatus.PAID, OrderStatus.PROCESSING, OrderStatus.READY}:
        lines += ["", "📦 Payment confirmed — your order is being prepared."]
    return "\n".join(lines)


def order_created(order: Order) -> str:
    item = order.item
    return "\n".join(
        [
            header("🧾 ORDER CREATED"),
            "",
            f"<b>Order #{esc(order.order_number)}</b>",
            "",
            f"{esc(item.product_name if item else '—')} — "
            f"{esc(item.plan_name if item else '—')}",
            "",
            "<b>Amount</b>",
            money(order.total, order.currency),
            "",
            DIVIDER,
            "",
            "Next step: choose how you want to pay.",
        ]
    )


def order_delivered(order: Order) -> str:
    item = order.item
    lines = [
        header("✅ ORDER COMPLETED"),
        "",
        f"<b>Order #{esc(order.order_number)}</b>",
        "",
        "<b>Product</b>",
        esc(item.product_name if item else "—"),
        "",
        "<b>Plan</b>",
        esc(item.plan_name if item else "—"),
        "",
    ]
    if order.delivery_content:
        lines += [
            "<b>🎁 Your delivery</b>",
            f"<pre>{esc(order.delivery_content)}</pre>",
            "",
        ]
    lines += [
        DIVIDER,
        "",
        "Your order has been fulfilled.",
        "Thank you for purchasing from our store ❤️",
    ]
    return "\n".join(lines)


def account(user_name: str, username: str | None, telegram_id: int, stats: dict[str, int]) -> str:
    return "\n".join(
        [
            header("👤 MY ACCOUNT"),
            "",
            "<b>Name</b>",
            esc(user_name),
            "",
            "<b>Username</b>",
            f"@{esc(username)}" if username else "—",
            "",
            "<b>Telegram ID</b>",
            f"<code>{telegram_id}</code>",
            "",
            DIVIDER,
            "",
            f"📦 Orders: <b>{stats.get('orders', 0)}</b>",
        ]
    )


def notifications(page: Page[NotificationRecipient], *, unread: int) -> str:
    if page.is_empty:
        return (
            f"{header('🔔 NOTIFICATIONS')}\n\n"
            "You have no notifications yet.\n\n"
            "Tap 🔔 Notify Me on a sold-out plan and we will alert you when it "
            "is restocked."
        )
    lines = [header("🔔 NOTIFICATIONS"), ""]
    if unread:
        lines.append(f"<b>{unread}</b> unread\n")
    for recipient in page.items:
        notification = recipient.notification
        if notification is None:
            continue
        mark = "🆕 " if not recipient.is_read else ""
        lines.append(f"{mark}{notification.type.icon} <b>{esc(notification.title)}</b>")
        lines.append(esc(notification.body))
        lines.append(f"<i>{format_dt(notification.created_at)}</i>")
        lines.append("")
    lines.append(DIVIDER)
    lines.append(f"📄 Page {esc(page.label)} · {page.total} total")
    return "\n".join(lines)


def stock_alerts(page: Page[StockAlert]) -> str:
    if page.is_empty:
        return (
            f"{header('🔖 MY WAITING LIST')}\n\n"
            "You are not waiting for any plan.\n\n"
            "Open a sold-out plan and tap 🔔 Notify Me to join a waiting list."
        )
    lines = [header("🔖 MY WAITING LIST"), ""]
    for alert in page.items:
        plan = alert.plan
        if plan is None:
            continue
        state = "🟢 Available now" if not plan.is_sold_out else "🔴 Sold out"
        lines.append(f"<b>{esc(plan.name)}</b>")
        lines.append(f"{money(plan.price, plan.currency)} · {state}")
        lines.append("")
    lines.append(DIVIDER)
    lines.append(f"📄 Page {esc(page.label)} · {page.total} plan(s)")
    return "\n".join(lines)


def search_prompt() -> str:
    return "\n".join(
        [
            header("🔎 SEARCH"),
            "",
            "Send what you are looking for.",
            "",
            "You can search by product, plan or category — for example:",
            "<code>ChatGPT</code>, <code>Canva Pro</code>, <code>AI</code>",
        ]
    )


def search_results(query: str, page: Page[Product]) -> str:
    if page.is_empty:
        return "\n".join(
            [
                header("🔎 SEARCH"),
                "",
                f"No products matched <b>{esc(query)}</b>.",
                "",
                "Try a shorter term, or browse the store instead.",
            ]
        )
    return "\n".join(
        [
            header("🔎 SEARCH RESULTS"),
            "",
            f"<b>{page.total}</b> result(s) for <b>{esc(query)}</b>",
            f"📄 Page {esc(page.label)}",
            "",
            "Tap a product to see its plans.",
        ]
    )


def support(support_username: str, support_text: str) -> str:
    lines = [header("📞 SUPPORT"), "", esc(support_text), ""]
    if support_username:
        lines.append(f"💬 Contact: @{esc(support_username)}")
    lines += [
        "",
        DIVIDER,
        "",
        "When contacting us, please include your order number so we can help "
        "faster.",
    ]
    return "\n".join(lines)


def help_text(body: str) -> str:
    return "\n".join(
        [
            header("ℹ️ HELP"),
            "",
            esc(body),
            "",
            DIVIDER,
            "",
            "<b>How ordering works</b>",
            "1️⃣ Pick a product in the 🏪 Store",
            "2️⃣ Choose a plan and confirm your order",
            "3️⃣ Pay with one of the available methods",
            "4️⃣ Send your transaction details",
            "5️⃣ Our team reviews the payment manually",
            "6️⃣ You receive your delivery in 📦 My Orders",
            "",
            "🔔 Sold out? Tap <b>Notify Me</b> and we will alert you on restock.",
        ]
    )
