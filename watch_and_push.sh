#!/bin/bash

# Thư mục cần theo dõi (là thư mục hiện tại)
TARGET_DIR=$(pwd)

echo "👀 Đang theo dõi thay đổi tại $TARGET_DIR..."

# Sử dụng inotifywait để bắt sự kiện thay đổi file
inotifywait -m -r -e close_write,create,move "$TARGET_DIR" --exclude '\.git' | while read path action file; do
    # Loại bỏ các file tạm hoặc file log nếu cần
    if [[ "$file" == *".swp"* || "$file" == *".git"* || "$file" == "autopush.sh" ]]; then
        continue
    fi

    echo "✨ Phát hiện thay đổi tại file: $file ($action)"
    
    # Đợi 1 giây để đảm bảo các thay đổi đã ghi xong hoàn toàn
    sleep 1
    
    ./autopush.sh "auto-push: cập nhật $file"
done
