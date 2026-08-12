---
name: fc_sbc_bot
description: Tự động hóa làm SBC và mở Pack trên EA FC UT Web App tích hợp PaleTools sử dụng Playwright Python
---
# Skill Tự động hóa làm SBC và mở Pack trên EA FC UT Web App

> [!IMPORTANT]
> **QUY ĐỊNH VẬN HÀNH BẮT BUỘC ĐỐI VỚI AI AGENT:**
> - Việc chạy skill phải được tự động kích hoạt hoàn toàn. **TUYỆT ĐỐI KHÔNG BẮT NGƯỜI DÙNG PHẢI TỰ CHẠY LỆNH** hay các file .bat.
> - Tất cả các thao tác phải được chạy trực quan trên trình duyệt Google Chrome hiển thị giao diện (`headless=False`). **NGHIÊM CẤM CHẠY NGẦM (HEADLESS)**.

Skill này tự động hóa việc hoàn thành các SBC yêu thích và mở pack phần thưởng trực tiếp trên EA Sports FC Ultimate Team Web App thông qua Playwright và PaleTools.

14: ## Hướng dẫn sử dụng:
15: 1. Đảm bảo bạn đã cài đặt các thư viện cần thiết (`pip install -r requirements.txt`).
16: 2. Sao chép đoạn mã Javascript của Bookmarklet PaleTools và dán vào tệp `resources/paletools.txt` (hoặc `resources/paletools.js`).
17: 3. Cập nhật các SBC cần làm, Pack cần mở, Token Telegram (nếu cần nhận cảnh báo) trong tệp `config.json`.
18: 4. Khởi chạy bot bằng lệnh `python main.py`.
19: 5. Trình duyệt Chrome sẽ tự động mở trang EA Web App. Hãy tự đăng nhập và xác thực 2FA.
20: 6. Sau khi đăng nhập thành công vào giao diện chính (Dashboard), bot sẽ tự động nhận diện và kích hoạt quy trình chạy tự động mà không cần can thiệp thêm từ Terminal.
