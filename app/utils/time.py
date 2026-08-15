"""Time helpers.

All timestamps are stored as naive UTC datetimes so behaviour is identical on
MySQL (``DATETIME``) and SQLite.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta


def utcnow() -> datetime:
    """Current UTC time as a naive ``datetime``."""
    return datetime.now(UTC).replace(tzinfo=None)


def in_minutes(minutes: int) -> datetime:
    """Naive UTC timestamp ``minutes`` in the future."""
    return utcnow() + timedelta(minutes=minutes)


def format_dt(value: datetime | None, fmt: str = "%Y-%m-%d %H:%M") -> str:
    """Render a datetime for Telegram messages, tolerating ``None``."""
    return value.strftime(fmt) if value else "—"


def format_time(value: datetime | None) -> str:
    return value.strftime("%I:%M %p").lstrip("0") if value else "—"


def humanize_timedelta(delta: timedelta) -> str:
    """Render a duration as ``2h 15m`` / ``45s``."""
    total = int(max(delta.total_seconds(), 0))
    hours, remainder = divmod(total, 3600)
    minutes, seconds = divmod(remainder, 60)
    parts: list[str] = []
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if not parts:
        parts.append(f"{seconds}s")
    return " ".join(parts)
