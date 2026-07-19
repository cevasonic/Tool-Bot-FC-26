import os
import sys
import time
import json
import re
from playwright.sync_api import sync_playwright

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def get_sbc_repeats_text(tile_locator):
    import re
    try:
        # 1. ƯU TIÊN tìm phần tử con chứa thông tin tiến trình hoàn thành (ví dụ: 1/1 SBCs)
        progress_el = tile_locator.locator(".ut-sbc-set-tile-view--progress-block, .progress-block, [class*='progress']").first
        if progress_el.count() > 0 and progress_el.is_visible():
            prog_text = progress_el.text_content()
            match_prog = re.search(r'(?:[Cc]ompleted|[Hh]oàn\s*thành|[Ll]ượt|[Ll]ần|[Rr]epeat[s]?|SBC[s]?)\s*[^0-9]*(\d+)\s*/\s*(\d+)', prog_text, re.IGNORECASE)
            if match_prog:
                done = int(match_prog.group(1))
                total = int(match_prog.group(2))
                return f"Parsed Completed format: {done}/{total} (Remaining: {max(0, total - done)})"

        # 2. Tìm phần tử con chứa thông tin repeatable tĩnh (ví dụ: Repeatable: 0)
        repeat_el = tile_locator.locator(".ut-squad-building-set-status-label-view.repeat, .repeat, [class*='repeat']").first
        if repeat_el.count() > 0 and repeat_el.is_visible():
            rep_text = repeat_el.text_content()
            match_rep = re.search(r'(?:[Rr]epeatable|[Rr]epeat|[Ll]ượt\s*làm\s*lại|[Ll]ặp\s*lại)\s*:\s*(\d+)', rep_text, re.IGNORECASE)
            if match_rep:
                val = int(match_rep.group(1))
                if val < 200:
                    return f"Parsed Repeatable format: {val}"
        
        # 3. Fallback dùng toàn bộ text của tile nếu cấu trúc HTML thay đổi
        tile_text = tile_locator.text_content()
        if tile_text:
            match_prog = re.search(r'(?:[Cc]ompleted|[Hh]oàn\s*thành|[Ll]ượt|[Ll]ần|[Rr]epeat[s]?)\s*[^0-9]*(\d+)\s*/\s*(\d+)', tile_text, re.IGNORECASE)
            if match_prog:
                done = int(match_prog.group(1))
                total = int(match_prog.group(2))
                return f"Parsed Completed format: {done}/{total} (Remaining: {max(0, total - done)})"
                
            match_rep = re.search(r'(?:[Rr]epeatable|[Rr]epeat|[Ll]ượt\s*làm\s*lại|[Ll]ặp\s*lại)\s*:\s*(\d+)\b', tile_text, re.IGNORECASE)
            if match_rep:
                val = int(match_rep.group(1))
                if val < 200:
                    return f"Parsed Repeatable format: {val}"

            if any(w in tile_text.lower() for w in ["completed", "hoàn thành", "đã hoàn thành", "đã làm"]):
                return "Parsed Completed format: Fully completed (Remaining: 0)"
            
    except Exception as e:
        return f"Error: {e}"
    return "Not detected"

def scan_sbc_tiles(page):
    print("\n--- SCANNED SBC TILES ---")
    selectors = [
        ".ut-sbc-tile-view",
        ".sbc-item-view",
        ".tile",
        ".sbcItem",
        ".sbc-tile",
        ".SbcItemView",
        ".ItemView"
    ]
    
    found_any = False
    scanned_texts = set()
    
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
                
                # Lấy tên SBC
                lines = [l.strip() for l in text.split('\n') if l.strip()]
                sbc_name = lines[0] if lines else "Unknown"
                
                result = get_sbc_repeats_text(loc)
                print(f"SBC: {sbc_name}")
                print(f"  Full Text: {text_clean[:120]}...")
                print(f"  Detection: {result}")
                print("-" * 40)
                found_any = True
        except Exception as e:
            pass
            
    if not found_any:
        print("No SBC tiles found on screen. Please make sure you are in the SBC menu and tiles are visible.")

def main():
    print("=== EA FC SBC Repeatable Detector Test ===")
    user_data_dir = os.path.join(BASE_DIR, "chrome_profile")
    
    with sync_playwright() as p:
        print("[INFO] Launching browser...")
        try:
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
            print(f"[WARNING] Could not launch Chrome with profile ({e}). Falling back to Chromium...")
            context = p.chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                headless=False,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox"
                ],
                viewport={"width": 1280, "height": 800}
            )
            
        page = context.pages[0] if context.pages else context.new_page()
        page.goto("https://www.ea.com/ea-sports-fc/ultimate-team/web-app/")
        
        print("\n" + "="*60)
        print("Please log in to the EA Web App and navigate to the SBC section.")
        print("Once you are on the SBC page, press ENTER in this terminal to scan.")
        print("Enter 'q' to quit.")
        print("="*60 + "\n")
        
        while True:
            cmd = input("Press ENTER to scan SBC tiles (or 'q' to quit): ").strip().lower()
            if cmd == 'q':
                break
            
            try:
                scan_sbc_tiles(page)
            except Exception as e:
                print(f"[ERROR] Error scanning page: {e}")
                
        context.close()

if __name__ == "__main__":
    main()
