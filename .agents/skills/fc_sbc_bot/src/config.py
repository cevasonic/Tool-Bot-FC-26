import os
import sys
import json
import datetime

# Do config.py nằm trong src/, nên thư mục gốc của bot là thư mục cha của src/
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PALETOOLS_PATH = os.path.join(BASE_DIR, "resources", "paletools.txt")

GLOBAL_CONFIG = None

def get_config():
    global GLOBAL_CONFIG
    if GLOBAL_CONFIG is None:
        config_path = os.path.join(BASE_DIR, "config.json")
        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    GLOBAL_CONFIG = json.load(f)
            except Exception:
                pass
    return GLOBAL_CONFIG

def set_config(cfg):
    global GLOBAL_CONFIG
    GLOBAL_CONFIG = cfg

class DualLogger(object):
    def __init__(self, filepath):
        self.terminal = sys.stdout
        self.log = open(filepath, "w", encoding="utf-8")
        self.buffer = ""

    def write(self, message):
        if not message:
            return
            
        self.buffer += message
        while "\n" in self.buffer:
            line, self.buffer = self.buffer.split("\n", 1)
            self._process_line(line + "\n")

    def _process_line(self, line):
        # Bỏ qua các dòng debug rác của SBC để giữ sạch log và console
        noise_keywords = [
            "[DEBUG_SBC]", 
            "DEBUG_SBC", 
            "Thử phân tích tile text:", 
            "Phát hiện status block", 
            "Tìm thấy repeat element text:", 
            "Không xác định được số lượt repeatable"
        ]
        if any(kw in line for kw in noise_keywords):
            return
            
        # Ghi ra terminal (giữ nguyên không thêm timestamp để console sạch sẽ)
        self.terminal.write(line)
        self.terminal.flush()
        
        # Ghi ra file log kèm timestamp ở đầu dòng
        clean_line = line.strip()
        if clean_line:
            timestamp = datetime.datetime.now().strftime("[%Y-%m-%d %H:%M:%S] ")
            self.log.write(timestamp + line)
        else:
            self.log.write(line)
        self.log.flush()

    def flush(self):
        if self.buffer:
            self._process_line(self.buffer)
            self.buffer = ""
        self.terminal.flush()
        self.log.flush()

def setup_logging():
    # Tạo thư mục logs trong thư mục project nếu chưa tồn tại
    logs_dir = os.path.join(BASE_DIR, "logs")
    if not os.path.exists(logs_dir):
        try:
            os.makedirs(logs_dir)
        except Exception:
            pass

    # Tạo tên file log chứa timestamp động cho mỗi lượt chạy
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_filepath = os.path.join(logs_dir, f"bot_{timestamp}.log")

    sys.stdout = DualLogger(log_filepath)
    sys.stderr = sys.stdout
    print(f"[INFO] Hệ thống log đã được khởi tạo: {log_filepath}")

def load_config_and_setup_logging():
    # Setup log trước để ghi lại quá trình load config
    setup_logging()
    
    config_path = os.path.join(BASE_DIR, "config.json")
    if not os.path.exists(config_path):
        print("[ERROR] Không tìm thấy tệp config.json!")
        sys.exit(1)
        
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
    except json.JSONDecodeError as jde:
        print(f"[ERROR] config.json có lỗi cú pháp JSON: {jde}")
        sys.exit(1)
    except Exception as e:
        print(f"[ERROR] Không thể đọc config.json: {e}")
        sys.exit(1)
        
    # Chuyển đổi cấu hình cũ sang cấu trúc workflow mới nếu cần thiết (Tương thích ngược)
    workflow = config.get("workflow")
    if workflow is None:
        print("[INFO] Không tìm thấy 'workflow' trong config.json. Tự động chuyển đổi cấu hình cũ sang workflow...")
        workflow = []
        step_num = 1
        
        target_sbcs = config.get("target_sbcs")
        if isinstance(target_sbcs, list):
            for sbc in target_sbcs:
                if isinstance(sbc, dict) and "name" in sbc:
                    workflow.append({
                        "step": step_num,
                        "type": "sbc",
                        "sbc_name": sbc["name"],
                        "max_repeats": sbc.get("max_repeats", 1)
                    })
                    step_num += 1
                    
        target_packs = config.get("target_packs")
        if isinstance(target_packs, list):
            for pack in target_packs:
                if isinstance(pack, str):
                    workflow.append({
                        "step": step_num,
                        "type": "open_pack",
                        "pack_name": pack,
                        "open_all": True
                    })
                    step_num += 1
        config["workflow"] = workflow
        
    set_config(config)
    return config
