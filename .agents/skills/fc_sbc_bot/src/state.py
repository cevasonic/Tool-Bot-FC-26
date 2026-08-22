import os
import json
import time
from src.config import BASE_DIR

STATE_FILE = os.path.join(BASE_DIR, "state.json")

def load_daily_state():
    """
    Nạp trạng thái hàng ngày từ state.json.
    Nếu file không tồn tại hoặc khác ngày hiện tại, trả về một trạng thái mới và ghi đè file.
    """
    current_date = time.strftime("%Y-%m-%d")
    default_state = {
        "date": current_date,
        "completed_sbcs": {},
        "opened_packs": {},
        "context_vars": {},
        "steps_finished": {}
    }
    
    if not os.path.exists(STATE_FILE):
        save_daily_state(default_state)
        return default_state
        
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            state = json.load(f)
            
        if state.get("date") == current_date:
            print(f"[STATE] Đã nạp thành công trạng thái ngày {current_date} từ lần chạy trước.")
            # Chuyển đổi các key trong steps_finished về int
            if "steps_finished" in state:
                state["steps_finished"] = {int(k) if k.isdigit() else k: v for k, v in state["steps_finished"].items()}
            return state
        else:
            print(f"[STATE] Phát hiện trạng thái cũ ngày {state.get('date')}. Hôm nay là {current_date}, tiến hành reset trạng thái hàng ngày.")
            save_daily_state(default_state)
            return default_state
    except Exception as e:
        print(f"[STATE] Không thể nạp state.json ({e}). Tiến hành khởi tạo trạng thái mới.")
        save_daily_state(default_state)
        return default_state

def save_daily_state(state):
    """
    Ghi trạng thái hiện tại vào state.json.
    """
    try:
        # Đảm bảo key trong steps_finished là string khi serialize ra JSON
        state_to_save = state.copy()
        if "steps_finished" in state_to_save:
            state_to_save["steps_finished"] = {str(k): v for k, v in state_to_save["steps_finished"].items()}
            
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state_to_save, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[STATE] Lỗi khi ghi state.json: {e}")
