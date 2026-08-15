"""Seed database product shells and disabled payment-method placeholders.

The seed intentionally creates **no plans, inventory or stock**. Products must
show as out of stock until an administrator adds real offers through the bot.
This prevents sample values from ever being shown or sold to customers.

Usage::

    python -m scripts.seed            # insert what is missing
    python -m scripts.seed --reset    # wipe catalog tables first
"""

from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import delete

from app.config import get_settings
from app.database.models import (
    Category,
    DeliveryType,
    Product,
)
from app.database.repositories import (
    CategoryRepository,
    PaymentMethodRepository,
    ProductRepository,
)
from app.database.session import Database
from app.services.settings_service import SettingsService
from app.utils.logging import configure_logging, get_logger
from app.utils.text import slugify

logger = get_logger("seed")

CATEGORIES: tuple[tuple[str, str, int], ...] = (
    ("AI", "🤖", 10),
    ("Design", "🎨", 20),
    ("Entertainment", "🎬", 30),
    ("Software", "💻", 40),
    ("Education", "📚", 50),
    ("VPN", "🔐", 60),
    ("Music", "🎵", 70),
    ("Productivity", "📈", 80),
)

# (name, emoji, category, featured, description, [(plan, duration, price, stock, delivery)])
PRODUCTS: tuple[tuple, ...] = (
    (
        "ChatGPT",
        "🤖",
        "AI",
        True,
        "OpenAI ChatGPT plans and API credit bundles.",
        (
            ("GPT TEAM (Business FW)", "6 Months", "15.00", 24, DeliveryType.ACCOUNT),
            ("GPT PLUS 30D (NW)", "30 Days", "3.08", 0, DeliveryType.ACCOUNT),
            ("GPT PLUS APPLE PAY 1M", "1 Month", "4.80", 128, DeliveryType.ACCOUNT),
            ("API 100M TOKEN CODEX 1D", "1 Day", "3.81", 0, DeliveryType.CODE),
            ("API 500M TOKEN CODEX 30D", "30 Days", "16.50", 0, DeliveryType.CODE),
        ),
    ),
    (
        "Canva",
        "🎨",
        "Design",
        True,
        "Canva Pro and Teams subscriptions.",
        (
            ("Canva Pro 1 Month", "1 Month", "4.00", 60, DeliveryType.ACCOUNT),
            ("Canva Pro 3 Months", "3 Months", "9.50", 35, DeliveryType.ACCOUNT),
            ("Canva Pro 1 Year", "12 Months", "24.00", 18, DeliveryType.ACCOUNT),
            ("Canva Teams 1 Year", "12 Months", "32.00", 0, DeliveryType.ACCOUNT),
        ),
    ),
    (
        "Spotify",
        "🎵",
        "Music",
        False,
        "Spotify Premium individual and family plans.",
        (
            ("Premium 1 Month", "1 Month", "3.50", 0, DeliveryType.ACCOUNT),
            ("Premium 3 Months", "3 Months", "8.00", 22, DeliveryType.ACCOUNT),
            ("Premium Family 1 Year", "12 Months", "28.00", 6, DeliveryType.ACCOUNT),
        ),
    ),
    (
        "Gamma AI",
        "📊",
        "AI",
        False,
        "AI presentation builder subscriptions.",
        (
            ("Gamma Plus 1 Month", "1 Month", "5.20", 14, DeliveryType.ACCOUNT),
            ("Gamma Pro 1 Year", "12 Months", "39.00", 4, DeliveryType.ACCOUNT),
        ),
    ),
    (
        "Netflix",
        "🎬",
        "Entertainment",
        True,
        "Netflix shared and private profiles.",
        (
            ("Netflix 1 Month (Profile)", "1 Month", "3.90", 45, DeliveryType.ACCOUNT),
            ("Netflix 3 Months (Profile)", "3 Months", "10.50", 12, DeliveryType.ACCOUNT),
            ("Netflix Private 1 Month", "1 Month", "9.90", 0, DeliveryType.ACCOUNT),
        ),
    ),
    (
        "Duolingo",
        "🦉",
        "Education",
        False,
        "Duolingo Super and Max plans.",
        (
            ("Super 1 Year", "12 Months", "14.00", 20, DeliveryType.ACCOUNT),
            ("Max 1 Year", "12 Months", "29.00", 3, DeliveryType.ACCOUNT),
        ),
    ),
    (
        "YouTube",
        "▶️",
        "Entertainment",
        False,
        "YouTube Premium subscriptions.",
        (
            ("Premium 1 Month", "1 Month", "2.90", 70, DeliveryType.ACCOUNT),
            ("Premium 12 Months", "12 Months", "21.00", 9, DeliveryType.ACCOUNT),
        ),
    ),
    (
        "Microsoft 365",
        "🪟",
        "Software",
        False,
        "Microsoft 365 Personal and Family licences.",
        (
            ("365 Personal 1 Year", "12 Months", "12.00", 25, DeliveryType.CODE),
            ("365 Family 1 Year", "12 Months", "19.50", 11, DeliveryType.CODE),
        ),
    ),
    (
        "Turnitin",
        "📝",
        "Education",
        False,
        "Turnitin similarity check access.",
        (
            ("Student Access 1 Month", "1 Month", "6.50", 0, DeliveryType.ACCOUNT),
            ("Instructor Access 1 Month", "1 Month", "11.00", 5, DeliveryType.ACCOUNT),
        ),
    ),
    (
        "Adobe",
        "🅰️",
        "Design",
        False,
        "Adobe Creative Cloud plans.",
        (
            ("Creative Cloud 1 Month", "1 Month", "9.90", 0, DeliveryType.ACCOUNT),
            ("Creative Cloud 1 Year", "12 Months", "69.00", 2, DeliveryType.ACCOUNT),
            ("Photoshop 1 Year", "12 Months", "34.00", 7, DeliveryType.ACCOUNT),
        ),
    ),
    (
        "Claude",
        "🧠",
        "AI",
        True,
        "Anthropic Claude Pro plans.",
        (
            ("Claude Pro 1 Month", "1 Month", "8.50", 33, DeliveryType.ACCOUNT),
            ("Claude Pro 1 Year", "12 Months", "84.00", 5, DeliveryType.ACCOUNT),
            ("Claude Team Seat", "1 Month", "18.00", 0, DeliveryType.ACCOUNT),
        ),
    ),
    (
        "Grok",
        "⚡",
        "AI",
        True,
        "xAI Grok subscriptions.",
        (
            ("Grok Premium 1 Month", "1 Month", "6.80", 40, DeliveryType.ACCOUNT),
            ("Grok Premium+ 1 Month", "1 Month", "14.00", 0, DeliveryType.ACCOUNT),
        ),
    ),
    (
        "Elsa Speak",
        "🗣",
        "Education",
        False,
        "Elsa Speak pronunciation coaching.",
        (
            ("Elsa Pro 1 Year", "12 Months", "16.00", 15, DeliveryType.CODE),
            ("Elsa Pro Lifetime", "Lifetime", "48.00", 2, DeliveryType.CODE),
        ),
    ),
    (
        "Figma",
        "🖌",
        "Design",
        False,
        "Figma professional seats.",
        (
            ("Professional 1 Month", "1 Month", "7.50", 18, DeliveryType.ACCOUNT),
            ("Professional 1 Year", "12 Months", "62.00", 0, DeliveryType.ACCOUNT),
        ),
    ),
    (
        "Veo",
        "🎥",
        "AI",
        True,
        "Google Veo video generation credits.",
        (
            ("Veo Credits 100", "One-off", "12.00", 26, DeliveryType.CODE),
            ("Veo Credits 500", "One-off", "48.00", 8, DeliveryType.CODE),
        ),
    ),
    (
        "CapCut",
        "✂️",
        "Design",
        True,
        "CapCut Pro editing subscriptions.",
        (
            ("CapCut Pro 1 Month", "1 Month", "4.20", 55, DeliveryType.ACCOUNT),
            ("CapCut Pro 1 Year", "12 Months", "29.00", 13, DeliveryType.ACCOUNT),
        ),
    ),
    (
        "Kling",
        "🎞",
        "AI",
        False,
        "Kling AI video generation plans.",
        (
            ("Kling Standard 1 Month", "1 Month", "9.00", 10, DeliveryType.ACCOUNT),
            ("Kling Pro 1 Month", "1 Month", "19.00", 0, DeliveryType.ACCOUNT),
        ),
    ),
    (
        "Cursor",
        "⌨️",
        "Software",
        True,
        "Cursor AI code editor subscriptions.",
        (
            ("Cursor Pro 1 Month", "1 Month", "11.00", 30, DeliveryType.ACCOUNT),
            ("Cursor Pro 1 Year", "12 Months", "110.00", 4, DeliveryType.ACCOUNT),
        ),
    ),
    (
        "Zoom",
        "📹",
        "Productivity",
        False,
        "Zoom Pro meeting licences.",
        (
            ("Zoom Pro 1 Month", "1 Month", "6.00", 21, DeliveryType.ACCOUNT),
            ("Zoom Pro 1 Year", "12 Months", "58.00", 0, DeliveryType.ACCOUNT),
        ),
    ),
    (
        "Scribd",
        "📖",
        "Education",
        False,
        "Scribd unlimited reading plans.",
        (
            ("Scribd 1 Month", "1 Month", "3.20", 44, DeliveryType.ACCOUNT),
            ("Scribd 1 Year", "12 Months", "24.00", 6, DeliveryType.ACCOUNT),
        ),
    ),
    (
        "HeyGen",
        "🧑‍💻",
        "AI",
        True,
        "HeyGen AI avatar video plans.",
        (
            ("HeyGen Creator 1 Month", "1 Month", "17.00", 9, DeliveryType.ACCOUNT),
            ("HeyGen Team 1 Month", "1 Month", "45.00", 0, DeliveryType.ACCOUNT),
        ),
    ),
    (
        "ElevenLabs",
        "🔊",
        "AI",
        True,
        "ElevenLabs voice synthesis plans.",
        (
            ("Starter 1 Month", "1 Month", "4.50", 38, DeliveryType.ACCOUNT),
            ("Creator 1 Month", "1 Month", "13.00", 12, DeliveryType.ACCOUNT),
            ("Pro 1 Month", "1 Month", "48.00", 0, DeliveryType.ACCOUNT),
        ),
    ),
    (
        "Notion",
        "📓",
        "Productivity",
        False,
        "Notion Plus and AI add-ons.",
        (
            ("Notion Plus 1 Year", "12 Months", "38.00", 16, DeliveryType.ACCOUNT),
            ("Notion AI 1 Year", "12 Months", "52.00", 0, DeliveryType.ACCOUNT),
        ),
    ),
    (
        "Gemini",
        "♊",
        "AI",
        True,
        "Google Gemini Advanced plans.",
        (
            ("Gemini Advanced 1 Month", "1 Month", "7.90", 41, DeliveryType.ACCOUNT),
            ("Gemini Advanced 1 Year", "12 Months", "79.00", 3, DeliveryType.ACCOUNT),
        ),
    ),
    (
        "Perplexity",
        "🔍",
        "AI",
        True,
        "Perplexity Pro research plans.",
        (
            ("Perplexity Pro 1 Month", "1 Month", "8.00", 27, DeliveryType.ACCOUNT),
            ("Perplexity Pro 1 Year", "12 Months", "76.00", 0, DeliveryType.ACCOUNT),
        ),
    ),
    (
        "NordVPN",
        "🔐",
        "VPN",
        False,
        "NordVPN multi-device subscriptions.",
        (
            ("NordVPN 1 Year", "12 Months", "22.00", 19, DeliveryType.CODE),
            ("NordVPN 2 Years", "24 Months", "36.00", 5, DeliveryType.CODE),
        ),
    ),
    (
        "Quizlet",
        "🧾",
        "Education",
        False,
        "Quizlet Plus study plans.",
        (
            ("Quizlet Plus 1 Year", "12 Months", "17.00", 23, DeliveryType.ACCOUNT),
        ),
    ),
    (
        "Coursera",
        "🎓",
        "Education",
        False,
        "Coursera Plus learning subscriptions.",
        (
            ("Coursera Plus 1 Month", "1 Month", "18.00", 0, DeliveryType.ACCOUNT),
            ("Coursera Plus 1 Year", "12 Months", "129.00", 2, DeliveryType.ACCOUNT),
        ),
    ),
)

#: Placeholders only — real credentials are set from the admin panel.
PAYMENT_METHODS: tuple[dict, ...] = (
    {
        "code": "binance",
        "name": "Binance",
        "emoji": "🟡",
        "network": None,
        "instructions": (
            "Send the exact amount as USDT to the Binance ID above, then submit "
            "your transaction ID."
        ),
        "sort_order": 10,
    },
    {
        "code": "bybit",
        "name": "Bybit",
        "emoji": "🔵",
        "network": None,
        "instructions": (
            "Send the exact amount as USDT to the Bybit UID above, then submit "
            "your transaction ID."
        ),
        "sort_order": 20,
    },
    {
        "code": "usdt",
        "name": "USDT",
        "emoji": "₮",
        "network": "TRC20",
        "instructions": (
            "Send the exact amount on the TRC20 network, then submit the "
            "transaction hash."
        ),
        "sort_order": 30,
    },
)


async def seed(reset: bool = False) -> None:
    settings = get_settings()
    configure_logging(settings.logging)
    database = Database(settings.db)

    async with database.session() as session:
        categories = CategoryRepository(session)
        products = ProductRepository(session)
        methods = PaymentMethodRepository(session)

        if reset:
            # Plans, inventory and stock alerts cascade from products.
            await session.execute(delete(Product))
            await session.execute(delete(Category))
            logger.info("seed.reset")

        category_ids: dict[str, int] = {}
        for name, emoji, order in CATEGORIES:
            slug = slugify(name, "category")
            existing = await categories.get_by_slug(slug)
            if existing is None:
                existing = await categories.create(
                    name=name, slug=slug, emoji=emoji, sort_order=order
                )
            category_ids[name] = existing.id

        created_products = 0
        for order, entry in enumerate(PRODUCTS, start=1):
            name, emoji, category, featured, description, _plan_rows = entry
            slug = slugify(name, "product")
            product = await products.get_by(slug=slug)
            if product is None:
                product = await products.create(
                    name=name,
                    slug=slug,
                    emoji=emoji,
                    description=description,
                    category_id=category_ids.get(category),
                    is_featured=featured,
                    sort_order=order * 10,
                )
                created_products += 1

        for payload in PAYMENT_METHODS:
            if await methods.get_by_code(payload["code"]) is None:
                await methods.create(
                    **payload,
                    #: Disabled until an administrator fills in real credentials.
                    is_enabled=False,
                    account_identifier=None,
                )

        await SettingsService(session).ensure_defaults()

    await database.dispose()
    logger.info(
        "seed.done",
        products=created_products,
        plans=0,
        inventory_items=0,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed sample store data.")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="delete existing products and categories first",
    )
    args = parser.parse_args()
    asyncio.run(seed(reset=args.reset))


if __name__ == "__main__":
    main()
