---
name: fc_sbc_bot
description: Tự động hóa làm SBC và mở Pack trên EA FC UT Web App tích hợp PaleTools sử dụng Playwright Python
---
# Skill Tự động hóa làm SBC và mở Pack trên EA FC UT Web App

> [!IMPORTANT]
> **QUY ĐỊNH VẬN HÀNH BẮT BUỘC ĐỐI VỚI AI AGENT:**
> - Việc chạy skill phải được tự động kích hoạt hoàn toàn. **TUYỆT ĐỐI KHÔNG BẮT NGƯỜI DÙNG PHẢI TỰ CHẠY LỆNH** hay các file .bat.
> - Tất cả các thao tác phải được chạy trực quan trên trình duyệt Google Chrome hiển thị giao diện (`headless=False`). **NGHIÊM CẤM CHẠY NGẦM (HEADLESS)**.
> - **HƯỚNG DẪN HIỂN THỊ CỬA SỔ CHROME TRÊN WINDOWS:** Khi chạy lệnh trực tiếp từ background shell của IDE, Windows sẽ tự động chạy ẩn Chrome. Để Chrome hiển thị trực quan trên màn hình người dùng, AI Agent **PHẢI** tạo một Scheduled Task tạm thời chạy ở chế độ tương tác (Interactive) rồi kích hoạt nó bằng các lệnh sau:
>   ```powershell
>   # 1. Tạo task tạm thời với đường dẫn batch file được bao trong dấu nháy kép escape
>   cmd.exe /c 'schtasks /create /tn "SBCBotTask" /tr "\"d:\Lap Trinh\FC 26 Tool\.agents\skills\fc_sbc_bot\run_bot_interactive.bat\"" /sc once /sd 01/01/2099 /st 00:00 /it /f'
>   # 2. Khởi chạy task ngay lập tức trong session của người dùng
>   schtasks /run /tn "SBCBotTask"
>   # 3. Xóa task tạm thời
>   schtasks /delete /tn "SBCBotTask" /f
>   ```

Skill này tự động hóa việc hoàn thành các SBC yêu thích và mở pack phần thưởng trực tiếp trên EA Sports FC Ultimate Team Web App thông qua Playwright và PaleTools.

14: ## Hướng dẫn sử dụng:
15: 1. Đảm bảo bạn đã cài đặt các thư viện cần thiết (`pip install -r requirements.txt`).
16: 2. Sao chép đoạn mã Javascript của Bookmarklet PaleTools và dán vào tệp `resources/paletools.txt` (hoặc `resources/paletools.js`).
17: 3. Cập nhật các SBC cần làm, Pack cần mở, Token Telegram (nếu cần nhận cảnh báo) trong tệp `config.json`.
18: 4. Khởi chạy bot bằng lệnh `python main.py`.
19: 5. Trình duyệt Chrome sẽ tự động mở trang EA Web App. Hãy tự đăng nhập và xác thực 2FA.
20: 6. Sau khi đăng nhập thành công vào giao diện chính (Dashboard), bot sẽ tự động nhận diện và kích hoạt quy trình chạy tự động mà không cần can thiệp thêm từ Terminal.
