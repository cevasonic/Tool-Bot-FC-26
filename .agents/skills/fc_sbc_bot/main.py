import os
import sys
import time
import json
from src.config import BASE_DIR, load_config_and_setup_logging
from src.browser import init_browser, register_exception_handler
from src.paletools import load_paletools_js, ensure_paletools_injected
from src.utils import set_active_page, sleep_human_like, dismiss_modals
from src.notification import alert_user_error
from src.sbc import execute_sbc_step
from src.store import execute_open_pack_step

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

def is_session_active(page):
    try:
        current_url = page.url
        if "auth.html" in current_url:
            return False
        return True
    except Exception:
        return False

def run():
    config = load_config_and_setup_logging()
    workflow = config.get("workflow", [])
    paletools_js = load_paletools_js()
    
    register_exception_handler()
    
    print("=== BẮT ĐẦU CHẠY FC ULTIMATE TEAM SBC BOT ===")
    
    with init_browser(config) as (context, page):
        # Thiết lập page hiện tại để dùng cho sleep_human_like và check_pause
        set_active_page(page)
        
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
            sleep_human_like(3.0, 5.0, page)
        except Exception as e:
            print(f"[ERROR] Lỗi khi chờ giao diện Dashboard: {e}")
            alert_user_error(page, config, "Lỗi tải Dashboard Web App")
            sys.exit(1)
            
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
        
        loop_count = 1
        max_loops = 3
        
        # Khởi tạo trạng thái hoàn thành của tất cả các bước trong workflow
        steps_finished = {}
        for idx, step_cfg in enumerate(workflow):
            steps_finished[idx] = False
                
        while loop_count <= max_loops:
            print(f"\n============================================================")
            print(f"[WORKFLOW LOOP] BẮT ĐẦU VÒNG LẶP WORKFLOW THỨ {loop_count}/{max_loops}")
            print(f"============================================================\n")
            
            any_sbc_made_progress = False
            session_lost = False
            
            for idx, step_cfg in enumerate(workflow):
                # Kiểm tra session trước khi bắt đầu mỗi bước
                if not is_session_active(page):
                    alert_user_error(page, config, "Session bị ngắt kết nối hoặc hết hạn (bị chuyển hướng về trang auth.html).")
                    print("[ERROR] Trình duyệt đã bị chuyển hướng về màn hình đăng nhập. Dừng thực thi workflow.")
                    session_lost = True
                    break
                    
                step_num = step_cfg.get("step", "N/A")
                step_type = step_cfg.get("type")
                
                if step_type == "sbc":
                    # Nếu bước SBC này đã hoàn thành ở vòng lặp trước, bỏ qua
                    if steps_finished.get(idx, False):
                        print(f"\n[WORKFLOW] Bước {step_num} (SBC: {step_cfg.get('sbc_name')}) đã hoàn thành ở vòng trước. Bỏ qua.")
                        continue
                        
                    sbc_name = step_cfg.get("sbc_name")
                    max_repeats = step_cfg.get("max_repeats", -1)
                    supply_pack_name = step_cfg.get("supply_pack_name")
                    if max_repeats == -1:
                        max_repeats = 999999
                        
                    print(f"\n[WORKFLOW] --- THỰC HIỆN BƯỚC {step_num} (SBC: {sbc_name}) ---")
                    
                    success_count, completed_sbcs_total, is_finished = execute_sbc_step(
                        page, config, paletools_js, sbc_name, max_repeats, completed_sbcs_total, supply_pack_name=supply_pack_name
                    )
                    
                    if success_count > 0:
                        any_sbc_made_progress = True
                        
                    steps_finished[idx] = is_finished
                    
                    save_count_key = step_cfg.get("save_count_key")
                    if save_count_key:
                        if save_count_key in context_vars:
                            context_vars[save_count_key] += success_count
                        else:
                            context_vars[save_count_key] = success_count
                        print(f"[WORKFLOW] Đã lưu số lần SBC thành công tích lũy: {context_vars[save_count_key]} lần vào biến '{save_count_key}'")
                        
                elif step_type == "open_pack":
                    # Nếu bước mở pack này đã hoàn thành ở vòng lặp trước, bỏ qua
                    if steps_finished.get(idx, False):
                        print(f"\n[WORKFLOW] Bước {step_num} (OPEN_PACK: {step_cfg.get('pack_name')}) đã hoàn thành ở vòng trước. Bỏ qua.")
                        continue

                    pack_name = step_cfg.get("pack_name")
                    open_all = step_cfg.get("open_all", False)
                    count_key = step_cfg.get("count_key")
                    
                    open_count = None
                    if count_key:
                        open_count = context_vars.get(count_key, 0)
                        if open_count <= 0:
                            # Tìm xem bước SBC nguồn đã hoàn thành hoàn toàn chưa
                            sbc_source_finished = True
                            for s_idx, s_cfg in enumerate(workflow):
                                if s_cfg.get("type") == "sbc" and s_cfg.get("save_count_key") == count_key:
                                    if not steps_finished.get(s_idx, False):
                                        sbc_source_finished = False
                                        break
                            if sbc_source_finished:
                                steps_finished[idx] = True
                            continue
                        print(f"\n[WORKFLOW] --- THỰC HIỆN BƯỚC {step_num} (OPEN_PACK: {pack_name}) ---")
                        print(f"[WORKFLOW] Lấy số lượng mở pack từ biến '{count_key}': {open_count} lần")
                    else:
                        print(f"\n[WORKFLOW] --- THỰC HIỆN BƯỚC {step_num} (OPEN_PACK: {pack_name}) ---")
                    
                    if not count_key and not open_all:
                        open_all = True
                        
                    opened_count, is_finished = execute_open_pack_step(
                        page, config, paletools_js, pack_name, open_count=open_count, open_all=open_all
                    )
                    
                    # Chỉ cập nhật và trừ bớt số lượng pack chưa mở nếu mở thành công ít nhất 1 pack
                    if count_key and opened_count > 0:
                        context_vars[count_key] = max(0, context_vars[count_key] - opened_count)
                        print(f"[WORKFLOW] Đã mở thành công {opened_count} pack. Số lượng pack còn lại cần mở trong biến '{count_key}': {context_vars[count_key]}")
                    
                    # Đánh dấu bước là hoàn thành nếu hàm execute_open_pack_step báo đã xong (hoặc đã mở hết pack)
                    if is_finished:
                        if count_key:
                            # Chỉ hoàn thành khi biến tích lũy về 0 VÀ bước SBC nguồn đã hoàn thành hoàn toàn
                            sbc_source_finished = True
                            for s_idx, s_cfg in enumerate(workflow):
                                if s_cfg.get("type") == "sbc" and s_cfg.get("save_count_key") == count_key:
                                    if not steps_finished.get(s_idx, False):
                                        sbc_source_finished = False
                                        break
                            if context_vars[count_key] <= 0 and sbc_source_finished:
                                steps_finished[idx] = True
                        else:
                            steps_finished[idx] = True
                            
                else:
                    print(f"[WARNING] Loại bước '{step_type}' không được hỗ trợ. Bỏ qua.")
                    
            if session_lost:
                break
                
            # Kiểm tra điều kiện thoát vòng lặp workflow:
            # 1. Tất cả các bước trong workflow đã hoàn thành (True)
            if all(steps_finished.values()):
                print("\n[WORKFLOW LOOP] Tất cả các bước trong workflow đã hoàn thành đúng và hết lượt!")
                break
                
            # 2. Nếu không có bước SBC nào làm thêm được lượt ở vòng này, dừng lại để tránh lặp vô ích
            if not any_sbc_made_progress and loop_count > 1:
                print("\n[WORKFLOW LOOP] Không có bước SBC nào thực hiện thêm thành công ở vòng lặp này. Dừng kiểm tra lại.")
                break
                
            loop_count += 1
            
        print("\n=== HOÀN THÀNH TOÀN BỘ CHƯƠNG TRÌNH BOT ===")

if __name__ == "__main__":
    run()
