"""Editable store settings and coupons."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Admin, AdminAction, Coupon, CouponType, Setting
from app.database.repositories import (
    AdminLogRepository,
    CouponRepository,
    SettingRepository,
)
from app.services.exceptions import NotFoundError, ValidationError
from app.utils.pagination import Page


@dataclass(frozen=True, slots=True)
class SettingKey:
    """Definition of a runtime-editable setting."""

    key: str
    label: str
    description: str
    default: str


#: Settings an administrator may edit from the panel.
SETTING_KEYS: tuple[SettingKey, ...] = (
    SettingKey(
        "store_welcome",
        "Welcome message",
        "Shown on the home screen under the store name.",
        "Buy digital subscriptions, licences and codes in a few taps.",
    ),
    SettingKey(
        "support_username",
        "Support contact",
        "Telegram username customers are told to contact (without @).",
        "",
    ),
    SettingKey(
        "support_text",
        "Support message",
        "Text shown on the 📞 Support screen.",
        "Our team replies within a few hours.",
    ),
    SettingKey(
        "help_text",
        "Help message",
        "Text shown on the ℹ️ Help screen.",
        "Pick a product, choose a plan, pay, then send your payment proof.",
    ),
    SettingKey(
        "payment_timeout_minutes",
        "Payment window (minutes)",
        "How long an unpaid order keeps its reserved stock.",
        "60",
    ),
    SettingKey(
        "auto_notify_stock",
        "Auto-notify waiting list",
        "When 'on', restocks notify the waiting list without a manual step.",
        "off",
    ),
    SettingKey(
        "store_open",
        "Store open",
        "Set to 'off' to temporarily stop new orders.",
        "on",
    ),
)

SETTING_MAP = {item.key: item for item in SETTING_KEYS}


class SettingsService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.settings = SettingRepository(session)
        self.coupons = CouponRepository(session)
        self.logs = AdminLogRepository(session)

    async def get(self, key: str) -> str:
        definition = SETTING_MAP.get(key)
        default = definition.default if definition else ""
        value = await self.settings.get_value(key, default)
        return value if value is not None else default

    async def get_bool(self, key: str) -> bool:
        return (await self.get(key)).strip().lower() in {"on", "1", "true", "yes"}

    async def get_int(self, key: str, default: int) -> int:
        raw = (await self.get(key)).strip()
        return int(raw) if raw.isdigit() else default

    async def set(
        self, key: str, value: str, *, admin: Admin | None = None
    ) -> Setting:
        if key not in SETTING_MAP:
            raise ValidationError("Unknown setting.")
        definition = SETTING_MAP[key]
        setting = await self.settings.set_value(key, value, definition.description)
        if admin is not None:
            await self.logs.log(
                admin.telegram_id,
                AdminAction.ADMIN_UPDATED_SETTINGS,
                admin_username=admin.user.username if admin.user else None,
                target_type="setting",
                target_id=setting.id,
                description=f"{key} = {value[:120]}",
            )
        return setting

    async def all_values(self) -> dict[str, str]:
        return {item.key: await self.get(item.key) for item in SETTING_KEYS}

    async def ensure_defaults(self) -> None:
        """Insert any missing setting rows so the admin UI can list them."""
        for item in SETTING_KEYS:
            if await self.settings.get_by(key=item.key) is None:
                await self.settings.create(
                    key=item.key, value=item.default, description=item.description
                )

    # ---------------------------------------------------------------- coupons
    async def paginate_coupons(self, page: int, per_page: int) -> Page[Coupon]:
        return await self.coupons.paginate_all(page, per_page)

    async def get_coupon(self, coupon_id: int) -> Coupon:
        coupon = await self.coupons.get(coupon_id)
        if coupon is None:
            raise NotFoundError("This coupon no longer exists.")
        return coupon

    async def create_coupon(
        self,
        *,
        code: str,
        type: CouponType,
        value: Decimal,
        admin: Admin,
        max_uses: int = 0,
        min_order_total: Decimal = Decimal("0.00"),
        description: str | None = None,
    ) -> Coupon:
        normalized = code.strip().upper()
        if not normalized or len(normalized) > 48:
            raise ValidationError("Coupon code must be 1-48 characters.")
        if await self.coupons.get_by_code(normalized):
            raise ValidationError("That coupon code already exists.")
        if type is CouponType.PERCENT and not (0 < value <= 100):
            raise ValidationError("Percentage discount must be between 1 and 100.")
        if value <= 0:
            raise ValidationError("Discount value must be greater than zero.")
        coupon = await self.coupons.create(
            code=normalized,
            type=type,
            value=value,
            max_uses=max_uses,
            min_order_total=min_order_total,
            description=description,
        )
        await self.logs.log(
            admin.telegram_id,
            AdminAction.ADMIN_CREATED_COUPON,
            admin_username=admin.user.username if admin.user else None,
            target_type="coupon",
            target_id=coupon.id,
            description=f"{normalized} ({type.value} {value})",
        )
        return coupon

    async def toggle_coupon(self, coupon: Coupon, admin: Admin) -> Coupon:
        coupon.is_active = not coupon.is_active
        await self.session.flush()
        await self.logs.log(
            admin.telegram_id,
            AdminAction.ADMIN_UPDATED_COUPON,
            admin_username=admin.user.username if admin.user else None,
            target_type="coupon",
            target_id=coupon.id,
            description=f"{coupon.code} active={coupon.is_active}",
        )
        return coupon

    async def delete_coupon(self, coupon: Coupon) -> None:
        await self.coupons.delete(coupon)

    # ------------------------------------------------------------- audit log
    async def paginate_logs(self, page: int, per_page: int) -> Page[object]:
        return await self.logs.paginate_recent(page, per_page)
