# Telegram Digital Product Store Bot

A production-oriented Telegram storefront for legitimate digital products —
subscriptions, licences, redeem codes and service plans — built with
**Python 3.12 + aiogram 3 + SQLAlchemy 2 + MySQL 8**.

Payments are **manually verified by an administrator**. The bot never claims a
payment was detected automatically.

```
PRODUCT → PLANS → ORDER → MANUAL PAYMENT → ADMIN REVIEW → FULFILLMENT
ADMIN ADDS STOCK → BACK-IN-STOCK DETECTED → PREVIEW → NOTIFY WAITING LIST / ALL
```

---

## Table of contents

1. [Project overview](#1-project-overview)
2. [Features](#2-features)
3. [Architecture](#3-architecture)
4. [Requirements](#4-requirements)
5. [Installation](#5-installation)
6. [Environment variables](#6-environment-variables)
7. [MySQL setup](#7-mysql-setup)
8. [Alembic migrations](#8-alembic-migrations)
9. [Seed data](#9-seed-data)
10. [Running locally](#10-running-locally)
11. [Running with Docker](#11-running-with-docker)
12. [BotFather setup](#12-botfather-setup)
13. [Webhook setup](#13-webhook-setup)
14. [Admin setup](#14-admin-setup)
15. [Payment method configuration](#15-payment-method-configuration)
16. [Deployment](#16-deployment)
17. [Troubleshooting](#17-troubleshooting)
18. [Testing](#18-testing)

---

## 1. Project overview

The store has two catalog levels:

```
ChatGPT                                  Canva
├── GPT TEAM — $15.00 — 24 left          ├── Canva Pro 1 Month
├── GPT PLUS 30D — $3.08 — SOLD OUT      ├── Canva Pro 3 Months
├── GPT PLUS APPLE PAY 1M — $4.80        ├── Canva Pro 1 Year
└── API 500M CODEX 30D — SOLD OUT        └── Canva Teams
```

A customer picks a **product** from a 3-column grid, then a **plan**. Available
plans can be bought; sold-out plans offer **🔔 Notify Me**. Checkout reserves
stock, the customer pays through an admin-configured channel (Binance / Bybit /
USDT / anything else you add), submits a transaction reference or screenshot,
and an administrator approves or rejects it by hand before fulfilling the order.

Nothing about the catalog is hard-coded: products, plans, categories, payment
credentials and store texts all live in the database and are edited from the
in-bot admin panel.

## 2. Features

**Storefront**

- 3-column paginated product grid, featured products first (🔥)
- Plan screen with per-plan status (🟢 available / 🔴 sold out), price, duration and stock
- Category browsing and search across product names, plan names and categories
- Order confirmation → payment method → instructions → evidence submission
- Order history with pagination, notification inbox, personal waiting list
- Persistent bottom menu plus inline navigation with ◀️ Back / 🏠 Home everywhere

**Manual payments**

- Payment channels configured in the database (ID/UID/wallet, network, instructions, minimum amount, screenshot requirement)
- Customer submits a transaction ID, a screenshot, or both
- Administrators get a review card with 「✅ Confirm / ❌ Reject / 🔎 View order」
- Rejection asks for a reason and lets the customer resubmit

**Stock & notifications (first-class)**

- Counter stock for manual plans, individual inventory rows for CODE/ACCOUNT/INFORMATION plans
- Bulk code import with duplicate detection, per-item enable/disable/delete
- Reservation at checkout, consumption at delivery, automatic release on cancel/refund/expiry
- `0 → >0` transitions are detected and reported as **BACK IN STOCK**
- Admin chooses per restock: preview, notify the waiting list, notify all users, or notify nobody
- Optional `auto_notify_stock` setting to notify the waiting list without a manual step

**Admin panel (same bot, role-gated)**

- Dashboard: users, orders, pending payments, completed orders, revenue, plans, stock, sold-out plans
- Products, plans, inventory, orders, users, payments, broadcasts, coupons, categories, settings
- Broadcasts with audience selection, preview, recipient count, estimated delivery, live progress and failure tracking
- Roles `SUPER_ADMIN` / `ADMIN` / `STAFF`, authorized by Telegram ID + database role
- Audit log of every significant admin action

**Reliability & security**

- Strict order state machine; invalid transitions are rejected in the service layer
- Order ownership checks on every customer-facing order action
- Row-level locking (`SELECT … FOR UPDATE`) when reserving the last unit
- Per-user anti-flood middleware; broadcast rate limiting; blocked users detected and skipped
- All secrets in environment variables, all payment credentials in the database
- HTML escaping of every dynamic value; input validation on every FSM step
- Structured logging (`structlog`), graceful handling of `TelegramForbiddenError`, `TelegramBadRequest`, `TelegramRetryAfter` and database errors

## 3. Architecture

Handlers never touch the database directly:

```
Telegram update
  → middlewares (errors → throttling → db session → user/admin resolution)
  → handler        (app/bot/handlers)   presentation only
  → service        (app/services)       business rules, validation, state machine
  → repository     (app/database/repositories)  the only place SQL is built
  → MySQL
```

```
telegram_store/
├── app/
│   ├── bot/
│   │   ├── handlers/         start, store, products, plans, orders, payments,
│   │   │   └── admin/        account, notifications, fallback + admin/*
│   │   ├── keyboards/        inline/reply keyboards (incl. admin/)
│   │   ├── texts/            message templates (customer, admin, notifications)
│   │   ├── callbacks/        aiogram CallbackData factories
│   │   ├── states/           FSM state groups
│   │   ├── middlewares/      db session, user, throttling, errors
│   │   ├── filters/          IsAdmin / AdminOnly
│   │   └── bootstrap.py      bot, dispatcher, admin bootstrap
│   ├── database/
│   │   ├── models/           18 tables
│   │   ├── repositories/     data access
│   │   ├── migrations/       Alembic
│   │   └── session.py        async engine + session factory
│   ├── services/             product, plan, inventory, order, payment,
│   │   │                     notification, broadcast, user, dashboard, settings
│   │   └── delivery.py       rate-limited, error-tolerant message dispatcher
│   ├── utils/                pagination, text, time, logging
│   ├── config.py             pydantic-settings
│   └── main.py               polling / webhook entry point
├── scripts/                  seed.py, create_admin.py
├── tests/                    142 tests (SQLite, no external services)
├── Dockerfile / docker-compose.yml
├── alembic.ini / requirements.txt / .env.example
```

### Database schema

`users`, `admins`, `categories`, `products`, `plans`, `inventory`, `orders`,
`order_items`, `order_status_history`, `payments`, `payment_methods`,
`notifications`, `notification_recipients`, `stock_alerts`, `broadcasts`,
`coupons`, `settings`, `admin_logs` — all with foreign keys and indexes on
`telegram_id`, `product_id`, `plan_id`, `order_id`, statuses and `created_at`.

### Order state machine

| From | Allowed next |
| --- | --- |
| `PENDING_PAYMENT` | `PAYMENT_SUBMITTED`, `CANCELLED` |
| `PAYMENT_SUBMITTED` | `PAID`, `PAYMENT_REJECTED`, `CANCELLED` |
| `PAYMENT_REJECTED` | `PAYMENT_SUBMITTED`, `CANCELLED` |
| `PAID` | `PROCESSING`, `READY`, `DELIVERED`, `CANCELLED`, `REFUNDED` |
| `PROCESSING` | `READY`, `DELIVERED`, `CANCELLED`, `REFUNDED` |
| `READY` | `DELIVERED`, `CANCELLED`, `REFUNDED` |
| `DELIVERED` | `REFUNDED` |
| `CANCELLED`, `REFUNDED` | — (terminal) |

Stock is reserved on creation, consumed on delivery, and released on
cancellation, refund or payment-window expiry.

## 4. Requirements

- Python 3.12+
- MySQL 8.0+
- Redis (optional — only for multi-instance FSM storage)
- A bot token from [@BotFather](https://t.me/BotFather)
- Docker + Docker Compose (optional)

## 5. Installation

```bash
git clone <your-repository-url>
cd telegram_store

python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

pip install -r requirements.txt        # runtime
pip install -r requirements-dev.txt    # runtime + test tooling

cp .env.example .env
$EDITOR .env                           # set BOT_TOKEN, BOT_ADMIN_IDS, DB_URL
```

## 6. Environment variables

`.env` is never committed; `.env.example` documents every option.

| Variable | Required | Default | Purpose |
| --- | --- | --- | --- |
| `BOT_TOKEN` | ✅ | — | Token from @BotFather |
| `BOT_ADMIN_IDS` | ✅ | — | Comma separated Telegram IDs promoted to `SUPER_ADMIN` at startup |
| `BOT_ADMIN_USERNAME` |  | — | Display-only label for the main admin |
| `DB_URL` | ✅ | `mysql+aiomysql://store:store@localhost:3306/telegram_store` | Async SQLAlchemy URL |
| `DB_ECHO` / `DB_POOL_SIZE` / `DB_MAX_OVERFLOW` |  | `false` / `10` / `20` | Engine tuning |
| `REDIS_ENABLED` / `REDIS_URL` |  | `false` | Redis-backed FSM storage |
| `WEBHOOK_ENABLED` |  | `false` | Serve webhooks instead of long polling |
| `WEBHOOK_BASE_URL` / `WEBHOOK_PATH` / `WEBHOOK_SECRET` / `WEBHOOK_PORT` |  | — / `/telegram/webhook` / — / `8080` | Webhook configuration |
| `STORE_NAME` / `STORE_CURRENCY` |  | `Digital Store` / `USD` | Branding |
| `STORE_PRODUCTS_PER_PAGE` / `STORE_PRODUCT_GRID_COLUMNS` |  | `27` / `3` | Storefront grid |
| `STORE_PLANS_PER_PAGE` / `STORE_ORDERS_PER_PAGE` / `STORE_NOTIFICATIONS_PER_PAGE` / `STORE_ADMIN_LIST_PAGE_SIZE` |  | `8` / `5` / `5` / `8` | Pagination |
| `STORE_PAYMENT_TIMEOUT_MINUTES` |  | `60` | How long an unpaid order holds stock |
| `STORE_BROADCAST_MESSAGES_PER_SECOND` / `STORE_BROADCAST_BATCH_SIZE` |  | `20` / `25` | Broadcast pacing |
| `SECURITY_RATE_LIMIT_ENABLED` / `SECURITY_RATE_LIMIT_INTERVAL` / `SECURITY_RATE_LIMIT_BURST` |  | `true` / `0.45` / `5` | Anti-flood |
| `LOG_LEVEL` / `LOG_JSON_FORMAT` |  | `INFO` / `false` | Logging |

Payment credentials are **not** environment variables — they live in the
`payment_methods` table and are edited from the admin panel.

## 7. MySQL setup

```sql
CREATE DATABASE telegram_store
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

CREATE USER 'store'@'%' IDENTIFIED BY 'change-me';
GRANT ALL PRIVILEGES ON telegram_store.* TO 'store'@'%';
FLUSH PRIVILEGES;
```

Then point `DB_URL` at it:

```
DB_URL=mysql+aiomysql://store:change-me@localhost:3306/telegram_store
```

The driver must be async (`mysql+aiomysql://`); the config layer rejects
synchronous URLs at startup.

## 8. Alembic migrations

```bash
alembic upgrade head          # create/update the schema
alembic current               # show the applied revision
alembic check                 # verify models match the database
alembic downgrade -1          # roll back one revision

# after changing a model:
alembic revision --autogenerate -m "describe your change"
```

Alembic reads `DB_URL` from your settings, so migrations can never target a
different database than the bot.

## 9. Seed data

```bash
python -m scripts.seed            # add sample data (idempotent)
python -m scripts.seed --reset    # wipe catalog tables first
```

This inserts 8 categories, 28 sample products (ChatGPT, Canva, Spotify, Netflix,
Claude, Gemini, Cursor, ElevenLabs …), 65 plans with fictional prices/stock, and
three **disabled** payment methods (Binance, Bybit, USDT) with no credentials.
Enable them from the admin panel once you enter your own details.

## 10. Running locally

```bash
alembic upgrade head
python -m scripts.seed
python -m app.main
```

Then open your bot in Telegram and send `/start`.

## 11. Running with Docker

```bash
cp .env.example .env      # set BOT_TOKEN and BOT_ADMIN_IDS
docker compose up -d --build
docker compose logs -f bot
```

Compose starts MySQL, runs `alembic upgrade head` in a one-shot `migrate`
service, then starts the bot. `DB_URL` is injected automatically, so the value in
`.env` is only used for local runs.

```bash
docker compose exec bot python -m scripts.seed        # sample data
docker compose --profile redis up -d redis            # optional Redis
docker compose down                                  # stop (keeps volumes)
```

## 12. BotFather setup

1. Talk to [@BotFather](https://t.me/BotFather) → `/newbot` → copy the token into `BOT_TOKEN`.
2. `/setdescription`, `/setabouttext`, `/setuserpic` for presentation.
3. Command hints are registered automatically on startup (`/start`, `/store`, `/search`, `/orders`, `/notifications`, `/account`, `/support`, `/help`, `/cancel`).
4. Keep group privacy mode on — the bot is designed for private chats.

## 13. Webhook setup

Long polling is the default and needs no public URL. For webhooks:

```
WEBHOOK_ENABLED=true
WEBHOOK_BASE_URL=https://store.example.com
WEBHOOK_PATH=/telegram/webhook
WEBHOOK_SECRET=<random-long-string>
WEBHOOK_PORT=8080
```

The bot registers the webhook itself and validates Telegram's secret header.
Terminate TLS in front of it, for example with nginx:

```nginx
location /telegram/webhook {
    proxy_pass http://127.0.0.1:8080;
    proxy_set_header X-Telegram-Bot-Api-Secret-Token $http_x_telegram_bot_api_secret_token;
}
```

## 14. Admin setup

1. Find your numeric Telegram ID (send `/account` to the bot, or ask [@userinfobot](https://t.me/userinfobot)).
2. Put it in `BOT_ADMIN_IDS` — every listed ID becomes `SUPER_ADMIN` on startup.
3. Send `/admin` in the bot to open the panel.

From the CLI:

```bash
python -m scripts.create_admin 123456789 --role SUPER_ADMIN
python -m scripts.create_admin 987654321 --role STAFF
python -m scripts.create_admin 987654321 --revoke
python -m scripts.create_admin --list
```

Roles:

| Role | Can do |
| --- | --- |
| `STAFF` | View the panel, review payments, fulfil orders, manage stock |
| `ADMIN` | Everything above + delete products/plans, broadcasts, settings, coupons |
| `SUPER_ADMIN` | Everything above + manage administrators, delete categories/coupons |

Authorization always checks the Telegram user ID against an active row in
`admins`; usernames are never trusted.

## 15. Payment method configuration

`/admin` → **💳 Payment methods** → pick a channel:

- 🔑 Account / wallet — Binance ID, Bybit UID or crypto address
- 🌐 Network — e.g. `TRC20` for USDT
- 📝 Instructions — shown to the customer with the amount
- 💵 Minimum amount, 🖼 screenshot requirement, 🟢 enable/disable

A method is only offered to customers when it is enabled **and** has an
account/wallet value, so a half-configured channel can never appear at checkout.
Add more channels by inserting rows into `payment_methods` (see
`scripts/seed.py` for the shape).

## 16. Deployment

**systemd**

```ini
[Unit]
Description=Telegram Store Bot
After=network-online.target mysql.service

[Service]
Type=simple
User=botuser
WorkingDirectory=/opt/telegram_store
EnvironmentFile=/opt/telegram_store/.env
ExecStart=/opt/telegram_store/.venv/bin/python -m app.main
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Checklist:

- `ENVIRONMENT=production`, `LOG_JSON_FORMAT=true`
- `chmod 600 .env`; never commit it
- Run `alembic upgrade head` as part of every deploy
- Back up MySQL regularly (orders, deliveries and inventory live there)
- Run a single instance, or enable Redis (`REDIS_ENABLED=true`) before scaling out
- Watch the logs for `telegram.flood_limit` and lower `STORE_BROADCAST_MESSAGES_PER_SECOND` if it appears

## 17. Troubleshooting

| Symptom | Cause / fix |
| --- | --- |
| `DB_URL must use an async driver` | Use `mysql+aiomysql://`, not `mysql://` or `mysql+pymysql://` |
| `Access denied for user` | Wrong credentials in `DB_URL`, or the user lacks grants |
| `Can't connect to MySQL server` | MySQL not running, or wrong host/port (inside Compose the host is `mysql`) |
| `TelegramUnauthorizedError` | `BOT_TOKEN` is wrong or was revoked |
| `/admin` says access is restricted | Your ID is not in `BOT_ADMIN_IDS`; add it and restart, or use `scripts.create_admin` |
| No payment methods at checkout | Every method is disabled or missing its account value → configure one in the panel |
| Buttons answer "no longer valid" | The message predates a restart or the item was deleted; reopen the menu |
| Broadcast has many failures | Those users blocked the bot; they are marked inactive and skipped next time |
| `alembic check` reports changes | A model changed without a migration → `alembic revision --autogenerate` |
| Restock did not notify anyone | By design: choose the audience on the confirmation screen, or set `auto_notify_stock` to `on` |
| Stock looks stuck | Units are reserved by open orders; cancel them or wait for `STORE_PAYMENT_TIMEOUT_MINUTES` |

## 18. Testing

```bash
pip install -r requirements-dev.txt
pytest                       # 142 tests
pytest tests/test_orders.py -v
```

Tests use SQLite built from the same ORM metadata as the MySQL migrations, so no
database, Redis or Telegram token is required. They cover user registration,
product listing and pagination, plan listing and sold-out behaviour, order
creation and the full state machine, stock reservation and release, payment
submission/approval/rejection, manual fulfilment, stock changes and
notifications, broadcasts and delivery error handling, admin authorization,
order ownership and invalid callback data.

`tests/test_integration_flow.py` additionally drives the **real dispatcher** with
synthetic Telegram updates and a fake API session, so middlewares, filters, FSM
states and keyboards are exercised end to end:

- `/start` → store grid → product → plan → order → payment method → evidence submitted → admin review card
- admin confirms → `PAID` → manual fulfilment → customer receives the delivery
- admin rejects with a reason → customer can resubmit, stock stays reserved
- 🔔 Notify Me on a sold-out plan → admin restocks → preview → waiting list notified (and nothing is sent before the admin chooses)
- authorization, order-ownership, stale callback data and unknown input paths
