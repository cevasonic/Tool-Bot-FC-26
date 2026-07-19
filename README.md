# Tool Bot EA FC 26 - SBC & Pack Opener

Dự án này là công cụ tự động hóa làm SBC (Squad Building Challenges) và mở Pack trên EA FC Ultimate Team Web App, tích hợp công cụ PaleTools sử dụng thư viện Playwright (Python).

---

## 🚀 Hướng dẫn cài đặt và sử dụng trên PC mới

Để chạy dự án này trên máy tính khác (PC mới) của bạn, hãy làm theo các bước dưới đây:

### 1. Yêu cầu hệ thống
- Đã cài đặt **Python 3.10+** (nhớ tick chọn "Add Python to PATH" khi cài đặt).
- Đã cài đặt trình duyệt **Google Chrome**.
- Đã cài đặt **Git**.

### 2. Clone dự án về máy PC mới
Mở Terminal hoặc Command Prompt (CMD) và chạy lệnh sau:
```bash
git clone https://github.com/cevasonic/Tool-Bot-FC-26.git
cd Tool-Bot-FC-26
```

### 3. Cài đặt các thư viện cần thiết
Cài đặt thư viện Python từ file `requirements.txt`:
```bash
pip install -r .agents/skills/fc_sbc_bot/requirements.txt
```

Sau đó cài đặt các browser driver của Playwright:
```bash
playwright install chromium
```

### 4. Cấu hình dự án
1. Tạo file cấu hình cá nhân `config.json` bằng cách copy từ file mẫu `config.json.example`:
   - **Trên Windows (CMD):**
     ```cmd
     copy .agents\skills\fc_sbc_bot\config.json.example .agents\skills\fc_sbc_bot\config.json
     ```
   - **Trên macOS / Linux (Terminal) hoặc Windows (Git Bash):**
     ```bash
     cp .agents/skills/fc_sbc_bot/config.json.example .agents/skills/fc_sbc_bot/config.json
     ```
2. Mở file `.agents/skills/fc_sbc_bot/config.json` lên và chỉnh sửa:
   - Các SBC mong muốn làm tự động tại mục `target_sbcs`.
   - Các Pack muốn mở tại mục `target_packs`.
   - Token Telegram và Chat ID của bạn tại mục `telegram` (nếu muốn gửi thông báo về điện thoại khi hoàn thành hoặc lỗi).

### 5. Khởi chạy Bot
Chạy script chính bằng Python:
```bash
python .agents/skills/fc_sbc_bot/main.py
```

### 💡 Quy trình hoạt động của Bot:
1. Trình duyệt Chrome sẽ tự động được mở ra và truy cập vào trang EA Sports FC Ultimate Team Web App.
2. **Nếu là lần đầu chạy:** Hãy thực hiện đăng nhập thủ công vào tài khoản EA của bạn, vượt qua xác thực bảo mật 2 lớp (2FA) nếu có. Trình duyệt sẽ lưu lại phiên đăng nhập của bạn vào thư mục `chrome_profile` (thư mục này đã được đưa vào `.gitignore` để không bị lộ lên GitHub).
3. Sau khi đã đăng nhập thành công và nhìn thấy màn hình trang chủ Web App, hãy quay lại cửa sổ Terminal đang chạy bot và nhấn phím **Enter** để kích hoạt bot chạy tự động.
4. Bot sẽ tự động nhúng PaleTools, thực hiện giải các SBC bạn đã cấu hình và tự động mở pack.
