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
from src.state import load_daily_state, save_daily_state

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
            # Reset trạng thái bot về running khi khởi động bot phiên mới
            try:
                page.evaluate("sessionStorage.setItem('bot_status', 'running')")
            except Exception:
                pass
            dismiss_modals(page)
            try:
                page.evaluate("document.title = '★★★ BOT CHROME WINDOW - THAO TAC TAI DAY ★★★'")
            except Exception:
                pass
        except Exception as e:
            print(f"[ERROR] Không thể nạp PaleTools: {e}")
            alert_user_error(page, config, "Lỗi nạp PaleTools.")
            sys.exit(1)
            
        # Nạp trạng thái hàng ngày từ state.json
        daily_state = load_daily_state()
        
        context_vars = daily_state.get("context_vars", {})
        completed_sbcs_daily = daily_state.get("completed_sbcs", {})
        opened_packs_daily = daily_state.get("opened_packs", {})
        steps_finished = daily_state.get("steps_finished", {})
        
        # Đảm bảo tất cả các bước trong workflow hiện tại được khởi tạo trạng thái
        for idx, step_cfg in enumerate(workflow):
            if idx not in steps_finished:
                steps_finished[idx] = False
                
        completed_sbcs_total = sum(completed_sbcs_daily.values())
        
        loop_count = 1
        max_loops = 3
                
        while loop_count <= max_loops:
            print(f"\n============================================================")
            print(f"[WORKFLOW LOOP] BẮT ĐẦU VÒNG LẶP WORKFLOW THỨ {loop_count}/{max_loops}")
            print(f"============================================================\n")
            
            # Đặt lại trạng thái hoàn thành của các tác vụ mở pack ở đầu vòng lặp mới (từ vòng 2 trở đi)
            if loop_count > 1:
                for idx, step_cfg in enumerate(workflow):
                    if step_cfg.get("type") == "open_pack":
                        steps_finished[idx] = False
                daily_state["steps_finished"] = steps_finished
                save_daily_state(daily_state)
            
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
                        
                    # Tính toán số lượt thực tế cần làm trong lượt chạy này dựa trên số lần đã làm trong ngày
                    done_today = completed_sbcs_daily.get(sbc_name, 0)
                    if max_repeats != 999999:
                        max_repeats_adjusted = max_repeats - done_today
                        if max_repeats_adjusted <= 0:
                            print(f"\n[WORKFLOW] Bước {step_num} (SBC: {sbc_name}) đã làm đủ số lần trong ngày ({done_today}/{max_repeats}). Đánh dấu hoàn thành.")
                            steps_finished[idx] = True
                            daily_state["steps_finished"] = steps_finished
                            save_daily_state(daily_state)
                            continue
                        print(f"[WORKFLOW] SBC '{sbc_name}' trong ngày đã làm {done_today} lần. Lượt này cần làm thêm {max_repeats_adjusted} lần (Mục tiêu: {max_repeats}).")
                        max_repeats_run = max_repeats_adjusted
                    else:
                        max_repeats_run = max_repeats
                        
                    # Định nghĩa callback lưu trạng thái thời gian thực sau mỗi lượt SBC thành công
                    def on_sbc_success_cb():
                        nonlocal completed_sbcs_total, any_sbc_made_progress
                        any_sbc_made_progress = True
                        completed_sbcs_daily[sbc_name] = completed_sbcs_daily.get(sbc_name, 0) + 1
                        completed_sbcs_total += 1
                        if save_count_key:
                            context_vars[save_count_key] = context_vars.get(save_count_key, 0) + 1
                            print(f"[STATE CALLBACK] Cập nhật: {sbc_name} (+1), {save_count_key} ({context_vars[save_count_key]})")
                        else:
                            print(f"[STATE CALLBACK] Cập nhật: {sbc_name} (+1)")
                        daily_state["completed_sbcs"] = completed_sbcs_daily
                        daily_state["context_vars"] = context_vars
                        save_daily_state(daily_state)
                        
                    print(f"\n[WORKFLOW] --- THỰC HIỆN BƯỚC {step_num} (SBC: {sbc_name}) ---")
                    
                    success_count, completed_sbcs_total_run, is_finished = execute_sbc_step(
                        page, config, paletools_js, sbc_name, max_repeats_run, completed_sbcs_total, supply_pack_name=supply_pack_name, on_success_cb=on_sbc_success_cb
                    )
                    
                    steps_finished[idx] = is_finished
                    
                    # Cập nhật và lưu lại trạng thái hoàn thành
                    daily_state["steps_finished"] = steps_finished
                    save_daily_state(daily_state)
                        
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
                                daily_state["steps_finished"] = steps_finished
                                save_daily_state(daily_state)
                            continue
                        print(f"\n[WORKFLOW] --- THỰC HIỆN BƯỚC {step_num} (OPEN_PACK: {pack_name}) ---")
                        print(f"[WORKFLOW] Lấy số lượng mở pack từ biến '{count_key}': {open_count} lần")
                    else:
                        print(f"\n[WORKFLOW] --- THỰC HIỆN BƯỚC {step_num} (OPEN_PACK: {pack_name}) ---")
                    
                    if not count_key and not open_all:
                        open_all = True
                        
                    # Định nghĩa callback lưu trạng thái thời gian thực sau mỗi lượt mở pack thành công
                    def on_pack_success_cb():
                        opened_packs_daily[pack_name] = opened_packs_daily.get(pack_name, 0) + 1
                        if count_key:
                            context_vars[count_key] = max(0, context_vars.get(count_key, 0) - 1)
                            print(f"[STATE CALLBACK] Đã mở 1 pack '{pack_name}'. Còn lại cần mở: {context_vars[count_key]}, Tổng đã mở hôm nay: {opened_packs_daily[pack_name]}")
                        else:
                            print(f"[STATE CALLBACK] Đã mở 1 pack '{pack_name}' (open_all), Tổng đã mở hôm nay: {opened_packs_daily[pack_name]}")
                        daily_state["context_vars"] = context_vars
                        daily_state["opened_packs"] = opened_packs_daily
                        save_daily_state(daily_state)
                        
                    opened_count, is_finished = execute_open_pack_step(
                        page, config, paletools_js, pack_name, open_count=open_count, open_all=open_all, on_success_cb=on_pack_success_cb
                    )
                    
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
                            
                    # Cập nhật và lưu lại trạng thái hoàn thành
                    daily_state["steps_finished"] = steps_finished
                    save_daily_state(daily_state)
                            
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
