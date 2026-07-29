import os
import sys
import time
import json
import random
import urllib.parse
import requests
import re
from playwright.sync_api import sync_playwright

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

def global_exception_handler(exctype, value, tb):
    if "closed" in str(value).lower() or "target" in str(value).lower():
        print("\n[INFO] Trình duyệt đã bị đóng đột ngột (bởi người dùng hoặc hệ thống). Dừng bot an toàn.")
    else:
        sys.__excepthook__(exctype, value, tb)

import sys
sys.excepthook = global_exception_handler

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PALETOOLS_PATH = os.path.join(BASE_DIR, "paletools.txt")

class DualLogger(object):
    def __init__(self, filepath):
        self.terminal = sys.stdout
        self.log = open(filepath, "a", encoding="utf-8")

    def write(self, message):
        self.terminal.write(message)
        self.log.write(message)
        self.log.flush()

    def flush(self):
        self.terminal.flush()
        self.log.flush()

sys.stdout = DualLogger(os.path.join(BASE_DIR, "run_interactive.log"))
sys.stderr = sys.stdout

GLOBAL_ACTIVE_PAGE = None

def sleep_human_like(min_sec, max_sec, page=None):
    global GLOBAL_ACTIVE_PAGE
    active_page = page or GLOBAL_ACTIVE_PAGE
    delay = random.uniform(min_sec, max_sec)
    start_time = time.time()
    while time.time() - start_time < delay:
        if active_page:
            try:
                check_pause(active_page)
            except Exception:
                pass
        remaining = delay - (time.time() - start_time)
        if remaining > 0:
            time.sleep(min(0.2, remaining))

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

def dismiss_modals(page):
    """Tự động kiểm tra và đóng/ẩn các modal hoặc pop-up (PaleTools modal, EA modal, v.v.) đang che màn hình."""
    try:
        modal_selectors = [
            ".view-modal-container",
            ".ea-dialog-view",
            ".dialog-modal",
            ".form-modal"
        ]
        for sel in modal_selectors:
            modals = page.locator(sel)
            count = modals.count()
            if count > 0:
                for i in range(count):
                    modal = modals.nth(i)
                    if modal.is_visible():
                        print(f"[INFO] Phát hiện modal '{sel}' đang che khuất màn hình. Tiến hành đóng...")
                        close_btn = modal.locator("button.close, .btn-flat, .dialog-close-btn, button:has-text('OK'), button:has-text('Close'), button:has-text('Đóng'), button:has-text('Tắt'), button:has-text('Accept')").first
                        if close_btn.count() > 0 and close_btn.is_visible():
                            try:
                                close_btn.click(timeout=2000, force=True)
                                sleep_human_like(0.5, 1.0)
                            except Exception:
                                pass
                        
                        if modal.is_visible():
                            page.keyboard.press("Escape")
                            sleep_human_like(0.5, 1.0)
                            
                        if modal.is_visible():
                            try:
                                page.evaluate("(sel) => { document.querySelectorAll(sel).forEach(el => el.style.display = 'none'); }", sel)
                                sleep_human_like(0.3, 0.5)
                            except Exception:
                                pass
    except Exception:
        pass

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

def ensure_bot_overlay(page):
    try:
        has_panel = page.evaluate("!!document.getElementById('bot-overlay-panel')")
        if not has_panel:
            page.evaluate("""() => {
                let div = document.createElement("div");
                div.id = "bot-overlay-panel";
                div.style.position = "fixed";
                div.style.top = "10px";
                div.style.left = "50%";
                div.style.transform = "translateX(-50%)";
                div.style.zIndex = "99999999";
                div.style.pointerEvents = "auto";
                div.style.background = "rgba(20, 20, 20, 0.95)";
                div.style.border = "2px solid #00ff88";
                div.style.borderRadius = "8px";
                div.style.padding = "8px 20px";
                div.style.color = "#fff";
                div.style.fontFamily = "system-ui, -apple-system, sans-serif";
                div.style.display = "flex";
                div.style.alignItems = "center";
                div.style.gap = "15px";
                div.style.boxShadow = "0 4px 15px rgba(0,0,0,0.5)";
                div.style.userSelect = "none";
                
                let title = document.createElement("span");
                title.style.fontWeight = "bold";
                title.style.color = "#00ff88";
                title.innerText = "FC SBC BOT:";
                
                let statusText = document.createElement("span");
                statusText.id = "bot-status-text";
                statusText.innerText = "Đang chạy...";
                statusText.style.color = "#00ff88";
                
                let btn = document.createElement("button");
                btn.id = "bot-pause-btn";
                btn.setAttribute("data-status", "running");
                btn.style.pointerEvents = "auto";
                btn.style.background = "#ff3366";
                btn.style.border = "none";
                btn.style.borderRadius = "4px";
                btn.style.color = "#fff";
                btn.style.padding = "5px 12px";
                btn.style.cursor = "pointer";
                btn.style.fontWeight = "bold";
                btn.style.transition = "0.2s";
                btn.innerText = "TẠM DỪNG (Pause)";
                
                btn.addEventListener("click", (e) => {
                    e.stopPropagation();
                    e.preventDefault();
                    if (btn.getAttribute("data-status") === "running") {
                        btn.setAttribute("data-status", "paused");
                        btn.innerText = "TIẾP TỤC (Resume)";
                        btn.style.background = "#00ff88";
                        btn.style.color = "#000";
                        statusText.innerText = "ĐÃ TẠM DỪNG";
                        statusText.style.color = "#ff3366";
                    } else {
                        btn.setAttribute("data-status", "running");
                        btn.innerText = "TẠM DỪNG (Pause)";
                        btn.style.background = "#ff3366";
                        btn.style.color = "#fff";
                        statusText.innerText = "Đang chạy...";
                        statusText.style.color = "#00ff88";
                    }
                });
                
                div.appendChild(title);
                div.appendChild(statusText);
                div.appendChild(btn);
                document.body.appendChild(div);
            }""")
    except Exception as e:
        print(f"[WARNING] Không thể tạo bảng điều khiển Overlay: {e}")

def check_keyboard_toggle():
    """Kiểm tra phím p/P/Space trên Console mà không gây block (tương thích Windows & macOS/Linux)."""
    try:
        import msvcrt
        if msvcrt.kbhit():
            ch = msvcrt.getch()
            if ch in [b'p', b'P', b' ']:
                return True
    except ImportError:
        import sys, select
        if sys.stdin in select.select([sys.stdin], [], [], 0)[0]:
            line = sys.stdin.readline()
            if any(k in line for k in ['p', 'P', ' ']):
                return True
    except Exception:
        pass
    return False

def check_pause(page):
    try:
        ensure_bot_overlay(page)
        
        if check_keyboard_toggle():
            page.evaluate("""() => {
                let btn = document.getElementById('bot-pause-btn');
                let statusText = document.getElementById('bot-status-text');
                if (btn) {
                    let isRunning = btn.getAttribute('data-status') === 'running';
                    btn.setAttribute('data-status', isRunning ? 'paused' : 'running');
                    btn.innerText = isRunning ? 'TIẾP TỤC (Resume)' : 'TẠM DỪNG (Pause)';
                    btn.style.background = isRunning ? '#00ff88' : '#ff3366';
                    btn.style.color = isRunning ? '#000' : '#fff';
                    statusText.innerText = isRunning ? 'ĐÃ TẠM DỪNG' : 'Đang chạy...';
                    statusText.style.color = isRunning ? '#ff3366' : '#00ff88';
                }
            }""")

        printed = False
        while True:
            if check_keyboard_toggle():
                page.evaluate("""() => {
                    let btn = document.getElementById('bot-pause-btn');
                    let statusText = document.getElementById('bot-status-text');
                    if (btn) {
                        let isPaused = btn.getAttribute('data-status') === 'paused';
                        if (isPaused) {
                            btn.setAttribute('data-status', 'running');
                            btn.innerText = 'TẠM DỪNG (Pause)';
                            btn.style.background = '#ff3366';
                            btn.style.color = '#fff';
                            statusText.innerText = 'Đang chạy...';
                            statusText.style.color = '#00ff88';
                        }
                    }
                }""")
            
            is_paused = page.evaluate("""() => {
                let btn = document.getElementById('bot-pause-btn');
                return btn && btn.getAttribute('data-status') === 'paused';
            }""")
            
            if not is_paused:
                break
                
            if not printed:
                print("\n" + "="*60)
                print("[PAUSE] BOT ĐÃ ĐƯỢC TẠM DỪNG!")
                print("-> Hãy click nút 'TIẾP TỤC (Resume)' trên Chrome hoặc nhấn 'p'/Space ở Console này để chạy tiếp.")
                print("="*60 + "\n")
                printed = True
                
            time.sleep(0.5)
            
        if printed:
            print("[RESUME] Bot đang TIẾP TỤC chạy...\n")

    except Exception as e:
        print(f"[WARNING] Lỗi trong check_pause: {e}")

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
            
    # 3. Partial match (target inside available, or available inside target)
    for name in available_names:
        if target_name.lower() in name.lower() or name.lower() in target_name.lower():
            return name
            
    return None

def find_sbc_tile(page, sbc_name):
    import re
    try:
        # Tìm phần tử text chứa tên SBC (dùng regex để không phân biệt chữ hoa chữ thường)
        name_locator = page.get_by_text(re.compile(re.escape(sbc_name.strip()), re.IGNORECASE))
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
                        return ancestor
                # Nếu không tìm thấy ancestor cụ thể, thử tìm ancestor tổng quát gần nhất
                general_ancestor = loc.locator("xpath=./ancestor::*[contains(@class, 'tile') or contains(@class, 'item') or contains(@class, 'sbc')][1]").first
                if general_ancestor.count() > 0 and general_ancestor.is_visible():
                    return general_ancestor
    except Exception as e:
        print(f"[WARNING] Lỗi trong find_sbc_tile: {e}")
    return None

def get_sbc_repeats(tile_locator):
    import re
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
        sleep_human_like(1.5, 2.5)
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
            sleep_human_like(1.5, 2.5)

        dismiss_modals(page)
        # Thử lại phím tắt '1' sau khi ở tab Store
        page.keyboard.press("1")
        sleep_human_like(1.5, 2.5)
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
                sleep_human_like(1.0, 1.5)

        if is_in_my_packs(page):
            return True
            
    except Exception as e:
        print(f"[WARNING] Lỗi khi chuyển sang trang My Packs: {e}")

    return is_in_my_packs(page)

def execute_sbc_step(page, config, paletools_js, sbc_name, max_repeats, completed_sbcs_total):
    delays = config.get("delays", {})
    original_sbc_name = sbc_name
    print(f"\n[SBC] Bắt đầu tác vụ SBC: {sbc_name} (Lặp tối đa: {max_repeats if max_repeats != 999999 else 'Không giới hạn'})")
    
    sbc_count = 0
    consecutive_errors = 0
    
    while sbc_count < max_repeats:
        check_pause(page)
        resolved_sbc = False
        check_captcha_or_errors(page, config)
        print(f"[INFO] Bắt đầu lượt SBC {sbc_count + 1}/{max_repeats if max_repeats != 999999 else 'Không giới hạn'}...")
        
        print("[INFO] Đang di chuyển tới menu SBC...")
        try:
            dismiss_modals(page)
            page.wait_for_selector(".ut-tab-bar-item.icon-sbc", timeout=15000)
            try:
                page.click(".ut-tab-bar-item.icon-sbc", timeout=5000)
            except Exception:
                page.click(".ut-tab-bar-item.icon-sbc", force=True)
            sleep_human_like(1.5, 2.5)
        except Exception as e:
            print(f"[ERROR] Không thể di chuyển tới menu SBC: {e}")
            alert_user_error(page, config, "Lỗi di chuyển tới menu SBC")
            consecutive_errors += 1
            if consecutive_errors >= 3:
                print("[ERROR] Quá nhiều lỗi điều hướng liên tiếp. Dừng bước SBC này.")
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
                sleep_human_like(1.5, 2.5)
                
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
                    sleep_human_like(0.6, 1.0)
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
                sleep_human_like(2.0, 3.5)
        except Exception as search_err:
            print(f"[WARNING] Lỗi khi sử dụng ô tìm kiếm: {search_err}")
        
        # Quét tìm tile SBC sau khi search bằng bộ lọc trực tiếp của Playwright
        try:
            tile_locator = find_sbc_tile(page, original_sbc_name)
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
                        sleep_human_like(1.5, 2.5)
                        
                        # Xóa ô tìm kiếm nếu đang có chữ để hiển thị lại toàn bộ danh mục của tab này
                        try:
                            search_input = page.locator("input[placeholder='Search'], .ut-sbc-hub-view input.search, .search input").first
                            if search_input.count() > 0:
                                search_input.click()
                                page.keyboard.press("ControlOrMeta+A")
                                page.keyboard.press("Backspace")
                                sleep_human_like(0.8, 1.5)
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
                            sleep_human_like(0.6, 1.0)
                        
                        # Tìm kiếm bằng bộ lọc trực tiếp của Playwright
                        try:
                            tile_locator = find_sbc_tile(page, original_sbc_name)
                            if tile_locator is not None:
                                is_visible_on_ui = True
                                print(f"[OK] Tìm thấy SBC '{original_sbc_name}' tại tab '{tab_name}'!")
                        except Exception as scan_err:
                            print(f"[WARNING] Lỗi khi quét tìm tile trong tab '{tab_name}': {scan_err}")
                        
                        if is_visible_on_ui:
                            break
                except Exception as tab_err:
                    print(f"[WARNING] Lỗi khi quét tab '{tab_name}': {tab_err}")
        
        # Dọn dẹp ô search sau khi tìm kiếm xong để không ảnh hưởng lượt quét SBC tiếp theo
        try:
            search_input = page.locator("input[placeholder='Search'], .ut-sbc-hub-view input.search, .search input").first
            if search_input.count() > 0 and search_input.is_visible():
                search_input.click()
                page.keyboard.press("ControlOrMeta+A")
                page.keyboard.press("Backspace")
                sleep_human_like(0.5, 1.0)
        except Exception:
            pass

        if not is_visible_on_ui:
            if sbc_count > 0:
                print(f"[INFO] SBC '{original_sbc_name}' không còn xuất hiện trên giao diện nữa (đã hoàn thành hết lượt khả dụng). Kết thúc bước SBC này.")
                break
            else:
                error_msg = f"Không tìm thấy SBC '{original_sbc_name}' trên giao diện sau khi thử mọi cách!"
                print(f"[ERROR] {error_msg}")
                alert_user_error(page, config, error_msg)
                print("[WARNING] Bỏ qua tác vụ SBC này...")
                break
        
        sbc_name = original_sbc_name
        resolved_sbc = True
        
        avail_repeats = get_sbc_repeats(tile_locator)
        if avail_repeats is not None:
            if avail_repeats == 0:
                print(f"[INFO] SBC '{original_sbc_name}' trên giao diện đã hết số lượt làm lại (Repeatable = 0). Kết thúc bước SBC.")
                break
            if sbc_count == 0:
                new_max = min(max_repeats, avail_repeats)
                print(f"[INFO] Xác định số lượt repeatable khả dụng trên UI: {avail_repeats}. Cấu hình max_repeats: {max_repeats}. Thiết lập chạy: {new_max} lượt.")
                max_repeats = new_max
                if max_repeats <= 0:
                    print(f"[INFO] Số lượt cần làm <= 0. Bỏ qua SBC '{original_sbc_name}'.")
                    break
            else:
                print(f"[INFO] Lượt chạy {sbc_count + 1}/{max_repeats}. Số lượt repeatable còn lại phát hiện trên UI: {avail_repeats}")
        else:
            print(f"[WARNING] Lượt chạy {sbc_count + 1}/{max_repeats}. Không thể quét số lượt repeatable từ giao diện. Chạy tiếp tục.")

        print(f"[INFO] Đang click vào SBC '{sbc_name}'...")
        try:
            # Click vào tile bằng Playwright
            dismiss_modals(page)
            try:
                tile_locator.click(timeout=5000)
            except Exception:
                tile_locator.click(force=True)
            print(f"[OK] Đã chọn SBC: {sbc_name} (Lượt {sbc_count + 1})")
            sleep_human_like(2.0, 3.0)
            
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
                
                sleep_human_like(1.5, 2.5)
        except Exception as e:
            print(f"[ERROR] Không thể chọn SBC '{sbc_name}': {e}")
            alert_user_error(page, config, f"Không thể tìm thấy SBC {sbc_name}")
            consecutive_errors += 1
            if consecutive_errors >= 3:
                print("[ERROR] Quá nhiều lỗi chọn SBC liên tiếp. Dừng bước SBC.")
                break
            continue
            
        page.focus("body")
        page.click("body", delay=100)
        
        sleep_human_like(delays.get("before_build_min", 1.5), delays.get("before_build_max", 3.0))
        
        print("[RPA] Nhấn phím 'T' để tự động điền template...")
        page.keyboard.press("t")
        
        sleep_human_like(delays.get("after_build_min", 2.5), delays.get("after_build_max", 4.5))
        
        print("[RPA] Nhấn phím 'S' để Submit...")
        page.keyboard.press("s")
        
        # Chụp ảnh debug trạng thái submit
        time.sleep(1.0)
        try:
            debug_screenshot_path = os.path.join(BASE_DIR, "submit_debug.png")
            page.screenshot(path=debug_screenshot_path)
            print(f"[INFO] Đã lưu ảnh chụp debug submit tại: {debug_screenshot_path}")
        except Exception as de_ex:
            print(f"[WARNING] Không thể chụp ảnh debug submit: {de_ex}")
        
        # 1. Kiểm tra hộp thoại báo lỗi không đủ điều kiện (Ineligible Squad do dính cầu thủ Concept/Loan)
        is_ineligible = False
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
                    sleep_human_like(1.0, 1.5)
                    page.keyboard.press("Escape")
                    sleep_human_like(1.5, 2.0)
        except Exception:
            pass

        if is_ineligible:
            print(f"[INFO] Tự động dừng làm SBC '{sbc_name}' do đã hết cầu thủ hợp lệ trong CLB.")
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
                    print(f"[RPA] Đang bấm Claim Rewards cho lượt {sbc_count + 1}...")
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
            print(f"[OK] Đã hoàn thành lượt {sbc_count}.")
        else:
            print(f"[WARNING] Lượt {sbc_count + 1} chưa được submit thành công (vẫn kẹt ở màn hình build squad hoặc có lỗi).")
            try:
                page.keyboard.press("Escape")
            except Exception:
                pass
            sleep_human_like(2.0, 3.0)
            consecutive_errors += 1
            if consecutive_errors >= 3:
                print("[ERROR] Quá nhiều lỗi submit liên tiếp. Dừng bước SBC.")
                break
            continue
            
        if sbc_count < max_repeats:
            sleep_human_like(delays.get("after_submit_min", 1.5), delays.get("after_submit_max", 3.0))
        else:
            time.sleep(0.3)
            
        if completed_sbcs_total % delays.get("batch_size", 10) == 0 and sbc_count < max_repeats:
            rest_time = delays.get("batch_rest_seconds", 60)
            print(f"[INFO] Tạm nghỉ để tránh bị ban tài khoản: {rest_time}s...")
            time.sleep(rest_time)
            
    print(f"[SBC] Hoàn thành bước SBC: {sbc_name} ({sbc_count} lần thành công).")
    
    # Cuối cùng kiểm tra và dọn dẹp popup claim reward nếu còn sót
    print("[RPA] Kiểm tra hộp thoại Claim Rewards còn chờ...")
    try:
        claim_btn = page.locator("button:has-text('Claim Rewards')").first
        if claim_btn.count() > 0 and claim_btn.is_visible():
            print("[RPA] Đang click Claim Rewards...")
            claim_btn.click()
            sleep_human_like(2.0, 3.0)
            page.keyboard.press("Escape")
            sleep_human_like(0.5, 1.0)
    except Exception:
        pass
        
    return sbc_count, completed_sbcs_total

def execute_open_pack_step(page, config, paletools_js, pack_name, open_count=None, open_all=False):
    print(f"\n[STORE] Tìm kiếm và mở Pack: {pack_name}")
    opened_so_far = 0
    
    while True:
        check_pause(page)
        
        # Kiểm tra điều kiện dừng:
        if not open_all and open_count is not None and opened_so_far >= open_count:
            print(f"[INFO] Đã mở đủ số lượng yêu cầu ({opened_so_far}/{open_count}) cho pack '{pack_name}'. Dừng mở.")
            break
            
        # Đảm bảo chuyển sang trang My Packs trước khi quét
        if not navigate_to_my_packs(page, config):
            print("[ERROR] Không thể chuyển sang trang My Packs. Dừng bước mở pack này.")
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
                locator.click()
                sleep_human_like(1.0, 1.8)
                
                tile_parent = locator.locator("xpath=./ancestor::*[contains(@class, 'tile') or contains(@class, 'Tile') or contains(@class, 'pack')]").first
                open_btn = tile_parent.locator("button").first if tile_parent.count() > 0 else locator.locator("button").first
                if open_btn.count() > 0:
                    open_btn.click()
                    sleep_human_like(1.5, 2.5)
                    
                    # Tự động xử lý vật phẩm unassigned (gửi vào Club/SBC Storage) sau khi mở pack
                    handle_unassigned_items(page, config)
                    # Đợi giao diện quay lại Store
                    sleep_human_like(0.5, 1.2)
                    wait_for_click_shield(page)
                    opened_so_far += 1
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
            
    print(f"[STORE] Hoàn thành mở pack '{pack_name}': Đã mở {opened_so_far} lần.")

def run():
    config_path = os.path.join(BASE_DIR, "config.json")
    if not os.path.exists(config_path):
        print("[ERROR] Không tìm thấy tệp config.json!")
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
        
    # Chuyển đổi cấu hình cũ sang cấu trúc workflow mới nếu cần thiết (Tương thích ngược)
    workflow = config.get("workflow")
    if workflow is None:
        print("[INFO] Không tìm thấy 'workflow' trong config.json. Tự động chuyển đổi cấu hình cũ sang workflow...")
        workflow = []
        step_num = 1
        
        target_sbcs = config.get("target_sbcs")
        if isinstance(target_sbcs, list):
            for sbc in target_sbcs:
                if isinstance(sbc, dict) and "name" in sbc:
                    workflow.append({
                        "step": step_num,
                        "type": "sbc",
                        "sbc_name": sbc["name"],
                        "max_repeats": sbc.get("max_repeats", 1)
                    })
                    step_num += 1
                    
        target_packs = config.get("target_packs")
        if isinstance(target_packs, list):
            for pack in target_packs:
                if isinstance(pack, str):
                    workflow.append({
                        "step": step_num,
                        "type": "open_pack",
                        "pack_name": pack,
                        "open_all": True
                    })
                    step_num += 1
    
    paletools_js = load_paletools_js()
    
    print("=== BẮT ĐẦU CHẠY FC ULTIMATE TEAM SBC BOT ===")
    
    with sync_playwright() as p:
        user_data_dir = os.path.join(BASE_DIR, "chrome_profile")
        if not os.path.exists(user_data_dir):
            os.makedirs(user_data_dir)
            
        context = None
        try:
            print("[INFO] Đang mở Google Chrome với cấu hình profile (Persistent Context)...")
            context = p.chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                headless=config.get("headless", False),
                channel="chrome",
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox"
                ],
                viewport={"width": 1280, "height": 800},
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
        except Exception as e:
            print(f"[WARNING] Không thể chạy Chrome bằng profile cá nhân ({e}).")
            print("[INFO] Đang chạy fallback bằng Chromium mặc định của Playwright...")
            try:
                context = p.chromium.launch_persistent_context(
                    user_data_dir=user_data_dir,
                    headless=config.get("headless", False),
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--no-sandbox"
                    ],
                    viewport={"width": 1280, "height": 800}
                )
            except Exception as e2:
                print(f"[ERROR] Không thể khởi chạy trình duyệt: {e2}")
                sys.exit(1)
        
        context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        # Đóng tất cả các tab phụ để tránh xung đột
        while len(context.pages) > 1:
            try:
                context.pages[-1].close()
            except Exception:
                break
        page = context.pages[0] if context.pages else context.new_page()
        global GLOBAL_ACTIVE_PAGE
        GLOBAL_ACTIVE_PAGE = page
        
        print("[INFO] Đang truy cập EA Sports FC Ultimate Team Web App...")
        page.goto("https://www.ea.com/ea-sports-fc/ultimate-team/web-app/")
        try:
            page.evaluate("document.title = '★★★ BOT CHROME WINDOW - THAO TAC TAI DAY ★★★'")
        except Exception:
            pass
        
        print("\n============================================================")
        print("[REQUEST] Vui lòng đăng nhập và xác minh 2FA trên cửa sổ Chrome vừa mở.")
        print("Khi bạn vào tới giao diện chính (Dashboard) của Web App, bot sẽ tự động tiếp tục.")
        print("============================================================\n")
        
        print("[INFO] Đang theo dõi trạng thái đăng nhập...")
        try:
            page.wait_for_selector(".ut-tab-bar", timeout=300000)
            print("[OK] Đã phát hiện giao diện Dashboard. Kích hoạt PaleTools...")
            sleep_human_like(3.0, 5.0)
        except Exception as e:
            print(f"[ERROR] Lỗi khi chờ giao diện Dashboard: {e}")
            alert_user_error(page, config, "Lỗi tải Dashboard Web App")
            
        try:
            page.evaluate(f"eval({json.dumps(paletools_js)})")
            print("[OK] PaleTools đã được nạp thành công. Chờ 5 giây để khởi động...")
            time.sleep(5)
            dismiss_modals(page)
            try:
                page.evaluate("document.title = '★★★ BOT CHROME WINDOW - THAO TAC TAI DAY ★★★'")
            except Exception:
                pass
        except Exception as e:
            print(f"[ERROR] Không thể nạp PaleTools: {e}")
            alert_user_error(page, config, "Lỗi nạp PaleTools.")
            sys.exit(1)
            
        # Khởi tạo các biến lưu trữ trạng thái chạy workflow
        context_vars = {}
        completed_sbcs_total = 0
        
        for step_cfg in workflow:
            step_num = step_cfg.get("step", "N/A")
            step_type = step_cfg.get("type")
            
            print(f"\n[WORKFLOW] --- THỰC HIỆN BƯỚC {step_num} (Loại: {step_type.upper()}) ---")
            
            if step_type == "sbc":
                sbc_name = step_cfg.get("sbc_name")
                max_repeats = step_cfg.get("max_repeats", -1)
                if max_repeats == -1:
                    max_repeats = 999999 # Coi như không giới hạn, bot tự dừng khi Repeatable = 0 hoặc hết thẻ
                
                success_count, completed_sbcs_total = execute_sbc_step(
                    page, config, paletools_js, sbc_name, max_repeats, completed_sbcs_total
                )
                
                save_count_key = step_cfg.get("save_count_key")
                if save_count_key:
                    context_vars[save_count_key] = success_count
                    print(f"[WORKFLOW] Đã lưu số lần SBC thành công: {success_count} lần vào biến '{save_count_key}'")
            
            elif step_type == "open_pack":
                pack_name = step_cfg.get("pack_name")
                open_all = step_cfg.get("open_all", False)
                count_key = step_cfg.get("count_key")
                
                open_count = None
                if count_key:
                    open_count = context_vars.get(count_key, 0)
                    print(f"[WORKFLOW] Lấy số lượng mở pack từ biến '{count_key}': {open_count} lần")
                    if open_count <= 0:
                        print(f"[WORKFLOW] Số lượng mở pack là {open_count}. Bỏ qua bước mở pack '{pack_name}'.")
                        continue
                
                # Nếu không cấu hình count_key và cũng không chọn open_all, mặc định sẽ là mở tất cả (open_all = True)
                if not count_key and not open_all:
                    open_all = True
                    
                execute_open_pack_step(
                    page, config, paletools_js, pack_name, open_count=open_count, open_all=open_all
                )
            
            else:
                print(f"[WARNING] Loại bước '{step_type}' không được hỗ trợ. Bỏ qua.")
                
        print("\n=== HOÀN THÀNH TOÀN BỘ CHƯƠNG TRÌNH BOT ===")
        context.close()

if __name__ == "__main__":
    run()
