import logging
from datetime import datetime
from telegram.ext import ContextTypes
import database as db
from database import EXPENSE_CATEGORIES

logger = logging.getLogger(__name__)

def fmt(amount):
    return f"{amount:,.0f} VND"

def progress_bar(current, target, width=10):
    pct = min(current / target * 100, 100) if target > 0 else 0
    filled = int(pct / (100 / width))
    return "█" * filled + "░" * (width - filled), pct

async def send_daily_summary(context: ContextTypes.DEFAULT_TYPE):
    """Gửi tóm tắt chi tiêu hàng ngày."""
    users = db.get_all_users()
    now = datetime.now()

    for user in users:
        if not user["daily_notify"]:
            continue
        try:
            summary = db.get_daily_summary(user["user_id"])
            monthly = db.get_monthly_summary(user["user_id"], now.month, now.year)

            total_today = summary["expense"]
            lines = [
                f"🌙 <b>Tóm tắt hôm nay {now.strftime('%d/%m/%Y')}</b>\n",
                f"💸 Chi tiêu hôm nay: <b>{fmt(total_today)}</b>",
                f"💰 Thu nhập hôm nay: <b>{fmt(summary['income'])}</b>",
            ]
            if summary["saving"] > 0:
                lines.append(f"🏦 Tiết kiệm hôm nay: <b>{fmt(summary['saving'])}</b>")

            lines.append(f"\n📊 <b>Lũy kế tháng {now.month}/{now.year}:</b>")
            lines.append(f"💸 Đã chi: <b>{fmt(monthly['total_expense'])}</b>")
            lines.append(f"💰 Thu nhập: <b>{fmt(monthly['total_income'])}</b>")

            balance = monthly["balance"]
            icon = "✅" if balance >= 0 else "🔴"
            lines.append(f"{icon} Số dư: <b>{fmt(balance)}</b>")

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
            logger.error(f"Daily notify error for {user['user_id']}: {e}")

async def send_weekly_summary(context: ContextTypes.DEFAULT_TYPE):
    """Gửi báo cáo hàng tuần (thứ 2)."""
    now = datetime.now()
    if now.weekday() != 0:  # 0 = Monday
        return

    users = db.get_all_users()
    for user in users:
        if not user["weekly_notify"]:
            continue
        try:
            stats = db.get_stats(user["user_id"], 7)
            total_expense = sum(v["total"] for v in stats["expense"].values())
            total_income = sum(v["total"] for v in stats["income"].values())
            total_saving = sum(v["total"] for v in stats["saving"].values())

            lines = ["📅 <b>Báo cáo tuần qua</b>\n"]
            lines.append(f"💰 Thu nhập: <b>{fmt(total_income)}</b>")
            lines.append(f"💸 Chi tiêu: <b>{fmt(total_expense)}</b>")
            if total_saving > 0:
                lines.append(f"🏦 Tiết kiệm: <b>{fmt(total_saving)}</b>")

            if stats["expense"]:
                lines.append("\n<b>Top chi tiêu:</b>")
                top = sorted(stats["expense"].items(), key=lambda x: -x[1]["total"])[:3]
                for cat, data in top:
                    label = EXPENSE_CATEGORIES.get(cat, cat)
                    lines.append(f"• {label}: {fmt(data['total'])}")

            balance = total_income - total_expense - total_saving
            lines.append(f"\n{'✅' if balance >= 0 else '🔴'} Số dư: <b>{fmt(balance)}</b>")

            await context.bot.send_message(
                chat_id=user["user_id"],
                text="\n".join(lines),
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Weekly notify error for {user['user_id']}: {e}")

async def send_monthly_summary(context: ContextTypes.DEFAULT_TYPE):
    """Gửi tổng kết đầu tháng (ngày 1)."""
    now = datetime.now()
    if now.day != 1:
        return

    # Tổng kết tháng trước
    month = now.month - 1 if now.month > 1 else 12
    year = now.year if now.month > 1 else now.year - 1

    users = db.get_all_users()
    for user in users:
        if not user["monthly_notify"]:
            continue
        try:
            s = db.get_monthly_summary(user["user_id"], month, year)

            lines = [f"📊 <b>Tổng kết tháng {month}/{year}</b>\n"]
            lines.append(f"💰 Thu nhập: <b>{fmt(s['total_income'])}</b>")
            lines.append(f"💸 Chi tiêu: <b>{fmt(s['total_expense'])}</b>")
            if s["total_saving"] > 0:
                lines.append(f"🏦 Tiết kiệm: <b>{fmt(s['total_saving'])}</b>")

            if s["expense_by_category"]:
                lines.append("\n<b>Chi theo danh mục:</b>")
                for cat, total in sorted(s["expense_by_category"].items(), key=lambda x: -x[1]):
                    label = EXPENSE_CATEGORIES.get(cat, cat)
                    lines.append(f"• {label}: {fmt(total)}")

            icon = "✅" if s["balance"] >= 0 else "🔴"
            lines.append(f"\n{icon} Số dư: <b>{fmt(s['balance'])}</b>")
            lines.append(f"\n🗓️ Tháng {now.month}/{now.year} bắt đầu rồi! Chúc bạn quản lý tốt 💪")

            await context.bot.send_message(
                chat_id=user["user_id"],
                text="\n".join(lines),
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Monthly notify error for {user['user_id']}: {e}")

async def process_recurring(context: ContextTypes.DEFAULT_TYPE):
    """Tự động ghi nhận giao dịch định kỳ."""
    due = db.get_due_recurring()
    for r in due:
        try:
            tx_id = db.add_transaction(
                r["user_id"], r["type"], r["amount"],
                r["category"], f"[Định kỳ] {r['description']}"
            )
            db.mark_recurring_run(r["id"])

            icon = "💸" if r["type"] == "expense" else "💰"
            cat = EXPENSE_CATEGORIES.get(r["category"], r["category"] or "")
            await context.bot.send_message(
                chat_id=r["user_id"],
                text=(
                    f"🔁 <b>Giao dịch định kỳ #{tx_id}</b>\n\n"
                    f"{icon} <b>{r['description']}</b>\n"
                    f"💵 {fmt(r['amount'])} — {cat}\n\n"
                    "Đã tự động ghi nhận!"
                ),
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Recurring error for {r['id']}: {e}")
