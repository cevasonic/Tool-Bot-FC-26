# Nguyên tắc Giải SBC Solver Tuần tự (EA FC UT)

Quy định các hành vi, ràng buộc và thuật toán giải SBC tự động dựa trên phương pháp tìm kiếm tham lam tuần tự (greedy swap) nhằm tối ưu hóa việc sử dụng các cầu thủ Untradeable và dọn sạch kho SBC Storage.

---

## 1. Quy trình Giải SBC (SBC Solver Workflow)

Thuật toán giải SBC tiến hành các bước theo trình tự sau:

1.  **Nhận yêu cầu SBC:** Trích xuất rating mục tiêu cần đạt (`target_rating`, ví dụ: `90`) và kích thước đội hình yêu cầu (`sbc_size`, ví dụ: `11`).
2.  **Lọc cầu thủ khả dụng:**
    *   Áp dụng các quy tắc bảo tồn và bảo vệ thẻ (Active Squad, Favorites, Blacklist).
    *   Chỉ chọn các thẻ không thể giao dịch (`untradeable == True`) và không phải thẻ Evolution (`evolution == False`).
    *   Chỉ sử dụng cầu thủ có rating tối thiểu là **82** (rating < 82 bị loại bỏ hoàn toàn).
3.  **Xác định giới hạn rating cao nhất trong Storage:**
    *   Tìm rating lớn nhất của cầu thủ trong **SBC Storage** (`sbc_storage == True`) trong số các thẻ khả dụng, ký hiệu là `max_storage_rating`.
    *   Nếu không có thẻ nào trong SBC Storage, `max_storage_rating` mặc định là rating lớn nhất của toàn bộ thẻ khả dụng trong danh sách đã lọc.
4.  **Khởi tạo đội hình xuất phát:**
    *   Sắp xếp danh sách cầu thủ khả dụng theo thứ tự rating tăng dần. Nếu cùng rating, ưu tiên cầu thủ có `sbc_storage == True` đứng trước.
    *   Lấy ra `sbc_size` (thường là 11) cầu thủ đầu tiên để đưa vào đội hình ban đầu.
5.  **Thuật toán Tăng Rating Tuần tự (Greedy Swap):**
    *   Tính toán rating đội hình dưới dạng số thực (`calculate_sbc_rating_float`).
    *   Nếu rating đội hình ban đầu đã đạt `>= target_rating - 0.5` (cho phép thấp hơn yêu cầu 0.5), thuật toán hoàn tất và trả về kết quả đầy đủ.
    *   Nếu chưa đạt, duyệt tuần tự qua từng vị trí cầu thủ `i` trong đội hình (từ vị trí 1 đến `sbc_size`):
        *   Tại vị trí `i`, liên tục thay thế cầu thủ hiện tại bằng cầu thủ tiếp theo có rating lớn hơn trong pool dự phòng (và phải `<= max_storage_rating`). Ưu tiên chọn cầu thủ có rating thấp nhất lớn hơn rating hiện tại và có `sbc_storage == True`.
        *   Sau mỗi lần thay thế, tính lại rating số thực của đội hình. Nếu đạt `>= target_rating - 0.5`, thuật toán dừng và trả về kết quả thành công.
6.  **Xác định kết quả:**
    *   Nếu sau khi duyệt qua toàn bộ các vị trí mà rating vẫn chưa đạt yêu cầu, thuật toán trả về nghiệm thiếu (Incomplete) với đội hình đã được nâng cấp tối đa.

---

## 2. Bảo tồn và Bảo vệ Cầu thủ (Card Protection Rules)

Cấm tuyệt đối không tự ý sử dụng các cầu thủ nằm trong danh sách bảo vệ của người dùng:
*   Cầu thủ thuộc đội hình đang sử dụng (**Active Squad**).
*   Cầu thủ được đánh dấu yêu thích (**Favorites**).
*   **Cầu thủ Evolution**: Cấm tuyệt đối không sử dụng các thẻ Evolution để giải SBC.
*   Cầu thủ thuộc danh sách đen bị khóa (**Blacklist IDs** trong cấu hình).

---

## 3. Lưu trữ Dữ liệu Debug

*   Ngay khi load xong dữ liệu cầu thủ từ Web App, Solver Manager sẽ ghi dữ liệu vào tệp tin [`club-data.json`](file:///Users/binhnguyenthanh/Documents/FC%20Ultimate/.agents/skills/fc_sbc_solve/Database/club-data.json) đặt trong thư mục `Database/` với định dạng chuẩn tương tự `debug_run.json` nhằm phục vụ việc debug hoặc kiểm tra lại cách giải.
