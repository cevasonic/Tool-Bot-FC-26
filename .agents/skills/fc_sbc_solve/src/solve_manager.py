import os
import time
import json
from src.solver import solve_sbc

# Thư mục gốc của skill sbc_solve
SOLVE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXTRACTOR_JS_PATH = os.path.join(SOLVE_DIR, "src", "sbc_extractor.js")


# =============================================================================
# PHẦN 1: INJECT SCRIPT
# =============================================================================

def inject_extractor_script(page):
    """Đọc và inject file sbc_extractor.js vào trang Web App."""
    if not os.path.exists(EXTRACTOR_JS_PATH):
        print(f"[SOLVER MANAGER ERROR] Không tìm thấy file script: {EXTRACTOR_JS_PATH}")
        return False
    try:
        with open(EXTRACTOR_JS_PATH, "r", encoding="utf-8") as f:
            js_content = f.read()
        page.evaluate(js_content)
        print("[SOLVER MANAGER] Đã inject sbc_extractor.js thành công.")
        return True
    except Exception as e:
        print(f"[SOLVER MANAGER ERROR] Lỗi khi inject script: {e}")
        return False


# =============================================================================
# PHẦN 2: PARSE YÊU CẦU SBC
# =============================================================================

_RATING_KEYS = [
    "teamrating", "squad_rating", "averagerating", "minrating",
    "min_rating", "rating", "teamsrating", "team_rating", "đánh_giá"
]
_RARE_KEYS = [
    "rare", "rarecount", "num_rare", "rareplayercount",
    "minrare", "min_rare", "numrare", "hiếm"
]
_TOTW_KEYS = [
    "totw", "totwcount", "tots", "totscount", "special",
    "specialcount", "inform", "informcount", "min_totw", "week", "in_form", "tuần", "đặc_biệt"
]
_SIZE_KEYS = [
    "squadsize", "count", "num_players", "playercount", "size"
]


def parse_sbc_requirements(sbc_challenge: dict) -> dict:
    """
    Chuyển đổi dữ liệu SBC Challenge thô từ Web App sang format chuẩn
    mà hàm solve_sbc() có thể xử lý trực tiếp.
    """
    parsed = {
        "name": sbc_challenge.get("name", "SBC Challenge"),
        "size": sbc_challenge.get("size", 11),
        "min_rating": 0,
        "min_rare": 0,
        "min_totw_tots": 0,
    }

    raw_reqs = sbc_challenge.get("requirements", [])
    if not raw_reqs:
        print("[SOLVER MANAGER WARNING] requirements[] trống — dùng giá trị mặc định (min_rating=0).")
        return parsed

    for req in raw_reqs:
        if not req:
            continue

        req_type = str(req.get("type", "")).lower().strip().replace(" ", "_")
        req_desc = str(req.get("desc", "")).lower().strip().replace(" ", "_")
        match_str = f"{req_type}|{req_desc}"
        raw_val  = req.get("value", 0)

        try:
            val = int(float(str(raw_val)))
        except (ValueError, TypeError):
            continue

        if val <= 0:
            continue

        if any(k in match_str for k in _RATING_KEYS):
            parsed["min_rating"] = val
            print(f"[SOLVER MANAGER] Parse → min_rating = {val} (match='{match_str}')")

        elif any(k in match_str for k in _RARE_KEYS):
            parsed["min_rare"] = val
            print(f"[SOLVER MANAGER] Parse → min_rare = {val} (match='{match_str}')")

        elif any(k in match_str for k in _TOTW_KEYS):
            parsed["min_totw_tots"] = val
            print(f"[SOLVER MANAGER] Parse → min_totw_tots = {val} (match='{match_str}')")

        elif any(k in match_str for k in _SIZE_KEYS):
            parsed["size"] = val
            print(f"[SOLVER MANAGER] Parse → size = {val} (match='{match_str}')")

        else:
            print(f"[SOLVER MANAGER] Bỏ qua requirement: type='{req_type}', value={val}, desc='{req.get('desc', '')}'")

    print(f"[SOLVER MANAGER] Kết quả parse: {json.dumps(parsed, ensure_ascii=False)}")
    return parsed


# =============================================================================
# PHẦN 3: TIỆN ÍCH GIAO DIỆN
# =============================================================================

def update_button_status(page, text: str, border_color: str):
    """Cập nhật trạng thái hiển thị của nút Solve."""
    try:
        safe_text = text.replace("'", "\\'")
        page.evaluate(f"""() => {{
            let btn = document.getElementById('sbc-solve-floating-btn');
            if (btn) {{
                btn.innerText = '{safe_text}';
                btn.style.borderColor = '{border_color}';
                btn.style.background = '#555555';
            }}
        }}""")
    except Exception:
        pass


def reset_button(page):
    """Khôi phục trạng thái ban đầu của nút Solve."""
    try:
        page.evaluate("""() => {
            let btn = document.getElementById('sbc-solve-floating-btn');
            if (btn) {
                btn.disabled = false;
                btn.innerText = '⚡ SBC SOLVE';
                btn.style.background = 'linear-gradient(135deg, #7b2cbf 0%, #3a0ca3 100%)';
                btn.style.borderColor = '#00f5d4';
                btn.style.transform = 'none';
            }
        }""")
    except Exception:
        pass


def get_club_cache_count(page) -> int:
    """Đếm số cầu thủ hiện có trong cache Club."""
    try:
        return page.evaluate("""() => {
            try {
                let r = repositories.Item.club ? repositories.Item.club.items : null;
                if (r && typeof r.values === 'function')
                    return Array.from(r.values()).filter(
                        i => i && (i.type === 'player' || (i.isPlayer && i.isPlayer()))
                    ).length;
                // Fallback cũ
                let clubObj = repositories.Item.getClub ? repositories.Item.getClub() : null;
                if (!clubObj || !clubObj._items) return 0;
                let items = clubObj._items;
                return Array.isArray(items) ? items.length : Object.keys(items).length;
            } catch(e) { return 0; }
        }""")
    except Exception:
        return 0


# =============================================================================
# PHẦN 4: PRELOAD CLUB PLAYERS TỪ PYTHON
# =============================================================================

def preload_club_players_python(page) -> int:
    """
    Python/Playwright điều khiển trực tiếp:
      1. Click tab Club → đợi 4s cho EA load cầu thủ vào cache
      2. Click về SBC → đợi 1.5s cho SBC load lại
    Trả về số cầu thủ đã load vào cache.
    """
    print("[SOLVER MANAGER] Preload: Click sang tab Club...")
    try:
        clicked = page.evaluate("""() => {
            let clubBtn = Array.from(document.querySelectorAll('.ut-tab-bar-item')).find(el => {
                let cls = el.className || '';
                return cls.includes('icon-club')
                    && !cls.includes('paletools')
                    && !cls.includes('analyzer');
            });
            if (clubBtn) {
                clubBtn.click();
                return true;
            }
            return false;
        }""")

        if not clicked:
            print("[SOLVER MANAGER WARNING] Không tìm thấy tab Club!")

        # Đợi EA load cầu thủ vào cache
        time.sleep(4.0)
        count = get_club_cache_count(page)
        print(f"[SOLVER MANAGER] Preload: Club cache = {count} cầu thủ.")

        # Navigate về SBC
        page.evaluate("""() => {
            let sbcBtn = document.querySelector('.ut-tab-bar-item.icon-sbc');
            if (sbcBtn) sbcBtn.click();
        }""")
        time.sleep(1.5)

        return count

    except Exception as e:
        print(f"[SOLVER MANAGER WARNING] Preload lỗi: {e}")
        return 0


# =============================================================================
# PHẦN 5: VÒNG LẶP GIÁM SÁT CHÍNH
# =============================================================================

def monitor_sbc_solver(page, config: dict):
    """
    Vòng lặp giám sát cờ hiệu sbc_solver_trigger.
    Khi user bấm nút SBC Solve:
      1. Kiểm tra cache — nếu < 50 thì preload từ Python (Club navigate)
      2. extractSbcAndPlayers() để lấy SBC info + players từ cache
      3. parse_sbc_requirements()
      4. solve_sbc() — MILP hoặc heuristic
      5. fillSquad() auto-fill lên sân
    """
    print("[SOLVER MANAGER] Đang khởi động vòng lặp giám sát nút SBC Solve...")
    inject_extractor_script(page)

    sbc_config = config.get("sbc_solver", {})
    print(f"[SOLVER MANAGER] Config solver: min_rating={sbc_config.get('min_rating_to_use', 70)}, "
          f"max_rating={sbc_config.get('max_rating_to_use', 89)}")

    while True:
        try:
            # ── 1. Đảm bảo script luôn được inject ────────────────────────────
            is_loaded = page.evaluate("typeof window.sbcSolveExtractor !== 'undefined'")
            if not is_loaded:
                inject_extractor_script(page)

            # ── 2. Kiểm tra cờ hiệu trigger ────────────────────────────────────
            is_triggered = page.evaluate("!!window.sbc_solver_trigger")
            if not is_triggered:
                time.sleep(1.0)
                continue

            print("\n" + "=" * 60)
            print("[SOLVER MANAGER] Phát hiện sự kiện bấm nút SBC Solve!")
            page.evaluate("window.sbc_solver_trigger = false")

            # ── 3. Preload Club Players nếu cache chưa đủ ──────────────────────
            cache_count = get_club_cache_count(page)
            print(f"[SOLVER MANAGER] Cache hiện tại: {cache_count} cầu thủ.")

            if cache_count < 50:
                print("[SOLVER MANAGER] Cache chưa đủ → Preload Club...")
                update_button_status(page, "⏳ LOADING CLUB...", "#74c0fc")
                preloaded = preload_club_players_python(page)
                print(f"[SOLVER MANAGER] Sau preload: {preloaded} cầu thủ trong cache.")
            else:
                print("[SOLVER MANAGER] Cache đủ, bỏ qua preload.")

            # ── 4. Extract SBC info + players ──────────────────────────────────
            print("[SOLVER MANAGER] Đang trích xuất dữ liệu SBC + cầu thủ...")
            update_button_status(page, "⏳ EXTRACTING...", "#74c0fc")
            extracted = page.evaluate("window.sbcSolveExtractor.extractSbcAndPlayers()")

            if not extracted:
                print("[SOLVER MANAGER ERROR] JS không phản hồi.")
                update_button_status(page, "❌ JS ERROR", "#ff3366")
                time.sleep(3); reset_button(page); continue

            if extracted.get("error"):
                print(f"[SOLVER MANAGER ERROR] {extracted['error']}")
                update_button_status(page, "❌ EXTRACT ERR", "#ff3366")
                time.sleep(3); reset_button(page); continue

            sbc_challenge = extracted.get("sbc_challenge")
            players       = extracted.get("players", [])

            if not sbc_challenge:
                print("[SOLVER MANAGER ERROR] Không lấy được SBC Challenge.")
                update_button_status(page, "❌ NO SBC", "#ff3366")
                time.sleep(3); reset_button(page); continue

            print(f"[SOLVER MANAGER] SBC: '{sbc_challenge['name']}' (size={sbc_challenge['size']})")
            print(f"[SOLVER MANAGER] Raw requirements: {json.dumps(sbc_challenge.get('requirements', []), ensure_ascii=False)}")
            print(f"[SOLVER MANAGER] Cầu thủ: {len(players)}")

            if len(players) == 0:
                print("[SOLVER MANAGER ERROR] Không có cầu thủ nào sau preload.")
                update_button_status(page, "❌ NO PLAYERS", "#ff9f1c")
                time.sleep(3); reset_button(page); continue

            # ── 5. Parse requirements ──────────────────────────────────────────
            requirements = parse_sbc_requirements(sbc_challenge)
            print(f"[SOLVER MANAGER] Yêu cầu: rating≥{requirements['min_rating']}, "
                  f"rare≥{requirements['min_rare']}, totw≥{requirements['min_totw_tots']}, "
                  f"size={requirements['size']}")

            # ── 6. Chạy Solver ────────────────────────────────────────────────
            print("[SOLVER MANAGER] Đang tính toán đội hình tối ưu (MILP)...")
            update_button_status(page, "⏳ SOLVING...", "#ffd43b")
            
            # Dump debug inputs
            try:
                debug_path = os.path.join(SOLVE_DIR, "logs", "debug_run.json")
                with open(debug_path, "w", encoding="utf-8") as df:
                    json.dump({"players": players, "requirements": requirements, "config": sbc_config}, df, ensure_ascii=False, indent=2)
                print(f"[SOLVER MANAGER] Đã ghi debug inputs vào: {debug_path}")
            except Exception as df_err:
                print(f"[SOLVER MANAGER WARNING] Không thể ghi debug inputs: {df_err}")

            result = solve_sbc(players, requirements, sbc_config)

            if not result:
                rating_min = min(p['rating'] for p in players) if players else 'N/A'
                rating_max = max(p['rating'] for p in players) if players else 'N/A'
                print(f"[SOLVER MANAGER ERROR] Không tìm được nghiệm!")
                print(f"  → min_rating_to_use={sbc_config.get('min_rating_to_use', 70)}")
                print(f"  → Rating players: {rating_min}–{rating_max}")
                update_button_status(page, "❌ NO SOLUTION", "#ff9f1c")
                time.sleep(3); reset_button(page); continue

            print(f"[SOLVER MANAGER SUCCESS] ✅ Rating đạt: {result['solved_rating']} (mục tiêu ≥{result['target_rating']})")
            for i, p in enumerate(result["players"]):
                tags = ("" + (" [STORAGE]" if p.get("sbc_storage") else "")
                           + (" [RARE]"    if p.get("rare")        else "")
                           + (" [TOTW]"    if p.get("totw")        else ""))
                print(f"  {i+1:2}. [{p['rating']}] {p['name']}{tags}")

            # ── 7. Auto-fill ──────────────────────────────────────────────────
            player_ids = [p["id"] for p in result["players"]]
            print(f"\n[SOLVER MANAGER] Auto-fill {len(player_ids)} cầu thủ...")
            update_button_status(page, "⏳ FILLING...", "#74c0fc")
            fill_res = page.evaluate(
                f"window.sbcSolveExtractor.fillSquad({json.dumps(player_ids)})"
            )

            if fill_res and fill_res.get("success"):
                filled = fill_res.get("filled", 0)
                print(f"[SOLVER MANAGER] ✅ Điền thành công {filled}/{len(player_ids)} cầu thủ!")
                update_button_status(page, f"✅ DONE! ({filled})", "#00f5d4")
            else:
                fill_err = fill_res.get("error", "?") if fill_res else "None"
                print(f"[SOLVER MANAGER ERROR] Fill thất bại: {fill_err}")
                update_button_status(page, "❌ FILL FAILED", "#ff3366")

            time.sleep(3)
            reset_button(page)
            print("=" * 60 + "\n")

        except KeyboardInterrupt:
            raise
        except Exception as loop_err:
            print(f"[SOLVER MANAGER WARNING] Lỗi: {loop_err}")
            import traceback
            traceback.print_exc()
            time.sleep(2.0)
