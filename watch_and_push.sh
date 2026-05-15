#!/bin/bash

TARGET_DIR=$(pwd)
DB_SOURCE="/var/lib/docker/volumes/expense-bot-v2_expense_data/_data/expenses.db"
DB_DEST="$TARGET_DIR/expenses.db"

echo "👀 Đang theo dõi thay đổi tại $TARGET_DIR..."
echo "🗄️ Đang theo dõi database tại $DB_SOURCE..."

# Theo dõi code thay đổi
inotifywait -m -r -e close_write,create,move "$TARGET_DIR" --exclude '\.git' | while read path action file; do
    if [[ "$file" == *".swp"* || "$file" == *".git"* || "$file" == "autopush.sh" || "$file" == "watch.log" ]]; then
        continue
    fi
    echo "✨ Code thay đổi: $file ($action)"
    sleep 1
    ./autopush.sh "auto-push: cập nhật $file"
done &

# Theo dõi database thay đổi (chạy song song)
inotifywait -m -e close_write,modify "$DB_SOURCE" | while read path action file; do
    echo "🗄️ Database thay đổi, đang backup..."
    sleep 2  # Đợi bot ghi xong
    sudo cp "$DB_SOURCE" "$DB_DEST"
    cd "$TARGET_DIR"
    ./autopush.sh "auto-backup: expenses.db $(date '+%Y-%m-%d %H:%M:%S')"
done &

wait
