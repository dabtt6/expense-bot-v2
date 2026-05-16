#!/bin/bash
set -e

# Lấy file từ container
docker cp telegram-expense-bot:/app/src/handlers.py /tmp/handlers.py
docker cp telegram-expense-bot:/app/src/bot.py /tmp/bot.py
docker cp telegram-expense-bot:/app/src/database.py /tmp/database.py

# Thêm update_notify_hour vào database.py
cat >> /tmp/database.py << 'PYEOF'

def update_notify_hour(user_id, hour):
    conn = get_connection()
    conn.execute("UPDATE user_settings SET daily_notify_hour=? WHERE user_id=?", (hour, user_id))
    conn.commit()
    conn.close()
PYEOF

# Sửa hàm settings và handle_settings trong handlers.py để thêm nút chọn giờ
# Thêm handler chọn giờ mới
cat >> /tmp/handlers.py << 'PYEOF'

async def handle_set_hour(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Hiển thị bàn phím chọn giờ gửi báo cáo."""
    query = update.callback_query
    await query.answer()

    # Tạo bàn phím 24 giờ, 4 nút mỗi hàng
    buttons = []
    row = []
    for h in range(24):
        row.append(InlineKeyboardButton(f"{h:02d}:00", callback_data=f"sethour_{h}"))
        if len(row) == 4:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton("❌ Hủy", callback_data="sethour_cancel")])

    await query.edit_message_text(
        "🕐 <b>Chọn giờ gửi báo cáo hàng ngày:</b>",
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode="HTML"
    )
    return SETTINGS_SELECT

async def handle_confirm_hour(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lưu giờ được chọn và restart scheduler."""
    query = update.callback_query
    await query.answer()

    if query.data == "sethour_cancel":
        await query.edit_message_text("❌ Đã hủy.")
        return ConversationHandler.END

    hour = int(query.data.replace("sethour_", ""))
    user = update.effective_user
    db.update_notify_hour(user.id, hour)

    await query.edit_message_text(
        f"✅ Đã đặt giờ gửi báo cáo: <b>{hour:02d}:00</b>\n\n"
        "⚠️ Giờ mới sẽ có hiệu lực sau khi bot được restart.\n"
        "Liên hệ admin hoặc dùng lệnh restart nếu cần áp dụng ngay.",
        parse_mode="HTML"
    )
    return ConversationHandler.END
PYEOF

# Sửa handle_settings để thêm nút "Đổi giờ báo cáo"
python3 << 'PYEOF'
with open("/tmp/handlers.py", "r") as f:
    content = f.read()

# Thêm nút đổi giờ vào keyboard trong settings
old = '''    keyboard = [
        [InlineKeyboardButton(f"{daily} Thông báo hàng ngày ({hour}:00)", callback_data="set_daily")],
        [InlineKeyboardButton(f"{weekly} Báo cáo hàng tuần (thứ 2)", callback_data="set_weekly")],
        [InlineKeyboardButton(f"{monthly} Tổng kết hàng tháng", callback_data="set_monthly")],
        [InlineKeyboardButton(f"{budget_alert} Cảnh báo vượt ngân sách", callback_data="set_budget_alert")],
        [InlineKeyboardButton(f"{quick} Nhập nhanh (gõ thẳng số tiền)", callback_data="set_quick")],
    ]

    await update.message.reply_text('''

new = '''    keyboard = [
        [InlineKeyboardButton(f"{daily} Thông báo hàng ngày ({hour:02d}:00)", callback_data="set_daily")],
        [InlineKeyboardButton(f"🕐 Đổi giờ báo cáo (hiện: {hour:02d}:00)", callback_data="set_hour")],
        [InlineKeyboardButton(f"{weekly} Báo cáo hàng tuần (thứ 2)", callback_data="set_weekly")],
        [InlineKeyboardButton(f"{monthly} Tổng kết hàng tháng", callback_data="set_monthly")],
        [InlineKeyboardButton(f"{budget_alert} Cảnh báo vượt ngân sách", callback_data="set_budget_alert")],
        [InlineKeyboardButton(f"{quick} Nhập nhanh (gõ thẳng số tiền)", callback_data="set_quick")],
    ]

    await update.message.reply_text('''

content = content.replace(old, new, 1)

# Sửa keyboard trong handle_settings (lần 2 xuất hiện) cũng tương tự
old2 = '''    keyboard = [
        [InlineKeyboardButton(f"{daily} Thông báo hàng ngày ({hour}:00)", callback_data="set_daily")],
        [InlineKeyboardButton(f"{weekly} Báo cáo hàng tuần (thứ 2)", callback_data="set_weekly")],
        [InlineKeyboardButton(f"{monthly} Tổng kết hàng tháng", callback_data="set_monthly")],
        [InlineKeyboardButton(f"{budget_alert} Cảnh báo vượt ngân sách", callback_data="set_budget_alert")],
        [InlineKeyboardButton(f"{quick} Nhập nhanh (gõ thẳng số tiền)", callback_data="set_quick")],
    ]

    await query.edit_message_text('''

new2 = '''    keyboard = [
        [InlineKeyboardButton(f"{daily} Thông báo hàng ngày ({hour:02d}:00)", callback_data="set_daily")],
        [InlineKeyboardButton(f"🕐 Đổi giờ báo cáo (hiện: {hour:02d}:00)", callback_data="set_hour")],
        [InlineKeyboardButton(f"{weekly} Báo cáo hàng tuần (thứ 2)", callback_data="set_weekly")],
        [InlineKeyboardButton(f"{monthly} Tổng kết hàng tháng", callback_data="set_monthly")],
        [InlineKeyboardButton(f"{budget_alert} Cảnh báo vượt ngân sách", callback_data="set_budget_alert")],
        [InlineKeyboardButton(f"{quick} Nhập nhanh (gõ thẳng số tiền)", callback_data="set_quick")],
    ]

    await query.edit_message_text('''

content = content.replace(old2, new2, 1)

# Thêm xử lý set_hour vào handle_settings
old3 = "    key_map = {"
new3 = """    if query.data == "set_hour":
        await handle_set_hour(update, context)
        return SETTINGS_SELECT

    key_map = {"""
content = content.replace(old3, new3, 1)

with open("/tmp/handlers.py", "w") as f:
    f.write(content)
print("handlers.py updated")
PYEOF

# Thêm callback pattern sethour_ vào settings_conv trong bot.py
sed -i 's/SETTINGS_SELECT: \[CallbackQueryHandler(handle_settings, pattern="\^set_")\]/SETTINGS_SELECT: [CallbackQueryHandler(handle_settings, pattern="^set_"), CallbackQueryHandler(handle_confirm_hour, pattern="^sethour_")]/' /tmp/bot.py

# Thêm import handle_set_hour, handle_confirm_hour
sed -i 's/    settings, handle_settings, daily_budget,/    settings, handle_settings, daily_budget, handle_set_hour, handle_confirm_hour,/' /tmp/bot.py

# Verify syntax
python3 -c "import ast; ast.parse(open('/tmp/handlers.py').read()); print('✅ handlers.py OK')"
python3 -c "import ast; ast.parse(open('/tmp/bot.py').read()); print('✅ bot.py OK')"
python3 -c "import ast; ast.parse(open('/tmp/database.py').read()); print('✅ database.py OK')"

# Copy trở lại container
docker cp /tmp/handlers.py telegram-expense-bot:/app/src/handlers.py
docker cp /tmp/bot.py telegram-expense-bot:/app/src/bot.py
docker cp /tmp/database.py telegram-expense-bot:/app/src/database.py

docker restart telegram-expense-bot
sleep 3
docker logs telegram-expense-bot --tail 5
echo "✅ Xong! Vào /caidat để chọn giờ."
