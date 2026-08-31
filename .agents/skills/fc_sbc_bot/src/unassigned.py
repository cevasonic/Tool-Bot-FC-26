import time
from src.utils import sleep_human_like, wait_for_click_shield
from src.paletools import trigger_bot_pause, check_pause, resume_bot_status
from src.notification import send_telegram_message, process_telegram_updates, get_console_input

def navigate_to_unassigned_screen(page):
    """
    Điều hướng đến màn hình vật phẩm unassigned từ bất kỳ màn hình nào.
    Trả về True nếu màn hình unassigned hiển thị, ngược lại trả về False.
    """
    # 1. Thử click nút "Take Me There" trên dialog cảnh báo nếu có
    try:
        take_me_there_btn = page.locator(".ea-dialog-view button:has-text('Take Me There'), .ea-dialog-view button:has-text('Take me there'), .ea-dialog-view button:has-text('Xử lý ngay')").first
        if take_me_there_btn.count() > 0 and take_me_there_btn.is_visible():
            print("[RPA] Click nút 'Take Me There' trên hộp thoại cảnh báo...")
            take_me_there_btn.click()
            time.sleep(2.5)
            if page.locator(".ut-unassigned-view, .unassigned-view").first.is_visible():
                return True
    except Exception:
        pass

    # 2. Thử click badge unassigned trên thanh top bar nếu hiển thị
    try:
        unassigned_selectors = [
            ".view-navbar-clubinfo-unassigned",
            ".view-navbar-currency-unassigned",
            ".unassigned-badge",
            ".icon-unassigned"
        ]
        for sel in unassigned_selectors:
            el = page.locator(sel).first
            if el.count() > 0 and el.is_visible():
                print(f"[RPA] Click unassigned badge ở top bar ({sel})...")
                el.click()
                time.sleep(2.5)
                if page.locator(".ut-unassigned-view, .unassigned-view").first.is_visible():
                    return True
    except Exception:
        pass

    # 3. Vào tab Store và click thẻ Unassigned Items
    try:
        store_tab = page.locator(".ut-tab-bar-item.icon-store").first
        if store_tab.count() > 0:
            print("[RPA] Click tab Store để tìm unassigned items...")
            store_tab.click()
            time.sleep(2.5)
            
            # Thử click vào thẻ Unassigned Items trên giao diện Store
            unassigned_tile = page.locator(".tile:has-text('Unassigned Items'), .tile:has-text('Vật phẩm chưa phân phối'), .tile:has-text('Unassigned'), .store-tile:has-text('Unassigned Items'), .store-tile:has-text('Vật phẩm chưa phân phối'), .store-tile:has-text('Unassigned')").first
            if unassigned_tile.count() > 0 and unassigned_tile.is_visible():
                print("[RPA] Tìm thấy thẻ Unassigned Items trên giao diện Store. Đang click...")
                unassigned_tile.click()
                time.sleep(2.5)
    except Exception as e:
        print(f"[WARNING] Lỗi khi chuyển sang Store và tìm thẻ unassigned: {e}")

    # Chờ màn hình unassigned hiển thị
    return wait_for_unassigned_screen(page, timeout_ms=8000)

def check_unassigned_badge_and_clear(page, config):
    try:
        # Selector badge unassigned ở top bar
        unassigned_selectors = [
            ".view-navbar-clubinfo-unassigned",
            ".view-navbar-currency-unassigned",
            ".unassigned-badge",
            ".icon-unassigned"
        ]
        
        has_unassigned = False
        target_el = None
        for sel in unassigned_selectors:
            el = page.locator(sel).first
            if el.count() > 0 and el.is_visible():
                text = el.text_content() or ""
                # Lọc lấy số
                digits = "".join([c for c in text if c.isdigit()])
                if digits and int(digits) > 0:
                    has_unassigned = True
                    target_el = el
                    break
                elif not digits: # Nếu hiển thị icon unassigned đơn thuần
                    has_unassigned = True
                    target_el = el
                    break
                    
        if has_unassigned:
            print(f"[WARNING] Phát hiện có vật phẩm unassigned chưa xử lý trên top bar. Đang di chuyển để dọn dẹp...")
            navigate_to_unassigned_screen(page)
            
            handle_unassigned_items(page, config)
            print("[OK] Đã dọn dẹp xong unassigned. Quay lại menu chính...")
            page.keyboard.press("Escape")
            time.sleep(1.0)
            return True
    except Exception as e:
        print(f"[WARNING] Lỗi khi kiểm tra unassigned badge: {e}")
    return False

def wait_for_unassigned_screen(page, timeout_ms=15000):
    print("[RPA] Đang chờ màn hình vật phẩm unassigned xuất hiện...")
    start_time = time.time()
    selectors = [
        "button:has-text('SBC Storage')",
        "button:has-text('Store All Items')",
        "button:has-text('Store All')",
        "button:has-text('Send Duplicates to SBC Storage')",
        ".ut-unassigned-view",
        ".unassigned-view",
        "button:has-text('Quick Sell')",
        ".layout-split"
    ]
    while time.time() - start_time < (timeout_ms / 1000.0):
        for sel in selectors:
            try:
                if page.locator(sel).first.is_visible():
                    print(f"[OK] Đã phát hiện màn hình unassigned (phần tử: {sel})")
                    return True
            except Exception:
                pass
        time.sleep(0.5)
    print("[WARNING] Quá thời gian chờ màn hình unassigned xuất hiện. Tiếp tục thực hiện các thao tác xử lý...")
    return False

def _run_unassigned_cleanup_actions(page):
    storage_buttons = [
        "button:has-text('SBC Storage')",
        "button:has-text('Send Duplicates to SBC Storage')",
        "button:has-text('Send all duplicates to SBC Storage')",
        "button:has-text('Move Duplicates to SBC Storage')",
        "button:has-text('Move to SBC Storage')",
        "button:has-text('Store Duplicates')",
        "button:has-text('Send to SBC Storage')",
        "button:has-text('Kho chứa SBC')",
        "button:has-text('Gửi cầu thủ trùng lặp')"
    ]
    
    club_buttons = [
        "button:has-text('Store All Items')",
        "button:has-text('Store All')",
        "button:has-text('Send All to Club')",
        "button:has-text('Send to My Club')",
        "button:has-text('Send to Club')",
        "button:has-text('Lưu trữ tất cả')"
    ]

    max_cleanup_attempts = 4
    for attempt in range(1, max_cleanup_attempts + 1):
        print(f"[RPA] Đang tiến hành dọn dẹp vật phẩm unassigned (Lần thử {attempt}/{max_cleanup_attempts})...")
        
        is_unassigned_visible = False
        try:
            if page.locator(".ut-unassigned-view, .unassigned-view").first.is_visible():
                is_unassigned_visible = True
        except Exception:
            pass
            
        if not is_unassigned_visible:
            print("[OK] Màn hình unassigned không còn hiển thị. Chuyển sang bước tiếp theo.")
            break
            
        # 1. Thử gửi vật phẩm không trùng lặp vào Club bằng phím Space (Shortcut của PaleTools)
        print("[RPA] Nhấn Space để gửi vật phẩm không trùng vào Club...")
        page.keyboard.press("Space")
        wait_for_click_shield(page)
        
        # 2. Xử lý các cầu thủ trùng lặp (Duplicates) gửi vào SBC Storage
        for selector in storage_buttons:
            try:
                loc = page.locator(selector).first
                if loc.is_visible():
                    btn_text = loc.text_content().strip() if loc.text_content() else ""
                    print(f"[RPA] Tìm thấy nút gửi duplicate: '{btn_text}'. Đang click...")
                    loc.click()
                    wait_for_click_shield(page)
                    
                    # Kiểm tra xem có hộp thoại xác nhận (dialog) xuất hiện không
                    try:
                        confirm_selectors = [
                            ".ea-dialog-view button:has-text('Yes')",
                            ".ea-dialog-view button:has-text('Ok')",
                            ".ea-dialog-view button:has-text('Confirm')",
                            ".ea-dialog-view button:has-text('Có')",
                            ".ea-dialog-view button:has-text('Xác nhận')"
                        ]
                        for c_sel in confirm_selectors:
                            c_btn = page.locator(c_sel).first
                            if c_btn.is_visible():
                                print(f"[RPA] Tìm thấy hộp thoại xác nhận, click '{c_btn.text_content().strip()}'...")
                                c_btn.click()
                                wait_for_click_shield(page)
                                break
                    except Exception:
                        pass
                    break
            except Exception:
                pass
                
        # 3. Thử click nút Store All để gửi các vật phẩm còn lại vào Club
        for selector in club_buttons:
            try:
                loc = page.locator(selector).first
                if loc.is_visible():
                    btn_text = loc.text_content().strip() if loc.text_content() else ""
                    print(f"[RPA] Tìm thấy nút Store All: '{btn_text}'. Đang click...")
                    loc.click()
                    wait_for_click_shield(page)
                    break
            except Exception:
                pass
                
        # 4. Gửi các vật phẩm không trùng lặp còn sót bằng Space lần nữa
        print("[RPA] Nhấn Space lần nữa để dọn dẹp các vật phẩm không trùng lặp còn sót...")
        page.keyboard.press("Space")
        wait_for_click_shield(page)
        
        # 5. Kiểm tra xem đã sạch hẳn unassigned chưa
        any_button_visible = False
        for selector in storage_buttons + club_buttons:
            try:
                if page.locator(selector).first.is_visible():
                    any_button_visible = True
                    break
            except Exception:
                pass
                
        # Kiểm tra xem trên màn hình còn hiển thị thẻ cầu thủ unassigned nào không
        has_items = False
        try:
            items_count = page.locator(".ut-unassigned-view .list-item, .unassigned-view .list-item, .ut-unassigned-view .tile, .unassigned-view .tile").count()
            if items_count > 0:
                has_items = True
        except Exception:
            pass
            
        if not any_button_visible and not has_items:
            print("[OK] Đã hoàn thành dọn dẹp vật phẩm unassigned thành công!")
            break
        else:
            print(f"[INFO] Vẫn còn nút thao tác hoặc thẻ unassigned trên màn hình. Sẽ thử lại ở lượt sau. (Nút: {any_button_visible}, Thẻ: {has_items})")
            time.sleep(1.0)
    
    # Chủ động quay lại My Packs bằng phím tắt "1" của PaleTools
    try:
        from src.store import is_in_my_packs
        print("[RPA] Nhấn phím '1' để quay lại My Packs (Shortcut PaleTools)...")
        page.keyboard.press("1")
        time.sleep(2.5) # Tăng nhẹ thời gian chờ để Web App phản hồi
        
        # Nếu nhấn phím '1' mà vẫn chưa về My Packs, thử click tab Store để fallback
        if not is_in_my_packs(page):
            print("[WARNING] Nhấn phím '1' chưa về My Packs. Thử click tab Store để fallback...")
            store_tab = page.locator(".ut-tab-bar-item.icon-store")
            if store_tab.count() > 0:
                store_tab.click()
                time.sleep(3.0) # Tăng nhẹ delay để trang Store tải xong
    except Exception as e:
        print(f"[WARNING] Lỗi khi quay lại Store/My Packs: {e}")

def handle_unassigned_items(page, config):
    # Tránh import vòng tròn bằng local import
    from src.store import is_in_my_packs
    from src.exceptions import SkipStepException
    
    print("[RPA] Bắt đầu xử lý vật phẩm unassigned sau khi mở pack...")
    
    # Chờ màn hình unassigned hiển thị đầy đủ
    wait_for_unassigned_screen(page, timeout_ms=15000)
    time.sleep(1.5)
    
    # Chạy dọn dẹp lần đầu
    _run_unassigned_cleanup_actions(page)
    
    # Kiểm tra xem sau khi dọn dẹp, màn hình unassigned còn tồn tại không
    still_unassigned = False
    try:
        if page.locator(".ut-unassigned-view, .unassigned-view").first.is_visible():
            still_unassigned = True
    except Exception:
        pass
        
    # Kiểm tra xem có dialog cảnh báo Unassigned Items nào che khuất không
    has_unassigned_dialog = False
    try:
        dialog = page.locator(".ea-dialog-view, .dialog-modal").first
        if dialog.count() > 0 and dialog.is_visible():
            d_text = dialog.text_content().lower()
            if any(kw in d_text for kw in ["unassigned items", "vật phẩm chưa phân phối", "unassigned", "sbc storage is full", "kho chứa sbc đã đầy"]):
                has_unassigned_dialog = True
                print(f"[WARNING] Phát hiện hộp thoại cảnh báo: '{dialog.text_content().strip()}'")
    except Exception:
        pass
        
    if still_unassigned or has_unassigned_dialog:
        while still_unassigned or has_unassigned_dialog:
            # Kích hoạt tạm dừng bot tự động
            trigger_bot_pause(page, "Phát hiện vật phẩm chưa phân phối (Unassigned Items) vẫn còn tồn tại. Có thể kho chứa SBC (SBC Storage) đã đầy 100/100.", config)
            
            # Tự động click tắt dialog cảnh báo nếu có để màn hình hiển thị sạch sẽ
            if has_unassigned_dialog:
                try:
                    ok_btn = page.locator(".ea-dialog-view button:has-text('Ok'), .ea-dialog-view button:has-text('OK'), .ea-dialog-view button:has-text('Confirm'), .ea-dialog-view button:has-text('Xác nhận')").first
                    if ok_btn.count() > 0 and ok_btn.is_visible():
                        ok_btn.click()
                        sleep_human_like(0.5, 1.0, page)
                except Exception:
                    pass
            
            # Hiển thị menu lựa chọn trên console
            print("\n" + "="*60)
            print("CẢNH BÁO: PHÁT HIỆN VẬT PHẨM CHƯA PHÂN PHỐI (UNASSIGNED ITEMS) VẪN CÒN TỒN TẠI!")
            print("Vui lòng nhập lựa chọn của bạn trong console (1, 2, hoặc 3):")
            print("  [1] Giữ nguyên trạng thái tạm dừng này để tôi tự xử lý thủ công.")
            print("  [2] Thử dọn dẹp lại (tự động di chuyển các thẻ unassigned vào SBC Storage/Club một lần nữa).")
            print("  [3] Bỏ qua bước hiện tại và chuyển sang bước tiếp theo trong workflow.")
            print("="*60 + "\n")
            
            # Gửi menu qua Telegram cho người dùng
            menu_msg = (
                "CẢNH BÁO: PHÁT HIỆN VẬT PHẨM CHƯA PHÂN PHỐI (UNASSIGNED ITEMS) VẪN CÒN TỒN TẠI!\n"
                "Vui lòng chọn phản hồi (1, 2, hoặc 3):\n"
                "  [1] Giữ nguyên trạng thái tạm dừng này để tôi tự xử lý thủ công.\n"
                "  [2] Thử dọn dẹp lại (tự động di chuyển các thẻ unassigned vào SBC Storage/Club một lần nữa).\n"
                "  [3] Bỏ qua bước hiện tại và chuyển sang bước tiếp theo trong workflow."
            )
            send_telegram_message(config, menu_msg)
            
            choice = None
            print("Đang chờ phản hồi từ console hoặc Telegram (1, 2, hoặc 3)...")
            last_tg_check = 0.0
            
            # Dọn dẹp hàng chờ console input cũ
            try:
                import queue
                from src.notification import _console_queue
                if _console_queue:
                    while not _console_queue.empty():
                        _console_queue.get_nowait()
            except Exception:
                pass
                
            while choice not in ["1", "2", "3"]:
                # 1. Kiểm tra Console Input (không chặn)
                console_in = get_console_input(timeout=0.1)
                if console_in in ["1", "2", "3"]:
                    choice = console_in
                    print(f"[INFO] Đã nhận được lựa chọn từ console: {choice}")
                    break
                    
                # 2. Kiểm tra Telegram updates (định kỳ mỗi 1.5s)
                current_time = time.time()
                if current_time - last_tg_check >= 1.5:
                    tg_choices = process_telegram_updates(config)
                    if tg_choices:
                        for tc in tg_choices:
                            if tc in ["1", "2", "3"]:
                                choice = tc
                                print(f"[INFO] Đã nhận được lựa chọn từ Telegram: {choice}")
                                send_telegram_message(config, f"Đã nhận phản hồi lựa chọn [{choice}]. Đang thực hiện...")
                                break
                    last_tg_check = current_time
                    
                time.sleep(0.1)
                    
            if choice == "1":
                print("[INFO] Đã chọn 1: Giữ trạng thái tạm dừng. Vui lòng tự xử lý trên Chrome.")
                print("Sau khi hoàn thành, hãy click nút 'TIẾP TỤC (Resume)' trên trình duyệt hoặc nhấn Enter ở đây để bot kiểm tra lại...")
                check_pause(page)
                
            elif choice == "2":
                print("[INFO] Đã chọn 2: Đang thử tự động di chuyển lại các cầu thủ unassigned...")
                # Đi vào màn hình unassigned để xử lý
                navigate_to_unassigned_screen(page)
                
                # Chạy lại cleanup
                _run_unassigned_cleanup_actions(page)
                # Reset trạng thái về running
                resume_bot_status(page)
                
            elif choice == "3":
                print("[INFO] Đã chọn 3: Bỏ qua bước hiện tại.")
                resume_bot_status(page)
                raise SkipStepException()
                
            # Đánh giá lại điều kiện để tiếp tục vòng lặp if unassigned vẫn còn
            still_unassigned = False
            try:
                if page.locator(".ut-unassigned-view, .unassigned-view").first.is_visible():
                    still_unassigned = True
            except Exception:
                pass
                
            has_unassigned_dialog = False
            try:
                dialog = page.locator(".ea-dialog-view, .dialog-modal").first
                if dialog.count() > 0 and dialog.is_visible():
                    d_text = dialog.text_content().lower()
                    if any(kw in d_text for kw in ["unassigned items", "vật phẩm chưa phân phối", "unassigned", "sbc storage is full", "kho chứa sbc đã đầy"]):
                        has_unassigned_dialog = True
            except Exception:
                pass
                
        print("[OK] Đã dọn dẹp sạch vật phẩm unassigned! Bot tiếp tục chạy...")
        return True
        
    return True
