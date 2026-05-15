import logging
import os
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ConversationHandler, filters
)
from handlers import (
    start, help_command, add_expense, add_income, quick_add, quick_help,
    view_summary, view_history, set_budget, view_budget, export_data,
    handle_category_selection, handle_amount_input, handle_description_input,
    handle_budget_input, handle_budget_category, handle_delete_selection,
    cancel, stats_command, handle_period_selection, delete_expense,
    add_saving, handle_saving_goal, handle_saving_amount,
    manage_goals, handle_goal_select, handle_goal_name, handle_goal_target, handle_goal_deadline,
    manage_recurring, handle_rec_action, handle_rec_amount, handle_rec_desc, handle_rec_day,
    settings, handle_settings,
    manage_debt, handle_debt_action, handle_debt_person,
    handle_debt_amount, handle_debt_desc, handle_debt_due,
)
from scheduler import (
    send_daily_summary, send_weekly_summary,
    send_monthly_summary, process_recurring
)
from database import init_db

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
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
DEBT_TYPE, DEBT_PERSON, DEBT_AMOUNT, DEBT_DESC, DEBT_DUE, DEBT_ACTION = 20, 21, 22, 23, 24, 25

TIMEOUT = 300

def all_fallbacks():
    return [
        CommandHandler("huy", cancel),
        CommandHandler("them", add_expense),
        CommandHandler("thunhap", add_income),
        CommandHandler("tomtat", view_summary),
        CommandHandler("lichsu", view_history),
        CommandHandler("nganquy", set_budget),
        CommandHandler("nganquy_xem", view_budget),
        CommandHandler("thongke", stats_command),
        CommandHandler("xoa", delete_expense),
        CommandHandler("xuatfile", export_data),
        CommandHandler("tietkiem", add_saving),
        CommandHandler("muctieu", manage_goals),
        CommandHandler("dinhky", manage_recurring),
        CommandHandler("caidat", settings),
        CommandHandler("no", manage_debt),
        CommandHandler("start", start),
        CommandHandler("help", help_command),
    ]

def make_conv(entry_points, states, name):
    return ConversationHandler(
        entry_points=entry_points,
        states=states,
        fallbacks=all_fallbacks(),
        conversation_timeout=TIMEOUT,
        allow_reentry=True,
        name=name,
    )

async def set_commands(application):
    await application.bot.set_my_commands([
        ("them",        "💸 Thêm chi tiêu"),
        ("thunhap",     "💰 Thêm thu nhập"),
        ("nhanh",       "⚡ Hướng dẫn nhập nhanh"),
        ("tomtat",      "📊 Tóm tắt tháng"),
        ("lichsu",      "📋 Lịch sử giao dịch"),
        ("thongke",     "📈 Thống kê chi tiết"),
        ("nganquy",     "💼 Đặt ngân sách"),
        ("nganquy_xem", "👀 Xem ngân sách"),
        ("tietkiem",    "🏦 Thêm tiết kiệm"),
        ("muctieu",     "🎯 Mục tiêu tiết kiệm"),
        ("dinhky",      "🔁 Chi tiêu định kỳ"),
        ("caidat",      "⚙️ Cài đặt thông báo"),
        ("xoa",         "🗑️ Xóa giao dịch"),
        ("xuatfile",    "📁 Xuất file CSV"),
        ("no",          "💳 Quản lý nợ"),
        ("help",        "❓ Trợ giúp"),
    ])

def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN not set!")

    init_db()

    app = Application.builder().token(token).post_init(set_commands).build()

    # ── Conversations ──────────────────────────────────────────────────────────

    add_expense_conv = make_conv(
        entry_points=[CommandHandler("them", add_expense)],
        states={
            CATEGORY: [CallbackQueryHandler(handle_category_selection, pattern="^cat_")],
            AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_amount_input)],
            DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_description_input)],
        },
        name="expense",
    )

    add_income_conv = make_conv(
        entry_points=[CommandHandler("thunhap", add_income)],
        states={
            AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_amount_input)],
            DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_description_input)],
        },
        name="income",
    )

    budget_conv = make_conv(
        entry_points=[CommandHandler("nganquy", set_budget)],
        states={
            BUDGET_CATEGORY: [CallbackQueryHandler(handle_budget_category, pattern="^bcat_")],
            BUDGET_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_budget_input)],
        },
        name="budget",
    )

    stats_conv = make_conv(
        entry_points=[CommandHandler("thongke", stats_command)],
        states={
            PERIOD_SELECT: [CallbackQueryHandler(handle_period_selection, pattern="^period_")],
        },
        name="stats",
    )

    delete_conv = make_conv(
        entry_points=[CommandHandler("xoa", delete_expense)],
        states={
            DELETE_SELECT: [CallbackQueryHandler(handle_delete_selection, pattern="^del_")],
        },
        name="delete",
    )

    saving_conv = make_conv(
        entry_points=[CommandHandler("tietkiem", add_saving)],
        states={
            SAVING_GOAL: [CallbackQueryHandler(handle_saving_goal, pattern="^sg_")],
            SAVING_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_saving_amount)],
        },
        name="saving",
    )

    goal_conv = make_conv(
        entry_points=[CommandHandler("muctieu", manage_goals)],
        states={
            GOAL_SELECT: [CallbackQueryHandler(handle_goal_select, pattern="^goal_|^gdel_")],
            GOAL_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_goal_name)],
            GOAL_TARGET: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_goal_target)],
            GOAL_DEADLINE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_goal_deadline)],
        },
        name="goal",
    )

    recurring_conv = make_conv(
        entry_points=[CommandHandler("dinhky", manage_recurring)],
        states={
            REC_TYPE: [CallbackQueryHandler(handle_rec_action, pattern="^rec_|^rtype_|^rcat_|^rdel_")],
            REC_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_rec_amount)],
            REC_DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_rec_desc)],
            REC_DAY: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_rec_day)],
        },
        name="recurring",
    )

    settings_conv = make_conv(
        entry_points=[CommandHandler("caidat", settings)],
        states={
            SETTINGS_SELECT: [CallbackQueryHandler(handle_settings, pattern="^set_")],
        },
        name="settings",
    )

    # ── Register handlers ──────────────────────────────────────────────────────

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("tomtat", view_summary))
    app.add_handler(CommandHandler("lichsu", view_history))
    app.add_handler(CommandHandler("nganquy_xem", view_budget))
    app.add_handler(CommandHandler("xuatfile", export_data))
    app.add_handler(CommandHandler("nhanh", quick_help))

    app.add_handler(add_expense_conv)
    app.add_handler(add_income_conv)
    app.add_handler(budget_conv)
    app.add_handler(stats_conv)
    app.add_handler(delete_conv)
    app.add_handler(saving_conv)
    app.add_handler(goal_conv)
    app.add_handler(recurring_conv)
    app.add_handler(settings_conv)

    debt_conv = make_conv(
        entry_points=[CommandHandler("no", manage_debt)],
        states={
            DEBT_ACTION: [CallbackQueryHandler(handle_debt_action, pattern="^debt_|^dpaid_")],
            DEBT_PERSON: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_debt_person)],
            DEBT_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_debt_amount)],
            DEBT_DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_debt_desc)],
            DEBT_DUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_debt_due)],
        },
        name="debt",
    )
    app.add_handler(debt_conv)

    # Quick add - nhắn thẳng số tiền
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        quick_add
    ))

    # ── Scheduler ─────────────────────────────────────────────────────────────

    job_queue = app.job_queue
    # Kiểm tra định kỳ mỗi giờ
    job_queue.run_repeating(process_recurring, interval=3600, first=10)
    # Thông báo hàng ngày lúc 21:00
    job_queue.run_daily(send_daily_summary, time=__import__('datetime').time(21, 0))
    # Báo cáo tuần mỗi thứ 2 lúc 8:00
    job_queue.run_daily(send_weekly_summary, time=__import__('datetime').time(8, 0))
    # Tổng kết tháng ngày 1 lúc 7:00
    job_queue.run_daily(send_monthly_summary, time=__import__('datetime').time(7, 0))

    logger.info("🤖 Bot v2.0 started!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
