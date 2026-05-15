#!/bin/bash

TARGET_DIR=$(pwd)
DB_SOURCE="/var/lib/docker/volumes/expense-bot-v2_expense_data/_data/expenses.db"
DB_DEST="$TARGET_DIR/expenses.db"

echo "👀 Đang theo dõi thay đổi tại $TARGET_DIR..."
echo "🗄️ Đang theo dõi database tại $DB_SOURCE..."

# Theo dõi code thay đổi
inotifywait -m -r -e close_write,create,move "$TARGET_DIR" --exclude '\.git' | while read path action file; do
    if [[ "$file" == *".swp"* || "$file" == *".git"* || "$file" == "autopush.sh" || "$file" == "watch.log" || "$file" == "expenses.db" ]]; then
        continue
    fi
    echo "✨ Code thay đổi: $file ($action)"
    sleep 1
    ./autopush.sh "auto-push: cập nhật $file"
done &

# Theo dõi database bằng cách poll mỗi 60 giây (tránh permission denied)
LAST_HASH=""
while true; do
    sleep 60
    CURRENT_HASH=$(sudo md5sum "$DB_SOURCE" 2>/dev/null | awk '{print $1}')
    if [[ -n "$CURRENT_HASH" && "$CURRENT_HASH" != "$LAST_HASH" ]]; then
        echo "🗄️ Database thay đổi, đang backup..."
        sudo cp "$DB_SOURCE" "$DB_DEST"
        sudo chown ubuntu:ubuntu "$DB_DEST"
        cd "$TARGET_DIR"
        ./autopush.sh "auto-backup: expenses.db $(date '+%Y-%m-%d %H:%M:%S')"
        LAST_HASH="$CURRENT_HASH"
    fi
done &

wait
