import sqlite3
import os
from datetime import datetime
from typing import Optional, List, Dict

DB_PATH = os.getenv("DB_PATH", "/app/data/expenses.db")

EXPENSE_CATEGORIES = {
    "food": "🍜 Ăn uống",
    "transport": "🚗 Di chuyển",
    "shopping": "🛍️ Mua sắm",
    "entertainment": "🎮 Giải trí",
    "health": "💊 Y tế",
    "bills": "📱 Hóa đơn",
    "education": "📚 Giáo dục",
    "saving": "🏦 Tiết kiệm",
    "other": "📦 Khác",
}

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            type TEXT NOT NULL CHECK(type IN ('expense', 'income', 'saving')),
            category TEXT,
            amount REAL NOT NULL,
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS budgets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            category TEXT NOT NULL,
            amount REAL NOT NULL,
            month INTEGER NOT NULL,
            year INTEGER NOT NULL,
            UNIQUE(user_id, category, month, year)
        );

        CREATE TABLE IF NOT EXISTS savings_goals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            target REAL NOT NULL,
            current REAL DEFAULT 0,
            deadline TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS recurring (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            type TEXT NOT NULL,
            category TEXT,
            amount REAL NOT NULL,
            description TEXT NOT NULL,
            day_of_month INTEGER NOT NULL,
            active INTEGER DEFAULT 1,
            last_run TEXT
        );

        CREATE TABLE IF NOT EXISTS user_settings (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            daily_notify INTEGER DEFAULT 0,
            daily_notify_hour INTEGER DEFAULT 21,
            weekly_notify INTEGER DEFAULT 0,
            monthly_notify INTEGER DEFAULT 1,
            budget_alert INTEGER DEFAULT 1,
            quick_add INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_tx_user ON transactions(user_id);
        CREATE INDEX IF NOT EXISTS idx_tx_date ON transactions(created_at);
    """)
    conn.commit()
    conn.close()

def upsert_user(user_id, username, first_name):
    conn = get_connection()
    conn.execute("""
        INSERT INTO user_settings (user_id, username, first_name)
        VALUES (?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET username=excluded.username, first_name=excluded.first_name
    """, (user_id, username, first_name))
    conn.commit()
    conn.close()

def get_user_settings(user_id):
    conn = get_connection()
    row = conn.execute("SELECT * FROM user_settings WHERE user_id=?", (user_id,)).fetchone()
    conn.close()
    return row

def update_setting(user_id, key, value):
    conn = get_connection()
    conn.execute(f"UPDATE user_settings SET {key}=? WHERE user_id=?", (value, user_id))
    conn.commit()
    conn.close()

def get_all_users():
    conn = get_connection()
    rows = conn.execute("SELECT * FROM user_settings").fetchall()
    conn.close()
    return rows

def add_transaction(user_id, type_, amount, category, description):
    conn = get_connection()
    cur = conn.execute("""
        INSERT INTO transactions (user_id, type, amount, category, description)
        VALUES (?, ?, ?, ?, ?)
    """, (user_id, type_, amount, category, description))
    conn.commit()
    row_id = cur.lastrowid
    conn.close()
    return row_id

def get_monthly_summary(user_id, month, year):
    conn = get_connection()
    expenses = conn.execute("""
        SELECT category, SUM(amount) as total FROM transactions
        WHERE user_id=? AND type='expense'
          AND strftime('%m',created_at)=? AND strftime('%Y',created_at)=?
        GROUP BY category
    """, (user_id, f"{month:02d}", str(year))).fetchall()

    income = conn.execute("""
        SELECT COALESCE(SUM(amount),0) as total FROM transactions
        WHERE user_id=? AND type='income'
          AND strftime('%m',created_at)=? AND strftime('%Y',created_at)=?
    """, (user_id, f"{month:02d}", str(year))).fetchone()

    saving = conn.execute("""
        SELECT COALESCE(SUM(amount),0) as total FROM transactions
        WHERE user_id=? AND type='saving'
          AND strftime('%m',created_at)=? AND strftime('%Y',created_at)=?
    """, (user_id, f"{month:02d}", str(year))).fetchone()

    conn.close()
    expense_by_cat = {r["category"]: r["total"] for r in expenses}
    total_expense = sum(expense_by_cat.values())
    return {
        "expense_by_category": expense_by_cat,
        "total_expense": total_expense,
        "total_income": income["total"],
        "total_saving": saving["total"],
        "balance": income["total"] - total_expense - saving["total"],
    }

def get_daily_summary(user_id):
    conn = get_connection()
    today = datetime.now().strftime("%Y-%m-%d")
    rows = conn.execute("""
        SELECT type, COALESCE(SUM(amount),0) as total FROM transactions
        WHERE user_id=? AND date(created_at)=?
        GROUP BY type
    """, (user_id, today)).fetchall()
    conn.close()
    result = {"expense": 0, "income": 0, "saving": 0}
    for r in rows:
        result[r["type"]] = r["total"]
    return result

def get_recent_transactions(user_id, limit=10):
    conn = get_connection()
    rows = conn.execute("""
        SELECT id, type, category, amount, description, created_at
        FROM transactions WHERE user_id=?
        ORDER BY created_at DESC LIMIT ?
    """, (user_id, limit)).fetchall()
    conn.close()
    return rows

def delete_transaction(tx_id, user_id):
    conn = get_connection()
    cur = conn.execute("DELETE FROM transactions WHERE id=? AND user_id=?", (tx_id, user_id))
    conn.commit()
    deleted = cur.rowcount > 0
    conn.close()
    return deleted

def set_budget(user_id, category, amount, month, year):
    conn = get_connection()
    conn.execute("""
        INSERT INTO budgets (user_id, category, amount, month, year)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(user_id, category, month, year) DO UPDATE SET amount=excluded.amount
    """, (user_id, category, amount, month, year))
    conn.commit()
    conn.close()

def get_budgets(user_id, month, year):
    conn = get_connection()
    rows = conn.execute("""
        SELECT b.category, b.amount as budget, COALESCE(SUM(t.amount),0) as spent
        FROM budgets b
        LEFT JOIN transactions t ON t.user_id=b.user_id AND t.category=b.category
          AND t.type='expense'
          AND strftime('%m',t.created_at)=? AND strftime('%Y',t.created_at)=?
        WHERE b.user_id=? AND b.month=? AND b.year=?
        GROUP BY b.category, b.amount
    """, (f"{month:02d}", str(year), user_id, month, year)).fetchall()
    conn.close()
    return rows

def get_over_budget_categories(user_id, month, year, threshold=0.8):
    budgets = get_budgets(user_id, month, year)
    alerts = []
    for b in budgets:
        if b["budget"] > 0:
            pct = b["spent"] / b["budget"]
            if pct >= threshold:
                alerts.append({"category": b["category"], "budget": b["budget"], "spent": b["spent"], "pct": pct})
    return alerts

# ── Savings Goals ──────────────────────────────────────────────────────────────

def add_savings_goal(user_id, name, target, deadline=None):
    conn = get_connection()
    cur = conn.execute("""
        INSERT INTO savings_goals (user_id, name, target, deadline)
        VALUES (?, ?, ?, ?)
    """, (user_id, name, target, deadline))
    conn.commit()
    gid = cur.lastrowid
    conn.close()
    return gid

def get_savings_goals(user_id):
    conn = get_connection()
    rows = conn.execute("""
        SELECT g.id, g.name, g.target, g.deadline,
               COALESCE(SUM(t.amount),0) as current
        FROM savings_goals g
        LEFT JOIN transactions t ON t.user_id=g.user_id AND t.type='saving'
          AND t.description LIKE '%[goal:'||g.id||']%'
        WHERE g.user_id=?
        GROUP BY g.id
    """, (user_id,)).fetchall()
    conn.close()
    return rows

def delete_savings_goal(goal_id, user_id):
    conn = get_connection()
    cur = conn.execute("DELETE FROM savings_goals WHERE id=? AND user_id=?", (goal_id, user_id))
    conn.commit()
    deleted = cur.rowcount > 0
    conn.close()
    return deleted

# ── Recurring ─────────────────────────────────────────────────────────────────

def add_recurring(user_id, type_, category, amount, description, day_of_month):
    conn = get_connection()
    cur = conn.execute("""
        INSERT INTO recurring (user_id, type, category, amount, description, day_of_month)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (user_id, type_, category, amount, description, day_of_month))
    conn.commit()
    rid = cur.lastrowid
    conn.close()
    return rid

def get_recurring(user_id):
    conn = get_connection()
    rows = conn.execute("SELECT * FROM recurring WHERE user_id=? AND active=1", (user_id,)).fetchall()
    conn.close()
    return rows

def delete_recurring(rid, user_id):
    conn = get_connection()
    cur = conn.execute("UPDATE recurring SET active=0 WHERE id=? AND user_id=?", (rid, user_id))
    conn.commit()
    deleted = cur.rowcount > 0
    conn.close()
    return deleted

def get_due_recurring():
    conn = get_connection()
    today = datetime.now()
    rows = conn.execute("""
        SELECT * FROM recurring WHERE active=1
          AND day_of_month=?
          AND (last_run IS NULL OR date(last_run) < date('now'))
    """, (today.day,)).fetchall()
    conn.close()
    return rows

def mark_recurring_run(rid):
    conn = get_connection()
    conn.execute("UPDATE recurring SET last_run=? WHERE id=?", (datetime.now().isoformat(), rid))
    conn.commit()
    conn.close()

def get_stats(user_id, days):
    conn = get_connection()
    rows = conn.execute("""
        SELECT type, category, SUM(amount) as total, COUNT(*) as count
        FROM transactions
        WHERE user_id=? AND created_at >= datetime('now', ?)
        GROUP BY type, category
    """, (user_id, f"-{days} days")).fetchall()
    conn.close()
    stats = {"expense": {}, "income": {}, "saving": {}}
    for r in rows:
        stats[r["type"]][r["category"] or "other"] = {"total": r["total"], "count": r["count"]}
    return stats

def get_all_transactions_csv(user_id):
    conn = get_connection()
    rows = conn.execute("""
        SELECT id, type, category, amount, description, created_at
        FROM transactions WHERE user_id=? ORDER BY created_at DESC
    """, (user_id,)).fetchall()
    conn.close()
    return rows
