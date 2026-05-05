#!/bin/bash
    # Lấy nội dung commit từ tham số truyền vào, nếu không có thì để mặc định
    MESSAGE=${1:-"auto sync: $(date '+%Y-%m-%d %H:%M:%S')"}

    echo "🚀 Đang bắt đầu đẩy code..."
    git add .
    git commit -m "$MESSAGE"
    git push origin main
    echo "✅ Đã đẩy code thành công với message: $MESSAGE"
    ```

3.  **Cấp quyền thực thi cho file:**
    ```bash
    chmod +x autopush.sh
    ```

4.  **Cách sử dụng:**
    *   Mỗi khi sửa code xong, bạn chỉ cần gõ: `./autopush.sh "tên commit của bạn"`
    *   Hoặc chỉ cần gõ: `./autopush.sh` (nó sẽ tự lấy ngày giờ làm tên commit).

---

### Cách 2: Tự động push theo thời gian (Dùng Cronjob)
Nếu bạn muốn máy tự động quét thư mục và push lên GitHub sau mỗi 1 tiếng (hoặc mỗi ngày) mà không cần chạm tay vào:

1.  **Mở trình quản lý tiến trình:**
    
```bash
    crontab -e
    ```

2.  **Thêm dòng này vào cuối file** (ví dụ: tự động push vào lúc 0 giờ mỗi ngày):
    
```bash
    0 0 * * * cd /home/ubuntu/expense-bot-v2 && ./autopush.sh "Auto backup cronjob"
    ```

---

### Cách 3: Tự động hóa "Xịn" với GitHub Actions (CI/CD)
Nếu "auto đẩy" của bạn ý là muốn **tự động deploy** hoặc **tự động build Docker** mỗi khi bạn push code lên GitHub, hãy làm như sau:

1.  Tạo thư mục: `mkdir -p .github/workflows`
2.  Tạo file: `nano .github/workflows/docker-build.yml`
3.  Dán cấu hình này (giả sử bạn muốn check lỗi mỗi khi push):

```yaml
name: CI Check
on: [push]
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Check files
        run: ls -la
