# Nguyên tắc Tối ưu hóa SBC Solve (EA FC UT)

Quy định các hành vi, ràng buộc toán học và thuật toán giải SBC nhằm đảm bảo độ chính xác tối đa, ưu tiên tuyệt đối chiến thuật High-Low và bảo vệ tài nguyên thẻ cận trung của người dùng.

> [!IMPORTANT]
> **TẬP TRUNG CHÍNH:** Solver chỉ tập trung duy nhất vào mục tiêu **Rating trung bình** và **Số lượng cầu thủ (size)**. Bỏ qua hoàn toàn các yêu cầu phụ khác (Rare, TOTW, TOTS) để tăng tối đa tính khả thi và độ linh hoạt của tổ hợp High-Low.

---

## 1. Phân tách và Lựa chọn Bộ giải (Solver Selection)
*   **SBC Rating thấp (min_rating < 87):**
    *   **Ưu tiên 1:** Khớp công thức tĩnh từ cơ sở dữ liệu `rating_combinations.json` (FUT.GG). Chỉ chấp nhận nghiệm database nếu rating thực tế của đội hình giải ra $\le min\_rating + 1$.
    *   **Ưu tiên 2:** Chạy MILP Solver làm fallback nếu database vô nghiệm hoặc bị lãng phí.
*   **SBC Rating cao (min_rating >= 87):**
    *   **Bắt buộc:** Bỏ qua hoàn toàn cơ sở dữ liệu FUT.GG combinations (do database FUT.GG chỉ chứa các công thức phân bổ rating đồng đều gây hao tổn thẻ tầm trung).
    *   **Hành động:** Kích hoạt trực tiếp bộ giải động **MILP Solver** để tính toán động tổ hợp High-Low.

---

## 2. Bộ lọc cứng theo Rating (Strict Rating Filter)
Để đảm bảo không lãng phí các thẻ rating thấp cận dưới ngoài vùng yêu cầu:
*   **Nếu min_rating >= 89:** Cấm tuyệt đối sử dụng các cầu thủ có rating $< 84$.
*   **Nếu min_rating <= 88:** Cấm tuyệt đối sử dụng các cầu thủ có rating $< 80$.

---

## 3. Thiết lập Chi phí ảo High-Low (Virtual Cost Curves)
Chi phí ảo (Virtual Cost) trong `solver.py` bắt buộc phải tuân thủ phân vùng động sau để ép thuật toán MILP chọn đúng chiến thuật High-Low và bảo toàn thẻ cận trung (84-92):

*   **Vùng cận dưới (Low-end dynamic range):**
    *   Nếu `min_rating <= 88`: Khoảng rating `81` đến `83` là cận dưới.
    *   Nếu `min_rating >= 89`: Khoảng rating `84` đến `86` là cận dưới.
*   **Công thức định giá chi phí ảo:**
    *   **Cận trên Storage ($r \ge min\_rating$):** Chi phí ảo rất rẻ, **tăng dần** theo rating: `cost = 10.0 + (r - min_rating) * 2.0`. Giúp ưu tiên lấy các thẻ cận trên thấp trước (ví dụ lấy 90 trước 95) để tránh lãng phí thẻ siêu cao.
    *   **Cận dưới Storage/Club động:** Chi phí ảo cực rẻ (`5` đến `30` điểm) để ưu tiên phối hợp gánh phần thiếu.
    *   **Cận trung (nằm giữa cận dưới và cận trên):** Chi phí ảo cực đắt (lên tới `250` điểm ở Storage và `400+` điểm ở Club) để ngăn cản tuyệt đối việc sử dụng thẻ cận trung.
    *   **Dưới cận dưới động ($r < low\_min$):** Chi phí ảo đắt vừa phải (`200` ở Storage và `350` ở Club) để chỉ dùng làm dự phòng cuối cùng khi hết thẻ cận dưới động.

---

## 4. Khống chế giới hạn trần Rating (Rating Upper Bound Limit)
Để ngăn chặn hoàn toàn việc giải ra rating quá cao gây lãng phí:
*   **Đối với MILP Solver:** Áp dụng ràng buộc giới hạn trên nghiêm ngặt đối với SBC rating cao:
    `Tổng contributions <= (min_rating + 2.5) * sbc_size`.
*   **Đối với Heuristic Solver:** Cấm tuyệt đối chấp nhận bất kỳ nghiệm nào có rating thực tế lớn hơn `min_rating + 1`.
*   Nếu không tìm thấy nghiệm nào thỏa mãn các điều kiện trên, hệ thống báo vô nghiệm thay vì giải sai lệch hoặc lãng phí rating.
