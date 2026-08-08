import os
import sys
import time
import re
from playwright.sync_api import sync_playwright

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def main():
    print("=== SBC Tile HTML Diagnostic (Robust Scan) ===")
    user_data_dir = os.path.join(BASE_DIR, "chrome_profile")
    
    with sync_playwright() as p:
        print("[INFO] Launching Chrome headless...")
        context = p.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox"
            ],
            viewport={"width": 1280, "height": 800}
        )
            
        page = context.pages[0] if context.pages else context.new_page()
        page.goto("https://www.ea.com/ea-sports-fc/ultimate-team/web-app/")
        
        print("[INFO] Waiting for login dashboard...")
        try:
            page.wait_for_selector(".ut-tab-bar", timeout=30000)
            print("[OK] Dashboard loaded.")
        except Exception:
            print("[ERROR] Timeout waiting for login dashboard.")
            context.close()
            return
            
        print("[INFO] Navigating to SBC menu...")
        page.locator(".ut-tab-bar-item.icon-sbc").click()
        
        # Wait for the SBC hub container to appear
        print("[INFO] Waiting for SBC Hub view to load...")
        try:
            page.wait_for_selector(".ut-sbc-hub-view, .ut-sbc-tile-view, .ut-sbc-grid-view", timeout=20000)
            print("[OK] SBC Hub loaded.")
            time.sleep(2.0)
        except Exception as e:
            print(f"[WARNING] Timeout waiting for SBC Hub view: {e}")
            page.screenshot(path=os.path.join(BASE_DIR, "sbc_hub_load_error.png"))
            context.close()
            return
        
        # List tab buttons
        try:
            buttons = page.locator(".ut-navigation-container button, .ut-sbc-hub-view button, .ut-navigation-bar button").all()
            print(f"[DEBUG] Found {len(buttons)} buttons in header:")
            for idx, btn in enumerate(buttons):
                if btn.is_visible():
                    print(f"  Button {idx}: '{btn.text_content().strip()}'")
        except Exception as e:
            print(f"[WARNING] Error listing buttons: {e}")
            
        # Click 'All' or 'Tất cả' tab
        clicked_tab = False
        for tab_name in ["All", "Tất cả", "Challenges", "Live", "Upgrades"]:
            try:
                tab_btn = page.locator(f"button:has-text('{tab_name}')").first
                if tab_btn.count() > 0 and tab_btn.is_visible():
                    print(f"[INFO] Clicking tab '{tab_name}'...")
                    tab_btn.click()
                    clicked_tab = True
                    time.sleep(3.0)
                    break
            except Exception:
                pass
                
        if not clicked_tab:
            print("[WARNING] Could not click any specific tab. Scanning default tab.")
                
        # Scroll down multiple times to lazy load all tiles
        print("[INFO] Scrolling down to load lazy tiles...")
        for scroll_attempt in range(5):
            page.evaluate("""
                window.scrollTo(0, document.body.scrollHeight);
                const containers = document.querySelectorAll('.ut-navigation-container-view, .ut-sbc-hub-view, .ut-sbc-grid-view');
                containers.forEach(c => {
                    c.scrollTop = c.scrollHeight;
                });
            """)
            time.sleep(0.8)
            
        # Print all visible SBC tiles
        selectors = [
            ".ut-sbc-tile-view",
            ".sbc-item-view",
            ".tile",
            ".sbcItem",
            ".SbcItemView"
        ]
        
        scanned_texts = set()
        print("\n=== SCANNING ALL SBC TILES ON PAGE ===")
        for selector in selectors:
            try:
                locators = page.locator(selector).all()
                for loc in locators:
                    if not loc.is_visible():
                        continue
                    text = loc.text_content()
                    if not text:
                        continue
                    text_clean = " ".join(text.split())
                    if text_clean in scanned_texts:
                        continue
                    scanned_texts.add(text_clean)
                    
                    lines = [l.strip() for l in text.split('\n') if l.strip()]
                    title = lines[0] if lines else "Unknown"
                    print(f"SBC: '{title}'")
                    print(f"  Raw lines: {lines}")
                    print(f"  Cleaned text: {text_clean}")
                    print("-" * 50)
            except Exception as e:
                pass
                
        page.screenshot(path=os.path.join(BASE_DIR, "broad_scan_sbc_page.png"))
        print("[INFO] Saved broad_scan_sbc_page.png")
        context.close()

if __name__ == "__main__":
    main()
