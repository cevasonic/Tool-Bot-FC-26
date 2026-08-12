import time
import random
from src.notification import alert_user_error

GLOBAL_ACTIVE_PAGE = None

def set_active_page(page):
    global GLOBAL_ACTIVE_PAGE
    GLOBAL_ACTIVE_PAGE = page

def get_active_page():
    return GLOBAL_ACTIVE_PAGE

def sleep_human_like(min_sec, max_sec, page=None):
    global GLOBAL_ACTIVE_PAGE
    # Import cục bộ để tránh import vòng tròn
    from src.paletools import check_pause
    
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
                        close_btn = modal.locator("button.close, .btn-flat, .dialog-close-btn, button:has-text('OK'), button:has-text('Close'), .btn-standard:has-text('OK'), .btn-standard:has-text('Close'), .btn-standard:has-text('Ok'), button:has-text('Đóng'), button:has-text('Tắt'), button:has-text('Accept')").first
                        if close_btn.count() > 0 and close_btn.is_visible():
                            try:
                                close_btn.click(timeout=2000, force=True)
                                sleep_human_like(0.5, 1.0, page)
                            except Exception:
                                pass
                        
                        if modal.is_visible():
                            page.keyboard.press("Escape")
                            sleep_human_like(0.5, 1.0, page)
    except Exception:
        pass

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
        sleep_human_like(2.0, 3.0, page)

def recover_from_crash(page, config, paletools_js):
    import os
    import json
    from src.config import BASE_DIR
    print("\n[WARNING] Phát hiện Web App có dấu hiệu bị sập hoặc đơ giao diện. Tiến hành reload trang để tự động khôi phục...")
    try:
        # Chụp ảnh debug trước khi reload
        try:
            os.makedirs(os.path.join(BASE_DIR, "logs"), exist_ok=True)
            page.screenshot(path=os.path.join(BASE_DIR, "logs", "crash_before_reload.png"))
        except Exception:
            pass
            
        page.reload()
        # Chờ Dashboard tải lại (tab bar xuất hiện)
        print("[INFO] Đang chờ Web App tải lại giao diện Dashboard...")
        page.wait_for_selector(".ut-tab-bar", timeout=90000)
        print("[OK] Đã tải xong Dashboard. Tiến hành nạp lại PaleTools...")
        sleep_human_like(2.0, 4.0, page)
        
        # Nạp lại PaleTools
        page.evaluate(f"eval({json.dumps(paletools_js)})")
        time.sleep(5)
        dismiss_modals(page)
        
        # Tạo lại overlay panel
        from src.paletools import ensure_bot_overlay
        ensure_bot_overlay(page)
        print("[OK] Đã khôi phục giao diện Web App thành công!\n")
        return True
    except Exception as reload_err:
        print(f"[ERROR] Không thể tự động khôi phục Web App: {reload_err}")
        return False
