#!/bin/bash
set -e

# Bước 1: Lấy file từ container ra
docker cp telegram-expense-bot:/app/src/database.py /tmp/database.py
docker cp telegram-expense-bot:/app/src/handlers.py /tmp/handlers.py
docker cp telegram-expense-bot:/app/src/bot.py /tmp/bot.py

# Bước 2: Thêm get_daily_budget_status vào database.py
cat >> /tmp/database.py << 'PYEOF'

def get_daily_budget_status(user_id):
    from calendar import monthrange
    import datetime as dt
    now = dt.datetime.now()
    month, year, today = now.month, now.year, now.day
    days_in_month = monthrange(year, month)[1]
    days_remaining = days_in_month - today + 1

    conn = get_connection()
    total_budget = conn.execute(
        "SELECT COALESCE(SUM(amount),0) as total FROM budgets WHERE user_id=? AND month=? AND year=?",
        (user_id, month, year)
    ).fetchone()["total"]

    if total_budget == 0:
        conn.close()
        return None

    spent_before = conn.execute(
        "SELECT COALESCE(SUM(amount),0) as total FROM transactions WHERE user_id=? AND type='expense' AND strftime('%m',created_at)=? AND strftime('%Y',created_at)=? AND date(created_at)<date('now')",
        (user_id, f"{month:02d}", str(year))
    ).fetchone()["total"]

    spent_today = conn.execute(
        "SELECT COALESCE(SUM(amount),0) as total FROM transactions WHERE user_id=? AND type='expense' AND date(created_at)=date('now')",
        (user_id,)
    ).fetchone()["total"]

    cats = conn.execute(
        "SELECT category, COALESCE(SUM(amount),0) as total FROM transactions WHERE user_id=? AND type='expense' AND date(created_at)=date('now') GROUP BY category",
        (user_id,)
    ).fetchall()
    conn.close()

    budget_remaining = total_budget - spent_before
    daily_limit = budget_remaining / days_remaining if days_remaining > 0 else 0
    pct = min(spent_today / daily_limit * 100, 100) if daily_limit > 0 else 0

    return {
        "total_budget": total_budget,
        "spent_today": spent_today,
        "spent_today_by_cat": {r["category"]: r["total"] for r in cats},
        "daily_limit": daily_limit,
        "remaining_today": daily_limit - spent_today,
        "days_remaining": days_remaining,
        "days_in_month": days_in_month,
        "today": today,
        "budget_remaining_month": budget_remaining,
        "pct_used_today": pct,
    }
PYEOF

# Bước 3: Thêm daily_budget handler vào handlers.py
cat >> /tmp/handlers.py << 'PYEOF'

async def daily_budget(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    now = datetime.now()
    data = db.get_daily_budget_status(user.id)

    if data is None:
        await update.message.reply_text("📭 Chưa đặt ngân sách tháng này.\nDùng /nganquy để đặt!")
        return

    daily_limit = data["daily_limit"]
    spent_today = data["spent_today"]
    remaining = data["remaining_today"]
    pct = data["pct_used_today"]

    filled = int(pct / 10)
    bar = "█" * filled + "░" * (10 - filled)
    status = "🔴" if pct >= 100 else ("🟡" if pct >= 80 else "🟢")

    lines = [
        f"📅 <b>Hạn mức hôm nay {now.strftime('%d/%m/%Y')}</b>\n",
        f"{status} <code>{bar}</code> {pct:.0f}%",
        f"💰 Hạn mức ngày: <b>{fmt(daily_limit)}</b>",
        f"💸 Đã chi: <b>{fmt(spent_today)}</b>",
    ]

    if remaining >= 0:
        lines.append(f"✅ Còn lại hôm nay: <b>{fmt(remaining)}</b>")
    else:
        lines.append(f"🔴 Đã vượt: <b>{fmt(abs(remaining))}</b>")

    if data["spent_today_by_cat"]:
        lines.append("\n<b>Chi hôm nay theo danh mục:</b>")
        for cat, total in sorted(data["spent_today_by_cat"].items(), key=lambda x: -x[1]):
            label = EXPENSE_CATEGORIES.get(cat, cat)
            lines.append(f"• {label}: {fmt(total)}")

    lines.append(
        f"\n📊 Ngân sách tháng: {fmt(data['total_budget'])}\n"
        f"Còn lại tháng: {fmt(data['budget_remaining_month'])}\n"
        f"Số ngày còn lại: {data['days_remaining']} ngày"
    )

    await update.message.reply_text("\n".join(lines), parse_mode="HTML")
PYEOF

# Bước 4: Thêm import daily_budget và CommandHandler vào bot.py
sed -i 's/    settings, handle_settings,/    settings, handle_settings, daily_budget,/' /tmp/bot.py
sed -i 's/app.add_handler(CommandHandler("nhanh", quick_help))/app.add_handler(CommandHandler("nhanh", quick_help))\n    app.add_handler(CommandHandler("hom_nay", daily_budget))/' /tmp/bot.py

# Bước 5: Copy trở lại vào container
docker cp /tmp/database.py telegram-expense-bot:/app/src/database.py
docker cp /tmp/handlers.py telegram-expense-bot:/app/src/handlers.py
docker cp /tmp/bot.py telegram-expense-bot:/app/src/bot.py

# Bước 6: Restart
docker restart telegram-expense-bot
sleep 3
docker logs telegram-expense-bot --tail 5
echo "✅ Done!"
