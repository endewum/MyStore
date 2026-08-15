"""Grant or revoke administrator access from the command line.

Useful for bootstrapping the first SUPER_ADMIN, or for recovery if you lock
yourself out of the panel.

Usage::

    python -m scripts.create_admin 123456789 --role SUPER_ADMIN
    python -m scripts.create_admin 123456789 --revoke
    python -m scripts.create_admin --list
"""

from __future__ import annotations

import argparse
import asyncio

from app.config import get_settings
from app.database.models import AdminRole
from app.database.session import Database
from app.services.registry import Services
from app.utils.logging import configure_logging, get_logger

logger = get_logger("create_admin")


async def run(args: argparse.Namespace) -> None:
    settings = get_settings()
    configure_logging(settings.logging)
    database = Database(settings.db)

    async with database.session() as session:
        services = Services(session, settings)
        if args.list:
            for admin in await services.users.list_admins():
                name = admin.user.display_name if admin.user else "—"
                print(f"{admin.telegram_id}\t{admin.role.value}\t{name}")
        elif args.revoke:
            await services.users.revoke_admin(args.telegram_id)
            print(f"Revoked admin access for {args.telegram_id}")
        else:
            admin = await services.users.grant_admin(
                args.telegram_id,
                AdminRole(args.role),
                note=args.note,
                username=args.username,
            )
            print(f"Granted {admin.role.value} to {admin.telegram_id}")
        await services.store_settings.ensure_defaults()

    await database.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage bot administrators.")
    parser.add_argument(
        "telegram_id", type=int, nargs="?", help="Telegram user ID of the admin"
    )
    parser.add_argument(
        "--role",
        default=AdminRole.SUPER_ADMIN.value,
        choices=[role.value for role in AdminRole],
    )
    parser.add_argument("--username", default=None, help="optional username label")
    parser.add_argument("--note", default="Created via CLI")
    parser.add_argument("--revoke", action="store_true", help="revoke admin access")
    parser.add_argument("--list", action="store_true", help="list administrators")
    args = parser.parse_args()

    if not args.list and args.telegram_id is None:
        parser.error("telegram_id is required unless --list is used")
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
