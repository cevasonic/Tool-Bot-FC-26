"""
solver.py — v3.1

Thuật toán giải SBC dựa trên tra cứu công thức rating tĩnh từ rating_combinations.json (FUT.GG),
ưu tiên nguồn cầu thủ từ SBC Storage, Club Untradeable rồi tới Club Tradeable.
Hỗ trợ giải thiếu thẻ (incomplete solution) nếu không đủ cầu thủ.
"""

import math
import json
import os

def calculate_sbc_rating(ratings: list) -> int:
    """
    Tính toán rating của đội hình SBC theo công thức chuẩn của EA FC.
    ratings: danh sách rating của các cầu thủ (ví dụ: [83, 82, 81, ...])
    """
    if not ratings:
        return 0
    size = len(ratings)
    total = sum(ratings)
    avg = total / size
    excess_sum = sum(max(0.0, r - avg) for r in ratings)
    return math.floor(avg + excess_sum / size)

def calculate_sbc_rating_float(ratings: list) -> float:
    """
    Tính toán rating của đội hình SBC dưới dạng số thực (không dùng math.floor).
    """
    if not ratings:
        return 0.0
    size = len(ratings)
    total = sum(ratings)
    avg = total / size
    excess_sum = sum(max(0.0, r - avg) for r in ratings)
    return avg + excess_sum / size

def solve_sbc(players: list, requirements: dict, config: dict):
    """
    Thuật toán giải SBC mới:
    1. Chỉ chọn cầu thủ untradeable = true và evolution = false.
    2. Min rating là 82.
    3. Ưu tiên chọn cầu thủ sbc_storage = true.
    4. Khởi đầu với sbc_size cầu thủ có rating thấp nhất.
    5. Tuần tự tăng rating từng vị trí cho đến khi đạt target_rating - 0.5
       hoặc đạt max rating của các thẻ trong sbc_storage.
    """
    target_rating = requirements.get("min_rating", 83)
    sbc_size = requirements.get("size", 11)
    
    # 1. Đọc cấu hình bảo vệ thẻ
    protected_config = config.get("protected_cards", {})
    protect_active = protected_config.get("active_squad", True)
    protect_favorites = protected_config.get("favorites", True)
    blacklist_ids = set(str(bid) for bid in protected_config.get("blacklist_ids", []))
    
    # 2. Lọc cầu thủ khả dụng
    valid_players = []
    for p in players:
        pid = str(p.get("id", ""))
        if pid in blacklist_ids:
            continue
        if protect_active and p.get("active_squad", False):
            continue
        if protect_favorites and p.get("favorite", False):
            continue
        
        # Chỉ chọn cầu thủ untradeable = true và evolution = false
        untradeable_val = p.get("untradeable")
        if untradeable_val not in (True, "true", "True"):
            continue
        
        evolution_val = p.get("evolution")
        if evolution_val in (True, "true", "True"):
            continue
        # Min rating là 82
        if p.get("rating", 0) < 82:
            continue
            
        valid_players.append(p)
        
    # 3. Tính max rating của các thẻ trong sbc_storage
    storage_ratings = [p["rating"] for p in valid_players if p.get("sbc_storage") == True]
    if storage_ratings:
        max_storage_rating = max(storage_ratings)
    else:
        # Nếu không có thẻ trong sbc_storage, lấy rating cao nhất của các cầu thủ khả dụng
        max_storage_rating = max(p["rating"] for p in valid_players) if valid_players else 99

    print(f"[SOLVER] Số cầu thủ khả dụng (Untradeable, Non-Evo, Rating>=82): {len(valid_players)}")
    print(f"[SOLVER] Rating cao nhất trong SBC Storage khả dụng: {max_storage_rating if storage_ratings else 'N/A (Mặc định lấy max khả dụng: ' + str(max_storage_rating) + ')'}")
    
    # 4. Sắp xếp các cầu thủ khả dụng: tăng dần rating, ưu tiên sbc_storage = True trước
    valid_players.sort(key=lambda p: (p["rating"], 0 if p.get("sbc_storage") else 1))
    
    # 5. Khởi tạo đội hình bằng sbc_size cầu thủ độc bản có rating thấp nhất
    selected_solution = []
    selected_def_ids = set()
    pool = []
    
    for p in valid_players:
        p_def_id = p.get("definitionId", p.get("name", p.get("id")))
        if len(selected_solution) < sbc_size:
            if p_def_id not in selected_def_ids:
                selected_solution.append(p)
                selected_def_ids.add(p_def_id)
            else:
                pool.append(p)
        else:
            pool.append(p)
            
    if len(selected_solution) < sbc_size:
        print(f"[SOLVER WARNING] Không đủ cầu thủ khả dụng độc bản để điền đội hình! Cần {sbc_size}, chỉ có {len(selected_solution)}.")
        is_complete = False
    else:
        # Kiểm tra xem đội hình xuất phát có đạt yêu cầu chưa (chấp nhận thấp hơn 0.5)
        current_rating_float = calculate_sbc_rating_float([p["rating"] for p in selected_solution])
        if current_rating_float >= target_rating - 0.5:
            is_complete = True
            print(f"[SOLVER] Đội hình ban đầu đạt yêu cầu rating: {current_rating_float:.2f} >= {target_rating - 0.5:.1f}")
        else:
            is_complete = False
            # 6. Tuần tự tăng rating từng cầu thủ ở vị trí i
            for i in range(sbc_size):
                while True:
                    current_player = selected_solution[i]
                    current_r = current_player["rating"]
                    
                    # Tìm candidates trong pool: rating lớn hơn current_r và <= max_storage_rating
                    # Chỉ chọn ứng viên có definitionId không trùng với bất kỳ vị trí khác trong đội hình
                    selected_def_ids_without_current = {
                        p.get("definitionId", p.get("name", p.get("id"))) for idx, p in enumerate(selected_solution) if idx != i
                    }
                    
                    candidates = []
                    for p in pool:
                        if p["rating"] > current_r and p["rating"] <= max_storage_rating:
                            p_def_id = p.get("definitionId", p.get("name", p.get("id")))
                            if p_def_id not in selected_def_ids_without_current:
                                candidates.append(p)
                            
                    if not candidates:
                        break
                        
                    # Sắp xếp candidates: tăng dần rating, ưu tiên sbc_storage = True
                    candidates.sort(key=lambda p: (p["rating"], 0 if p.get("sbc_storage") else 1))
                    p_new = candidates[0]
                    
                    # Thực hiện hoán đổi
                    pool.remove(p_new)
                    pool.append(current_player)
                    selected_solution[i] = p_new
                    
                    # Tính toán lại rating
                    current_rating_float = calculate_sbc_rating_float([p["rating"] for p in selected_solution])
                    if current_rating_float >= target_rating - 0.5:
                        is_complete = True
                        break
                
                if is_complete:
                    print(f"[SOLVER] Đạt yêu cầu rating sau khi tăng vị trí {i+1}: {current_rating_float:.2f} >= {target_rating - 0.5:.1f}")
                    break
                    
    # Sắp xếp lại selected_solution cho đẹp mắt trước khi trả về (theo rating giảm dần)
    selected_solution.sort(key=lambda p: p["rating"], reverse=True)
    
    solved_rating = calculate_sbc_rating([p["rating"] for p in selected_solution])
    
    result = {
        "sbc_name": requirements.get("name", "SBC Challenge"),
        "target_rating": target_rating,
        "solved_rating": solved_rating,
        "total_cost": 0, # Vì chỉ dùng untradeable nên cost là 0
        "is_complete": is_complete,
        "players": [
            {
                "id": p["id"],
                "name": p["name"],
                "rating": p["rating"],
                "position": p.get("position", "SUB"),
                "rare": p.get("rare", False),
                "totw": p.get("totw", False),
                "tots": p.get("tots", False),
                "sbc_storage": p.get("sbc_storage", False),
                "untradeable": p.get("untradeable", False)
            }
            for p in selected_solution
        ]
    }
    return result

# =============================================================================
# TEST OFFLINE VỚI FILE CSV
# =============================================================================

if __name__ == "__main__":
    import csv
    import sys

    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8')

    print("[SOLVER TEST] Chạy test solver mới với file club-analyzer-2.csv...")
    SRC_DIR = os.path.dirname(os.path.abspath(__file__))
    SOLVE_DIR = os.path.dirname(SRC_DIR)
    csv_path = os.path.join(SOLVE_DIR, "Database", "club-analyzer-2.csv")

    mock_players = []
    try:
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rarity = row.get("Rarity", "").lower()
                discard_val = row.get("Discard Value", "0") or "0"
                try:
                    discard_val = int(float(discard_val))
                except ValueError:
                    discard_val = 500

                mock_players.append({
                    "id": row.get("Id", "0"),
                    "name": row.get("Name", "Unknown"),
                    "rating": int(row.get("Rating", 0) or 0),
                    "position": row.get("Position", "SUB"),
                    "rare": any(k in rarity for k in ["rare", "hero", "icon", "special"]),
                    "totw": any(k in rarity for k in ["totw", "in form"]),
                    "tots": "tots" in rarity,
                    "untradeable": row.get("Untradeable", "false").lower() == "true",
                    "sbc_storage": row.get("Location", "").lower() in ["storage", "sbcstorage"],
                    "market_price": discard_val
                })

        print(f"[SOLVER TEST] Đã load {len(mock_players)} cầu thủ từ CSV.\n")

        # --- Test 1: SBC 83+ với size 11 ---
        print("=" * 50)
        print("TEST 1: SBC 83+ (min_rating=83, size=11)")
        reqs_1 = {"name": "83+ Upgrade", "min_rating": 83, "size": 11}
        cfg_1  = {"protected_cards": {"active_squad": True, "favorites": True, "evolutions": True, "blacklist_ids": []}}
        result_1 = solve_sbc(mock_players, reqs_1, cfg_1)
        if result_1:
            status_str = "ĐẦY ĐỦ" if result_1["is_complete"] else "THIẾU THẺ"
            print(f"✅ Kết quả: {status_str}! Rating: {result_1['solved_rating']} (Mục tiêu: {result_1['target_rating']})")
            for i, p in enumerate(result_1["players"]):
                tags = (" [STORAGE]" if p["sbc_storage"] else "") + (" [UNTRADEABLE]" if p["untradeable"] else "")
                print(f"  {i+1:2}. [{p['rating']}] {p['name']}{tags}")
        else:
            print("❌ Không tìm được nghiệm.")

        # --- Test 2: SBC 90+ với size 11 ---
        print("=" * 50)
        print("TEST 2: SBC 90+ (min_rating=90, size=11)")
        reqs_2 = {"name": "90+ Upgrade", "min_rating": 90, "size": 11}
        result_2 = solve_sbc(mock_players, reqs_2, cfg_1)
        if result_2:
            status_str = "ĐẦY ĐỦ" if result_2["is_complete"] else "THIẾU THẺ"
            print(f"✅ Kết quả: {status_str}! Rating: {result_2['solved_rating']} (Mục tiêu: {result_2['target_rating']})")
            for i, p in enumerate(result_2["players"]):
                tags = (" [STORAGE]" if p["sbc_storage"] else "") + (" [UNTRADEABLE]" if p["untradeable"] else "")
                print(f"  {i+1:2}. [{p['rating']}] {p['name']}{tags}")
        else:
            print("❌ Không tìm được nghiệm.")

    except FileNotFoundError:
        print(f"[TEST ERROR] Không tìm thấy file CSV: {csv_path}")
    except Exception as err:
        import traceback
        print(f"[TEST ERROR] {err}")
        traceback.print_exc()
