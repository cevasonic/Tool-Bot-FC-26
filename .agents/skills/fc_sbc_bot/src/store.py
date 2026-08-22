import time
from src.utils import sleep_human_like, wait_for_click_shield, dismiss_modals
from src.paletools import ensure_paletools_injected, check_pause
from src.notification import alert_user_error

def get_pack_info(tile):
    pack_name = None
    for sub_sel in [".name", ".title", "h1", "h2", "h3"]:
        try:
            name_el = tile.locator(sub_sel)
            if name_el.count() > 0:
                t = name_el.first.text_content()
                if t and t.strip():
                    pack_name = t.strip()
                    break
        except Exception:
            pass
            
    if not pack_name:
        return None, 0
        
    quantity = 1
    # Thử tìm phần tử số lượng bằng các class phổ biến
    for count_sel in [
        ".count", ".quantity", ".badge", ".notification", ".amount", ".number",
        ".ut-store-pack-details-view--user-quantity", ".ut-store-pack-details-view--quantity"
    ]:
        try:
            count_el = tile.locator(count_sel)
            if count_el.count() > 0:
                c_text = count_el.first.text_content()
                if c_text:
                    c_clean = c_text.strip().lower().replace("x", "")
                    if c_clean.isdigit():
                        quantity = int(c_clean)
                        return pack_name, quantity
        except Exception:
            pass
            
    return pack_name, quantity

def find_best_match(target_name, available_names):
    if not available_names:
        return None
    
    # 1. Exact match
    if target_name in available_names:
        return target_name
        
    # 2. Case-insensitive and whitespace-insensitive exact match
    target_clean = "".join(target_name.lower().split())
    for name in available_names:
        name_clean = "".join(name.lower().split())
        if target_clean == name_clean:
            return name
            
    # 3. Thuật toán so khớp thông minh kiểm tra quy tắc loại trừ chéo nghiêm ngặt
    target_words = [w.lower() for w in target_name.split() if w.lower() not in ["pack", "packs"]]
    
    exclusive_keywords = [
        "premium", "rare", "common", "gold", "silver", "bronze", "jumbo", "ultimate", "mega",
        "80+", "81+", "82+", "83+", "84+", "85+", "78", "80", "11x", "5x", "3x", "2x", "x2", "x3", "x5", "two", "three", "five"
    ]
    
    best_match = None
    max_overlap = 0
    
    for name in available_names:
        name_lower = name.lower()
        name_words = [w.lower() for w in name.split() if w.lower() not in ["pack", "packs"]]
        
        # Kiểm tra quy tắc loại trừ chéo nghiêm ngặt:
        # Bất kỳ từ khóa độc quyền nào (loại pack, số lượng, rating) lệch nhau đều coi là mismatch và loại bỏ
        is_mismatch = False
        for kw in exclusive_keywords:
            in_name = any(kw in w for w in name_words)
            in_target = any(kw in w for w in target_words)
            if in_name != in_target:
                is_mismatch = True
                break
                
        if is_mismatch:
            continue
            
        # Tính số từ trùng lặp
        overlap = 0
        for tw in target_words:
            if any(tw in nw or nw in tw for nw in name_words):
                overlap += 1
                
        # Tất cả các từ khóa chính trong cấu hình phải xuất hiện trong tên trên UI
        essential_target_words = [w for w in target_words if w not in ["x2", "x3", "x5", "5x", "11x", "two", "three", "five"]]
        all_essential_matched = True
        for ew in essential_target_words:
            if not any(ew in nw for nw in name_words):
                all_essential_matched = False
                break
                
        if all_essential_matched and overlap > max_overlap:
            max_overlap = overlap
            best_match = name
            
    return best_match

def is_in_my_packs(page):
    try:
        # 1. Kiểm tra tiêu đề trang "Packs" ở navigation bar
        title = page.locator(".ut-navigation-bar-view h1.title, .ut-navigation-bar-view .title").first
        if title.count() > 0 and title.is_visible() and title.text_content() and "pack" in title.text_content().lower():
            return True
            
        # 2. Kiểm tra tab "My Packs" ở bất kỳ thẻ nào trên trang
        my_packs_tab = page.locator("button:has-text('My Packs'), div:has-text('My Packs'), span:has-text('My Packs'), .ut-navigation-container *:has-text('My Packs')").first
        if my_packs_tab.count() > 0 and my_packs_tab.is_visible():
            return True
            
        # 3. Kiểm tra sự xuất hiện của nút "Open" trên các pack item
        open_btn = page.locator("button:has-text('Open'), .tile button:has-text('Open'), .store-tile button:has-text('Open'), button:has-text('Open Pack')").first
        if open_btn.count() > 0 and open_btn.is_visible():
            return True
    except Exception:
        pass
    return False

def navigate_to_my_packs(page, config):
    if is_in_my_packs(page):
        return True

    print("\n[STORE] Navigating to Store / My Packs...")
    try:
        dismiss_modals(page)
        # 1. Thử bấm phím tắt '1' của PaleTools để chuyển thẳng tới My Packs
        page.keyboard.press("1")
        sleep_human_like(1.5, 2.5, page)
        if is_in_my_packs(page):
            print("[OK] Đã chuyển đến My Packs qua phím tắt PaleTools ('1')!")
            return True

        # 2. Chuyển sang tab Store
        store_tab = page.locator(".ut-tab-bar-item.icon-store")
        if store_tab.count() > 0:
            try:
                store_tab.click(timeout=5000)
            except Exception:
                store_tab.click(force=True)
            wait_for_click_shield(page)
            sleep_human_like(1.5, 2.5, page)

        dismiss_modals(page)
        # Thử lại phím tắt '1' sau khi ở tab Store
        page.keyboard.press("1")
        sleep_human_like(1.5, 2.5, page)
        if is_in_my_packs(page):
            print("[OK] Đã chuyển đến My Packs qua phím tắt PaleTools ('1')!")
            return True

        # 3. Thử click trực tiếp ô Packs trên Store
        packs_tile = page.locator(".tile.packs-tile button, .tile.packs-tile .btn-standard, .tile.packs-tile h1, .tile.packs-tile .tileHeader, .tile.packs-tile").first
        if packs_tile.count() > 0 and packs_tile.is_visible():
            for attempt in range(1, 4):
                print(f"[INFO] Thử click vào ô Packs lần {attempt}...")
                try:
                    packs_tile.click(timeout=2000, force=True)
                except Exception:
                    pass
                wait_for_click_shield(page, timeout=3000)
                if is_in_my_packs(page):
                    print("[OK] Đã chuyển trang Packs thành công!")
                    return True
                sleep_human_like(1.0, 1.5, page)

        if is_in_my_packs(page):
            return True
            
    except Exception as e:
        print(f"[WARNING] Lỗi khi chuyển sang trang My Packs: {e}")

    return is_in_my_packs(page)

def open_single_supply_pack(page, config, paletools_js, pack_name):
    """
    Tìm và mở đúng 1 pack tiếp tế có tên pack_name.
    Trả về True nếu mở thành công 1 pack, False nếu không tìm thấy pack để mở.
    """
    # Tránh import vòng tròn
    from src.unassigned import handle_unassigned_items

    print(f"\n[STORE] Tìm kiếm và mở 1 pack tiếp tế: {pack_name}")
    
    # Đảm bảo chuyển sang trang My Packs trước khi quét
    if not navigate_to_my_packs(page, config):
        print("[ERROR] Không thể chuyển sang trang My Packs để tìm pack tiếp tế. Thử tự động khôi phục...")
        from src.utils import recover_from_crash
        if recover_from_crash(page, config, paletools_js) and navigate_to_my_packs(page, config):
            print("[OK] Đã khôi phục và chuyển sang My Packs thành công!")
        else:
            print("[ERROR] Vẫn không thể chuyển sang trang My Packs sau khi khôi phục.")
            return False
    
    # Đảm bảo PaleTools luôn được inject
    ensure_paletools_injected(page, paletools_js)
    
    # Đợi danh sách các Pack tải xong
    try:
        page.wait_for_selector(".tile, .store-tile, .pack-tile, .ut-store-pack-details-view", state="visible", timeout=5000)
    except Exception:
        pass
    
    # Thử quét lại nhiều lần nếu không tìm thấy pack
    best_match = None
    available_packs_with_qty = {}
    for scan_attempt in range(1, 4):
        if scan_attempt > 1:
            print(f"[INFO] Thử quét lại danh sách pack lần {scan_attempt} sau 2s...")
            time.sleep(2.0)
            try:
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            except Exception:
                pass
        
        try:
            pack_tiles = page.locator(".tile, .store-tile, .pack-tile, .ut-store-pack-details-view").all()
            available_packs_with_qty = {}
            for tile in pack_tiles:
                p_name, p_qty = get_pack_info(tile)
                if p_name:
                    if p_name in available_packs_with_qty:
                        available_packs_with_qty[p_name] += p_qty
                    else:
                        available_packs_with_qty[p_name] = p_qty
            available_packs = list(available_packs_with_qty.keys())
            
            best_match = find_best_match(pack_name, available_packs)
            if best_match:
                break
        except Exception as e:
            print(f"[ERROR] Lỗi khi quét danh sách pack ở lần thử {scan_attempt}: {e}")
            
    if not best_match:
        print(f"[INFO] Không tìm thấy Pack tiếp tế '{pack_name}' trong Store (đã hết pack tiếp tế này).")
        return False
        
    resolved_pack_name = best_match
    
    try:
        pack_selector = "h1, h2, h3, .name, .title"
        locator = page.locator(pack_selector).filter(has_text=resolved_pack_name).first
        
        if locator.count() > 0:
            print(f"[OK] Đang mở 1 pack tiếp tế: {resolved_pack_name}")
            dismiss_modals(page)
            locator.click()
            sleep_human_like(1.0, 1.8, page)
            
            tile_parent = locator.locator("xpath=./ancestor::*[contains(@class, 'tile') or contains(@class, 'Tile') or contains(@class, 'pack')]").first
            open_btn = tile_parent.locator("button").first if tile_parent.count() > 0 else locator.locator("button").first
            if open_btn.count() > 0:
                open_btn.click()
                sleep_human_like(1.5, 2.5, page)
                
                # Tự động xử lý vật phẩm unassigned sau khi mở pack
                handle_unassigned_items(page, config)
                # Đợi giao diện quay lại Store
                sleep_human_like(0.5, 1.2, page)
                wait_for_click_shield(page)
                return True
            else:
                print(f"[WARNING] Không tìm thấy nút xác nhận mở cho pack: {resolved_pack_name}")
                return False
        else:
            print(f"[INFO] Không tìm thấy phần tử pack '{resolved_pack_name}' trên giao diện.")
            return False
    except Exception as e:
        print(f"[ERROR] Lỗi khi mở pack tiếp tế {resolved_pack_name}: {e}")
        return False

def execute_open_pack_step(page, config, paletools_js, pack_name, open_count=None, open_all=False, on_success_cb=None):
    # Tránh import vòng tròn
    from src.unassigned import handle_unassigned_items

    print(f"\n[STORE] Tìm kiếm và mở Pack: {pack_name}")
    opened_so_far = 0
    is_finished = False
    
    while True:
        check_pause(page)
        dismiss_modals(page)
        
        # Kiểm tra điều kiện dừng:
        if not open_all and open_count is not None and opened_so_far >= open_count:
            print(f"[INFO] Đã mở đủ số lượng yêu cầu ({opened_so_far}/{open_count}) cho pack '{pack_name}'. Dừng mở.")
            is_finished = True
            break
            
        # Đảm bảo chuyển sang trang My Packs trước khi quét
        if not navigate_to_my_packs(page, config):
            print("[ERROR] Không thể chuyển sang trang My Packs. Thử tự động khôi phục bằng reload trang...")
            from src.utils import recover_from_crash
            if recover_from_crash(page, config, paletools_js):
                # Thử lại sau khi khôi phục
                if navigate_to_my_packs(page, config):
                    print("[OK] Đã khôi phục và chuyển sang My Packs thành công!")
                else:
                    print("[ERROR] Vẫn không thể chuyển sang trang My Packs sau khi khôi phục. Dừng bước mở pack này.")
                    is_finished = False
                    break
            else:
                print("[ERROR] Khôi phục thất bại. Dừng bước mở pack này.")
                is_finished = False
                break
        
        # Đảm bảo PaleTools luôn được inject
        ensure_paletools_injected(page, paletools_js)
        
        # Đợi danh sách các Pack tải xong
        try:
            page.wait_for_selector(".tile, .store-tile, .pack-tile, .ut-store-pack-details-view", state="visible", timeout=5000)
        except Exception:
            pass
        
        # Thử quét lại nhiều lần nếu không tìm thấy pack (đề phòng giao diện tải chậm hoặc bị cuộn)
        best_match = None
        available_packs_with_qty = {}
        for scan_attempt in range(1, 4):
            if scan_attempt > 1:
                print(f"[INFO] Thử quét lại danh sách pack lần {scan_attempt} sau 2s...")
                time.sleep(2.0)
                # Cuộn trang xuống dưới để load thêm các pack bị ẩn
                try:
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                except Exception:
                    pass
            
            try:
                pack_tiles = page.locator(".tile, .store-tile, .pack-tile, .ut-store-pack-details-view").all()
                available_packs_with_qty = {}
                for tile in pack_tiles:
                    p_name, p_qty = get_pack_info(tile)
                    if p_name:
                        if p_name in available_packs_with_qty:
                            available_packs_with_qty[p_name] += p_qty
                        else:
                            available_packs_with_qty[p_name] = p_qty
                available_packs = list(available_packs_with_qty.keys())
                
                best_match = find_best_match(pack_name, available_packs)
                if best_match:
                    break
            except Exception as e:
                print(f"[ERROR] Lỗi khi quét danh sách pack ở lần thử {scan_attempt}: {e}")
                
        if not best_match:
            print(f"[INFO] Không tìm thấy Pack '{pack_name}' trên giao diện sau nhiều lần quét (hoặc đã mở hết).")
            is_finished = True
            break
            
        resolved_pack_name = best_match
        qty = available_packs_with_qty.get(resolved_pack_name, 0)
        # Đảm bảo nếu pack hiển thị trên màn hình thì số lượng tối thiểu là 1
        qty = max(1, qty)
            
        print(f"[INFO] Phát hiện còn {qty} pack '{resolved_pack_name}' khả dụng.")
        
        try:
            pack_selector = "h1, h2, h3, .name, .title"
            locator = page.locator(pack_selector).filter(has_text=resolved_pack_name).first
            
            if locator.count() > 0:
                print(f"[OK] Đang mở pack: {resolved_pack_name} (Lượt {opened_so_far + 1})")
                dismiss_modals(page)
                locator.click()
                sleep_human_like(1.0, 1.8, page)
                
                tile_parent = locator.locator("xpath=./ancestor::*[contains(@class, 'tile') or contains(@class, 'Tile') or contains(@class, 'pack')]").first
                open_btn = tile_parent.locator("button").first if tile_parent.count() > 0 else locator.locator("button").first
                if open_btn.count() > 0:
                    open_btn.click()
                    sleep_human_like(1.5, 2.5, page)
                    
                    # Tự động xử lý vật phẩm unassigned (gửi vào Club/SBC Storage) sau khi mở pack
                    handle_unassigned_items(page, config)
                    # Đợi giao diện quay lại Store
                    sleep_human_like(0.5, 1.2, page)
                    wait_for_click_shield(page)
                    opened_so_far += 1
                    if on_success_cb:
                        try:
                            on_success_cb()
                        except Exception as cb_err:
                            print(f"[WARNING] Lỗi khi gọi callback lưu trạng thái mở pack: {cb_err}")
                else:
                    print(f"[WARNING] Không tìm thấy nút xác nhận mở cho pack: {resolved_pack_name}")
                    is_finished = False
                    break
            else:
                print(f"[INFO] Không tìm thấy phần tử pack '{resolved_pack_name}' trên giao diện.")
                is_finished = False
                break
        except Exception as e:
            print(f"[ERROR] Lỗi khi mở pack {resolved_pack_name}: {e}")
            alert_user_error(page, config, f"Lỗi khi mở pack {resolved_pack_name}")
            is_finished = False
            break
            
    print(f"[STORE] Hoàn thành mở pack '{pack_name}': Đã mở {opened_so_far} lần.")
    return opened_so_far, is_finished
