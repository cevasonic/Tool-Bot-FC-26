import os
import time
import re
import json
from src.config import BASE_DIR
from src.utils import sleep_human_like, dismiss_modals, check_captcha_or_errors, wait_for_click_shield
from src.paletools import check_pause, ensure_paletools_injected, ensure_bot_overlay, trigger_bot_pause
from src.notification import alert_user_error
from src.unassigned import check_unassigned_badge_and_clear
from src.store import open_single_supply_pack

def check_concept_players_in_squad(page):
    try:
        # Trong EA Web App, các cầu thủ Concept trên sân có class .concept hoặc .player.concept
        concept_count = page.evaluate("""() => {
            const players = document.querySelectorAll('.pitch .player.concept, .pitch .concept, .squad-slot .concept');
            return players.length;
        }""")
        if concept_count > 0:
            print(f"[WARNING] Phát hiện có {concept_count} cầu thủ Concept trong đội hình Builder (thiếu thẻ thực tế).")
            return True
    except Exception as e:
        print(f"[WARNING] Lỗi khi kiểm tra cầu thủ Concept: {e}")
    return False

def find_sbc_tile(page, sbc_name):
    try:
        # Thử tìm kiếm chính xác hoàn toàn trước (exact match) để tránh nhầm lẫn các SBC tương tự (ví dụ: Silver Upgrade vs Daily Silver Upgrade)
        exact_regex = re.compile(r'^\s*' + re.escape(sbc_name.strip()) + r'\s*$', re.IGNORECASE)
        name_locator = page.get_by_text(exact_regex)
        count = name_locator.count()
        
        # Nếu không tìm thấy exact match nào hiển thị, fallback về so khớp chứa (contains)
        is_exact_found = False
        for i in range(count):
            if name_locator.nth(i).is_visible():
                is_exact_found = True
                break
                
        if not is_exact_found:
            contains_regex = re.compile(re.escape(sbc_name.strip()), re.IGNORECASE)
            name_locator = page.get_by_text(contains_regex)
            count = name_locator.count()
            
        for i in range(count):
            loc = name_locator.nth(i)
            if loc.is_visible():
                # Thử tìm các thẻ cha phổ biến của EA Web App
                for ancestor_xpath in [
                    "./ancestor::*[contains(@class, 'ut-sbc-tile-view')]",
                    "./ancestor::*[contains(@class, 'sbc-item-view')]",
                    "./ancestor::*[contains(@class, 'tile')]",
                    "./ancestor::*[contains(@class, 'sbcItem')]",
                    "./ancestor::*[contains(@class, 'sbc-tile')]",
                    "./ancestor::*[contains(@class, 'SbcItemView')]",
                    "./ancestor::*[contains(@class, 'ItemView')]"
                ]:
                    ancestor = loc.locator(f"xpath={ancestor_xpath}").first
                    if ancestor.count() > 0 and ancestor.is_visible():
                        return ancestor, loc
                # Nếu không tìm thấy ancestor cụ thể, thử tìm ancestor tổng quát gần nhất
                general_ancestor = loc.locator("xpath=./ancestor::*[contains(@class, 'tile') or contains(@class, 'item') or contains(@class, 'sbc')][1]").first
                if general_ancestor.count() > 0 and general_ancestor.is_visible():
                    return general_ancestor, loc
    except Exception as e:
        print(f"[WARNING] Lỗi trong find_sbc_tile: {e}")
    return None, None

def get_sbc_repeats(tile_locator):
    try:
        tile_text = (tile_locator.text_content() or "").strip()
        tile_text_lower = tile_text.lower()
        
        # Log debug
        print(f"[DEBUG_SBC] Thử phân tích tile text: '{' '.join(tile_text.split())}'")
        
        # Loại bỏ các chuỗi thống kê số lần đã hoàn thành hoặc trạng thái số lượng để tránh match nhầm các từ khóa hoàn thành
        # Ví dụ: "completed 75 times", "hoàn thành 104 lần", "completed 0 times"
        clean_text = re.sub(r'(?:completed|hoàn\s*thành)\s*[\d.,]+\s*(?:times|lần)', '', tile_text_lower)
        
        # Kiểm tra nhanh các từ khóa biểu thị đã hoàn thành hoàn toàn (không bao gồm "complete" hay "completed" thô sơ vì dễ dính vào mô tả)
        completed_keywords = [
            "đã hoàn thành", "đã làm",
            "expired", "đã hết hạn", "repeatable: 0", "repeat: 0", 
            "0 repeatable", "0 left", "0 repeats", "0/10 repeatable", "0/3 repeatable"
        ]
        for kw in completed_keywords:
            if kw in clean_text:
                print(f"[DEBUG_SBC]   Khớp từ khóa completed nhanh: '{kw}'. Trả về 0.")
                return 0
                
        done_times = None
        
        # 1. Kiểm tra class hoặc status block biểu thị Completed
        try:
            status_block = tile_locator.locator(".completed, [class*='completed'], .ut-sbc-set-tile-view--status-block")
            if status_block.count() > 0:
                for idx in range(status_block.count()):
                    block_text = (status_block.nth(idx).text_content() or "").lower()
                    print(f"[DEBUG_SBC]   Phát hiện status block {idx}: '{block_text.strip()}'")
                    
                    # A. Kiểm tra dạng số lần hoàn thành: "completed N times" hoặc "hoàn thành N lần"
                    match_done = re.search(r'(?:completed|hoàn\s*thành)\s*(\d+)\s*(?:times|lần)', block_text)
                    if match_done:
                        done_times = int(match_done.group(1))
                        print(f"[DEBUG_SBC]     Đã hoàn thành {done_times} lần theo status block.")
                        continue
                    
                    # B. Nếu có dạng phân số X/Y (ví dụ "0/1", "1/1", "1/2")
                    match_fraction = re.search(r'(\d+)\s*/\s*(\d+)', block_text)
                    if match_fraction:
                        done = int(match_fraction.group(1))
                        total = int(match_fraction.group(2))
                        if done < total:
                            print(f"[DEBUG_SBC]     SBC chưa hoàn thành hết các squad ({done}/{total} < 100%). Tiếp tục kiểm tra.")
                            continue
                        else:
                            # Đã xong các squad (ví dụ 1/1).
                            # Nếu không có chữ "repeatable" / "lặp lại" / "làm lại" trong tile text, thì đây là SBC không lặp lại và đã hoàn thành!
                            has_repeat_keywords = any(r in tile_text_lower for r in ["repeatable", "repeatable: ", "lặp lại", "lượt làm lại"])
                            if not has_repeat_keywords:
                                print(f"[DEBUG_SBC]     Đã hoàn thành các squad của SBC không lặp lại ({done}/{total}). Trả về 0.")
                                return 0
                            else:
                                print(f"[DEBUG_SBC]     Đã xong các squad ({done}/{total}). Kiểm tra số lượt lặp lại.")
                    
                    if "completed" in block_text or "hoàn thành" in block_text:
                        # Chỉ coi là đã hoàn thành nếu KHÔNG phải là phân số dở dang (ví dụ 0/1) hoặc ghi nhận số lần đã làm
                        if not match_fraction and not match_done:
                            print(f"[DEBUG_SBC]     Phát hiện chữ Completed đơn độc. Trả về 0.")
                            return 0
        except Exception as e:
            print(f"[DEBUG_SBC] Lỗi khi quét status_block: {e}")
            pass

        # 2. Tìm số lượt Repeatable: N
        match_rep = re.search(
            r'\b(?:Repeatable|Repeat|Lượt\s*làm\s*lại|Lặp\s*lại)[ \t]*:[ \t]*(\d+)\b(?![ \t]*(?:day|hour|min|sec|d|h|m|ngày|giờ|phút))', 
            tile_text, 
            re.IGNORECASE
        )
        if match_rep:
            total_repeats = int(match_rep.group(1))
            print(f"[DEBUG_SBC]   Regex tìm thấy Repeatable còn lại: {total_repeats} (từ tile_text)")
            if total_repeats < 200:
                return total_repeats

        # 3. Kiểm tra trong phần tử label trạng thái repeat cụ thể
        try:
            repeat_el = tile_locator.locator(".ut-squad-building-set-status-label-view.repeat, .repeat, [class*='repeat']").first
            if repeat_el.count() > 0 and repeat_el.is_visible():
                rep_text = repeat_el.text_content() or ""
                print(f"[DEBUG_SBC]   Tìm thấy repeat element text: '{rep_text.strip()}'")
                match_label = re.search(
                    r'\b(?:Repeatable|Repeat|Lượt\s*làm\s*lại|Lặp\s*lại)[ \t]*:[ \t]*(\d+)\b(?![ \t]*(?:day|hour|min|sec|d|h|m|ngày|giờ|phút))', 
                    rep_text, 
                    re.IGNORECASE
                )
                if match_label:
                    total_repeats = int(match_label.group(1))
                    print(f"[DEBUG_SBC]     Regex tìm thấy Repeatable còn lại: {total_repeats} (từ repeat element)")
                    if total_repeats < 200:
                        return total_repeats
        except Exception as e:
            print(f"[DEBUG_SBC] Lỗi khi check repeat_el: {e}")
            pass

        # 4. Kiểm tra các từ khóa đặc trưng biểu thị hết hạn/hoàn thành nhưng loại trừ mô tả chung
        # Không bao gồm "completed" hay "complete" hay "0/" thô sơ ở đây
        completed_keywords = [
            "đã hoàn thành", "đã làm", 
            "expired", "đã hết hạn", "repeatable: 0", "repeat: 0", 
            "0 repeatable", "0 left", "0 repeats", "0/10 repeatable", "0/3 repeatable"
        ]
        for kw in completed_keywords:
            if kw in clean_text:
                print(f"[DEBUG_SBC]   Khớp từ khóa completed: '{kw}'. Trả về 0.")
                return 0

    except Exception as e:
        print(f"[WARNING] Lỗi khi phân tích số lượt repeatable: {e}")
    print(f"[DEBUG_SBC]   Không xác định được số lượt repeatable từ UI. Trả về None.")
    return None

def execute_sbc_step(page, config, paletools_js, sbc_name, max_repeats, completed_sbcs_total, supply_pack_name=None, on_success_cb=None):
    delays = config.get("delays", {})
    original_sbc_name = sbc_name
    print(f"\n[SBC] Bắt đầu tác vụ SBC: {sbc_name} (Lặp tối đa: {max_repeats if max_repeats != 999999 else 'Không giới hạn'})")
    
    sbc_count = 0
    consecutive_errors = 0
    is_finished = False
    consecutive_supplies = 0
    
    # Kiểm tra và dọn dẹp unassigned items trước khi bắt đầu các lượt SBC
    check_unassigned_badge_and_clear(page, config)
    
    while sbc_count < max_repeats:
        check_pause(page)
        resolved_sbc = False
        check_captcha_or_errors(page, config)
        print(f"[INFO] Bắt đầu lượt SBC {sbc_count + 1}/{max_repeats if max_repeats != 999999 else 'Không giới hạn'}...")
        
        print("[INFO] Đang di chuyển tới menu SBC...")
        try:
            dismiss_modals(page)
            # Nếu đang kẹt ở màn hình Builder, thử bấm nút Back của Web App
            back_btn = page.locator(".ut-navigation-bar button.ut-navigation-button-control--prev, .ut-navigation-bar button.back, button:has-text('◀')").first
            if back_btn.count() > 0 and back_btn.is_visible():
                print("[INFO] Phát hiện đang ở view con/SBC Builder. Click nút Back để quay lại danh sách...")
                try:
                    back_btn.click(timeout=3000)
                    sleep_human_like(1.0, 2.0, page)
                except Exception:
                    pass
            
            page.wait_for_selector(".ut-tab-bar-item.icon-sbc", timeout=15000)
            try:
                page.click(".ut-tab-bar-item.icon-sbc", timeout=5000)
            except Exception:
                page.click(".ut-tab-bar-item.icon-sbc", force=True)
            sleep_human_like(1.5, 2.5, page)
        except Exception as e:
            print(f"[ERROR] Không thể di chuyển tới menu SBC: {e}")
            alert_user_error(page, config, "Lỗi di chuyển tới menu SBC")
            
            # Thử tự động khôi phục bằng cách reload trang
            from src.utils import recover_from_crash
            if recover_from_crash(page, config, paletools_js):
                consecutive_errors = 0
                continue
                
            consecutive_errors += 1
            if consecutive_errors >= 3:
                print("[ERROR] Quá nhiều lỗi điều hướng liên tiếp. Dừng bước SBC này.")
                is_finished = False
                break
            continue
        
        # Tìm kiếm SBC trên giao diện
        tile_locator = None
        is_visible_on_ui = False
        
        # Bấm tab All để tìm kiếm diện rộng
        try:
            all_tab_btn = page.locator("button:has-text('All')").first
            if all_tab_btn.count() > 0:
                print("[INFO] Click tab 'All' để tìm kiếm diện rộng...")
                all_tab_btn.click()
                sleep_human_like(1.5, 2.5, page)
                
                # Cuộn xuống để tải thêm các SBC (lazy loading)
                print("[INFO] Đang cuộn xuống để tải thêm các SBC...")
                for scroll_attempt in range(5):
                    page.evaluate("""
                        window.scrollTo(0, document.body.scrollHeight);
                        const containers = document.querySelectorAll('.ut-navigation-container-view, .ut-sbc-hub-view, .ut-sbc-grid-view');
                        containers.forEach(c => {
                            c.scrollTop = c.scrollHeight;
                        });
                    """)
                    sleep_human_like(0.6, 1.0, page)
        except Exception as tab_err:
            print(f"[WARNING] Không thể bấm tab 'All' hoặc cuộn trang: {tab_err}")
        
        # Thử sử dụng hộp tìm kiếm (Search Input) trước để lọc nhanh
        try:
            dismiss_modals(page)
            search_input = page.locator("input[placeholder='Search'], .ut-sbc-hub-view input.search, .search input").first
            if search_input.count() > 0 and search_input.is_visible():
                print(f"[INFO] Nhập '{original_sbc_name}' vào ô Tìm kiếm...")
                try:
                    search_input.click(timeout=5000)
                except Exception:
                    search_input.click(force=True)
                # Xóa text cũ nếu có
                page.keyboard.press("ControlOrMeta+A")
                page.keyboard.press("Backspace")
                # Nhập tên SBC
                search_input.type(original_sbc_name)
                sleep_human_like(2.0, 3.5, page)
        except Exception as search_err:
            print(f"[WARNING] Lỗi khi sử dụng ô tìm kiếm: {search_err}")
            
        # Quét tìm tile SBC sau khi search bằng bộ lọc trực tiếp của Playwright
        tile_locator, text_locator = None, None
        try:
            tile_locator, text_locator = find_sbc_tile(page, original_sbc_name)
            if tile_locator is not None:
                is_visible_on_ui = True
                print(f"[OK] Tìm thấy SBC '{original_sbc_name}' trên giao diện sau khi tìm kiếm!")
        except Exception as scan_err:
            print(f"[WARNING] Lỗi khi quét tìm tile: {scan_err}")

        # Nếu vẫn chưa tìm thấy, tiến hành quét thủ công qua các tab (đề phòng ô search không hoạt động)
        if not is_visible_on_ui:
            print("[INFO] Chưa tìm thấy SBC qua ô Tìm kiếm. Tiến hành quét thủ công qua các tab...")
            tabs_to_try = ["Favourites", "Upgrades", "Challenges", "All"]
            for tab_name in tabs_to_try:
                try:
                    tab_btn = page.locator(f"button:has-text('{tab_name}')").first
                    if tab_btn.count() > 0:
                        print(f"[INFO] Đang click tab '{tab_name}'...")
                        tab_btn.click()
                        sleep_human_like(1.5, 2.5, page)
                        
                        # Xóa ô tìm kiếm nếu đang có chữ để hiển thị lại toàn bộ danh mục của tab này
                        try:
                            search_input = page.locator("input[placeholder='Search'], .ut-sbc-hub-view input.search, .search input").first
                            if search_input.count() > 0:
                                search_input.click()
                                page.keyboard.press("ControlOrMeta+A")
                                page.keyboard.press("Backspace")
                                sleep_human_like(0.8, 1.5, page)
                        except Exception:
                            pass
                        
                        # Cuộn xuống để tải thêm các SBC trong tab này
                        print("[INFO] Đang cuộn xuống để tải thêm các SBC trong tab...")
                        for scroll_attempt in range(3):
                            page.evaluate("""
                                window.scrollTo(0, document.body.scrollHeight);
                                const containers = document.querySelectorAll('.ut-navigation-container-view, .ut-sbc-hub-view, .ut-sbc-grid-view');
                                containers.forEach(c => {
                                    c.scrollTop = c.scrollHeight;
                                });
                            """)
                            sleep_human_like(0.6, 1.0, page)
                        
                        # Tìm kiếm bằng bộ lọc trực tiếp của Playwright
                        try:
                            tile_locator, text_locator = find_sbc_tile(page, original_sbc_name)
                            if tile_locator is not None:
                                is_visible_on_ui = True
                                print(f"[OK] Tìm thấy SBC '{original_sbc_name}' tại tab '{tab_name}'!")
                        except Exception as scan_err:
                            print(f"[WARNING] Lỗi khi quét tìm tile trong tab '{tab_name}': {scan_err}")
                        
                        if is_visible_on_ui:
                            break
                except Exception as tab_err:
                    print(f"[WARNING] Lỗi khi quét tab '{tab_name}': {tab_err}")
        
        if not is_visible_on_ui:
            if sbc_count > 0:
                print(f"[INFO] SBC '{original_sbc_name}' không còn xuất hiện trên giao diện nữa (đã hoàn thành hết lượt khả dụng). Kết thúc bước SBC này.")
                is_finished = True
                break
            else:
                error_msg = f"Không tìm thấy SBC '{original_sbc_name}' trên giao diện sau khi thử mọi cách!"
                print(f"[ERROR] {error_msg}")
                alert_user_error(page, config, error_msg)
                print("[WARNING] Bỏ qua tác vụ SBC này...")
                is_finished = False
                break
        
        sbc_name = original_sbc_name
        resolved_sbc = True
        
        avail_repeats = get_sbc_repeats(tile_locator)
        if avail_repeats is not None:
            if avail_repeats == 0:
                print(f"[INFO] SBC '{original_sbc_name}' trên giao diện đã hết số lượt làm lại (Repeatable = 0). Kết thúc bước SBC.")
                is_finished = True
                break
            if sbc_count == 0:
                new_max = min(max_repeats, avail_repeats)
                print(f"[INFO] Xác định số lượt repeatable khả dụng trên UI: {avail_repeats}. Cấu hình max_repeats: {max_repeats}. Thiết lập chạy: {new_max} lượt.")
                max_repeats = new_max
                if max_repeats <= 0:
                    print(f"[INFO] Số lượt cần làm <= 0. Bỏ qua SBC '{original_sbc_name}'.")
                    is_finished = True
                    break
            else:
                print(f"[INFO] Lượt chạy {sbc_count + 1}/{max_repeats}. Số lượt repeatable còn lại phát hiện trên UI: {avail_repeats}")
        else:
            print(f"[WARNING] Lượt chạy {sbc_count + 1}/{max_repeats}. Không thể quét số lượt repeatable từ giao diện. Chạy tiếp tục.")
  
        print(f"[INFO] Đang click vào SBC '{sbc_name}'...")
        try:
            dismiss_modals(page)
            
            # Chờ một chút để Web App hoàn tất việc bind các event listener sau khi render tile
            sleep_human_like(1.5, 2.5, page)
            
            # Danh sách các phương thức và tọa độ click thử nghiệm để đảm bảo click mở được SBC thành công
            click_attempts = [
                {"x": 80, "y": 50},   # Lượt 1: Click lệch lề trái vùng chữ tên SBC (vùng an toàn nhất)
                "js",                 # Lượt 2: Click bằng Javascript trực tiếp vào tile (Vũ khí tối thượng, bỏ qua mọi click shield/pointer-events)
                {"x": 100, "y": 60},  # Lượt 3: Lệch phải và xuống dưới một chút
                "text",               # Lượt 4: Click trực tiếp vào text_locator
                None                  # Lượt 5: Click vào tâm mặc định của tile
            ]
            
            builder_loaded = False
            for idx, attempt in enumerate(click_attempts):
                try:
                    wait_for_click_shield(page, timeout=3000)
                except Exception:
                    pass
                
                try:
                    if attempt == "js":
                        print(f"[RPA] Thử click vào tile '{sbc_name}' bằng Javascript (Lần thử {idx + 1})...")
                        tile_handle = tile_locator.element_handle(timeout=3000)
                        if tile_handle:
                            page.evaluate("el => el.click()", tile_handle)
                        else:
                            raise Exception("Không lấy được element handle của tile")
                    elif attempt == "text":
                        if text_locator is not None:
                            print(f"[RPA] Thử click vào text của SBC '{sbc_name}' (Lần thử {idx + 1})...")
                            text_locator.click(timeout=3000)
                    elif isinstance(attempt, dict):
                        print(f"[RPA] Thử click vào tile '{sbc_name}' tại tọa độ tương đối x={attempt['x']}, y={attempt['y']} (Lần thử {idx + 1})...")
                        tile_locator.click(position=attempt, timeout=3000)
                    else:
                        print(f"[RPA] Thử click vào tâm mặc định của tile '{sbc_name}' (Lần thử {idx + 1})...")
                        tile_locator.click(timeout=3000)
                except Exception as click_err:
                    print(f"[WARNING] Click lần thử {idx + 1} gặp lỗi: {click_err}")
                    try:
                        # Thử force click nếu click thường lỗi
                        if attempt == "text" and text_locator is not None:
                            text_locator.click(force=True)
                        elif isinstance(attempt, dict):
                            tile_locator.click(position=attempt, force=True)
                        elif attempt != "js":
                            tile_locator.click(force=True)
                    except Exception:
                        pass
                
                # Chờ Web App phản hồi và tải giao diện Builder (tăng thời gian chờ)
                sleep_human_like(2.0, 3.5, page)
                
                # Kiểm tra xem đã vào Builder chưa
                search_visible = False
                try:
                    search_input = page.locator("input[placeholder='Search'], .ut-sbc-hub-view input.search, .search input").first
                    if search_input.count() > 0 and search_input.is_visible():
                        search_visible = True
                except Exception:
                    pass
                
                if not search_visible:
                    builder_loaded = True
                    print(f"[OK] Đã chuyển sang màn hình SBC Builder thành công ở lần thử thứ {idx + 1}!")
                    break
            
            if not builder_loaded:
                print(f"[WARNING] Không thể vào SBC Builder cho '{sbc_name}'. Tiến hành reload lại trang Web App để sửa lỗi đơ giao diện...")
                try:
                    page.reload()
                    # Chờ trang tải lại và Dashboard xuất hiện
                    page.wait_for_selector(".ut-tab-bar", timeout=60000)
                    print("[OK] Đã reload trang thành công. Nạp lại PaleTools...")
                    page.evaluate(f"eval({json.dumps(paletools_js)})")
                    time.sleep(5)
                    dismiss_modals(page)
                    # Tạo lại overlay panel
                    ensure_bot_overlay(page)
                except Exception as reload_err:
                    print(f"[ERROR] Lỗi khi reload trang và nạp lại PaleTools: {reload_err}")
                
                raise Exception("Không thể chuyển sang màn hình SBC Builder sau tất cả các lượt thử click và đã thử reload trang")
            
            # Tự động phát hiện xem có cần cấu hình template hay không bằng cách check nút Build Using Template của PaleTools
            is_template_disabled = page.evaluate("""() => {
                const buttons = Array.from(document.querySelectorAll('button'));
                const tBtn = buttons.find(b => {
                    const txt = b.innerText.toLowerCase();
                    return txt.includes('template') || txt.includes('bằng mẫu') || txt.includes('plantilla') || txt.includes('modelo');
                });
                if (tBtn) {
                    return tBtn.disabled || tBtn.classList.contains('disabled') || tBtn.getAttribute('disabled') !== null;
                }
                return true;
            }""")
            
            if (sbc_count == 0 and config.get("setup_mode", False)) or is_template_disabled:
                if is_template_disabled:
                    print(f"[INFO] Nút 'Build Using Template' bị disabled hoặc không tìm thấy. Kích hoạt Setup Mode cho SBC '{sbc_name}'...")
                else:
                    print("[SETUP MODE] Đang hiển thị nút tương tác trên Chrome. Hãy cấu hình template trong PaleTools...")
                
                try:
                    page.evaluate("window.bot_setup_completed = false")
                except Exception:
                    pass
                
                setup_start = time.time()
                timeout = 600.0  # 10 phút
                printed_log = False
                
                while time.time() - setup_start < timeout:
                    try:
                        completed = page.evaluate("!!window.bot_setup_completed")
                        if completed:
                            print("[SETUP MODE] Đã xác nhận cấu hình xong. Tiếp tục chạy bot...")
                            break
                    except Exception:
                        pass
                    
                    # Vẽ lại nút nếu nó bị mất do Web App render lại
                    try:
                        has_btn = page.evaluate("!!document.getElementById('bot-resume-button')")
                        if not has_btn:
                            if not printed_log:
                                print("[SETUP MODE] Vẽ nút kích hoạt bot và chờ bạn cấu hình template trên giao diện Web App...")
                                printed_log = True
                            
                            page.evaluate("""() => {
                                const oldBtn = document.getElementById('bot-resume-button');
                                if (oldBtn) oldBtn.remove();
                                
                                const btn = document.createElement("button");
                                btn.id = "bot-resume-button";
                                btn.innerText = "★★★ BẤM VÀO ĐÂY SAU KHI CẤU HÌNH XONG TEMPLATE SBC ★★★";
                                btn.style.position = "fixed";
                                btn.style.top = "15px";
                                btn.style.left = "50%";
                                btn.style.transform = "translateX(-50%)";
                                btn.style.zIndex = "999999";
                                btn.style.padding = "15px 30px";
                                btn.style.backgroundColor = "#28a745";
                                btn.style.color = "white";
                                btn.style.border = "3px solid #fff";
                                btn.style.borderRadius = "8px";
                                btn.style.fontWeight = "bold";
                                btn.style.fontSize = "16px";
                                btn.style.cursor = "pointer";
                                btn.style.boxShadow = "0 8px 16px rgba(0,0,0,0.3)";
                                btn.style.transition = "all 0.3s ease";
                                
                                btn.onmouseover = () => { btn.style.backgroundColor = "#218838"; };
                                btn.onmouseout = () => { btn.style.backgroundColor = "#28a745"; };
                                
                                btn.onclick = () => {
                                    btn.innerText = "Đang kích hoạt bot...";
                                    btn.style.backgroundColor = "#d39e00";
                                    window.bot_setup_completed = true;
                                    setTimeout(() => { btn.remove(); }, 800);
                                };
                                document.body.appendChild(btn);
                            }""")
                    except Exception:
                        pass
                    
                    time.sleep(1.0)
                else:
                    print("[WARNING] Quá thời gian chờ cấu hình template (10 phút). Chạy tiếp tục.")
                
                sleep_human_like(1.5, 2.5, page)
        except Exception as e:
            print(f"[ERROR] Không thể chọn SBC '{sbc_name}': {e}")
            alert_user_error(page, config, f"Không thể tìm thấy SBC {sbc_name}")
            consecutive_errors += 1
            if consecutive_errors >= 3:
                print("[ERROR] Quá nhiều lỗi chọn SBC liên tiếp. Dừng bước SBC.")
                is_finished = False
                break
            continue
            
        page.focus("body")
        page.click("body", delay=100)
        
        sleep_human_like(delays.get("before_build_min", 1.5), delays.get("before_build_max", 3.0), page)
        
        print("[RPA] Nhấn phím 'T' để tự động điền template...")
        page.keyboard.press("t")
        
        sleep_human_like(delays.get("after_build_min", 2.5), delays.get("after_build_max", 4.5), page)
        
        # Kiểm tra xem đội hình có chứa cầu thủ Concept nào không hoặc trống/thiếu thẻ
        # (Ở đây ta cứ bấm 'T' xong là bấm 'S' thử submit trước. Nếu kẹt mới kiểm tra nguyên nhân)
        print("[RPA] Nhấn phím 'S' để thực hiện Submit...")
        page.keyboard.press("s")
        sleep_human_like(2.0, 3.0, page)
        
        # 1. Xử lý các hộp thoại xác nhận submit nếu xuất hiện (Submit Anyway, Confirm, v.v.)
        confirm_selectors = [
            "button:has-text('Submit Anyway')",
            "button:has-text('Tell Me Again')",
            ".ea-dialog-view button:has-text('Yes')",
            ".ea-dialog-view button:has-text('Ok')",
            ".ea-dialog-view button:has-text('Confirm')",
            ".ea-dialog-view button:has-text('Có')",
            ".ea-dialog-view button:has-text('Xác nhận')",
            "button:has-text('Ok')",
            "button:has-text('OK')"
        ]
        for c_sel in confirm_selectors:
            try:
                c_btn = page.locator(c_sel).first
                if c_btn.count() > 0 and c_btn.is_visible():
                    print(f"[RPA] Phát hiện hộp thoại xác nhận submit: '{c_btn.text_content().strip()}'. Đang click...")
                    c_btn.click()
                    sleep_human_like(1.5, 2.5, page)
                    break
            except Exception:
                pass
                
        # 2. Xác thực xem đã submit thành công chưa (Builder biến mất hoặc có nút Claim Rewards)
        submit_verified = False
        
        # Thử tìm và click Claim Rewards (nếu xuất hiện)
        try:
            claim_btn = page.locator("button:has-text('Claim Rewards')").first
            if claim_btn.count() > 0 and claim_btn.is_visible():
                print(f"[RPA] Đang bấm Claim Rewards cho lượt {sbc_count + 1}...")
                claim_btn.click()
                submit_verified = True
                sleep_human_like(2.0, 3.0, page)
        except Exception:
            pass
            
        # Kiểm tra xem đã quay về màn hình Favourites/SBC List chưa
        if not submit_verified:
            try:
                # Nếu không còn ở màn hình Squad Builder (ví dụ: không còn nút Back của Builder hoặc không còn sân bóng)
                # Hoặc nếu tìm thấy tiêu đề của danh sách SBC (Favourites)
                fav_btn = page.locator("button:has-text('Favourites')").first
                is_back_to_list = (fav_btn.count() > 0 and fav_btn.is_visible()) or (page.locator(".ut-squad-builder-value, .pitch, .squad-slot").count() == 0)
                if is_back_to_list:
                    submit_verified = True
            except Exception:
                pass
                
        # 3. Xử lý trường hợp chưa submit thành công (vẫn kẹt ở Builder)
        if not submit_verified:
            print("[INFO] Vẫn còn ở màn hình Builder sau khi Submit. Đang quét nguyên nhân...")
            
            # Chụp ảnh debug
            try:
                debug_screenshot_path = os.path.join(BASE_DIR, "logs", "submit_debug.png")
                page.screenshot(path=debug_screenshot_path)
                print(f"[INFO] Đã lưu ảnh chụp debug submit tại: {debug_screenshot_path}")
            except Exception:
                pass
                
            # Kiểm tra xem có Dialog báo lỗi không đủ điều kiện (Ineligible Squad do dính cầu thủ Concept/Loan)
            is_ineligible = False
            try:
                error_dialog = page.locator(".ea-dialog-view, .dialog-modal").filter(has_text=re.compile(r'(Ineligible Squad|Concept|Loan|Không đủ điều kiện|cannot be submitted)', re.IGNORECASE)).first
                if error_dialog.count() > 0 and error_dialog.is_visible():
                    is_ineligible = True
                    print(f"[WARNING] Phát hiện Dialog lỗi: SBC '{sbc_name}' không đủ điều kiện.")
                    
                    # Click đóng Dialog lỗi
                    ok_btn = error_dialog.locator("button, .btn-standard").filter(has_text=re.compile(r'^(Ok|OK|Confirm|Xác nhận)$', re.IGNORECASE)).first
                    if ok_btn.count() > 0 and ok_btn.is_visible():
                        ok_btn.click()
                    else:
                        page.keyboard.press("Escape")
                    sleep_human_like(1.5, 2.5, page)
            except Exception:
                pass
                
            # Kiểm tra xem có cầu thủ Concept thực tế trên sân không
            is_concept_detected = check_concept_players_in_squad(page)
            
            # Kiểm tra xem đội hình có bị trống trơn sau khi điền template không (lỗi No Players Found)
            is_squad_empty = False
            try:
                player_count = page.evaluate("""() => {
                    const slots = document.querySelectorAll('.pitch .player, .squad-slot .player, .pitch .player-card');
                    return slots.length;
                }""")
                if player_count == 0:
                    is_squad_empty = True
                    print("[WARNING] Đội hình trống trơn (0 cầu thủ).")
            except Exception:
                pass
                
            # Kiểm tra thông báo "No Players Found"
            is_no_players_toast = False
            try:
                toast_el = page.locator(".toast, .notification, [class*='toast'], [class*='notification'], .ut-toast, .ut-notification-bar").filter(has_text=re.compile(r'(No Players Found|Không tìm thấy cầu thủ|No players|No Players)', re.IGNORECASE)).first
                if toast_el.count() > 0 and toast_el.is_visible():
                    is_no_players_toast = True
                    print(f"[WARNING] Phát hiện Toast lỗi: '{toast_el.text_content().strip()}'.")
            except Exception:
                pass
                
            # Nếu thực sự do thiếu thẻ (Concept, Trống, hoặc Toast báo)
            if is_concept_detected or is_squad_empty or is_no_players_toast or is_ineligible:
                if supply_pack_name and consecutive_supplies < 3:
                    print(f"[INFO] Xác định thiếu thẻ bài. Đang thoát Builder để mở pack cứu tế (Lần {consecutive_supplies + 1}/3)...")
                    try:
                        page.keyboard.press("Escape")
                        sleep_human_like(1.5, 2.5, page)
                        back_btn = page.locator(".ut-navigation-bar button.ut-navigation-button-control--prev, .ut-navigation-bar button.back, button:has-text('◀')").first
                        if back_btn.count() > 0 and back_btn.is_visible():
                            back_btn.click()
                            sleep_human_like(1.5, 2.5, page)
                    except Exception:
                        pass
                        
                    print(f"[INFO] Thử mở 1 pack tiếp tế '{supply_pack_name}'...")
                    opened = open_single_supply_pack(page, config, paletools_js, supply_pack_name)
                    if opened:
                        consecutive_supplies += 1  # Tăng số lần tiếp tế liên tiếp
                        print(f"[OK] Đã mở thành công pack tiếp tế. Quay lại làm tiếp SBC '{sbc_name}'...")
                        continue
                        
                # Nếu không có pack cứu tế hoặc đã cứu tế 3 lần liên tiếp rồi mà vẫn thiếu thẻ
                print(f"[INFO] Tự động dừng làm SBC '{sbc_name}' do đã hết cầu thủ hợp lệ hoặc đã dùng hết lượt mở cứu tế liên tiếp.")
                is_finished = False
                break
                
            # Nếu không phải thiếu thẻ (lỗi lag mạng hoặc kẹt thông thường)
            print(f"[WARNING] Lượt {sbc_count + 1} chưa được submit thành công (lag mạng hoặc lỗi kẹt).")
            consecutive_errors += 1
            if consecutive_errors >= 3:
                print("[ERROR] Quá nhiều lỗi submit liên tiếp. Dừng bước SBC này.")
                is_finished = False
                break
            continue
            
        # 4. Submit thành công
        sbc_count += 1
        completed_sbcs_total += 1
        consecutive_errors = 0
        consecutive_supplies = 0  # Reset số lần tiếp tế liên tiếp khi làm thành công
        print(f"[OK] Đã hoàn thành lượt {sbc_count}.")
        if on_success_cb:
            try:
                on_success_cb()
            except Exception as cb_err:
                print(f"[WARNING] Lỗi khi gọi callback lưu trạng thái SBC: {cb_err}")
            
        if sbc_count < max_repeats:
            sleep_human_like(delays.get("after_submit_min", 1.5), delays.get("after_submit_max", 3.0), page)
        else:
            time.sleep(0.3)
            
        if completed_sbcs_total % delays.get("batch_size", 10) == 0 and sbc_count < max_repeats:
            rest_time = delays.get("batch_rest_seconds", 60)
            print(f"[INFO] Tạm nghỉ để tránh bị ban tài khoản: {rest_time}s...")
            time.sleep(rest_time)
            
    # Chỉ gán is_finished = True nếu hoàn thành đủ max_repeats
    if sbc_count >= max_repeats:
        is_finished = True
    print(f"[SBC] Hoàn thành bước SBC: {sbc_name} ({sbc_count} lần thành công).")
    
    # Cuối cùng kiểm tra và dọn dẹp popup claim reward nếu còn sót
    print("[RPA] Kiểm tra hộp thoại Claim Rewards còn chờ...")
    try:
        claim_btn = page.locator("button:has-text('Claim Rewards')").first
        if claim_btn.count() > 0 and claim_btn.is_visible():
            print("[RPA] Đang click Claim Rewards...")
            claim_btn.click()
            sleep_human_like(2.0, 3.0, page)
            page.keyboard.press("Escape")
            sleep_human_like(0.5, 1.0, page)
    except Exception:
        pass
        
    return sbc_count, completed_sbcs_total, is_finished
