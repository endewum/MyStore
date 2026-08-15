"""Text formatting, validation and slug helpers."""

from __future__ import annotations

import html
import re
import unicodedata
from decimal import Decimal, InvalidOperation

DIVIDER = "━━━━━━━━━━━━━━━━━━━━"

_SLUG_STRIP = re.compile(r"[^a-z0-9]+")
_EMOJI_ONLY = re.compile(r"^\W{1,8}$", re.UNICODE)


def slugify(value: str, fallback: str = "item") -> str:
    """ASCII slug suitable for a unique database column."""
    normalized = unicodedata.normalize("NFKD", value)
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii").lower()
    slug = _SLUG_STRIP.sub("-", ascii_only).strip("-")
    return slug[:100] or fallback


def esc(value: object) -> str:
    """HTML-escape any value before embedding it in a Telegram message."""
    return html.escape(str(value if value is not None else ""), quote=False)


def truncate(value: str, limit: int = 40, suffix: str = "…") -> str:
    value = value.strip()
    if len(value) <= limit:
        return value
    return value[: max(limit - len(suffix), 1)].rstrip() + suffix


def money(amount: Decimal | float | int, currency: str = "USD") -> str:
    """Render an amount as ``$12.34`` (or ``12.34 EUR`` for other currencies)."""
    value = Decimal(str(amount)).quantize(Decimal("0.01"))
    if currency.upper() == "USD":
        return f"${value:,.2f}"
    return f"{value:,.2f} {currency.upper()}"


def parse_money(raw: str) -> Decimal:
    """Parse a user-entered price. Raises ``ValueError`` when invalid."""
    cleaned = raw.strip().replace("$", "").replace(",", "").replace(" ", "")
    try:
        value = Decimal(cleaned)
    except (InvalidOperation, ArithmeticError) as error:
        raise ValueError("Enter a price like 12.50") from error
    if value < 0:
        raise ValueError("Price cannot be negative.")
    if value > Decimal("999999.99"):
        raise ValueError("Price is too large.")
    return value.quantize(Decimal("0.01"))


def parse_positive_int(raw: str, *, maximum: int = 100_000) -> int:
    """Parse a positive integer quantity from user input."""
    cleaned = raw.strip().replace(",", "").replace(" ", "")
    if not cleaned.isdigit():
        raise ValueError("Enter a whole number, for example 25")
    value = int(cleaned)
    if value <= 0:
        raise ValueError("Enter a number greater than zero.")
    if value > maximum:
        raise ValueError(f"Maximum allowed is {maximum:,}.")
    return value


def clean_text(raw: str, *, max_length: int, field: str = "value") -> str:
    """Trim and length-check a free-text field coming from Telegram."""
    value = " ".join(raw.strip().split())
    if not value:
        raise ValueError(f"{field.capitalize()} cannot be empty.")
    if len(value) > max_length:
        raise ValueError(f"{field.capitalize()} must be at most {max_length} characters.")
    return value


def clean_multiline(raw: str, *, max_length: int, field: str = "value") -> str:
    """Trim a multi-line field while preserving intentional line breaks."""
    value = "\n".join(line.rstrip() for line in raw.strip().splitlines())
    if not value:
        raise ValueError(f"{field.capitalize()} cannot be empty.")
    if len(value) > max_length:
        raise ValueError(f"{field.capitalize()} must be at most {max_length} characters.")
    return value


def clean_emoji(raw: str) -> str:
    """Accept a short emoji/symbol used as a product or category icon."""
    value = raw.strip()
    if not value or len(value) > 8:
        raise ValueError("Send a single emoji, for example 🤖")
    return value


def split_lines(raw: str, *, limit: int = 500) -> list[str]:
    """Split a bulk paste into unique, non-empty lines."""
    seen: dict[str, None] = {}
    for line in raw.splitlines():
        value = line.strip()
        if value:
            seen.setdefault(value, None)
        if len(seen) >= limit:
            break
    return list(seen)


def progress_bar(percent: int, width: int = 10) -> str:
    filled = min(max(int(percent / 100 * width), 0), width)
    return "▰" * filled + "▱" * (width - filled)
