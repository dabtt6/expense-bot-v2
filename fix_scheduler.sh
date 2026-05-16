#!/bin/bash
set -e

docker cp telegram-expense-bot:/app/src/scheduler.py /tmp/scheduler.py
docker cp telegram-expense-bot:/app/src/bot.py /tmp/bot.py

# Thêm hàm smart_daily_notify vào scheduler.py
cat >> /tmp/scheduler.py << 'PYEOF'

async def smart_daily_notify(context):
    """Kiểm tra mỗi phút, gửi cho user đúng giờ họ đã cài."""
    now = datetime.now()
    # Chỉ chạy đúng phút 0 của mỗi giờ
    if now.minute != 0:
        return

    current_hour = now.hour
    users = db.get_all_users()

    for user in users:
        if not user["daily_notify"]:
            continue
        if user["daily_notify_hour"] != current_hour:
            continue
        try:
            summary = db.get_daily_summary(user["user_id"])
            monthly = db.get_monthly_summary(user["user_id"], now.month, now.year)

            lines = [
                f"🌅 <b>Báo cáo {now.strftime('%d/%m/%Y')} - {current_hour:02d}:00</b>\n",
                f"💸 Chi hôm nay: <b>{fmt(summary['expense'])}</b>",
                f"💰 Thu hôm nay: <b>{fmt(summary['income'])}</b>",
            ]
            if summary["saving"] > 0:
                lines.append(f"🏦 Tiết kiệm: <b>{fmt(summary['saving'])}</b>")

            lines.append(f"\n📊 <b>Lũy kế tháng {now.month}/{now.year}:</b>")
            lines.append(f"💸 Đã chi: <b>{fmt(monthly['total_expense'])}</b>")
            lines.append(f"💰 Thu nhập: <b>{fmt(monthly['total_income'])}</b>")

            balance = monthly["balance"]
            lines.append(f"{'✅' if balance >= 0 else '🔴'} Số dư: <b>{fmt(balance)}</b>")

            # Hạn mức ngày
            data = db.get_daily_budget_status(user["user_id"])
            if data:
                remaining = data["remaining_today"]
                lines.append(
                    f"\n📅 <b>Hạn mức hôm nay:</b>\n"
                    f"💰 Hạn mức: {fmt(data['daily_limit'])}\n"
                    f"{'✅ Còn lại' if remaining >= 0 else '🔴 Vượt'}: <b>{fmt(abs(remaining))}</b>"
                )

            # Cảnh báo ngân sách
            if user["budget_alert"]:
                alerts = db.get_over_budget_categories(user["user_id"], now.month, now.year, threshold=0.8)
                if alerts:
                    lines.append("\n⚠️ <b>Cảnh báo ngân sách:</b>")
                    for a in alerts:
                        label = EXPENSE_CATEGORIES.get(a["category"], a["category"])
                        status = "🔴 Vượt" if a["pct"] >= 1 else "🟡 Gần hết"
                        lines.append(f"{status} {label}: {a['pct']*100:.0f}%")

            await context.bot.send_message(
                chat_id=user["user_id"],
                text="\n".join(lines),
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Smart daily notify error for {user['user_id']}: {e}")
PYEOF

# Sửa bot.py: thay run_daily bằng run_repeating mỗi 60 giây
python3 << 'PYEOF'
with open("/tmp/bot.py", "r") as f:
    content = f.read()

# Thêm import smart_daily_notify
content = content.replace(
    "from scheduler import (\n    send_daily_summary, send_weekly_summary,\n    send_monthly_summary, process_recurring\n)",
    "from scheduler import (\n    send_daily_summary, send_weekly_summary,\n    send_monthly_summary, process_recurring, smart_daily_notify\n)"
)

# Thay run_daily send_daily_summary bằng run_repeating smart_daily_notify
content = content.replace(
    "    job_queue.run_daily(send_daily_summary, time=__import__('datetime').time(6, 0))",
    "    job_queue.run_repeating(smart_daily_notify, interval=60, first=10)"
)

with open("/tmp/bot.py", "w") as f:
    f.write(content)
print("bot.py updated")
PYEOF

python3 -c "import ast; ast.parse(open('/tmp/scheduler.py').read()); print('✅ scheduler.py OK')"
python3 -c "import ast; ast.parse(open('/tmp/bot.py').read()); print('✅ bot.py OK')"

docker cp /tmp/scheduler.py telegram-expense-bot:/app/src/scheduler.py
docker cp /tmp/bot.py telegram-expense-bot:/app/src/bot.py

docker restart telegram-expense-bot
sleep 3
docker logs telegram-expense-bot --tail 5
echo "✅ Xong! Báo cáo sẽ gửi đúng giờ đã cài trong /caidat"
