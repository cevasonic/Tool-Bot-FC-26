import os
import sys
from contextlib import contextmanager
from playwright.sync_api import sync_playwright
from src.config import BASE_DIR

def global_exception_handler(exctype, value, tb):
    if "closed" in str(value).lower() or "target" in str(value).lower():
        print("\n[INFO] Trình duyệt đã bị đóng đột ngột (bởi người dùng hoặc hệ thống). Dừng bot an toàn.")
    else:
        sys.__excepthook__(exctype, value, tb)

def register_exception_handler():
    sys.excepthook = global_exception_handler

@contextmanager
def init_browser(config):
    with sync_playwright() as p:
        user_data_dir = os.path.join(BASE_DIR, "chrome_profile")
        if not os.path.exists(user_data_dir):
            try:
                os.makedirs(user_data_dir)
            except Exception:
                pass
            
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
            print(f"\n[WARNING] Không thể chạy Chrome bằng profile cá nhân ({e}).")
            print("[IMPORTANT] GỢI Ý: Hãy kiểm tra và đảm bảo không có cửa sổ Chrome nào khác đang mở profile này.")
            print("[INFO] Đang chạy fallback bằng Chromium với thư mục profile dự phòng (chrome_profile_fallback)...")
            fallback_user_data_dir = os.path.join(BASE_DIR, "chrome_profile_fallback")
            if not os.path.exists(fallback_user_data_dir):
                try:
                    os.makedirs(fallback_user_data_dir)
                except Exception:
                    pass
            try:
                context = p.chromium.launch_persistent_context(
                    user_data_dir=fallback_user_data_dir,
                    headless=config.get("headless", False),
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--no-sandbox"
                    ],
                    viewport={"width": 1280, "height": 800}
                )
            except Exception as e2:
                print(f"[ERROR] Không thể khởi chạy trình duyệt fallback: {e2}")
                sys.exit(1)
        
        context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        # Đóng tất cả các tab phụ để tránh xung đột
        while len(context.pages) > 1:
            try:
                context.pages[-1].close()
            except Exception:
                break
        page = context.pages[0] if context.pages else context.new_page()
        
        try:
            yield context, page
        finally:
            if context:
                try:
                    context.close()
                except Exception:
                    pass
