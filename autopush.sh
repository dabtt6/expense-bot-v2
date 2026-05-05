#!/bin/bash
MESSAGE=${1:-"auto sync: $(date '+%Y-%m-%d %H:%M:%S')"}

echo "🚀 Đang bắt đầu đẩy code..."
git add .
git commit -m "$MESSAGE"
git push origin main
echo "✅ Đã đẩy code thành công với message: $MESSAGE"
