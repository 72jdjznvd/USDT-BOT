import os
import sqlite3
import asyncio
from pathlib import Path
from datetime import datetime, timezone

BASE_DIR = Path(file).resolve().parent
DB_PATH = Path(os.getenv("DATABASE_PATH", str(BASE_DIR / "p2p.db")))

_db = None
_lock = asyncio.Lock()

def now():
return datetime.now(timezone.utc).isoformat()

async def connect_db():
global _db

async with _lock:
    if _db is not None:
        return

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    _db = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    _db.row_factory = sqlite3.Row
    _db.execute("PRAGMA foreign_keys = ON")

    _db.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        telegram_id INTEGER PRIMARY KEY,
        username TEXT,
        first_name TEXT,
        last_name TEXT,
        language TEXT DEFAULT 'az',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_ref TEXT UNIQUE NOT NULL,
        telegram_id INTEGER NOT NULL,
        kind TEXT NOT NULL,
        amount TEXT NOT NULL,
        rate TEXT NOT NULL,
        total TEXT NOT NULL,
        currency TEXT DEFAULT 'AZN',
        status TEXT DEFAULT 'pending',
        payment_method TEXT,
        receipt_file_id TEXT,
        txid TEXT UNIQUE,
        bank_name TEXT,
        customer_note TEXT,
        rejection_reason TEXT,
        admin_id INTEGER,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        expires_at TEXT,
        completed_at TEXT,
        FOREIGN KEY (telegram_id) REFERENCES users(telegram_id)
    );

    CREATE TABLE IF NOT EXISTS audit_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_ref TEXT,
        admin_id INTEGER,
        action TEXT NOT NULL,
        details TEXT,
        created_at TEXT NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_orders_user
    ON orders(telegram_id);

    CREATE INDEX IF NOT EXISTS idx_orders_status
    ON orders(status);
    """)

    _db.commit()

async def close_db():
global _db

async with _lock:
    if _db is not None:
        _db.close()
        _db = None

def _connection():
if _db is None:
raise RuntimeError("Database is not connected. Call connect_db() first.")
return _db

async def save_user(
telegram_id,
username=None,
first_name=None,
last_name=None,
language="az",
):
async with _lock:
db = _connection()
timestamp = now()

    db.execute("""
        INSERT INTO users (
            telegram_id, username, first_name, last_name,
            language, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(telegram_id) DO UPDATE SET
            username = excluded.username,
            first_name = excluded.first_name,
            last_name = excluded.last_name,
            language = excluded.language,
            updated_at = excluded.updated_at
    """, (
        telegram_id, username, first_name, last_name,
        language, timestamp, timestamp
    ))
    db.commit()

async def get_user(telegram_id):
async with _lock:
row = _connection().execute(
"SELECT * FROM users WHERE telegram_id = ?",
(telegram_id,),
).fetchone()
return dict(row) if row else None

async def create_order(
order_ref,
telegram_id,
kind,
amount,
rate,
total,
currency="AZN",
payment_method=None,
):
async with _lock:
db = _connection()
timestamp = now()

    db.execute("""
        INSERT INTO orders (
            order_ref, telegram_id, kind, amount, rate, total,
            currency, status, payment_method, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?)
    """, (
        order_ref, telegram_id, kind, str(amount), str(rate),
        str(total), currency, payment_method, timestamp, timestamp
    ))
    db.commit()
    return order_ref

def _order_query(where_clause="", params=(), limit=None):
sql = """
SELECT o.*, u.username, u.first_name, u.last_name,
u.language
FROM orders o
LEFT JOIN users u ON u.telegram_id = o.telegram_id
"""

if where_clause:
    sql += " WHERE " + where_clause

sql += " ORDER BY o.id DESC"

if limit is not None:
    sql += " LIMIT ?"
    params = tuple(params) + (int(limit),)

rows = _connection().execute(sql, params).fetchall()
return [dict(row) for row in rows]

async def get_order(order_ref):
async with _lock:
rows = _order_query("o.order_ref = ?", (order_ref,), limit=1)
return rows[0] if rows else None

async def list_orders(status=None, limit=20):
async with _lock:
if status:
return _order_query("o.status = ?", (status,), limit)
return _order_query(limit=limit)

async def list_user_orders(telegram_id, limit=10):
async with _lock:
return _order_query(
"o.telegram_id = ?",
(telegram_id,),
limit,
)

async def set_receipt(order_ref, file_id):
async with _lock:
db = _connection()
cursor = db.execute("""
UPDATE orders
SET receipt_file_id = ?, status = 'review', updated_at = ?
WHERE order_ref = ? AND kind = 'buy' AND status = 'pending'
""", (file_id, now(), order_ref))
db.commit()
return cursor.rowcount == 1

async def set_txid(order_ref, txid):
txid = txid.strip()

if not txid:
    return False

async with _lock:
    db = _connection()

    # UNIQUE constraint prevents the same TXID being reused.
    try:
        cursor = db.execute("""
            UPDATE orders
            SET txid = ?, status = 'review', updated_at = ?
            WHERE order_ref = ? AND kind = 'sell' AND status = 'pending'
        """, (txid, now(), order_ref))
        db.commit()
        return cursor.rowcount == 1
    except sqlite3.IntegrityError:
        db.rollback()
        return False

async def set_bank(order_ref, bank_name):
async with _lock:
db = _connection()
cursor = db.execute("""
UPDATE orders
SET bank_name = ?, payment_method = ?, updated_at = ?
WHERE order_ref = ? AND kind = 'sell' AND status = 'review'
""", (bank_name, bank_name, now(), order_ref))
db.commit()
return cursor.rowcount == 1

async def admin_decide(
order_ref,
admin_id,
decision,
reason=None,
):
if decision not in ("approve", "reject"):
return False

new_status = "approved" if decision == "approve" else "rejected"

async with _lock:
    db = _connection()

    cursor = db.execute("""
        UPDATE orders
        SET status = ?, admin_id = ?, rejection_reason = ?,
            updated_at = ?
        WHERE order_ref = ? AND status = 'review'
    """, (
        new_status, admin_id, reason, now(), order_ref
    ))

    if cursor.rowcount != 1:
        db.rollback()
        return False

    db.execute("""
        INSERT INTO audit_log (
            order_ref, admin_id, action, details, created_at
        )
        VALUES (?, ?, ?, ?, ?)
    """, (
        order_ref, admin_id, decision, reason, now()
    ))

    db.commit()
    return True

async def dashboard_stats():
async with _lock:
db = _connection()

    total = db.execute(
        "SELECT COUNT(*) FROM orders"
    ).fetchone()[0]

    rows = db.execute("""
        SELECT status, COUNT(*) AS count
        FROM orders GROUP BY status
    """).fetchall()

    return {
        "total": total,
        "by_status": {
            row["status"]: row["count"] for row in rows
        },
    }

async def log_admin_action(
admin_id,
action,
order_ref=None,
details=None,
):
async with _lock:
db = _connection()
db.execute("""
INSERT INTO audit_log (
order_ref, admin_id, action, details, created_at
)
VALUES (?, ?, ?, ?, ?)
""", (order_ref, admin_id, action, details, now()))
db.commit()
