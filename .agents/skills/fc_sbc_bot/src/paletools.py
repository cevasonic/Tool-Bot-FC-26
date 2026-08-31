import os
import sys
import json
import time
import urllib.parse
from src.config import BASE_DIR, PALETOOLS_PATH

def load_paletools_js():
    import urllib.parse
    from src.config import BASE_DIR
    
    # Danh sách các đường dẫn tìm kiếm khả dụng theo thứ tự ưu tiên
    possible_paths = [
        os.path.join(BASE_DIR, "resources", "paletools.txt"),
        os.path.join(BASE_DIR, "resources", "paletools.js"),
        os.path.join(BASE_DIR, "paletools.txt"),
        os.path.join(BASE_DIR, "paletools.js")
    ]
    
    found_path = None
    for path in possible_paths:
        if os.path.exists(path):
            found_path = path
            break
            
    if found_path:
        print(f"[INFO] Đang nạp script PaleTools từ: {found_path}")
        with open(found_path, "r", encoding="utf-8") as f:
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

    print(f"[ERROR] Không tìm thấy file script PaleTools (yêu cầu một trong các file sau tồn tại: "
          f"resources/paletools.txt, resources/paletools.js, paletools.txt, hoặc paletools.js). "
          f"Vui lòng chuẩn bị file script này.")
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
                
                let currentStatus = sessionStorage.getItem("bot_status") || "running";
                
                let statusText = document.createElement("span");
                statusText.id = "bot-status-text";
                statusText.innerText = currentStatus === "paused" ? "ĐÃ TẠM DỪNG" : "Đang chạy...";
                statusText.style.color = currentStatus === "paused" ? "#ff3366" : "#00ff88";
                
                let btn = document.createElement("button");
                btn.id = "bot-pause-btn";
                btn.setAttribute("data-status", currentStatus);
                btn.style.pointerEvents = "auto";
                btn.style.background = currentStatus === "paused" ? "#00ff88" : "#ff3366";
                btn.style.border = "none";
                btn.style.borderRadius = "4px";
                btn.style.color = currentStatus === "paused" ? "#000" : "#fff";
                btn.style.padding = "5px 12px";
                btn.style.cursor = "pointer";
                btn.style.fontWeight = "bold";
                btn.style.transition = "0.2s";
                btn.innerText = currentStatus === "paused" ? "TIẾP TỤC (Resume)" : "TẠM DỪNG (Pause)";
                
                btn.addEventListener("click", (e) => {
                    e.stopPropagation();
                    e.preventDefault();
                    if (btn.getAttribute("data-status") === "running") {
                        btn.setAttribute("data-status", "paused");
                        sessionStorage.setItem("bot_status", "paused");
                        btn.innerText = "TIẾP TỤC (Resume)";
                        btn.style.background = "#00ff88";
                        btn.style.color = "#000";
                        statusText.innerText = "ĐÃ TẠM DỪNG";
                        statusText.style.color = "#ff3366";
                    } else {
                        btn.setAttribute("data-status", "running");
                        sessionStorage.setItem("bot_status", "running");
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
                    let nextStatus = isRunning ? 'paused' : 'running';
                    btn.setAttribute('data-status', nextStatus);
                    sessionStorage.setItem("bot_status", nextStatus);
                    btn.innerText = isRunning ? 'TIẾP TỤC (Resume)' : 'TẠM DỪNG (Pause)';
                    btn.style.background = isRunning ? '#00ff88' : '#ff3366';
                    btn.style.color = isRunning ? '#000' : '#fff';
                    statusText.innerText = isRunning ? 'ĐÃ TẠM DỪNG' : 'Đang chạy...';
                    statusText.style.color = isRunning ? '#ff3366' : '#00ff88';
                }
            }""")

        printed = False
        last_tg_check = 0.0
        while True:
            if check_keyboard_toggle():
                page.evaluate("""() => {
                    let btn = document.getElementById('bot-pause-btn');
                    let statusText = document.getElementById('bot-status-text');
                    if (btn) {
                        let isPaused = btn.getAttribute('data-status') === 'paused';
                        if (isPaused) {
                            btn.setAttribute('data-status', 'running');
                            sessionStorage.setItem("bot_status", "running");
                            btn.innerText = 'TẠM DỪNG (Pause)';
                            btn.style.background = '#ff3366';
                            btn.style.color = '#fff';
                            statusText.innerText = 'Đang chạy...';
                            statusText.style.color = '#00ff88';
                        }
                    }
                }""")
            
            is_paused = page.evaluate("""() => {
                return sessionStorage.getItem("bot_status") === 'paused';
            }""")
            
            if not is_paused:
                break
                
            if not printed:
                print("\n" + "="*60)
                print("[PAUSE] BOT ĐÃ ĐƯỢC TẠM DỪNG!")
                print("-> Hãy click nút 'TIẾP TỤC (Resume)' trên thanh điều khiển Chrome để chạy tiếp.")
                print("="*60 + "\n")
                printed = True
                
            # Kiểm tra tin nhắn Telegram định kỳ mỗi 1.5 giây khi tạm dừng
            current_time = time.time()
            if current_time - last_tg_check >= 1.5:
                try:
                    from src.config import get_config
                    from src.notification import process_telegram_updates
                    config = get_config()
                    if config:
                        process_telegram_updates(config)
                except Exception:
                    pass
                last_tg_check = current_time
                
            time.sleep(0.5)
            
        if printed:
            print("[RESUME] Bot đang TIẾP TỤC chạy...\n")

    except Exception as e:
        print(f"[WARNING] Lỗi trong check_pause: {e}")

def trigger_bot_pause(page, reason, config=None):
    print(f"\n[ALERT] KÍCH HOẠT TẠM DỪNG BOT TỰ ĐỘNG! Lý do: {reason}")
    
    # Thử lấy số lượng cầu thủ trong SBC Storage qua JS của Web App
    sbc_storage_count = None
    try:
        sbc_storage_count = page.evaluate("""() => {
            return new Promise((resolve) => {
                if (typeof services === 'undefined' || !services.Item || typeof services.Item.searchStorageItems !== 'function') {
                    try {
                        let storageRepo = repositories.Item.storage;
                        if (storageRepo && typeof storageRepo.values === 'function') {
                            resolve(Array.from(storageRepo.values()).filter(i => i && (i.type === 'player' || (i.isPlayer && i.isPlayer()))).length);
                        } else if (repositories.Item.getStorageItems) {
                            let si = repositories.Item.getStorageItems() || [];
                            resolve(si.filter(i => i && (i.type === 'player' || (i.isPlayer && i.isPlayer()))).length);
                        } else {
                            resolve(0);
                        }
                    } catch(e) { resolve(0); }
                    return;
                }
                try {
                    let criteria = new UTSearchCriteriaDTO();
                    criteria.type = SearchType && SearchType.PLAYER ? SearchType.PLAYER : 'player';
                    criteria.count = 250;
                    criteria.offset = 0;
                    let obs = services.Item.searchStorageItems(criteria);
                    obs.observe(window, function(observer, response) {
                        if (response && response.success && response.response && response.response.items) {
                            let count = response.response.items.filter(i => i && (i.type === 'player' || (i.isPlayer && i.isPlayer()))).length;
                            resolve(count);
                        } else {
                            resolve(0);
                        }
                    });
                } catch(e) { resolve(0); }
            });
        }""")
    except Exception as e:
        print(f"[WARNING] Không thể lấy số lượng cầu thủ trong SBC Storage: {e}")

    sbc_storage_info = ""
    if sbc_storage_count is not None:
        sbc_storage_info = f"\nSố lượng cầu thủ trong SBC Storage hiện tại: {sbc_storage_count}/100"
        print(f"[INFO] {sbc_storage_info.strip()}")
        
    # Gửi thông báo Telegram nếu cấu hình cho phép
    try:
        if config is None:
            config_path = os.path.join(BASE_DIR, "config.json")
            if os.path.exists(config_path):
                with open(config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
        
        if config:
            # Chụp màn hình khi tạm dừng để gửi kèm Telegram
            screenshot_path = os.path.join(BASE_DIR, "logs", "pause_screenshot.png")
            try:
                os.makedirs(os.path.dirname(screenshot_path), exist_ok=True)
                page.screenshot(path=screenshot_path)
            except Exception as se:
                print(f"[WARNING] Không thể chụp ảnh màn hình khi tạm dừng: {se}")
                screenshot_path = None
                
            from src.notification import send_telegram_message
            send_telegram_message(
                config, 
                f"KÍCH HOẠT TẠM DỪNG BOT TỰ ĐỘNG!\nLý do: {reason}{sbc_storage_info}", 
                photo_path=screenshot_path
            )
    except Exception as te:
        print(f"[WARNING] Không thể gửi thông báo tạm dừng Telegram: {te}")

    try:
        page.evaluate("""() => {
            sessionStorage.setItem("bot_status", "paused");
            let btn = document.getElementById('bot-pause-btn');
            let statusText = document.getElementById('bot-status-text');
            if (btn) {
                btn.setAttribute('data-status', 'paused');
                btn.innerText = 'TIẾP TỤC (Resume)';
                btn.style.background = '#00ff88';
                btn.style.color = '#000';
            }
            if (statusText) {
                statusText.innerText = 'ĐÃ TẠM DỪNG';
                statusText.style.color = '#ff3366';
            }
        }""")
        
        # Phát âm thanh cảnh báo lỗi nếu chạy trên macOS
        if sys.platform == "darwin":
            try:
                os.system("say 'Attention, bot paused due to unassigned items'")
                os.system("afplay /System/Library/Sounds/Glass.aiff &")
            except Exception:
                pass
            
    except Exception as e:
        print(f"[WARNING] Không thể kích hoạt nút tạm dừng qua JS: {e}")

def resume_bot_status(page):
    try:
        page.evaluate("""() => {
            sessionStorage.setItem("bot_status", "running");
            let btn = document.getElementById('bot-pause-btn');
            let statusText = document.getElementById('bot-status-text');
            if (btn) {
                btn.setAttribute('data-status', 'running');
                btn.innerText = 'TẠM DỪNG (Pause)';
                btn.style.background = '#ff3366';
                btn.style.color = '#fff';
            }
            if (statusText) {
                statusText.innerText = 'Đang chạy...';
                statusText.style.color = '#00ff88';
            }
        }""")
    except Exception as e:
        print(f"[WARNING] Không thể cập nhật trạng thái hoạt động qua JS: {e}")
