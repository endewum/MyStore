"""Generic pagination helpers used by repositories and keyboards."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Generic, TypeVar

T = TypeVar("T")


@dataclass(slots=True)
class Page(Generic[T]):
    """One page of results plus the metadata keyboards need."""

    items: list[T] = field(default_factory=list)
    page: int = 1
    per_page: int = 10
    total: int = 0

    @property
    def total_pages(self) -> int:
        if self.per_page <= 0:
            return 1
        return max(1, -(-self.total // self.per_page))

    @property
    def has_previous(self) -> bool:
        return self.page > 1

    @property
    def has_next(self) -> bool:
        return self.page < self.total_pages

    @property
    def is_empty(self) -> bool:
        return not self.items

    @property
    def label(self) -> str:
        return f"{self.page}/{self.total_pages}"

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.per_page


def normalize_page(page: int, total: int, per_page: int) -> int:
    """Clamp a (possibly stale) page number into the valid range."""
    if per_page <= 0:
        return 1
    total_pages = max(1, -(-total // per_page))
    return min(max(page, 1), total_pages)
