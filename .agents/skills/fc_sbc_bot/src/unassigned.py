import time
from src.utils import sleep_human_like
from src.paletools import trigger_bot_pause, check_pause

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
            print(f"[WARNING] Phát hiện có vật phẩm unassigned chưa xử lý trên top bar. Đang click để dọn dẹp...")
            if target_el:
                target_el.click()
                time.sleep(2.0)
            else:
                store_tab = page.locator(".ut-tab-bar-item.icon-store").first
                if store_tab.count() > 0:
                    store_tab.click()
                    time.sleep(2.0)
            
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

def handle_unassigned_items(page, config):
    # Tránh import vòng tròn bằng local import
    from src.store import is_in_my_packs
    
    print("[RPA] Bắt đầu xử lý vật phẩm unassigned sau khi mở pack...")
    
    # Chờ màn hình unassigned hiển thị đầy đủ
    wait_for_unassigned_screen(page, timeout_ms=15000)
    time.sleep(1.5)
    
    # 1. Thử gửi vật phẩm không trùng lặp vào Club bằng phím Space (Shortcut của PaleTools)
    print("[RPA] Thử gửi vật phẩm không trùng vào Club (nhấn Space)...")
    page.keyboard.press("Space")
    time.sleep(1.5)
    
    # 2. Xử lý các cầu thủ trùng lặp (Duplicates) gửi vào SBC Storage
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
    
    # Thử click nút SBC Storage trước
    for selector in storage_buttons:
        try:
            locators = page.locator(selector).all()
            for loc in locators:
                if loc.is_visible():
                    btn_text = loc.text_content().strip() if loc.text_content() else ""
                    print(f"[RPA] Tìm thấy nút gửi duplicate: '{btn_text}'. Đang click...")
                    loc.click()
                    time.sleep(1.5)
                    
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
                                time.sleep(1.0)
                                break
                    except Exception:
                        pass
                    break
        except Exception:
            pass
            
    # Thử click nút Store All để gửi các vật phẩm còn lại vào Club
    for selector in club_buttons:
        try:
            locators = page.locator(selector).all()
            for loc in locators:
                if loc.is_visible():
                    btn_text = loc.text_content().strip() if loc.text_content() else ""
                    print(f"[RPA] Tìm thấy nút Store All: '{btn_text}'. Đang click...")
                    loc.click()
                    time.sleep(1.5)
                    break
        except Exception:
            pass
            
    # Cuối cùng, thử nhấn Space một lần nữa để dọn dẹp nốt nếu còn sót
    page.keyboard.press("Space")
    time.sleep(1.0)
    
    # VÒNG LẶP CHỜ: Đợi cho đến khi không còn nút thao tác nào hiển thị trên UI (xác nhận dọn dẹp sạch unassigned)
    print("[RPA] Đang chờ xác nhận việc dọn dẹp vật phẩm unassigned hoàn tất...")
    cleanup_timeout = 8.0
    start_cleanup = time.time()
    while time.time() - start_cleanup < cleanup_timeout:
        any_visible = False
        for selector in storage_buttons + club_buttons:
            try:
                if page.locator(selector).first.is_visible():
                    any_visible = True
                    break
            except Exception:
                pass
        if not any_visible:
            print("[OK] Đã hoàn thành dọn dẹp vật phẩm unassigned thành công!")
            break
        time.sleep(0.5)
    
    # 主動 quay lại My Packs bằng phím tắt "1" của PaleTools
    try:
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
        # Kích hoạt tạm dừng bot tự động
        trigger_bot_pause(page, "Phát hiện vật phẩm chưa phân phối (Unassigned Items) vẫn còn tồn tại. Có thể kho chứa SBC (SBC Storage) đã đầy 100/100.")
        # Tự động click tắt dialog cảnh báo nếu có để màn hình hiển thị sạch sẽ
        if has_unassigned_dialog:
            try:
                ok_btn = page.locator(".ea-dialog-view button:has-text('Ok'), .ea-dialog-view button:has-text('OK'), .ea-dialog-view button:has-text('Confirm'), .ea-dialog-view button:has-text('Xác nhận')").first
                if ok_btn.count() > 0 and ok_btn.is_visible():
                    ok_btn.click()
                    sleep_human_like(0.5, 1.0, page)
            except Exception:
                pass
        # Gọi check_pause để bot lập tức tạm dừng
        check_pause(page)
        return False
        
    return True
