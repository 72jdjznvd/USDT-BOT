
import os
import asyncpg
import logging
from datetime import datetime, timezone
from decimal import Decimal

logger = logging.getLogger(__name__)

_pool = None


async def connect_db():
    global _pool

    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError("DATABASE_URL Render Environment-də yoxdur.")

    if _pool is not None:
        return _pool

    _pool = await asyncpg.create_pool(
        dsn=database_url,
        min_size=1,
        max_size=10,
        command_timeout=30,
        ssl="require" if "localhost" not in database_url else None,
    )

    async with _pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                telegram_id BIGINT PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                language TEXT NOT NULL DEFAULT 'az',
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS orders (
                id BIGSERIAL PRIMARY KEY,
                order_ref TEXT UNIQUE NOT NULL,
                telegram_id BIGINT NOT NULL REFERENCES users(telegram_id),
                kind TEXT NOT NULL CHECK (kind IN ('buy', 'sell')),
                amount NUMERIC(24, 6) NOT NULL CHECK (amount > 0),
                rate NUMERIC(18, 6) NOT NULL CHECK (rate > 0),
                total NUMERIC(24, 2) NOT NULL CHECK (total > 0),
                currency TEXT NOT NULL DEFAULT 'AZN',
                status TEXT NOT NULL DEFAULT 'pending',
                payment_method TEXT,
                receipt_file_id TEXT,
                txid TEXT UNIQUE,
                bank_name TEXT,
                customer_note TEXT,
                rejection_reason TEXT,
                admin_id BIGINT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                expires_at TIMESTAMPTZ,
                completed_at TIMESTAMPTZ
            );

            CREATE INDEX IF NOT EXISTS idx_orders_user
                ON orders(telegram_id, created_at DESC);

            CREATE INDEX IF NOT EXISTS idx_orders_status
                ON orders(status, created_at DESC);

            CREATE TABLE IF NOT EXISTS audit_log (
                id BIGSERIAL PRIMARY KEY,
                admin_id BIGINT,
                order_ref TEXT,
                action TEXT NOT NULL,
                details TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
        """)

    logger.info("PostgreSQL bağlantısı hazır.")
    return _pool


async def close_db():
    global _pool

    if _pool is not None:
        await _pool.close()
        _pool = None


def get_pool():
    if _pool is None:
        raise RuntimeError("Əvvəl connect_db() çağırılmalıdır.")
    return _pool


async def save_user(
    telegram_id: int,
    username: str | None,
    first_name: str | None,
    last_name: str | None,
    language: str = "az",
):
    pool = get_pool()

    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO users (
                telegram_id, username, first_name,
                last_name, language
            )
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (telegram_id) DO UPDATE SET
                username = EXCLUDED.username,
                first_name = EXCLUDED.first_name,
                last_name = EXCLUDED.last_name,
                language = EXCLUDED.language,
                updated_at = NOW()
        """, telegram_id, username, first_name, last_name, language)


async def get_user(telegram_id: int):
    pool = get_pool()

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM users WHERE telegram_id = $1",
            telegram_id,
        )
        return dict(row) if row else None


async def create_order(
    order_ref: str,
    telegram_id: int,
    kind: str,
    amount: Decimal,
    rate: Decimal,
    total: Decimal,
    payment_method: str | None = None,
    expires_at: datetime | None = None,
):
    if kind not in ("buy", "sell"):
        raise ValueError("Əməliyyat növü buy və ya sell olmalıdır.")

    if amount <= 0 or rate <= 0 or total <= 0:
        raise ValueError("Məbləğ və məzənnə müsbət olmalıdır.")

    pool = get_pool()

    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow("""
                INSERT INTO orders (
                    order_ref, telegram_id, kind,
                    amount, rate, total,
                    payment_method, expires_at
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                RETURNING *
            """, order_ref, telegram_id, kind, amount, rate,
                total, payment_method, expires_at)

            return dict(row)


async def get_order(order_ref: str):
    pool = get_pool()

    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT o.*, u.username, u.first_name, u.last_name
            FROM orders o
            JOIN users u ON u.telegram_id = o.telegram_id
            WHERE o.order_ref = $1
        """, order_ref)

        return dict(row) if row else None


async def list_orders(status: str | None = None, limit: int = 20):
    pool = get_pool()
    limit = max(1, min(int(limit), 100))

    async with pool.acquire() as conn:
        if status:
            rows = await conn.fetch("""
                SELECT o.*, u.username, u.first_name, u.last_name
                FROM orders o
                JOIN users u ON u.telegram_id = o.telegram_id
                WHERE o.status = $1
                ORDER BY o.created_at DESC
                LIMIT $2
            """, status, limit)
        else:
            rows = await conn.fetch("""
                SELECT o.*, u.username, u.first_name, u.last_name
                FROM orders o
                JOIN users u ON u.telegram_id = o.telegram_id
                ORDER BY o.created_at DESC
                LIMIT $1
            """, limit)

        return [dict(row) for row in rows]


async def list_user_orders(telegram_id: int, limit: int = 20):
    pool = get_pool()
    limit = max(1, min(int(limit), 100))

    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT * FROM orders
            WHERE telegram_id = $1
            ORDER BY created_at DESC
            LIMIT $2
        """, telegram_id, limit)

        return [dict(row) for row in rows]


async def set_receipt(order_ref: str, file_id: str):
    pool = get_pool()

    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow("""
                UPDATE orders
                SET receipt_file_id = $2,
                    status = 'review',
                    updated_at = NOW()
                WHERE order_ref = $1
                  AND kind = 'buy'
                  AND status = 'pending'
                  AND (expires_at IS NULL OR expires_at > NOW())
                RETURNING *
            """, order_ref, file_id)

            return dict(row) if row else None


async def set_txid(order_ref: str, txid: str):
    txid = txid.strip()
    if not txid or any(c.isspace() for c in txid):
        raise ValueError("TXID formatı düzgün deyil.")

    pool = get_pool()

    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow("""
                UPDATE orders
                SET txid = $2,
                    status = 'review',
                    updated_at = NOW()
                WHERE order_ref = $1
                  AND kind = 'sell'
                  AND status = 'pending'
                  AND (expires_at IS NULL OR expires_at > NOW())
                RETURNING *
            """, order_ref, txid)

            return dict(row) if row else None


async def set_bank(order_ref: str, bank_name: str):
    pool = get_pool()

    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            UPDATE orders
            SET bank_name = $2, updated_at = NOW()
            WHERE order_ref = $1
              AND kind = 'sell'
              AND status = 'review'
            RETURNING *
        """, order_ref, bank_name)

        return dict(row) if row else None


async def admin_decide(
    order_ref: str,
    admin_id: int,
    decision: str,
    reason: str | None = None,
):
    allowed = {
        "approve": "approved",
        "reject": "rejected",
        "complete": "completed",
    }

    if decision not in allowed:
        raise ValueError("Naməlum admin qərarı.")

    new_status = allowed[decision]
    pool = get_pool()

    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow("""
                SELECT * FROM orders
                WHERE order_ref = $1
                FOR UPDATE
            """, order_ref)

            if not row:
                return None

            current = row["status"]

            if decision in ("approve", "reject") and current != "review":
                return None

            if decision == "complete" and current != "approved":
                return None

            updated = await conn.fetchrow("""
                UPDATE orders
                SET status = $2,
                    admin_id = $3,
                    rejection_reason = $4,
                    updated_at = NOW(),
                    completed_at = CASE
                        WHEN $2 = 'completed' THEN NOW()
                        ELSE completed_at
                    END
                WHERE order_ref = $1
                RETURNING *
            """, order_ref, new_status, admin_id, reason)

            await conn.execute("""
                INSERT INTO audit_log (
                    admin_id, order_ref, action, details
                )
                VALUES ($1, $2, $3, $4)
            """, admin_id, order_ref, decision, reason)

            return dict(updated)


async def dashboard_stats():
    pool = get_pool()

    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT
                COUNT(*) FILTER (
                    WHERE status IN ('pending', 'review', 'approved')
                ) AS active_orders,
                COUNT(*) FILTER (
                    WHERE status = 'completed'
                      AND created_at >= CURRENT_DATE
                ) AS completed_today,
                COUNT(*) FILTER (
                    WHERE created_at >= CURRENT_DATE
                ) AS orders_today,
                COALESCE(
                    SUM(total) FILTER (
                        WHERE status = 'completed'
                          AND created_at >= CURRENT_DATE
                    ), 0
                ) AS turnover_today,
                COUNT(DISTINCT telegram_id) AS customers
            FROM orders
        """)

        return dict(row)


async def log_admin_action(
    admin_id: int,
    action: str,
    order_ref: str | None = None,
    details: str | None = None,
):
    pool = get_pool()

    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO audit_log (
                admin_id, order_ref, action, details
            )
            VALUES ($1, $2, $3, $4)
        """, admin_id, order_ref, action, details)
