import csv
import io
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
import database as db
from database import EXPENSE_CATEGORIES

logger = logging.getLogger(__name__)

(
    CATEGORY, AMOUNT, DESCRIPTION,
    BUDGET_CATEGORY, BUDGET_AMOUNT,
    DELETE_SELECT, PERIOD_SELECT,
    GOAL_NAME, GOAL_TARGET, GOAL_DEADLINE, GOAL_SELECT,
    SAVING_GOAL, SAVING_AMOUNT,
    REC_TYPE, REC_CATEGORY, REC_AMOUNT, REC_DESC, REC_DAY, REC_DELETE,
    SETTINGS_SELECT,
) = range(20)

def fmt(amount):
    return f"{amount:,.0f} VND"

def get_category_keyboard(prefix="cat_", extra=None):
    buttons = []
    cats = list(EXPENSE_CATEGORIES.items())
    for i in range(0, len(cats), 2):
        row = [InlineKeyboardButton(label, callback_data=f"{prefix}{key}") for key, label in cats[i:i+2]]
        buttons.append(row)
    if extra:
        buttons.append(extra)
    return InlineKeyboardMarkup(buttons)

def progress_bar(current, target, width=10):
    pct = min(current / target * 100, 100) if target > 0 else 0
    filled = int(pct / (100 / width))
    return "█" * filled + "░" * (width - filled), pct

# ─── /start ───────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db.upsert_user(user.id, user.username or "", user.first_name or "")
    await update.message.reply_text(
        f"👋 Xin chào <b>{user.first_name}</b>!\n\n"
        "🤖 <b>Bot Quản Lý Chi Tiêu v2.0</b>\n\n"
        "📌 <b>Chi tiêu &amp; Thu nhập:</b>\n"
        "• /them — Thêm chi tiêu\n"
        "• /thunhap — Thêm thu nhập\n"
        "• /nhanh — Nhập nhanh (VD: <code>50000 bún bò</code>)\n\n"
        "📊 <b>Báo cáo:</b>\n"
        "• /tomtat — Tóm tắt tháng\n"
        "• /lichsu — Lịch sử giao dịch\n"
        "• /thongke — Thống kê chi tiết\n\n"
        "💰 <b>Ngân sách &amp; Tiết kiệm:</b>\n"
        "• /nganquy — Đặt ngân sách\n"
        "• /nganquy_xem — Xem ngân sách\n"
        "• /tietkiem — Thêm tiết kiệm\n"
        "• /mucTieu — Quản lý mục tiêu\n\n"
        "🔁 <b>Tự động:</b>\n"
        "• /dinhky — Chi tiêu định kỳ\n\n"
        "⚙️ <b>Cài đặt:</b>\n"
        "• /caidat — Thông báo &amp; cài đặt\n"
        "• /xoa — Xóa giao dịch\n"
        "• /xuatfile — Xuất CSV\n\n"
        "💡 <b>Tip:</b> Nhắn thẳng <code>50000 cà phê</code> để ghi nhanh!",
        parse_mode="HTML"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)

# ─── Quick Add (nhắn thẳng số tiền + mô tả) ──────────────────────────────────

async def quick_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    settings = db.get_user_settings(user.id)
    if not settings or not settings["quick_add"]:
        return

    text = update.message.text.strip()
    parts = text.split(None, 1)
    if not parts:
        return

    raw = parts[0].replace(",", "").replace(".", "")
    try:
        amount = float(raw)
        if amount <= 0 or amount > 1_000_000_000:
            return
    except ValueError:
        return

    desc = parts[1] if len(parts) > 1 else None
    tx_id = db.add_transaction(user.id, "expense", amount, "other", desc)

    # Kiểm tra cảnh báo ngân sách
    now = datetime.now()
    alerts = db.get_over_budget_categories(user.id, now.month, now.year, threshold=0.8)
    alert_text = ""
    for a in alerts:
        if a["category"] == "other":
            bar, pct = progress_bar(a["spent"], a["budget"])
            status = "🔴 Vượt" if pct >= 100 else "🟡 Gần hết"
            alert_text += f"\n⚠️ {status} ngân sách {EXPENSE_CATEGORIES.get(a['category'], a['category'])}: {pct:.0f}%"

    desc_text = f" — {desc}" if desc else ""
    await update.message.reply_text(
        f"⚡ <b>Ghi nhanh #{tx_id}</b>\n"
        f"💸 <b>{fmt(amount)}</b>{desc_text}\n"
        f"📂 Danh mục: 📦 Khác{alert_text}\n\n"
        "Dùng /them để chọn danh mục cụ thể.",
        parse_mode="HTML"
    )

# ─── /nhanh ───────────────────────────────────────────────────────────────────

async def quick_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "⚡ <b>Nhập nhanh</b>\n\n"
        "Nhắn trực tiếp vào chat theo định dạng:\n"
        "<code>số_tiền mô_tả</code>\n\n"
        "Ví dụ:\n"
        "• <code>50000 bún bò</code>\n"
        "• <code>200000 đổ xăng</code>\n"
        "• <code>1500000 tiền điện</code>\n\n"
        "Sẽ tự động ghi vào danh mục 📦 Khác.\n"
        "Dùng /them để chọn danh mục cụ thể.",
        parse_mode="HTML"
    )

# ─── /them ────────────────────────────────────────────────────────────────────

async def add_expense(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["tx_type"] = "expense"
    await update.message.reply_text(
        "💸 <b>Thêm chi tiêu mới</b>\n\nChọn danh mục:",
        reply_markup=get_category_keyboard("cat_"),
        parse_mode="HTML"
    )
    return CATEGORY

async def handle_category_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    cat_key = query.data.replace("cat_", "")
    context.user_data["category"] = cat_key
    cat_label = EXPENSE_CATEGORIES.get(cat_key, cat_key)
    await query.edit_message_text(
        f"✅ Danh mục: <b>{cat_label}</b>\n\n💰 Nhập số tiền (VD: 50000):",
        parse_mode="HTML"
    )
    return AMOUNT

# ─── /thunhap ─────────────────────────────────────────────────────────────────

async def add_income(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["tx_type"] = "income"
    context.user_data["category"] = "income"
    await update.message.reply_text(
        "💰 <b>Thêm thu nhập</b>\n\nNhập số tiền (VD: 5000000):",
        parse_mode="HTML"
    )
    return AMOUNT

async def handle_amount_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().replace(",", "").replace(".", "")
    try:
        amount = float(text)
        if amount <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Số tiền không hợp lệ. Nhập lại (VD: 50000):")
        return AMOUNT

    context.user_data["amount"] = amount
    await update.message.reply_text(
        f"✅ Số tiền: <b>{fmt(amount)}</b>\n\n📝 Nhập mô tả (hoặc - để bỏ qua):",
        parse_mode="HTML"
    )
    return DESCRIPTION

async def handle_description_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    desc = update.message.text.strip()
    if desc == "-":
        desc = None

    tx_type = context.user_data.get("tx_type", "expense")
    amount = context.user_data["amount"]
    category = context.user_data.get("category")

    tx_id = db.add_transaction(user.id, tx_type, amount, category, desc)

    if tx_type == "expense":
        cat_label = EXPENSE_CATEGORIES.get(category, category)
        icon, type_label = "💸", "Chi tiêu"
    elif tx_type == "income":
        cat_label, icon, type_label = "Thu nhập", "💰", "Thu nhập"
    else:
        cat_label, icon, type_label = "Tiết kiệm", "🏦", "Tiết kiệm"

    desc_text = f"\n📝 {desc}" if desc else ""

    # Cảnh báo ngân sách nếu là chi tiêu
    alert_text = ""
    if tx_type == "expense":
        now = datetime.now()
        alerts = db.get_over_budget_categories(user.id, now.month, now.year, threshold=0.8)
        for a in alerts:
            if a["category"] == category:
                status = "🔴 Vượt ngân sách" if a["pct"] >= 1 else "🟡 Gần hết ngân sách"
                alert_text = f"\n\n{status} <b>{EXPENSE_CATEGORIES.get(category, category)}</b>: {a['pct']*100:.0f}%"

    await update.message.reply_text(
        f"{icon} <b>{type_label} đã lưu #{tx_id}</b>\n\n"
        f"📂 {cat_label}\n"
        f"💵 <b>{fmt(amount)}</b>"
        f"{desc_text}{alert_text}",
        parse_mode="HTML"
    )
    context.user_data.clear()
    return ConversationHandler.END

# ─── /tomtat ──────────────────────────────────────────────────────────────────

async def view_summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    now = datetime.now()
    s = db.get_monthly_summary(user.id, now.month, now.year)

    lines = [f"📊 <b>Tóm tắt tháng {now.month}/{now.year}</b>\n"]
    lines.append(f"💰 Thu nhập: <b>{fmt(s['total_income'])}</b>")
    lines.append(f"💸 Chi tiêu: <b>{fmt(s['total_expense'])}</b>")
    if s["total_saving"] > 0:
        lines.append(f"🏦 Tiết kiệm: <b>{fmt(s['total_saving'])}</b>")

    if s["expense_by_category"]:
        lines.append("\n<b>Chi theo danh mục:</b>")
        for cat, total in sorted(s["expense_by_category"].items(), key=lambda x: -x[1]):
            label = EXPENSE_CATEGORIES.get(cat, cat)
            pct = total / s["total_expense"] * 100 if s["total_expense"] > 0 else 0
            bar, _ = progress_bar(total, s["total_expense"])
            lines.append(f"{label}\n  <code>{bar}</code> {pct:.0f}% — {fmt(total)}")

    icon = "✅" if s["balance"] >= 0 else "🔴"
    lines.append(f"\n{icon} Số dư: <b>{fmt(s['balance'])}</b>")

    await update.message.reply_text("\n".join(lines), parse_mode="HTML")

# ─── /lichsu ──────────────────────────────────────────────────────────────────

async def view_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    rows = db.get_recent_transactions(user.id, 10)
    if not rows:
        await update.message.reply_text("📭 Chưa có giao dịch nào.")
        return

    lines = ["📋 <b>10 giao dịch gần nhất:</b>\n"]
    for r in rows:
        dt = datetime.fromisoformat(r["created_at"]).strftime("%d/%m %H:%M")
        icon = {"expense": "💸", "income": "💰", "saving": "🏦"}.get(r["type"], "📦")
        cat = EXPENSE_CATEGORIES.get(r["category"], r["category"] or "Thu nhập")
        desc = f" — {r['description']}" if r["description"] else ""
        lines.append(f"{icon} <code>#{r['id']}</code> <b>{fmt(r['amount'])}</b>\n  {cat}{desc}\n  🕐 {dt}")

    await update.message.reply_text("\n\n".join(lines), parse_mode="HTML")

# ─── /nganquy ─────────────────────────────────────────────────────────────────

async def set_budget(update: Update, context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now()
    context.user_data["budget_month"] = now.month
    context.user_data["budget_year"] = now.year
    await update.message.reply_text(
        f"💼 <b>Đặt ngân sách tháng {now.month}/{now.year}</b>\n\nChọn danh mục:",
        reply_markup=get_category_keyboard("bcat_"),
        parse_mode="HTML"
    )
    return BUDGET_CATEGORY

async def handle_budget_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    cat_key = query.data.replace("bcat_", "")
    context.user_data["budget_category"] = cat_key
    await query.edit_message_text(
        f"✅ <b>{EXPENSE_CATEGORIES.get(cat_key, cat_key)}</b>\n\n💰 Nhập ngân sách tối đa:",
        parse_mode="HTML"
    )
    return BUDGET_AMOUNT

async def handle_budget_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text.strip().replace(",", "").replace(".", "")
    try:
        amount = float(text)
        if amount <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Không hợp lệ. Nhập lại:")
        return BUDGET_AMOUNT

    cat = context.user_data["budget_category"]
    month = context.user_data["budget_month"]
    year = context.user_data["budget_year"]
    db.set_budget(user.id, cat, amount, month, year)

    await update.message.reply_text(
        f"✅ Ngân sách <b>{EXPENSE_CATEGORIES.get(cat, cat)}</b>:\n"
        f"💰 <b>{fmt(amount)}</b> / tháng {month}/{year}",
        parse_mode="HTML"
    )
    context.user_data.clear()
    return ConversationHandler.END

async def view_budget(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    now = datetime.now()
    budgets = db.get_budgets(user.id, now.month, now.year)

    if not budgets:
        await update.message.reply_text("📭 Chưa có ngân sách.\nDùng /nganquy để đặt.")
        return

    lines = [f"💼 <b>Ngân sách tháng {now.month}/{now.year}:</b>\n"]
    for b in budgets:
        label = EXPENSE_CATEGORIES.get(b["category"], b["category"])
        bar, pct = progress_bar(b["spent"], b["budget"])
        status = "🔴" if pct >= 90 else ("🟡" if pct >= 70 else "🟢")
        remaining = max(b["budget"] - b["spent"], 0)
        lines.append(
            f"{status} <b>{label}</b>\n"
            f"  <code>{bar}</code> {pct:.0f}%\n"
            f"  Đã chi: {fmt(b['spent'])} / {fmt(b['budget'])}\n"
            f"  Còn lại: {fmt(remaining)}"
        )

    await update.message.reply_text("\n\n".join(lines), parse_mode="HTML")

# ─── /thongke ─────────────────────────────────────────────────────────────────

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("7 ngày", callback_data="period_7"),
         InlineKeyboardButton("30 ngày", callback_data="period_30")],
        [InlineKeyboardButton("90 ngày", callback_data="period_90"),
         InlineKeyboardButton("365 ngày", callback_data="period_365")],
    ]
    await update.message.reply_text(
        "📈 <b>Thống kê</b>\n\nChọn kỳ:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )
    return PERIOD_SELECT

async def handle_period_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    days = int(query.data.replace("period_", ""))
    user = update.effective_user
    stats = db.get_stats(user.id, days)

    total_expense = sum(v["total"] for v in stats["expense"].values())
    total_income = sum(v["total"] for v in stats["income"].values())
    total_saving = sum(v["total"] for v in stats["saving"].values())

    lines = [f"📈 <b>Thống kê {days} ngày qua:</b>\n"]
    if total_income > 0:
        lines.append(f"💰 Tổng thu: <b>{fmt(total_income)}</b>")
    lines.append(f"💸 Tổng chi: <b>{fmt(total_expense)}</b>")
    if total_saving > 0:
        lines.append(f"🏦 Tiết kiệm: <b>{fmt(total_saving)}</b>")

    if stats["expense"]:
        lines.append("\n<b>Chi tiết:</b>")
        for cat, data in sorted(stats["expense"].items(), key=lambda x: -x[1]["total"]):
            label = EXPENSE_CATEGORIES.get(cat, cat)
            lines.append(f"• {label}: <b>{fmt(data['total'])}</b> ({data['count']} lần)")

    balance = total_income - total_expense - total_saving
    lines.append(f"\n{'✅' if balance >= 0 else '🔴'} Số dư: <b>{fmt(balance)}</b>")

    await query.edit_message_text("\n".join(lines), parse_mode="HTML")
    return ConversationHandler.END

# ─── /tietkiem ────────────────────────────────────────────────────────────────

async def add_saving(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    goals = db.get_savings_goals(user.id)

    if not goals:
        await update.message.reply_text(
            "📭 Chưa có mục tiêu tiết kiệm.\nDùng /muctieu để tạo mục tiêu trước!"
        )
        return ConversationHandler.END

    buttons = [[InlineKeyboardButton(f"🎯 {g['name']} ({fmt(g['current'])}/{fmt(g['target'])})",
                callback_data=f"sg_{g['id']}")] for g in goals]
    buttons.append([InlineKeyboardButton("💰 Tiết kiệm chung (không gắn mục tiêu)", callback_data="sg_0")])

    await update.message.reply_text(
        "🏦 <b>Thêm tiết kiệm</b>\n\nChọn mục tiêu:",
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode="HTML"
    )
    return SAVING_GOAL

async def handle_saving_goal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    goal_id = int(query.data.replace("sg_", ""))
    context.user_data["saving_goal_id"] = goal_id
    await query.edit_message_text("💰 Nhập số tiền tiết kiệm:", parse_mode="HTML")
    return SAVING_AMOUNT

async def handle_saving_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text.strip().replace(",", "").replace(".", "")
    try:
        amount = float(text)
        if amount <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Không hợp lệ. Nhập lại:")
        return SAVING_AMOUNT

    goal_id = context.user_data.get("saving_goal_id", 0)
    desc = f"[goal:{goal_id}]" if goal_id > 0 else "Tiết kiệm chung"

    tx_id = db.add_transaction(user.id, "saving", amount, "saving", desc)

    msg = f"🏦 <b>Đã lưu tiết kiệm #{tx_id}</b>\n💵 <b>{fmt(amount)}</b>"

    if goal_id > 0:
        goals = db.get_savings_goals(user.id)
        goal = next((g for g in goals if g["id"] == goal_id), None)
        if goal:
            bar, pct = progress_bar(goal["current"], goal["target"])
            msg += f"\n\n🎯 <b>{goal['name']}</b>\n<code>{bar}</code> {pct:.0f}%\n{fmt(goal['current'])} / {fmt(goal['target'])}"
            if pct >= 100:
                msg += "\n\n🎉 <b>Chúc mừng! Đã đạt mục tiêu!</b>"

    await update.message.reply_text(msg, parse_mode="HTML")
    context.user_data.clear()
    return ConversationHandler.END

# ─── /muctieu ─────────────────────────────────────────────────────────────────

async def manage_goals(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    goals = db.get_savings_goals(user.id)

    keyboard = [
        [InlineKeyboardButton("➕ Tạo mục tiêu mới", callback_data="goal_new")],
    ]
    if goals:
        keyboard.append([InlineKeyboardButton("🗑️ Xóa mục tiêu", callback_data="goal_delete")])

    lines = ["🎯 <b>Mục tiêu tiết kiệm</b>\n"]
    if goals:
        for g in goals:
            bar, pct = progress_bar(g["current"], g["target"])
            deadline_text = f"\n  📅 Hạn: {g['deadline']}" if g["deadline"] else ""
            lines.append(
                f"<b>{g['name']}</b>\n"
                f"  <code>{bar}</code> {pct:.0f}%\n"
                f"  {fmt(g['current'])} / {fmt(g['target'])}"
                f"{deadline_text}"
            )
    else:
        lines.append("Chưa có mục tiêu nào.")

    await update.message.reply_text(
        "\n\n".join(lines),
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )
    return GOAL_SELECT

async def handle_goal_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "goal_new":
        await query.edit_message_text("🎯 <b>Tạo mục tiêu mới</b>\n\nNhập tên mục tiêu (VD: Mua xe, Du lịch):", parse_mode="HTML")
        return GOAL_NAME

    if query.data == "goal_delete":
        user = update.effective_user
        goals = db.get_savings_goals(user.id)
        buttons = [[InlineKeyboardButton(f"🗑️ {g['name']}", callback_data=f"gdel_{g['id']}")] for g in goals]
        buttons.append([InlineKeyboardButton("❌ Hủy", callback_data="gdel_cancel")])
        await query.edit_message_text(
            "Chọn mục tiêu muốn xóa:",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        return GOAL_SELECT

    if query.data.startswith("gdel_"):
        if query.data == "gdel_cancel":
            await query.edit_message_text("❌ Đã hủy.")
            return ConversationHandler.END
        user = update.effective_user
        goal_id = int(query.data.replace("gdel_", ""))
        db.delete_savings_goal(goal_id, user.id)
        await query.edit_message_text("✅ Đã xóa mục tiêu.")
        return ConversationHandler.END

    return ConversationHandler.END

async def handle_goal_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["goal_name"] = update.message.text.strip()
    await update.message.reply_text("💰 Nhập số tiền mục tiêu (VD: 50000000):")
    return GOAL_TARGET

async def handle_goal_target(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().replace(",", "").replace(".", "")
    try:
        target = float(text)
        if target <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Không hợp lệ. Nhập lại:")
        return GOAL_TARGET

    context.user_data["goal_target"] = target
    await update.message.reply_text(
        "📅 Nhập deadline (VD: 31/12/2025) hoặc - để bỏ qua:"
    )
    return GOAL_DEADLINE

async def handle_goal_deadline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text.strip()
    deadline = None
    if text != "-":
        try:
            datetime.strptime(text, "%d/%m/%Y")
            deadline = text
        except ValueError:
            await update.message.reply_text("❌ Định dạng sai. Nhập DD/MM/YYYY hoặc -:")
            return GOAL_DEADLINE

    name = context.user_data["goal_name"]
    target = context.user_data["goal_target"]
    gid = db.add_savings_goal(user.id, name, target, deadline)

    deadline_text = f"\n📅 Hạn: {deadline}" if deadline else ""
    await update.message.reply_text(
        f"✅ <b>Đã tạo mục tiêu #{gid}</b>\n\n"
        f"🎯 <b>{name}</b>\n"
        f"💰 Mục tiêu: {fmt(target)}"
        f"{deadline_text}\n\n"
        "Dùng /tietkiem để bắt đầu tiết kiệm!",
        parse_mode="HTML"
    )
    context.user_data.clear()
    return ConversationHandler.END

# ─── /dinhky ──────────────────────────────────────────────────────────────────

async def manage_recurring(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    rows = db.get_recurring(user.id)

    lines = ["🔁 <b>Chi tiêu định kỳ</b>\n"]
    keyboard = [[InlineKeyboardButton("➕ Thêm mới", callback_data="rec_new")]]

    if rows:
        for r in rows:
            icon = "💸" if r["type"] == "expense" else "💰"
            cat = EXPENSE_CATEGORIES.get(r["category"], r["category"] or "")
            lines.append(f"{icon} <b>{r['description']}</b>\n  {cat} — {fmt(r['amount'])}\n  📅 Ngày {r['day_of_month']} hàng tháng")
        keyboard.append([InlineKeyboardButton("🗑️ Xóa định kỳ", callback_data="rec_delete")])
    else:
        lines.append("Chưa có giao dịch định kỳ.")

    await update.message.reply_text(
        "\n\n".join(lines),
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )
    return REC_TYPE

async def handle_rec_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "rec_new":
        keyboard = [
            [InlineKeyboardButton("💸 Chi tiêu", callback_data="rtype_expense"),
             InlineKeyboardButton("💰 Thu nhập", callback_data="rtype_income")]
        ]
        await query.edit_message_text("Loại giao dịch định kỳ:", reply_markup=InlineKeyboardMarkup(keyboard))
        return REC_TYPE

    if query.data == "rec_delete":
        user = update.effective_user
        rows = db.get_recurring(user.id)
        buttons = [[InlineKeyboardButton(f"🗑️ {r['description']} ({fmt(r['amount'])})",
                    callback_data=f"rdel_{r['id']}")] for r in rows]
        buttons.append([InlineKeyboardButton("❌ Hủy", callback_data="rdel_cancel")])
        await query.edit_message_text("Chọn định kỳ muốn xóa:", reply_markup=InlineKeyboardMarkup(buttons))
        return REC_TYPE

    if query.data.startswith("rdel_"):
        if query.data == "rdel_cancel":
            await query.edit_message_text("❌ Đã hủy.")
            return ConversationHandler.END
        user = update.effective_user
        rid = int(query.data.replace("rdel_", ""))
        db.delete_recurring(rid, user.id)
        await query.edit_message_text("✅ Đã xóa giao dịch định kỳ.")
        return ConversationHandler.END

    if query.data.startswith("rtype_"):
        rtype = query.data.replace("rtype_", "")
        context.user_data["rec_type"] = rtype
        await query.edit_message_text(
            "Chọn danh mục:",
            reply_markup=get_category_keyboard("rcat_")
        )
        return REC_CATEGORY

    if query.data.startswith("rcat_"):
        cat = query.data.replace("rcat_", "")
        context.user_data["rec_category"] = cat
        await query.edit_message_text(f"✅ {EXPENSE_CATEGORIES.get(cat, cat)}\n\nNhập số tiền:")
        return REC_AMOUNT

    return ConversationHandler.END

async def handle_rec_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().replace(",", "").replace(".", "")
    try:
        amount = float(text)
        if amount <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Không hợp lệ. Nhập lại:")
        return REC_AMOUNT
    context.user_data["rec_amount"] = amount
    await update.message.reply_text("📝 Nhập tên/mô tả (VD: Tiền thuê nhà, Tiền điện):")
    return REC_DESC

async def handle_rec_desc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["rec_desc"] = update.message.text.strip()
    await update.message.reply_text("📅 Ghi nhận vào ngày mấy hàng tháng? (1-28):")
    return REC_DAY

async def handle_rec_day(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    try:
        day = int(update.message.text.strip())
        if not 1 <= day <= 28:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Nhập số từ 1-28:")
        return REC_DAY

    rtype = context.user_data["rec_type"]
    category = context.user_data.get("rec_category", "other")
    amount = context.user_data["rec_amount"]
    desc = context.user_data["rec_desc"]

    rid = db.add_recurring(user.id, rtype, category, amount, desc, day)
    icon = "💸" if rtype == "expense" else "💰"

    await update.message.reply_text(
        f"✅ <b>Đã thêm định kỳ #{rid}</b>\n\n"
        f"{icon} <b>{desc}</b>\n"
        f"💵 {fmt(amount)} — ngày {day} hàng tháng",
        parse_mode="HTML"
    )
    context.user_data.clear()
    return ConversationHandler.END

# ─── /caidat ──────────────────────────────────────────────────────────────────

async def settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    s = db.get_user_settings(user.id)

    daily = "✅" if s and s["daily_notify"] else "❌"
    weekly = "✅" if s and s["weekly_notify"] else "❌"
    monthly = "✅" if s and s["monthly_notify"] else "❌"
    budget_alert = "✅" if s and s["budget_alert"] else "❌"
    quick = "✅" if s and s["quick_add"] else "❌"
    hour = s["daily_notify_hour"] if s else 21

    keyboard = [
        [InlineKeyboardButton(f"{daily} Thông báo hàng ngày ({hour}:00)", callback_data="set_daily")],
        [InlineKeyboardButton(f"{weekly} Báo cáo hàng tuần (thứ 2)", callback_data="set_weekly")],
        [InlineKeyboardButton(f"{monthly} Tổng kết hàng tháng", callback_data="set_monthly")],
        [InlineKeyboardButton(f"{budget_alert} Cảnh báo vượt ngân sách", callback_data="set_budget_alert")],
        [InlineKeyboardButton(f"{quick} Nhập nhanh (gõ thẳng số tiền)", callback_data="set_quick")],
    ]

    await update.message.reply_text(
        "⚙️ <b>Cài đặt thông báo</b>\n\nBấm để bật/tắt:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )
    return SETTINGS_SELECT

async def handle_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = update.effective_user
    s = db.get_user_settings(user.id)

    key_map = {
        "set_daily": "daily_notify",
        "set_weekly": "weekly_notify",
        "set_monthly": "monthly_notify",
        "set_budget_alert": "budget_alert",
        "set_quick": "quick_add",
    }

    if query.data in key_map:
        db_key = key_map[query.data]
        current = s[db_key] if s else 0
        db.update_setting(user.id, db_key, 0 if current else 1)

    # Refresh
    s = db.get_user_settings(user.id)
    daily = "✅" if s and s["daily_notify"] else "❌"
    weekly = "✅" if s and s["weekly_notify"] else "❌"
    monthly = "✅" if s and s["monthly_notify"] else "❌"
    budget_alert = "✅" if s and s["budget_alert"] else "❌"
    quick = "✅" if s and s["quick_add"] else "❌"
    hour = s["daily_notify_hour"] if s else 21

    keyboard = [
        [InlineKeyboardButton(f"{daily} Thông báo hàng ngày ({hour}:00)", callback_data="set_daily")],
        [InlineKeyboardButton(f"{weekly} Báo cáo hàng tuần (thứ 2)", callback_data="set_weekly")],
        [InlineKeyboardButton(f"{monthly} Tổng kết hàng tháng", callback_data="set_monthly")],
        [InlineKeyboardButton(f"{budget_alert} Cảnh báo vượt ngân sách", callback_data="set_budget_alert")],
        [InlineKeyboardButton(f"{quick} Nhập nhanh (gõ thẳng số tiền)", callback_data="set_quick")],
    ]

    await query.edit_message_text(
        "⚙️ <b>Cài đặt thông báo</b>\n\nBấm để bật/tắt:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )
    return SETTINGS_SELECT

# ─── /xoa ─────────────────────────────────────────────────────────────────────

async def delete_expense(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    rows = db.get_recent_transactions(user.id, 8)
    if not rows:
        await update.message.reply_text("📭 Không có giao dịch nào.")
        return ConversationHandler.END

    buttons = []
    for r in rows:
        dt = datetime.fromisoformat(r["created_at"]).strftime("%d/%m")
        icon = {"expense": "💸", "income": "💰", "saving": "🏦"}.get(r["type"], "📦")
        label = f"{icon} #{r['id']} {fmt(r['amount'])} ({dt})"
        buttons.append([InlineKeyboardButton(label, callback_data=f"del_{r['id']}")])
    buttons.append([InlineKeyboardButton("❌ Hủy", callback_data="del_cancel")])

    await update.message.reply_text(
        "🗑️ <b>Chọn giao dịch muốn xóa:</b>",
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode="HTML"
    )
    return DELETE_SELECT

async def handle_delete_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "del_cancel":
        await query.edit_message_text("❌ Đã hủy.")
        return ConversationHandler.END

    tx_id = int(query.data.replace("del_", ""))
    success = db.delete_transaction(tx_id, update.effective_user.id)
    if success:
        await query.edit_message_text(f"✅ Đã xóa giao dịch <code>#{tx_id}</code>.", parse_mode="HTML")
    else:
        await query.edit_message_text("❌ Không tìm thấy.")
    return ConversationHandler.END

# ─── /xuatfile ────────────────────────────────────────────────────────────────

async def export_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    rows = db.get_all_transactions_csv(user.id)
    if not rows:
        await update.message.reply_text("📭 Chưa có dữ liệu.")
        return

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Loại", "Danh mục", "Số tiền (VND)", "Mô tả", "Thời gian"])
    for r in rows:
        cat = EXPENSE_CATEGORIES.get(r["category"], r["category"] or "")
        type_map = {"expense": "Chi tiêu", "income": "Thu nhập", "saving": "Tiết kiệm"}
        writer.writerow([r["id"], type_map.get(r["type"], r["type"]), cat, r["amount"], r["description"] or "", r["created_at"]])

    output.seek(0)
    filename = f"chi_tieu_{user.id}_{datetime.now().strftime('%Y%m%d')}.csv"
    await update.message.reply_document(
        document=output.getvalue().encode("utf-8-sig"),
        filename=filename,
        caption=f"📊 Xuất {len(rows)} giao dịch thành công!"
    )

# ─── /huy ─────────────────────────────────────────────────────────────────────

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("❌ Đã hủy thao tác.")
    return ConversationHandler.END

# ─── /no (Quản lý nợ) ─────────────────────────────────────────────────────────

DEBT_TYPE, DEBT_PERSON, DEBT_AMOUNT, DEBT_DESC, DEBT_DUE, DEBT_ACTION = 20, 21, 22, 23, 24, 25

async def manage_debt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    summary = db.get_debt_summary(user.id)

    owe = summary["owe"]
    lend = summary["lend"]

    lines = ["💳 <b>Quản lý nợ</b>\n"]
    lines.append(f"🔴 Tôi đang nợ: <b>{fmt(owe['total'])}</b> ({owe['count']} khoản)")
    lines.append(f"🟢 Người khác nợ tôi: <b>{fmt(lend['total'])}</b> ({lend['count']} khoản)")

    net = lend["total"] - owe["total"]
    if net >= 0:
        lines.append(f"\n✅ Thực tế đang được nợ: <b>{fmt(net)}</b>")
    else:
        lines.append(f"\n🔴 Thực tế đang nợ ròng: <b>{fmt(abs(net))}</b>")

    keyboard = [
        [InlineKeyboardButton("🔴 Tôi vay/nợ người khác", callback_data="debt_owe"),
         InlineKeyboardButton("🟢 Cho người khác vay", callback_data="debt_lend")],
        [InlineKeyboardButton("📋 Xem danh sách nợ", callback_data="debt_list"),
         InlineKeyboardButton("✅ Đánh dấu đã trả", callback_data="debt_paid")],
        [InlineKeyboardButton("🕐 Lịch sử đã trả", callback_data="debt_history")],
    ]

    await update.message.reply_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )
    return DEBT_ACTION

async def handle_debt_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = update.effective_user

    if query.data in ("debt_owe", "debt_lend"):
        dtype = "owe" if query.data == "debt_owe" else "lend"
        context.user_data["debt_type"] = dtype
        label = "vay/nợ" if dtype == "owe" else "cho vay"
        await query.edit_message_text(
            f"👤 Nhập tên người bạn <b>{label}</b>:",
            parse_mode="HTML"
        )
        return DEBT_PERSON

    if query.data == "debt_list":
        debts = db.get_debts(user.id, paid=0)
        if not debts:
            await query.edit_message_text("📭 Không có khoản nợ nào đang mở.")
            return ConversationHandler.END

        lines = ["📋 <b>Danh sách nợ hiện tại:</b>\n"]
        for d in debts:
            icon = "🔴" if d["type"] == "owe" else "🟢"
            action = "Nợ" if d["type"] == "owe" else "Cho vay"
            due = f" | Hạn: {d['due_date']}" if d["due_date"] else ""
            desc = f"\n  📝 {d['description']}" if d["description"] else ""
            lines.append(
                f"{icon} <code>#{d['id']}</code> {action} <b>{d['person']}</b>\n"
                f"  💵 {fmt(d['amount'])}{due}{desc}"
            )

        await query.edit_message_text("\n\n".join(lines), parse_mode="HTML")
        return ConversationHandler.END

    if query.data == "debt_paid":
        debts = db.get_debts(user.id, paid=0)
        if not debts:
            await query.edit_message_text("📭 Không có khoản nợ nào cần đánh dấu.")
            return ConversationHandler.END

        buttons = []
        for d in debts:
            icon = "🔴" if d["type"] == "owe" else "🟢"
            label = f"{icon} #{d['id']} {d['person']} — {fmt(d['amount'])}"
            buttons.append([InlineKeyboardButton(label, callback_data=f"dpaid_{d['id']}")])
        buttons.append([InlineKeyboardButton("❌ Hủy", callback_data="dpaid_cancel")])

        await query.edit_message_text(
            "✅ <b>Chọn khoản đã thanh toán:</b>",
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode="HTML"
        )
        return DEBT_ACTION

    if query.data.startswith("dpaid_"):
        if query.data == "dpaid_cancel":
            await query.edit_message_text("❌ Đã hủy.")
            return ConversationHandler.END
        debt_id = int(query.data.replace("dpaid_", ""))
        success = db.mark_debt_paid(debt_id, user.id)
        if success:
            await query.edit_message_text(f"✅ Đã đánh dấu khoản <code>#{debt_id}</code> là <b>đã trả</b>! 🎉", parse_mode="HTML")
        else:
            await query.edit_message_text("❌ Không tìm thấy khoản nợ.")
        return ConversationHandler.END

    if query.data == "debt_history":
        debts = db.get_debts(user.id, paid=1)
        if not debts:
            await query.edit_message_text("📭 Chưa có khoản nợ nào đã thanh toán.")
            return ConversationHandler.END

        lines = ["🕐 <b>Lịch sử đã trả:</b>\n"]
        for d in debts[:10]:
            icon = "🔴" if d["type"] == "owe" else "🟢"
            paid_at = datetime.fromisoformat(d["paid_at"]).strftime("%d/%m/%Y") if d["paid_at"] else ""
            lines.append(
                f"{icon} {d['person']} — {fmt(d['amount'])}\n"
                f"  ✅ Trả ngày: {paid_at}"
            )

        await query.edit_message_text("\n\n".join(lines), parse_mode="HTML")
        return ConversationHandler.END

    return ConversationHandler.END

async def handle_debt_person(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["debt_person"] = update.message.text.strip()
    await update.message.reply_text("💰 Nhập số tiền (VD: 500000):")
    return DEBT_AMOUNT

async def handle_debt_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().replace(",", "").replace(".", "")
    try:
        amount = float(text)
        if amount <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Không hợp lệ. Nhập lại:")
        return DEBT_AMOUNT
    context.user_data["debt_amount"] = amount
    await update.message.reply_text("📝 Nhập ghi chú (hoặc - để bỏ qua):")
    return DEBT_DESC

async def handle_debt_desc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    desc = update.message.text.strip()
    context.user_data["debt_desc"] = None if desc == "-" else desc
    await update.message.reply_text("📅 Nhập hạn trả (DD/MM/YYYY) hoặc - để bỏ qua:")
    return DEBT_DUE

async def handle_debt_due(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text.strip()
    due_date = None
    if text != "-":
        try:
            datetime.strptime(text, "%d/%m/%Y")
            due_date = text
        except ValueError:
            await update.message.reply_text("❌ Định dạng sai. Nhập DD/MM/YYYY hoặc -:")
            return DEBT_DUE

    dtype = context.user_data["debt_type"]
    person = context.user_data["debt_person"]
    amount = context.user_data["debt_amount"]
    desc = context.user_data.get("debt_desc")

    did = db.add_debt(user.id, dtype, person, amount, desc, due_date)

    icon = "🔴" if dtype == "owe" else "🟢"
    action = "Nợ" if dtype == "owe" else "Cho vay"
    due_text = f"\n📅 Hạn trả: {due_date}" if due_date else ""
    desc_text = f"\n📝 {desc}" if desc else ""

    await update.message.reply_text(
        f"{icon} <b>{action} đã lưu #{did}</b>\n\n"
        f"👤 {person}\n"
        f"💵 <b>{fmt(amount)}</b>"
        f"{desc_text}{due_text}\n\n"
        "Dùng /no để xem tổng quan.",
        parse_mode="HTML"
    )
    context.user_data.clear()
    return ConversationHandler.END
