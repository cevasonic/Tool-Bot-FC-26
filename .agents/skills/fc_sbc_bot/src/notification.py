import os
import sys
import requests
from src.config import BASE_DIR

def alert_user_error(page, config, message):
    print(f"\n[ALERT] ERROR OR MANUAL INTERVENTION REQUIRED: {message}")
    
    # 1. Chụp ảnh màn hình để debug
    screenshot_path = os.path.join(BASE_DIR, "logs", "error_screenshot.png")
    try:
        page.screenshot(path=screenshot_path)
        print(f"[INFO] Đã lưu ảnh chụp lỗi tại: {screenshot_path}")
    except Exception as se:
        print(f"[WARNING] Không thể chụp ảnh màn hình: {se}")

    # 2. Alert sound on macOS
    if sys.platform == "darwin":
        try:
            os.system("say 'Attention, error detected'")
            os.system("afplay /System/Library/Sounds/Glass.aiff &")
        except Exception:
            pass
        
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
