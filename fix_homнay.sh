#!/bin/bash

# Thêm hàm get_daily_budget_status vào database.py
docker exec telegram-expense-bot python3 -c "
import sys
sys.path.insert(0, '/app/src')
import database as db
print('DB OK')
"

# Thêm function vào database.py
docker exec telegram-expense-bot bash -c "cat >> /app/src/database.py << 'PYEOF'

def get_daily_budget_status(user_id):
    from calendar import monthrange
    now = __import__('datetime').datetime.now()
    month, year = now.month, now.year
    today = now.day
    days_in_month = monthrange(year, month)[1]
    days_remaining = days_in_month - today + 1

    conn = get_connection()
    total_budget = conn.execute('''
        SELECT COALESCE(SUM(amount), 0) as total FROM budgets
        WHERE user_id=? AND month=? AND year=?
    ''', (user_id, month, year)).fetchone()['total']

    if total_budget == 0:
        conn.close()
        return None

    spent_before_today = conn.execute('''
        SELECT COALESCE(SUM(amount), 0) as total FROM transactions
        WHERE user_id=? AND type='expense'
          AND strftime('%m', created_at)=?
          AND strftime('%Y', created_at)=?
          AND date(created_at) < date('now')
    ''', (user_id, f'{month:02d}', str(year))).fetchone()['total']

    spent_today = conn.execute('''
        SELECT COALESCE(SUM(amount), 0) as total FROM transactions
        WHERE user_id=? AND type='expense' AND date(created_at) = date('now')
    ''', (user_id,)).fetchone()['total']

    spent_today_by_cat = conn.execute('''
        SELECT category, COALESCE(SUM(amount), 0) as total FROM transactions
        WHERE user_id=? AND type='expense' AND date(created_at) = date('now')
        GROUP BY category
    ''', (user_id,)).fetchall()
    conn.close()

    budget_remaining = total_budget - spent_before_today
    daily_limit = budget_remaining / days_remaining if days_remaining > 0 else 0
    remaining_today = daily_limit - spent_today

    return {
        'total_budget': total_budget,
        'spent_before_today': spent_before_today,
        'spent_today': spent_today,
        'spent_today_by_cat': {r['category']: r['total'] for r in spent_today_by_cat},
        'daily_limit': daily_limit,
        'remaining_today': remaining_today,
        'days_remaining': days_remaining,
        'days_in_month': days_in_month,
        'today': today,
        'budget_remaining_month': budget_remaining,
        'pct_used_today': min(spent_today / daily_limit * 100, 100) if daily_limit > 0 else 0,
    }
PYEOF"

# Thêm handler vào handlers.py
docker exec telegram-expense-bot bash -c "cat >> /app/src/handlers.py << 'PYEOF'

async def daily_budget(update, context):
    from datetime import datetime
    user = update.effective_user
    now = datetime.now()
    data = __import__('database').get_daily_budget_status(user.id)

    if data is None:
        await update.message.reply_text(
            '📭 Bạn chưa đặt ngân sách tháng này.\nDùng /nganquy để đặt trước!'
        )
        return

    daily_limit = data['daily_limit']
    spent_today = data['spent_today']
    remaining = data['remaining_today']
    pct = data['pct_used_today']

    filled = int(pct / 10)
    bar = '█' * filled + '░' * (10 - filled)
    status = '🔴' if pct >= 100 else ('🟡' if pct >= 80 else '🟢')

    def fmt(x): return f'{x:,.0f} VND'

    lines = [
        f'📅 <b>Hạn mức hôm nay {now.strftime(\"%d/%m/%Y\")}</b>\n',
        f'{status} <code>{bar}</code> {pct:.0f}%',
        f'💰 Hạn mức ngày: <b>{fmt(daily_limit)}</b>',
        f'💸 Đã chi: <b>{fmt(spent_today)}</b>',
    ]

    if remaining >= 0:
        lines.append(f'✅ Còn lại hôm nay: <b>{fmt(remaining)}</b>')
    else:
        lines.append(f'🔴 Đã vượt: <b>{fmt(abs(remaining))}</b>')

    if data['spent_today_by_cat']:
        lines.append('\n<b>Chi hôm nay:</b>')
        from database import EXPENSE_CATEGORIES
        for cat, total in sorted(data['spent_today_by_cat'].items(), key=lambda x: -x[1]):
            label = EXPENSE_CATEGORIES.get(cat, cat)
            lines.append(f'• {label}: {fmt(total)}')

    lines.append(
        f'\n📊 Ngân sách tháng: {fmt(data[\"total_budget\"])}\n'
        f'Còn lại tháng: {fmt(data[\"budget_remaining_month\"])}\n'
        f'Số ngày còn lại: {data[\"days_remaining\"]} ngày'
    )

    await update.message.reply_text('\n'.join(lines), parse_mode='HTML')
PYEOF"

# Thêm import và handler vào bot.py
docker exec telegram-expense-bot sed -i 's/from handlers import (/from handlers import (\n    daily_budget,/' /app/src/bot.py

docker restart telegram-expense-bot
echo "✅ Done!"
