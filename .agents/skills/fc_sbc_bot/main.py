import os
import sys
import time
import json
import random
import urllib.parse
import requests
from playwright.sync_api import sync_playwright

def global_exception_handler(exctype, value, tb):
    if "closed" in str(value).lower() or "target" in str(value).lower():
        print("\n[INFO] Trình duyệt đã bị đóng đột ngột (bởi người dùng hoặc hệ thống). Dừng bot an toàn.")
    else:
        sys.__excepthook__(exctype, value, tb)

import sys
sys.excepthook = global_exception_handler

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PALETOOLS_PATH = os.path.join(BASE_DIR, "paletools.txt")

def sleep_human_like(min_sec, max_sec):
    delay = random.uniform(min_sec, max_sec)
    time.sleep(delay)

def alert_user_error(page, config, message):
    print(f"\n[ALERT] ERROR OR MANUAL INTERVENTION REQUIRED: {message}")
    
    # 1. Chụp ảnh màn hình để debug
    try:
        screenshot_path = os.path.join(BASE_DIR, "error_screenshot.png")
        page.screenshot(path=screenshot_path)
        print(f"[INFO] Đã lưu ảnh chụp lỗi tại: {screenshot_path}")
    except Exception as se:
        print(f"[WARNING] Không thể chụp ảnh màn hình: {se}")

    # 2. Alert sound on macOS
    if sys.platform == "darwin":
        os.system("say 'Attention, error detected'")
        os.system("afplay /System/Library/Sounds/Glass.aiff &")
        
    # 3. Send Telegram Webhook notification
    telegram_cfg = config.get("telegram", {})
    if telegram_cfg.get("enabled", False):
        bot_token = telegram_cfg.get("bot_token")
        chat_id = telegram_cfg.get("chat_id")
        if bot_token and chat_id and chat_id != "YOUR_CHAT_ID":
            try:
                text_msg = f"[FC SBC Bot Alert] {message}"
                send_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
                requests.post(send_url, json={"chat_id": chat_id, "text": text_msg}, timeout=10)
                
                # Send photo
                if os.path.exists(screenshot_path):
                    send_photo_url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"
                    with open(screenshot_path, "rb") as photo:
                        requests.post(send_photo_url, data={"chat_id": chat_id}, files={"photo": photo}, timeout=15)
            except Exception as te:
                print(f"[WARNING] Could not send Telegram alert: {te}")

def check_captcha_or_errors(page, config):
    # Check for captcha or EA dialog
    captcha_selectors = [
        "iframe[src*='arkoselabs']", 
        ".ea-dialog-view:has-text('Verification')", 
        ".ea-dialog-view:has-text('Security Challenge')",
        ".ea-dialog-view:has-text('Captcha')"
    ]
    
    is_captcha_detected = False
    for selector in captcha_selectors:
        try:
            if page.locator(selector).count() > 0:
                is_captcha_detected = True
                break
        except Exception:
            pass
            
    if is_captcha_detected:
        alert_user_error(page, config, "Captcha detected from EA Web App!")
        print("\n[PAUSED] Please solve captcha in Chrome browser. Once done, press [ENTER] here to continue...")
        input()
        print("[INFO] Resuming...")
        sleep_human_like(2.0, 3.0)

def wait_for_click_shield(page, timeout=20000):
    try:
        shield = page.locator(".ut-click-shield")
        if shield.count() > 0:
            try:
                shield.wait_for(state="hidden", timeout=timeout)
                print("[INFO] Click shield đã ẩn. Sẵn sàng tương tác.")
            except Exception:
                pass
    except Exception:
        pass
    time.sleep(1.0)

def handle_unassigned_items(page, config):
    print("[RPA] Bắt đầu xử lý vật phẩm unassigned sau khi mở pack...")
    time.sleep(3.0)  # Đợi màn hình mở pack hoàn tất hiển thị các cầu thủ
    
    # 1. Thử gửi vật phẩm không trùng lặp vào Club bằng phím Space (Shortcut của PaleTools)
    print("[RPA] Thử gửi vật phẩm không trùng vào Club (nhấn Space)...")
    page.keyboard.press("Space")
    time.sleep(2.0)
    
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
                    time.sleep(2.0)
                    
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
                                time.sleep(1.5)
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
                    time.sleep(2.0)
                    break
        except Exception:
            pass
            
    # Cuối cùng, thử nhấn Space một lần nữa để dọn dẹp nốt nếu còn sót
    page.keyboard.press("Space")
    time.sleep(1.5)
    print("[RPA] Đã hoàn thành dọn dẹp vật phẩm unassigned.")
    
    # Chủ động quay lại My Packs bằng phím tắt "1" của PaleTools
    try:
        print("[RPA] Nhấn phím '1' để quay lại My Packs (Shortcut PaleTools)...")
        page.keyboard.press("1")
        time.sleep(2.0)
        
        # Nếu nhấn phím '1' mà vẫn chưa về My Packs, thử click tab Store để fallback
        if not is_in_my_packs(page):
            print("[WARNING] Nhấn phím '1' chưa về My Packs. Thử click tab Store để fallback...")
            store_tab = page.locator(".ut-tab-bar-item.icon-store")
            if store_tab.count() > 0:
                store_tab.click()
                time.sleep(2.5)
    except Exception as e:
        print(f"[WARNING] Lỗi khi quay lại Store/My Packs: {e}")

def load_paletools_js():
    txt_path = os.path.join(BASE_DIR, "paletools.txt")
    if os.path.exists(txt_path):
        print("[INFO] Found paletools.txt. Filtering clean source code...")
        with open(txt_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
            
        content = ""
        for line in lines:
            line_str = line.strip()
            if line_str.lower().startswith("javascript:") or line_str.startswith("function") or len(line_str) > 1000:
                content = line_str
                break
                
        if not content:
            content = "".join(lines).strip()
            
        if content.lower().startswith("javascript:"):
            content = content[len("javascript:"):]
            
        return urllib.parse.unquote(content)

    print("[ERROR] Could not find paletools.txt! Please prepare this file.")
    sys.exit(1)

def ensure_paletools_injected(page, paletools_js):
    try:
        # Kiểm tra xem PaleTools đã hiển thị trên UI chưa (có tab PaleTools ở menu trái)
        is_active = page.evaluate("!!document.querySelector('.icon-paletools, [class*=\"paletools\"], [id*=\"paletools\"]')")
        if not is_active:
            print("[INFO] PaleTools chưa được kích hoạt trên giao diện. Đang tiến hành inject...")
            page.evaluate(f"eval({json.dumps(paletools_js)})")
            time.sleep(5)
            try:
                page.evaluate("document.title = '★★★ BOT CHROME WINDOW - THAO TAC TAI DAY ★★★'")
            except Exception:
                pass
            
            # Đợi thêm một chút để PaleTools load giao diện
            try:
                page.wait_for_selector(".icon-paletools", timeout=8000)
                print("[OK] Đã kích hoạt PaleTools thành công trên giao diện.")
            except Exception:
                print("[WARNING] PaleTools đã inject nhưng biểu tượng menu chưa xuất hiện.")
        else:
            # Nếu đối tượng JS bị mất nhưng UI vẫn còn (rất hiếm), kiểm tra xem có cần nạp lại không
            is_js_ok = page.evaluate("typeof paletools !== 'undefined' || typeof paleJesus !== 'undefined'")
            if not is_js_ok:
                page.evaluate(f"eval({json.dumps(paletools_js)})")
                time.sleep(3)
    except Exception as e:
        print(f"[WARNING] Không thể kiểm tra hoặc inject lại PaleTools: {e}")

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
            
    # Nếu không tìm thấy class cụ thể, thử parse từ text_content của toàn bộ tile
    try:
        tile_text = tile.text_content()
        if tile_text:
            # Loại bỏ tên pack ra khỏi text của tile
            remaining_text = tile_text.replace(pack_name, "").strip()
            # Tìm tất cả các số độc lập trong remaining_text
            import re
            numbers = re.findall(r'\b\d+\b', remaining_text)
            if numbers:
                quantity = int(numbers[0])
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
            
    # 3. Partial match (target inside available, or available inside target)
    for name in available_names:
        if target_name.lower() in name.lower() or name.lower() in target_name.lower():
            return name
            
    return None

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

    print("\n[STORE] Navigating to Store to open packs...")
    try:
        # Kiểm tra xem có đang ở Store chính không, nếu không thì click tab Store
        store_tab = page.locator(".ut-tab-bar-item.icon-store")
        if store_tab.count() > 0:
            store_tab.click()
            wait_for_click_shield(page)
            time.sleep(2.0)

        # Chụp ảnh debug Store chính
        try:
            store_debug_path = os.path.join(BASE_DIR, "store_debug.png")
            page.screenshot(path=store_debug_path)
            print(f"[INFO] Đã chụp ảnh debug Store chính tại: {store_debug_path}")
        except Exception as se_ex:
            print(f"[WARNING] Không thể chụp ảnh debug Store: {se_ex}")

        # Định vị tile Packs hoặc nút bấm bên trong nó
        packs_tile = page.locator(".tile.packs-tile button, .tile.packs-tile .btn-standard, .tile.packs-tile h1, .tile.packs-tile .tileHeader, .tile.packs-tile").first
        packs_tile.wait_for(state="visible", timeout=15000)
        
        # Đưa trang lên phía trước để nhận event click tốt hơn
        try:
            page.bring_to_front()
        except Exception:
            pass
        
        print("[INFO] Tiến hành click vào ô Packs (thử tối đa 5 lần)...")
        success_transition = False
        
        for attempt in range(1, 6):
            print(f"[INFO] Thử click vào ô Packs lần {attempt}...")
            try:
                packs_tile.click(timeout=2000)
            except Exception:
                pass
            
            # Dispatch Mouse/Pointer Events bằng JS để mô phỏng click thật
            try:
                el = packs_tile.element_handle()
                if el:
                    page.evaluate("""el => {
                        const events = ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click'];
                        events.forEach(evtName => {
                            el.dispatchEvent(new MouseEvent(evtName, {
                                bubbles: true,
                                cancelable: true,
                                view: window
                            }));
                        });
                        
                        // Thử click cả thẻ con (nếu có)
                        const child = el.querySelector('h1, .tileHeader, div');
                        if (child) {
                            events.forEach(evtName => {
                                child.dispatchEvent(new MouseEvent(evtName, {
                                    bubbles: true,
                                    cancelable: true,
                                    view: window
                                }));
                            });
                        }
                    }""", el)
            except Exception:
                pass
            
            # Chờ click shield ẩn
            wait_for_click_shield(page, timeout=3000)
            
            # Kiểm tra xem đã chuyển sang trang Packs thành công chưa
            if is_in_my_packs(page):
                print("[OK] Đã chuyển trang Packs thành công!")
                success_transition = True
                break
        
        if not success_transition:
            print("\n============================================================")
            print("[REQUEST] Bot không thể click tự động vào ô 'Packs' do xung đột giao diện.")
            print("Vui lòng tự click vào ô 'Packs' trên trình duyệt Chrome.")
            print("Sau khi đã vào trang danh sách Packs, quay lại đây và nhấn [ENTER] để tiếp tục...")
            print("============================================================\n")
            alert_user_error(page, config, "Vui lòng click vào ô Packs trên trình duyệt")
            input()
            return True
            
        return True
    except Exception as e:
        print(f"[ERROR] Error navigating to Store: {e}")
        alert_user_error(page, config, "Error entering Store -> My Packs")
        return False

def run():
    config_path = os.path.join(BASE_DIR, "config.json")
    if not os.path.exists(config_path):
        print("[ERROR] Could not find config.json!")
        sys.exit(1)
        
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
    except json.JSONDecodeError as jde:
        print(f"[ERROR] config.json có lỗi cú pháp JSON: {jde}")
        sys.exit(1)
    except Exception as e:
        print(f"[ERROR] Không thể đọc config.json: {e}")
        sys.exit(1)
        
    # Validate cấu trúc config.json
    target_sbcs = config.get("target_sbcs")
    if target_sbcs is not None:
        if not isinstance(target_sbcs, list):
            print("[ERROR] Cấu hình 'target_sbcs' trong config.json phải là một danh sách (list).")
            sys.exit(1)
        for idx, sbc in enumerate(target_sbcs):
            if not isinstance(sbc, dict):
                print(f"[ERROR] Mục thứ {idx+1} trong 'target_sbcs' phải là một đối tượng (dict).")
                sys.exit(1)
            if "name" not in sbc:
                print(f"[ERROR] Mục thứ {idx+1} trong 'target_sbcs' thiếu trường bắt buộc 'name'.")
                sys.exit(1)
            if not isinstance(sbc["name"], str) or not sbc["name"].strip():
                print(f"[ERROR] Trường 'name' trong SBC thứ {idx+1} phải là một chuỗi văn bản không được để trống.")
                sys.exit(1)
                
    target_packs = config.get("target_packs")
    if target_packs is not None:
        if not isinstance(target_packs, list):
            print("[ERROR] Cấu hình 'target_packs' trong config.json phải là một danh sách (list).")
            sys.exit(1)
        for idx, pack in enumerate(target_packs):
            if not isinstance(pack, str) or not pack.strip():
                print(f"[ERROR] Tên Pack thứ {idx+1} trong 'target_packs' phải là một chuỗi văn bản không được để trống.")
                sys.exit(1)
        
    paletools_js = load_paletools_js()
    
    print("=== STARTING FC ULTIMATE TEAM SBC BOT ===")
    
    with sync_playwright() as p:
        user_data_dir = os.path.join(BASE_DIR, "chrome_profile")
        if not os.path.exists(user_data_dir):
            os.makedirs(user_data_dir)
            
        context = None
        try:
            print("[INFO] Opening Google Chrome with profile (Persistent Context)...")
            context = p.chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                headless=False,
                channel="chrome",
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox"
                ],
                viewport={"width": 1280, "height": 800},
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
        except Exception as e:
            print(f"[WARNING] Could not launch Chrome with profile ({e}).")
            print("[INFO] Falling back to default Playwright Chromium with profile...")
            try:
                context = p.chromium.launch_persistent_context(
                    user_data_dir=user_data_dir,
                    headless=False,
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--no-sandbox"
                    ],
                    viewport={"width": 1280, "height": 800}
                )
            except Exception as e2:
                print(f"[ERROR] Failed to start browser: {e2}")
                sys.exit(1)
        
        context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        # Đóng tất cả các tab phụ để tránh xung đột tab ẩn
        while len(context.pages) > 1:
            try:
                context.pages[-1].close()
            except Exception:
                break
        page = context.pages[0] if context.pages else context.new_page()
        
        print("[INFO] Loading EA Sports FC Ultimate Team Web App...")
        page.goto("https://www.ea.com/ea-sports-fc/ultimate-team/web-app/")
        try:
            page.evaluate("document.title = '★★★ BOT CHROME WINDOW - THAO TAC TAI DAY ★★★'")
        except Exception:
            pass
        
        print("\n============================================================")
        print("[REQUEST] Please login and verify 2FA on the opened Chrome window.")
        print("Once you reach the Web App Dashboard, the bot will automatically proceed.")
        print("============================================================\n")
        
        print("[INFO] Monitoring login status...")
        try:
            page.wait_for_selector(".ut-tab-bar", timeout=300000)
            print("[OK] Dashboard detected. Activating PaleTools...")
            sleep_human_like(3.0, 5.0)
        except Exception as e:
            print(f"[ERROR] Error waiting for Dashboard: {e}")
            alert_user_error(page, config, "Error loading Web App dashboard")
            
        try:
            page.evaluate(f"eval({json.dumps(paletools_js)})")
            print("[OK] PaleTools injected successfully. Waiting 5s for startup...")
            time.sleep(5)
            try:
                page.evaluate("document.title = '★★★ BOT CHROME WINDOW - THAO TAC TAI DAY ★★★'")
            except Exception:
                pass
        except Exception as e:
            print(f"[ERROR] Could not inject PaleTools: {e}")
            alert_user_error(page, config, "Failed to inject PaleTools.")
            sys.exit(1)
            
        completed_sbcs_total = 0
        delays = config.get("delays", {})
        
        for sbc in config.get("target_sbcs", []):
            original_sbc_name = sbc.get("name")
            sbc_name = original_sbc_name
            max_repeats = sbc.get("max_repeats", 1)
            print(f"\n[SBC] Starting SBC task: {sbc_name} (Repeats: {max_repeats})")
            
            sbc_count = 0
            consecutive_errors = 0
            while sbc_count < max_repeats:
                resolved_sbc = False
                check_captcha_or_errors(page, config)
                print(f"[INFO] Starting SBC repeat {sbc_count + 1}/{max_repeats}...")
                
                print("[INFO] Navigating to SBC menu...")
                try:
                    page.wait_for_selector(".ut-tab-bar-item.icon-sbc", timeout=15000)
                    page.click(".ut-tab-bar-item.icon-sbc")
                    sleep_human_like(1.5, 2.5)
                    
                    page.wait_for_selector("button:has-text('Favourites')", timeout=15000)
                    page.click("button:has-text('Favourites')")
                    sleep_human_like(3.0, 4.5)
                except Exception as e:
                    print(f"[ERROR] Could not navigate to SBC Favourites at repeat {sbc_count + 1}: {e}")
                    alert_user_error(page, config, "Error navigating to SBC Favourites")
                    consecutive_errors += 1
                    if consecutive_errors >= 3:
                        print("[ERROR] Quá nhiều lỗi điều hướng liên tiếp. Dừng bot để bảo vệ tài khoản.")
                        sys.exit(1)
                    continue
                
                # Định vị tile SBC thực sự hiển thị trên giao diện Favourites
                import re
                tile_locator = page.locator(".tile:visible, .sbc-tile:visible, .sbcItem:visible, .ut-sbc-tile-view:visible").filter(has_text=re.compile(f"^{re.escape(original_sbc_name)}$", re.IGNORECASE)).first
                
                is_visible_on_ui = False
                try:
                    if tile_locator.count() > 0 and tile_locator.is_visible():
                        is_visible_on_ui = True
                except Exception:
                    pass

                if not is_visible_on_ui:
                    # Nếu thực sự không thấy SBC trên giao diện Favourites:
                    if sbc_count > 0:
                        print(f"[INFO] SBC '{original_sbc_name}' không còn xuất hiện trong Favourites nữa (đã hoàn thành hết lượt khả dụng). Chuyển sang bước tiếp theo...")
                        break
                    else:
                        error_msg = f"Không tìm thấy SBC '{original_sbc_name}' đang hiển thị trong Favourites!"
                        print(f"[ERROR] {error_msg}")
                        alert_user_error(page, config, error_msg)
                        print("[WARNING] Bỏ qua tác vụ SBC này để tiếp tục các tác vụ khác (hoặc mở Pack)...")
                        break
                
                sbc_name = original_sbc_name
                resolved_sbc = True
                
                if sbc_count == 0:
                    try:
                        avail_repeats = None
                        tile_text = tile_locator.text_content()
                        if tile_text:
                            match = re.search(r'[Rr]epeatable\s*:\s*(\d+)', tile_text)
                            if match:
                                avail_repeats = int(match.group(1))
                                print(f"[INFO] Quét thấy thông tin: '{sbc_name}' có Repeatable: {avail_repeats}")
                        
                        if avail_repeats is not None:
                            if avail_repeats < max_repeats:
                                print(f"[INFO] Giới hạn lại số lần chạy từ {max_repeats} xuống {avail_repeats} lượt repeatable khả dụng trên giao diện.")
                                max_repeats = avail_repeats
                            elif avail_repeats > max_repeats:
                                print(f"[INFO] Số lượt repeatable trên giao diện là {avail_repeats}, nhưng bot chỉ chạy tối đa {max_repeats} lần theo cấu hình.")
                    except Exception as re_ex:
                        print(f"[WARNING] Không thể tự động quét số lượt repeatable: {re_ex}")

                print(f"[INFO] Finding SBC '{sbc_name}' in Favourites...")
                try:
                    # Click vào tile bằng Playwright
                    tile_locator.click()
                    print(f"[OK] Selected SBC: {sbc_name} (Repeat {sbc_count + 1})")
                    sleep_human_like(2.0, 3.0)
                    
                    if sbc_count == 0 and config.get("setup_mode", False):
                        print("\n" + "="*60)
                        print("[SETUP MODE] Bot paused at SBC screen for template setup.")
                        print("Please configure SBC template in PaleTools on the browser.")
                        print("Once template is saved, return here and press [ENTER].")
                        print("="*60 + "\n")
                        input("Press [ENTER] after template setup in PaleTools to continue...")
                        sleep_human_like(1.5, 2.5)
                except Exception as e:
                    print(f"[ERROR] Could not select SBC '{sbc_name}': {e}")
                    alert_user_error(page, config, f"Could not find SBC {sbc_name} in Favourites")
                    consecutive_errors += 1
                    if consecutive_errors >= 3:
                        print("[ERROR] Quá nhiều lỗi chọn SBC liên tiếp. Dừng bot để bảo vệ tài khoản.")
                        sys.exit(1)
                    continue
                    
                page.focus("body")
                page.click("body", delay=100)
                
                sleep_human_like(delays.get("before_build_min", 1.5), delays.get("before_build_max", 3.0))
                
                print("[RPA] Pressing 'T' for auto-fill...")
                page.keyboard.press("t")
                
                sleep_human_like(delays.get("after_build_min", 2.5), delays.get("after_build_max", 4.5))
                
                print("[RPA] Pressing 'S' to Submit...")
                page.keyboard.press("s")
                
                # Chụp ảnh debug trạng thái submit
                time.sleep(1.0)
                try:
                    debug_screenshot_path = os.path.join(BASE_DIR, "submit_debug.png")
                    page.screenshot(path=debug_screenshot_path)
                    print(f"[INFO] Đã lưu ảnh chụp debug submit tại: {debug_screenshot_path}")
                except Exception as de_ex:
                    print(f"[WARNING] Không thể chụp ảnh debug submit: {de_ex}")
                
                # Đợi thêm một chút xem có dialog xác nhận xuất hiện không (ví dụ cảnh báo Active Squad)
                sleep_human_like(0.2, 0.8)
                confirm_selectors = [
                    "button:has-text('Submit Anyway')",
                    "button:has-text('Submit and Don\'t Tell Me Again')",
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
                            sleep_human_like(1.5, 2.5)
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
                            sleep_human_like(1.2, 1.8)
                            
                            # Quét lại dialog một lần nữa sau khi click trực tiếp
                            for c_sel in confirm_selectors:
                                c_btn = page.locator(c_sel).first
                                if c_btn.count() > 0 and c_btn.is_visible():
                                    print(f"[RPA] Phát hiện hộp thoại xác nhận sau khi click Submit: '{c_btn.text_content().strip()}'. Đang click...")
                                    c_btn.click()
                                    sleep_human_like(1.5, 2.5)
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
                            print(f"[RPA] Clicking Claim Rewards for repeat {sbc_count + 1}...")
                            claim_btn.click()
                            submit_verified = True
                            sleep_human_like(2.0, 3.0)
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
                    print(f"[OK] Completed repeat {sbc_count}.")
                else:
                    print(f"[WARNING] Lượt {sbc_count + 1} chưa được submit thành công (vẫn kẹt ở màn hình build squad hoặc có lỗi).")
                    try:
                        page.keyboard.press("Escape")
                    except Exception:
                        pass
                    sleep_human_like(2.0, 3.0)
                    consecutive_errors += 1
                    if consecutive_errors >= 3:
                        print("[ERROR] Quá nhiều lỗi submit liên tiếp. Dừng bot để bảo vệ tài khoản.")
                        sys.exit(1)
                    continue
                    
                if sbc_count < max_repeats:
                    sleep_human_like(delays.get("after_submit_min", 1.5), delays.get("after_submit_max", 3.0))
                else:
                    time.sleep(0.3)
                    
                if completed_sbcs_total % delays.get("batch_size", 10) == 0 and sbc_count < max_repeats:
                    rest_time = delays.get("batch_rest_seconds", 60)
                    print(f"[INFO] Rest interval to prevent ban: {rest_time}s...")
                    time.sleep(rest_time)
                    
            print(f"[SBC] Finished task: {sbc_name} ({sbc_count} times).")
            
        print("\n[RPA] Checking for any pending Claim Rewards dialog...")
        try:
            claim_btn = page.locator("button:has-text('Claim Rewards')").first
            claim_btn.wait_for(state="visible", timeout=4000)
            print("[RPA] Clicking Claim Rewards...")
            claim_btn.click()
            sleep_human_like(2.0, 3.0)
            page.keyboard.press("Escape")
            sleep_human_like(0.5, 1.0)
        except Exception:
            print("[INFO] No Claim Rewards dialog found. Proceeding.")
            page.keyboard.press("Escape")
            
        for pack_name in config.get("target_packs", []):
            print(f"[STORE] Searching for pack: {pack_name}")
            
            while True:
                # Đảm bảo chuyển sang trang My Packs trước khi quét
                if not navigate_to_my_packs(page, config):
                    print("[ERROR] Không thể chuyển sang trang My Packs. Bỏ qua pack này.")
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
                                available_packs_with_qty[p_name] = p_qty
                        available_packs = list(available_packs_with_qty.keys())
                        
                        best_match = find_best_match(pack_name, available_packs)
                        if best_match:
                            break
                    except Exception as e:
                        print(f"[ERROR] Lỗi khi quét danh sách pack ở lần thử {scan_attempt}: {e}")
                        
                if not best_match:
                    print(f"[INFO] Không tìm thấy Pack '{pack_name}' trên giao diện sau nhiều lần quét (hoặc đã mở hết).")
                    break
                    
                resolved_pack_name = best_match
                qty = available_packs_with_qty.get(resolved_pack_name, 0)
                # Đảm bảo nếu pack hiển thị trên màn hình thì số lượng tối thiểu là 1
                qty = max(1, qty)
                    
                print(f"[INFO] Phát hiện còn {qty} pack '{resolved_pack_name}' khả dụng. Tiến hành mở...")
                
                try:
                    pack_selector = "h1, h2, h3, .name, .title"
                    locator = page.locator(pack_selector).filter(has_text=resolved_pack_name).first
                    
                    if locator.count() > 0:
                        print(f"[OK] Đang mở pack: {resolved_pack_name} (Số lượng còn lại: {qty})")
                        locator.click()
                        sleep_human_like(2.0, 3.0)
                        
                        tile_parent = locator.locator("xpath=./ancestor::*[contains(@class, 'tile') or contains(@class, 'Tile') or contains(@class, 'pack')]").first
                        open_btn = tile_parent.locator("button").first if tile_parent.count() > 0 else locator.locator("button").first
                        if open_btn.count() > 0:
                            open_btn.click()
                            sleep_human_like(5.0, 8.0)
                            
                            # Tự động xử lý vật phẩm unassigned (gửi vào Club/SBC Storage) sau khi mở pack
                            handle_unassigned_items(page, config)
                            # Đợi giao diện quay lại Store
                            sleep_human_like(3.0, 4.0)
                            wait_for_click_shield(page)
                        else:
                            print(f"[WARNING] Không tìm thấy nút xác nhận mở cho pack: {resolved_pack_name}")
                            break
                    else:
                        print(f"[INFO] Không tìm thấy phần tử pack '{resolved_pack_name}' trên giao diện.")
                        break
                except Exception as e:
                    print(f"[ERROR] Lỗi khi mở pack {resolved_pack_name}: {e}")
                    alert_user_error(page, config, f"Lỗi khi mở pack {resolved_pack_name}")
                    break
                
        print("\n=== PROGRAM COMPLETED ===")
        context.close()

if __name__ == "__main__":
    run()
