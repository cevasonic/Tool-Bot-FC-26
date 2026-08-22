import os
import sys
import json
import time
import datetime
from playwright.sync_api import sync_playwright

# Thêm thư mục hiện tại vào sys.path để import được src/
SKILL_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(SKILL_DIR)

from src.solve_manager import monitor_sbc_solver

class DualLogger(object):
    """
    Ghi đồng thời đầu ra log vào cả Terminal (stdout) và file log.
    """
    def __init__(self, filepath):
        self.terminal = sys.stdout
        self.log = open(filepath, "w", encoding="utf-8")

    def write(self, message):
        self.terminal.write(message)
        self.log.write(message)
        self.log.flush()

    def flush(self):
        self.terminal.flush()
        self.log.flush()

def setup_logging():
    """
    Khởi tạo thư mục logs/ và file log riêng cho kỹ năng giải SBC.
    """
    logs_dir = os.path.join(SKILL_DIR, "logs")
    try:
        os.makedirs(logs_dir, exist_ok=True)
    except Exception:
        pass
    
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_filepath = os.path.join(logs_dir, f"solver_{timestamp}.log")
    
    sys.stdout = DualLogger(log_filepath)
    sys.stderr = sys.stdout
    print(f"[INFO] Hệ thống log SBC Solver đã được khởi tạo: {log_filepath}")

def load_config():
    """
    Tải cấu hình từ config.json của bot chính.
    """
    bot_dir = os.path.abspath(os.path.join(SKILL_DIR, "..", "fc_sbc_bot"))
    config_path = os.path.join(bot_dir, "config.json")
    
    default_config = {
        "sbc_solver": {
            "enabled": True,
            "min_rating_to_use": 80,   # Fix #6: Hạ xuống 80 để solver có đủ lựa chọn
            "max_rating_to_use": 89,   # Fix #6: Tăng lên 89 cho các SBC rating cao
            "prioritize_untradeable": True,
            "prioritize_sbc_storage": True,
            "protected_cards": {
                "active_squad": True,
                "favorites": True,
                "evolutions": True,
                "blacklist_ids": []
            }
        }
    }
    
    if not os.path.exists(config_path):
        return default_config
        
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
            if "sbc_solver" not in config:
                config["sbc_solver"] = default_config["sbc_solver"]
            return config
    except Exception:
        return default_config

def load_paletools_js():
    """
    Đọc script PaleTools từ thư mục tài nguyên của fc_sbc_bot.
    """
    import urllib.parse
    bot_dir = os.path.abspath(os.path.join(SKILL_DIR, "..", "fc_sbc_bot"))
    
    possible_paths = [
        os.path.join(bot_dir, "resources", "paletools.txt"),
        os.path.join(bot_dir, "resources", "paletools.js"),
        os.path.join(bot_dir, "paletools.txt"),
        os.path.join(bot_dir, "paletools.js")
    ]
    
    for path in possible_paths:
        if os.path.exists(path):
            print(f"[INFO] Tìm thấy script PaleTools tại: {path}")
            with open(path, "r", encoding="utf-8") as f:
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
            
    print("[WARNING] Không tìm thấy tệp tin script PaleTools để inject.")
    return None

def main():
    # Setup hệ thống ghi log riêng trước khi chạy
    setup_logging()
    
    config = load_config()
    bot_dir = os.path.abspath(os.path.join(SKILL_DIR, "..", "fc_sbc_bot"))
    chrome_profile_dir = os.path.join(bot_dir, "chrome_profile")
    
    print("\n" + "="*70)
    print("      KÍCH HOẠT KHỞI CHẠY INTERACTIVE SBC SOLVER (FC26)")
    print("="*70 + "\n")
    print(f"[INFO] Profile trình duyệt: {chrome_profile_dir}")
    print("[INFO] Đang khởi chạy Google Chrome...")

    with sync_playwright() as p:
        if not os.path.exists(chrome_profile_dir):
            try:
                os.makedirs(chrome_profile_dir)
            except Exception:
                pass

        context = None
        try:
            context = p.chromium.launch_persistent_context(
                user_data_dir=chrome_profile_dir,
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
            print(f"\n[ERROR] Không thể khởi chạy trình duyệt bằng profile Chrome chính ({e}).")
            print("[GUIDE] Vui lòng đóng tất cả các cửa sổ Chrome đang chạy profile này trước khi khởi chạy tool.")
            return

        context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        page = context.pages[0] if context.pages else context.new_page()

        # Lắng nghe console log
        page.on("console", lambda msg: print(f"[BROWSER CONSOLE] {msg.type.upper()}: {msg.text}"))
        page.on("pageerror", lambda err: print(f"[BROWSER JS EXCEPTION] {err.message}"))

        print("[INFO] Đang điều hướng tới EA FC Web App...")
        page.goto("https://www.ea.com/ea-sports-fc/ultimate-team/web-app/")

        print("[INFO] Vui lòng đăng nhập (nếu cần) và chờ giao diện chính (Dashboard) xuất hiện...")
        
        try:
            page.wait_for_selector(".ut-tab-bar", timeout=180000)
            print("[OK] Đăng nhập thành công! Đã phát hiện Dashboard.")
        except Exception as e:
            print(f"[ERROR] Quá thời gian chờ đăng nhập: {e}")
            context.close()
            return

        paletools_js = load_paletools_js()
        if paletools_js:
            print("[INFO] Đang tiến hành kích hoạt PaleTools trên trình duyệt...")
            try:
                page.evaluate(f"eval({json.dumps(paletools_js)})")
                print("[OK] Đã gửi lệnh kích hoạt PaleTools.")
                time.sleep(3)
            except Exception as pt_err:
                print(f"[WARNING] Không thể inject PaleTools: {pt_err}")

        try:
            monitor_sbc_solver(page, config)
        except KeyboardInterrupt:
            print("\n[INFO] Đang dừng SBC Solver theo yêu cầu...")
        finally:
            print("[INFO] Đang đóng trình duyệt và dọn dẹp tài nguyên...")
            context.close()

if __name__ == "__main__":
    main()
