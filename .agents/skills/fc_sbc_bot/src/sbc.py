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
                            # Đã xong các squad (ví dụ 1/1), nhưng nếu là repeatable thì vẫn có thể làm lại
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
        completed_keywords = [
            "đã hoàn thành", "đã làm", 
            "expired", "đã hết hạn", "repeatable: 0", "repeat: 0", 
            "0 repeatable", "0 left", "0 repeats"
        ]
        for kw in completed_keywords:
            if kw in tile_text_lower:
                print(f"[DEBUG_SBC]   Khớp từ khóa completed: '{kw}'. Trả về 0.")
                return 0

    except Exception as e:
        print(f"[WARNING] Lỗi khi phân tích số lượt repeatable: {e}")
    print(f"[DEBUG_SBC]   Không xác định được số lượt repeatable từ UI. Trả về None.")
    return None

def execute_sbc_step(page, config, paletools_js, sbc_name, max_repeats, completed_sbcs_total, supply_pack_name=None):
    delays = config.get("delays", {})
    original_sbc_name = sbc_name
    print(f"\n[SBC] Bắt đầu tác vụ SBC: {sbc_name} (Lặp tối đa: {max_repeats if max_repeats != 999999 else 'Không giới hạn'})")
    
    sbc_count = 0
    consecutive_errors = 0
    is_finished = False
    
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
                
                # Inject nút bấm tương tác vào giao diện Web App
                page.evaluate("""() => {
                    // Xóa nút cũ nếu có
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
                        setTimeout(() => { btn.remove(); }, 800);
                    };
                    document.body.appendChild(btn);
                }""")
                
                # Chờ cho đến khi nút biến mất (do người dùng click)
                try:
                    page.wait_for_selector("#bot-resume-button", state="detached", timeout=600000)
                    print("[SETUP MODE] Đã xác nhận cấu hình xong. Tiếp tục chạy bot...")
                except Exception as wait_ex:
                    print(f"[WARNING] Quá thời gian chờ cấu hình template: {wait_ex}")
                
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
        
        # Kiểm tra xem đội hình có chứa cầu thủ Concept nào không trước khi bấm Submit
        is_concept_detected = check_concept_players_in_squad(page)
        is_ineligible = False
        
        if is_concept_detected:
            is_ineligible = True
            print("[INFO] Đội hình chứa cầu thủ Concept. Đang quay lại danh sách SBC để tiếp tế thẻ...")
            try:
                page.keyboard.press("Escape")
                sleep_human_like(1.5, 2.5, page)
                # Đề phòng kẹt, bấm nút Back của Web App
                back_btn = page.locator(".ut-navigation-bar button.ut-navigation-button-control--prev, .ut-navigation-bar button.back").first
                if back_btn.count() > 0 and back_btn.is_visible():
                    back_btn.click()
                    sleep_human_like(1.5, 2.5, page)
            except Exception as back_err:
                print(f"[WARNING] Lỗi khi bấm Back để thoát Builder: {back_err}")
        else:
            print("[RPA] Nhấn phím 'S' để Submit...")
            page.keyboard.press("s")
            
            # Chụp ảnh debug trạng thái submit
            time.sleep(1.0)
            try:
                debug_screenshot_path = os.path.join(BASE_DIR, "logs", "submit_debug.png")
                page.screenshot(path=debug_screenshot_path)
                print(f"[INFO] Đã lưu ảnh chụp debug submit tại: {debug_screenshot_path}")
            except Exception as de_ex:
                print(f"[WARNING] Không thể chụp ảnh debug submit: {de_ex}")
            
            # 1. Kiểm tra hộp thoại báo lỗi không đủ điều kiện (Ineligible Squad do dính cầu thủ Concept/Loan từ EA)
            try:
                dialog_el = page.locator(".ea-dialog-view, .dialog-modal").first
                if dialog_el.count() > 0 and dialog_el.is_visible():
                    d_text = dialog_el.text_content().lower()
                    if any(kw in d_text for kw in ["ineligible squad", "concept", "loan", "cannot be submitted", "không đủ điều kiện"]):
                        is_ineligible = True
                        print(f"[WARNING] SBC '{sbc_name}' chứa cầu thủ Concept/Loan hoặc không đủ điều kiện (hết cầu thủ thực trong CLB).")
                        ok_btn = dialog_el.locator("button:has-text('Ok'), button:has-text('OK'), button.close").first
                        if ok_btn.count() > 0 and ok_btn.is_visible():
                            ok_btn.click()
                        else:
                            page.keyboard.press("Escape")
                        sleep_human_like(1.0, 1.5, page)
                        page.keyboard.press("Escape")
                        sleep_human_like(1.5, 2.0, page)
            except Exception:
                pass

        if is_ineligible:
            if supply_pack_name:
                print(f"[INFO] Thiếu thẻ cho SBC '{sbc_name}'. Thử mở 1 pack tiếp tế '{supply_pack_name}'...")
                opened = open_single_supply_pack(page, config, paletools_js, supply_pack_name)
                if opened:
                    print(f"[OK] Đã mở thành công pack tiếp tế. Quay lại làm tiếp SBC '{sbc_name}'...")
                    continue
            print(f"[INFO] Tự động dừng làm SBC '{sbc_name}' do đã hết cầu thủ hợp lệ trong CLB.")
            is_finished = True
            break

        confirm_selectors = [
            "button:has-text('Submit Anyway')",
            "button:has-text('Tell Me Again')",
            ".ea-dialog-view button:has-text('Yes')",
            ".ea-dialog-view button:has-text('Ok')",
            ".ea-dialog-view button:has-text('Confirm')",
            ".ea-dialog-view button:has-text('Có')",
            ".ea-dialog-view button:has-text('Xác nhận')"
        ]
        dialog_found = False
        for c_sel in confirm_selectors:
            try:
                c_btn = page.locator(c_sel).first
                if c_btn.count() > 0 and c_btn.is_visible():
                    print(f"[RPA] Phát hiện hộp thoại xác nhận submit: '{c_btn.text_content().strip()}'. Đang click...")
                    c_btn.click()
                    dialog_found = True
                    sleep_human_like(1.5, 2.5, page)
                    break
            except Exception:
                pass
        
        # Kiểm tra thông báo lỗi màu đỏ (negative notifications) từ Web App
        submit_success = True
        try:
            error_notif = page.locator(".notification.negative, .ut-notification-bar.negative").first
            if error_notif.count() > 0 and error_notif.is_visible():
                err_text = error_notif.text_content().strip() if error_notif.text_content() else "Lỗi không xác định"
                print(f"[ERROR] Phát hiện lỗi submit từ Web App: '{err_text}'")
                submit_success = False
        except Exception:
            pass

        # Kiểm tra xem có modal container nào hiển thị không
        is_modal_visible = False
        try:
            modal = page.locator(".view-modal-container, .ea-dialog-view").first
            if modal.count() > 0 and modal.is_visible():
                is_modal_visible = True
        except Exception:
            pass

        # Nếu vẫn còn nút Submit hiển thị và click được trên giao diện, và KHÔNG có modal nào che khuất
        if submit_success and not is_modal_visible:
            try:
                submit_btn = page.locator("button:has-text('Submit'), button.submit, .sbc-submit-button").first
                if submit_btn.count() > 0 and submit_btn.is_visible() and submit_btn.is_enabled():
                    print("[RPA] Phím tắt 's' có vẻ không hoạt động hoặc kẹt. Thử click trực tiếp nút Submit trên UI...")
                    submit_btn.click()
                    sleep_human_like(1.2, 1.8, page)
                    
                    # Quét lại dialog một lần nữa sau khi click trực tiếp
                    for c_sel in confirm_selectors:
                        c_btn = page.locator(c_sel).first
                        if c_btn.count() > 0 and c_btn.is_visible():
                            print(f"[RPA] Phát hiện hộp thoại xác nhận sau khi click Submit: '{c_btn.text_content().strip()}'. Đang click...")
                            c_btn.click()
                            sleep_human_like(1.5, 2.5, page)
                            break
            except Exception as click_ex:
                print(f"[WARNING] Không thể click nút Submit trên UI: {click_ex}")

        # Xác thực xem đã thực sự submit thành công hay chưa
        submit_verified = False
        if submit_success:
            # 1. Thử tìm và click Claim Rewards (nếu xuất hiện)
            try:
                claim_btn = page.locator("button:has-text('Claim Rewards')").first
                if claim_btn.count() > 0 and claim_btn.is_visible():
                    print(f"[RPA] Đang bấm Claim Rewards cho lượt {sbc_count + 1}...")
                    claim_btn.click()
                    submit_verified = True
                    sleep_human_like(2.0, 3.0, page)
            except Exception:
                pass

            # 2. Kiểm tra xem giao diện đã tự động quay về màn hình Favourites chưa
            if not submit_verified:
                is_back_to_list = False
                try:
                    fav_btn = page.locator("button:has-text('Favourites')").first
                    if fav_btn.count() > 0 and fav_btn.is_visible():
                        is_back_to_list = True
                except Exception:
                    pass
                
                if is_back_to_list:
                    print(f"[OK] Submit thành công lượt {sbc_count + 1} (Giao diện tự động quay lại danh sách).")
                    submit_verified = True

        # Xử lý kết quả xác thực
        if submit_verified:
            sbc_count += 1
            completed_sbcs_total += 1
            consecutive_errors = 0  # Reset số lỗi liên tiếp
            print(f"[OK] Đã hoàn thành lượt {sbc_count}.")
        else:
            print(f"[WARNING] Lượt {sbc_count + 1} chưa được submit thành công (vẫn kẹt ở màn hình build squad hoặc có lỗi).")
            try:
                page.keyboard.press("Escape")
            except Exception:
                pass
            sleep_human_like(2.0, 3.0, page)
            consecutive_errors += 1
            if consecutive_errors >= 3:
                print("[ERROR] Quá nhiều lỗi submit liên tiếp. Dừng bước SBC.")
                is_finished = False
                break
            continue
            
        if sbc_count < max_repeats:
            sleep_human_like(delays.get("after_submit_min", 1.5), delays.get("after_submit_max", 3.0), page)
        else:
            time.sleep(0.3)
            
        if completed_sbcs_total % delays.get("batch_size", 10) == 0 and sbc_count < max_repeats:
            rest_time = delays.get("batch_rest_seconds", 60)
            print(f"[INFO] Tạm nghỉ để tránh bị ban tài khoản: {rest_time}s...")
            time.sleep(rest_time)
            
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
