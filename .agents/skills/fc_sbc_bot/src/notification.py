import os
import sys
import queue
import threading
import requests
from src.config import BASE_DIR

# Biến toàn cục để theo dõi updates của Telegram
_last_update_id = 0
_telegram_updates_initialized = False

# Biến toàn cục cho luồng console input không chặn
_console_queue = None
_console_thread = None

def start_console_thread():
    global _console_queue, _console_thread
    if _console_queue is None:
        _console_queue = queue.Queue()
        _console_thread = threading.Thread(target=_read_console_inputs, daemon=True)
        _console_thread.start()

def _read_console_inputs():
    while True:
        try:
            line = sys.stdin.readline()
            if not line:
                break
            _console_queue.put(line.strip())
        except Exception:
            break

def get_console_input(timeout=0.1):
    start_console_thread()
    try:
        return _console_queue.get(timeout=timeout)
    except queue.Empty:
        return None

def send_telegram_message(config, message, photo_path=None):
    """Gửi tin nhắn Telegram thông báo độc lập, có thể kèm ảnh chụp màn hình."""
    if not config:
        print("[WARNING] Telegram: Không thể gửi tin nhắn vì tham số cấu hình trống (config is None).")
        return
        
    telegram_cfg = config.get("telegram", {})
    if not telegram_cfg.get("enabled", False):
        print("[INFO] Telegram: Đang TẮT (enabled=False). Bỏ qua gửi tin nhắn.")
        return
        
    bot_token = telegram_cfg.get("bot_token")
    chat_id = telegram_cfg.get("chat_id")
    
    # Kiểm tra các giá trị cấu hình hợp lệ
    is_valid = True
    if not bot_token or bot_token in ["YOUR_TELEGRAM_BOT_TOKEN", ""]:
        print("[WARNING] Telegram đang BẬT nhưng Bot Token chưa được cấu hình hợp lệ.")
        is_valid = False
    if not chat_id or chat_id in ["YOUR_TELEGRAM_CHAT_ID", "YOUR_CHAT_ID", ""]:
        print("[WARNING] Telegram đang BẬT nhưng Chat ID chưa được cấu hình hợp lệ.")
        is_valid = False
        
    if is_valid:
        try:
            text_msg = f"[FC SBC Bot Alert] {message}"
            send_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            print(f"[INFO] Telegram: Đang gửi tin nhắn tới Chat ID '{chat_id}'...")
            response = requests.post(send_url, json={"chat_id": chat_id, "text": text_msg}, timeout=10)
            response.raise_for_status()
            
            # Gửi ảnh chụp màn hình nếu có
            if photo_path and os.path.exists(photo_path):
                print(f"[INFO] Telegram: Đang gửi kèm ảnh chụp màn hình: '{photo_path}'...")
                send_photo_url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"
                with open(photo_path, "rb") as photo:
                    photo_response = requests.post(send_photo_url, data={"chat_id": chat_id}, files={"photo": photo}, timeout=15)
                    photo_response.raise_for_status()
            print("[OK] Đã gửi thông báo Telegram thành công.")
        except Exception as te:
            print(f"[WARNING] Không thể gửi thông báo Telegram: {te}")

def set_telegram_commands(config):
    """Thiết lập menu các lệnh điều khiển cho Telegram Bot."""
    if not config:
        return
    telegram_cfg = config.get("telegram", {})
    if not telegram_cfg.get("enabled", False):
        return
    bot_token = telegram_cfg.get("bot_token")
    if not bot_token or bot_token in ["YOUR_TELEGRAM_BOT_TOKEN", ""]:
        return
    try:
        url = f"https://api.telegram.org/bot{bot_token}/setMyCommands"
        commands = [
            {"command": "screenshot", "description": "Chụp ảnh màn hình Chrome hiện tại"},
            {"command": "pause", "description": "Tạm dừng bot"},
            {"command": "resume", "description": "Chạy tiếp bot"},
            {"command": "status", "description": "Xem báo cáo tiến độ"},
            {"command": "stop", "description": "Tắt bot hoàn toàn"}
        ]
        print("[INFO] Telegram: Đang thiết lập menu lệnh điều khiển...")
        res = requests.post(url, json={"commands": commands}, timeout=5)
        if res.status_code == 200:
            print("[OK] Đã thiết lập menu lệnh Telegram thành công.")
        else:
            print(f"[WARNING] Thiết lập menu lệnh thất bại, API trả về code {res.status_code}")
    except Exception as e:
        print(f"[WARNING] Lỗi khi thiết lập menu lệnh Telegram: {e}")

def init_telegram_updates(config):
    """Khởi tạo offset của Telegram updates để bỏ qua các tin nhắn cũ trước đó và cài đặt menu lệnh."""
    global _last_update_id, _telegram_updates_initialized
    if _telegram_updates_initialized:
        return
    if not config:
        return
    telegram_cfg = config.get("telegram", {})
    if not telegram_cfg.get("enabled", False):
        return
    bot_token = telegram_cfg.get("bot_token")
    if not bot_token or bot_token in ["YOUR_TELEGRAM_BOT_TOKEN", ""]:
        return
    
    try:
        url = f"https://api.telegram.org/bot{bot_token}/getUpdates"
        print("[INFO] Telegram: Đang kết nối tới Telegram để khởi tạo update offset...")
        res = requests.get(url, params={"offset": -1, "timeout": 0}, timeout=5)
        if res.status_code == 200:
            data = res.json()
            if data.get("ok") and data.get("result"):
                _last_update_id = data["result"][-1]["update_id"]
                print(f"[INFO] Telegram: Khởi tạo thành công update offset = {_last_update_id}")
            else:
                print("[INFO] Telegram: Không có tin nhắn cũ nào cần bỏ qua.")
        else:
            print(f"[WARNING] Telegram: Khởi tạo offset thất bại, API trả về code {res.status_code}")
    except Exception as e:
        print(f"[WARNING] Telegram: Lỗi khi khởi tạo update offset: {e}")
        
    # Thiết lập menu lệnh
    set_telegram_commands(config)
    _telegram_updates_initialized = True

def process_telegram_updates(config):
    """Kiểm tra tin nhắn Telegram mới để xử lý các lệnh và lựa chọn phản hồi."""
    global _last_update_id
    import json
    import time
    if not config:
        return []
    
    telegram_cfg = config.get("telegram", {})
    if not telegram_cfg.get("enabled", False):
        return []
        
    bot_token = telegram_cfg.get("bot_token")
    chat_id = str(telegram_cfg.get("chat_id", ""))
    if not bot_token or bot_token in ["YOUR_TELEGRAM_BOT_TOKEN", ""]:
        return []
        
    # Đảm bảo đã được khởi tạo
    init_telegram_updates(config)
    
    url = f"https://api.telegram.org/bot{bot_token}/getUpdates"
    params = {"offset": _last_update_id + 1, "timeout": 0}
    
    try:
        response = requests.get(url, params=params, timeout=5)
        if response.status_code != 200:
            return []
            
        data = response.json()
        if not data.get("ok"):
            return []
            
        updates = data.get("result", [])
        choices = []
        for upd in updates:
            upd_id = upd.get("update_id")
            if upd_id is not None:
                _last_update_id = max(_last_update_id, upd_id)
                
            message = upd.get("message")
            if not message:
                continue
                
            msg_chat = message.get("chat", {})
            msg_chat_id = str(msg_chat.get("id", ""))
            
            # Chỉ xử lý tin nhắn từ đúng chat_id được cấu hình để bảo mật
            if chat_id and msg_chat_id != chat_id:
                continue
                
            text = message.get("text", "").strip()
            if not text:
                continue
                
            cmd = text.lower()
            if cmd.startswith("/"):
                # Xử lý các lệnh hệ thống
                if cmd == "/screenshot":
                    print(f"[INFO] Telegram: Nhận lệnh '/screenshot' từ Chat ID {msg_chat_id}")
                    from src.utils import get_active_page
                    active_page = get_active_page()
                    if active_page:
                        screenshot_path = os.path.join(BASE_DIR, "logs", "telegram_requested_screenshot.png")
                        os.makedirs(os.path.dirname(screenshot_path), exist_ok=True)
                        try:
                            active_page.screenshot(path=screenshot_path)
                            send_telegram_message(config, "Ảnh chụp màn hình Chrome hiện tại:", photo_path=screenshot_path)
                        except Exception as se:
                            send_telegram_message(config, f"Lỗi khi chụp màn hình: {se}")
                    else:
                        send_telegram_message(config, "Không tìm thấy trang web đang hoạt động để chụp màn hình.")
                        
                elif cmd == "/pause":
                    print(f"[INFO] Telegram: Nhận lệnh '/pause' từ Chat ID {msg_chat_id}")
                    from src.utils import get_active_page
                    active_page = get_active_page()
                    if active_page:
                        try:
                            active_page.evaluate("sessionStorage.setItem('bot_status', 'paused')")
                            active_page.evaluate("""() => {
                                let btn = document.getElementById('bot-pause-btn');
                                let statusText = document.getElementById('bot-status-text');
                                if (btn) {
                                    btn.setAttribute('data-status', 'paused');
                                    btn.innerText = 'TIẾP TỤC (Resume)';
                                    btn.style.background = '#00ff88';
                                    btn.style.color = '#000';
                                    statusText.innerText = 'ĐÃ TẠM DỪNG';
                                    statusText.style.color = '#ff3366';
                                }
                            }""")
                            send_telegram_message(config, "Bot đã được TẠM DỪNG từ xa thành công.")
                        except Exception as se:
                            send_telegram_message(config, f"Lỗi khi thực hiện tạm dừng: {se}")
                    else:
                        send_telegram_message(config, "Không tìm thấy trang web đang hoạt động để tạm dừng.")
                        
                elif cmd == "/resume":
                    print(f"[INFO] Telegram: Nhận lệnh '/resume' từ Chat ID {msg_chat_id}")
                    from src.utils import get_active_page
                    active_page = get_active_page()
                    if active_page:
                        try:
                            active_page.evaluate("sessionStorage.setItem('bot_status', 'running')")
                            active_page.evaluate("""() => {
                                let btn = document.getElementById('bot-pause-btn');
                                let statusText = document.getElementById('bot-status-text');
                                if (btn) {
                                    btn.setAttribute('data-status', 'running');
                                    btn.innerText = 'TẠM DỪNG (Pause)';
                                    btn.style.background = '#ff3366';
                                    btn.style.color = '#fff';
                                    statusText.innerText = 'Đang chạy...';
                                    statusText.style.color = '#00ff88';
                                }
                            }""")
                            send_telegram_message(config, "Bot đã được TIẾP TỤC chạy từ xa.")
                        except Exception as se:
                            send_telegram_message(config, f"Lỗi khi thực hiện chạy tiếp: {se}")
                    else:
                        send_telegram_message(config, "Không tìm thấy trang web đang hoạt động để chạy tiếp.")
                        
                elif cmd == "/stop":
                    print(f"[INFO] Telegram: Nhận lệnh '/stop' từ Chat ID {msg_chat_id}")
                    send_telegram_message(config, "Nhận lệnh tắt bot từ xa. Đang tắt trình duyệt và dừng chương trình Python...")
                    time.sleep(1)
                    os._exit(0)
                    
                elif cmd in ["/status", "/ketqua"]:
                    print(f"[INFO] Telegram: Nhận lệnh xem trạng thái từ Chat ID {msg_chat_id}")
                    state_path = os.path.join(BASE_DIR, "state.json")
                    if os.path.exists(state_path):
                        try:
                            with open(state_path, "r", encoding="utf-8") as sf:
                                state_data = json.load(sf)
                            
                            date_str = state_data.get("date", "N/A")
                            completed_sbcs = state_data.get("completed_sbcs", {})
                            opened_packs = state_data.get("opened_packs", {})
                            
                            bot_state_str = "Đang chạy 🏃‍♂️"
                            sbc_storage_info = "N/A"
                            ratings_info = "Chưa có dữ liệu"
                            from src.utils import get_active_page
                            active_page = get_active_page()
                            if active_page:
                                try:
                                    is_paused = active_page.evaluate("sessionStorage.getItem('bot_status') === 'paused'")
                                    if is_paused:
                                        bot_state_str = "Đang tạm dừng ⏸️"
                                        
                                    js_data = active_page.evaluate("""() => {
                                        return new Promise((resolve) => {
                                            let result = {
                                                sbc_storage_count: 0,
                                                unassigned_count: 0,
                                                ratings: {}
                                            };
                                            
                                            function addRating(rating) {
                                                if (rating && rating >= 40 && rating <= 100) {
                                                    result.ratings[rating] = (result.ratings[rating] || 0) + 1;
                                                }
                                            }
                                            
                                            // 1. Load SBC Storage
                                            let p_storage = new Promise((resStorage) => {
                                                if (typeof services === 'undefined' || !services.Item || typeof services.Item.searchStorageItems !== 'function') {
                                                    resStorage([]);
                                                    return;
                                                }
                                                try {
                                                    let criteria = new UTSearchCriteriaDTO();
                                                    criteria.type = (typeof SearchType !== 'undefined' && SearchType.PLAYER) ? SearchType.PLAYER : 'player';
                                                    criteria.count = 90;
                                                    criteria.offset = 0;
                                                    let obs = services.Item.searchStorageItems(criteria);
                                                    obs.observe(window, function(observer, response) {
                                                        let items = response?.response?.items || [];
                                                        let players = items.filter(i => i && (i.type === 'player' || (i.isPlayer && i.isPlayer())));
                                                        resStorage(players);
                                                    });
                                                } catch(e) {
                                                    resStorage([]);
                                                }
                                            });
                                            
                                            // 2. Load Unassigned
                                            let p_unassigned = new Promise((resUnassigned) => {
                                                try {
                                                    if (typeof repositories !== 'undefined' && repositories.Item && typeof repositories.Item.getUnassignedItems === 'function') {
                                                        let ui = repositories.Item.getUnassignedItems() || [];
                                                        let players = ui.filter(i => i && (i.type === 'player' || (i.isPlayer && i.isPlayer())));
                                                        resUnassigned(players);
                                                    } else {
                                                        resUnassigned([]);
                                                    }
                                                } catch(e) {
                                                    resUnassigned([]);
                                                }
                                            });
                                            
                                            // 3. Load Club Players (phân trang bypass cache)
                                            let p_club = new Promise((resClub) => {
                                                if (typeof services === 'undefined' || !services.Club || typeof services.Club.search !== 'function') {
                                                    resClub([]);
                                                    return;
                                                }
                                                if (typeof UTSearchCriteriaDTO === 'undefined') {
                                                    resClub([]);
                                                    return;
                                                }
                                                
                                                let accumulated = [];
                                                let offset = 0;
                                                const PAGE_SIZE = 90;
                                                let maxPages = 20; // tối đa 1800 cầu thủ
                                                
                                                const loadPage = () => {
                                                    if (maxPages-- <= 0) {
                                                        resClub(accumulated);
                                                        return;
                                                    }
                                                    
                                                    // Reset cache của club.items trước mỗi trang để ép request mới
                                                    try {
                                                        if (repositories.Item.club && repositories.Item.club.items && typeof repositories.Item.club.items.reset === 'function') {
                                                            repositories.Item.club.items.reset();
                                                        }
                                                    } catch(e) {}
                                                    
                                                    let criteria = new UTSearchCriteriaDTO();
                                                    criteria.type = (typeof SearchType !== 'undefined' && SearchType.PLAYER) ? SearchType.PLAYER : 'player';
                                                    criteria.count = PAGE_SIZE;
                                                    criteria.offset = offset;
                                                    criteria.cacheable = false;
                                                    
                                                    try {
                                                        let obs = services.Club.search(criteria);
                                                        obs.observe(window, function(observer, response) {
                                                            if (response && response.success && response.response && response.response.items) {
                                                                let items = response.response.items;
                                                                let pagePlayers = items.filter(item => item && (item.type === 'player' || (item.isPlayer && item.isPlayer())));
                                                                accumulated = accumulated.concat(pagePlayers);
                                                                
                                                                if (items.length < PAGE_SIZE || response.response.retrievedAll) {
                                                                    resClub(accumulated);
                                                                } else {
                                                                    offset += PAGE_SIZE;
                                                                    setTimeout(loadPage, 150); // Chờ 150ms để không bị rate limit
                                                                }
                                                            } else {
                                                                resClub(accumulated);
                                                            }
                                                        });
                                                    } catch(err) {
                                                        resClub(accumulated);
                                                    }
                                                };
                                                loadPage();
                                            });
                                            
                                            // 4. Tổng hợp tất cả sau khi hoàn thành các Promise
                                            Promise.all([p_storage, p_unassigned, p_club]).then(([storageItems, unassignedItems, clubItems]) => {
                                                result.sbc_storage_count = storageItems.length;
                                                result.unassigned_count = unassignedItems.length;
                                                
                                                // Dùng Map để lọc trùng ID
                                                let uniquePlayersMap = new Map();
                                                
                                                storageItems.forEach(p => {
                                                    if (p && p.id != null) uniquePlayersMap.set(String(p.id), p);
                                                });
                                                unassignedItems.forEach(p => {
                                                    if (p && p.id != null && !uniquePlayersMap.has(String(p.id))) {
                                                        uniquePlayersMap.set(String(p.id), p);
                                                    }
                                                });
                                                clubItems.forEach(p => {
                                                    if (p && p.id != null && !uniquePlayersMap.has(String(p.id))) {
                                                        uniquePlayersMap.set(String(p.id), p);
                                                    }
                                                });
                                                
                                                // Gom rating (lọc thẻ Loan)
                                                uniquePlayersMap.forEach(p => {
                                                    if (p && !p.loan && p.rating) {
                                                        addRating(p.rating);
                                                    }
                                                });
                                                
                                                resolve(result);
                                            }).catch(() => {
                                                resolve(result);
                                            });
                                        });
                                    }""")
                                    
                                    if js_data:
                                        sbc_count = js_data.get("sbc_storage_count", 0)
                                        unassigned_count = js_data.get("unassigned_count", 0)
                                        sbc_storage_info = f"{sbc_count}/100"
                                        if unassigned_count > 0:
                                            sbc_storage_info += f" (+ {unassigned_count} Unassigned)"
                                            
                                        ratings_dict = js_data.get("ratings", {})
                                        # Nhóm và sắp xếp rating từ cao xuống thấp
                                        sorted_ratings = sorted([int(k) for k in ratings_dict.keys()], reverse=True)
                                        
                                        rating_lines = []
                                        # Chỉ hiển thị các rating >= 75 chi tiết (mỗi rate 1 dòng), dưới 75 gom nhóm
                                        under_75_count = 0
                                        for r in sorted_ratings:
                                            count = ratings_dict.get(str(r), 0)
                                            if r >= 75:
                                                rating_lines.append(f"- Rating **{r}**: {count} thẻ")
                                            else:
                                                under_75_count += count
                                                
                                        if under_75_count > 0:
                                            rating_lines.append(f"- Rating **Dưới 75**: {under_75_count} thẻ")
                                            
                                        ratings_info = "\n".join(rating_lines) if rating_lines else "Không có cầu thủ nào."
                                except Exception as je:
                                    print(f"[WARNING] Lỗi lấy thông tin cầu thủ qua JS: {je}")
                                    pass
                            
                            sbc_msg = "\n".join([f"- {k}: {v} lần" for k, v in completed_sbcs.items()]) or "- Chưa hoàn thành SBC nào."
                            pack_msg = "\n".join([f"- {k}: {v} pack" for k, v in opened_packs.items()]) or "- Chưa mở pack nào."
                            
                            report_msg = (
                                f"📊 **BÁO CÁO TIẾN ĐỘ GRIND ({date_str})**\n"
                                f"Trạng thái bot: **{bot_state_str}**\n"
                                f"📦 Kho chứa SBC Storage: **{sbc_storage_info}**\n\n"
                                f"⭐ **Thống kê rating cầu thủ (Club + Storage):**\n"
                                f"{ratings_info}\n\n"
                                f"✅ **SBC đã làm:**\n{sbc_msg}\n\n"
                                f"📦 **Pack đã mở:**\n{pack_msg}"
                            )
                            send_telegram_message(config, report_msg)
                        except Exception as se:
                            send_telegram_message(config, f"Lỗi đọc file state.json: {se}")
                    else:
                        send_telegram_message(config, "Không tìm thấy file state.json.")
            else:
                # Nếu không phải lệnh hệ thống, trả về lựa chọn thông thường (ví dụ: "1", "2", "3" hoặc workflow "15, 16, 17")
                print(f"[INFO] Telegram: Nhận tin nhắn thông thường '{text}' từ người dùng.")
                choices.append(text)
                
        return choices
    except Exception:
        # Không in lỗi ra log để tránh spam khi mất mạng tạm thời
        pass
    return []

def alert_user_error(page, config, message):
    print(f"\n[ALERT] ERROR OR MANUAL INTERVENTION REQUIRED: {message}")
    
    # 1. Chụp ảnh màn hình để debug
    screenshot_path = os.path.join(BASE_DIR, "logs", "error_screenshot.png")
    try:
        page.screenshot(path=screenshot_path)
        print(f"[INFO] Đã lưu ảnh chụp lỗi tại: {screenshot_path}")
    except Exception as se:
        print(f"[WARNING] Không thể chụp ảnh màn hình: {se}")
        screenshot_path = None

    # 2. Alert sound on macOS
    if sys.platform == "darwin":
        try:
            os.system("say 'Attention, error detected'")
            os.system("afplay /System/Library/Sounds/Glass.aiff &")
        except Exception:
            pass
        
    # 3. Send Telegram Webhook notification
    send_telegram_message(config, message, photo_path=screenshot_path)

