---
name: fc_sbc_bot
description: Tự động hóa làm SBC và mở Pack trên EA FC UT Web App tích hợp PaleTools sử dụng Playwright Python
---
# Skill Tự động hóa làm SBC và mở Pack trên EA FC UT Web App

Skill này tự động hóa việc hoàn thành các SBC yêu thích và mở pack phần thưởng trực tiếp trên EA Sports FC Ultimate Team Web App thông qua Playwright và PaleTools.

## Hướng dẫn sử dụng:
1. Đảm bảo bạn đã cài đặt các thư viện cần thiết (`pip install -r requirements.txt`).
2. Copy đoạn mã Javascript của Bookmarklet PaleTools dán hoàn toàn vào tệp `paletools.js`.
3. Cập nhật các SBC cần làm, Pack cần mở, Token Telegram (nếu cần nhận cảnh báo) trong tệp `config.json`.
4. Khởi chạy file `main.py`.
5. Trình duyệt Chrome sẽ tự động mở trang EA Web App. Hãy tự đăng nhập và xác thực 2FA.
6. Sau khi đã vào giao diện Web App thành công, quay lại Terminal và nhấn phím **Enter** để kích hoạt bot chạy tự động.
