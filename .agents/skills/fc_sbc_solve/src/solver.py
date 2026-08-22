"""
solver.py — v2.0

Thuật toán tối ưu hóa giải SBC cho EA FC 26.

CHIẾN LƯỢC SOLVER:
  - Primary:  MILP (Mixed-Integer Linear Programming) bằng thư viện PuLP
              → Tối ưu hóa tuyến tính đảm bảo tìm được nghiệm tốt nhất
              → Nhanh hơn nhiều so với brute-force với tập cầu thủ lớn
  - Fallback: Đệ quy heuristic (sử dụng nếu PuLP không được cài)
              → Tương thích ngược, không cần cài thêm

CÔNG THỨC RATING SBC CỦA EA:
  rating = floor(avg + excess_sum / size)
  Trong đó: excess_sum = sum(max(0, r - avg) for r in ratings)

  Lưu ý: MILP xấp xỉ bằng ràng buộc sum(rating) >= min_rating * size,
  sau đó verify lại bằng calculate_sbc_rating() chính xác.
"""

import math
import json


# =============================================================================
# PHẦN 1: CÔNG THỨC RATING SBC CỦA EA
# =============================================================================

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


# =============================================================================
# PHẦN 2: MILP SOLVER (Primary)
# =============================================================================

def solve_sbc_milp(valid_players: list, min_rating: int, min_rare: int,
                   min_totw_tots: int, sbc_size: int):
    """
    Giải SBC bằng Mixed-Integer Linear Programming (PuLP).

    Biến quyết định: x[i] ∈ {0, 1} — chọn cầu thủ i hay không

    Hàm mục tiêu:
        Minimize: sum(x[i] * cost[i])

    Các ràng buộc:
        1. sum(x) == sbc_size                              (đúng số cầu thủ)
        2. sum(x[i] * rating[i]) >= min_rating * sbc_size  (xấp xỉ rating)
        3. sum(x[i] if rare[i]) >= min_rare                (ràng buộc Rare)
        4. sum(x[i] if totw/tots[i]) >= min_totw_tots      (ràng buộc TOTW)

    Sau khi giải xong, verify lại bằng calculate_sbc_rating() chính xác.
    Nếu không đạt → tăng target thêm 1 và thử lại (tối đa 3 lần).

    Trả về: list cầu thủ được chọn, hoặc None nếu không tìm được.
    """
    try:
        import pulp
    except ImportError:
        return None  # PuLP không được cài → fallback

    n = len(valid_players)
    if n < sbc_size:
        return None

    # Thử với target_sum tăng dần (để bù cho phần excess không mô hình hóa được)
    for bonus in range(4):
        target_sum = (min_rating + bonus) * sbc_size

        prob = pulp.LpProblem(f"SBC_Solver_bonus{bonus}", pulp.LpMinimize)
        x = [pulp.LpVariable(f"x_{i}", cat='Binary') for i in range(n)]

        # Hàm mục tiêu: tối thiểu hóa tổng chi phí
        prob += pulp.lpSum(x[i] * valid_players[i]['cost'] for i in range(n))

        # Ràng buộc 1: Đúng sbc_size cầu thủ
        prob += pulp.lpSum(x) == sbc_size

        # Ràng buộc 2: Xấp xỉ rating (tổng rating >= target_sum)
        prob += pulp.lpSum(x[i] * valid_players[i]['rating'] for i in range(n)) >= target_sum

        # Ràng buộc 3: Số Rare tối thiểu
        if min_rare > 0:
            prob += pulp.lpSum(
                x[i] for i in range(n) if valid_players[i].get('rare', False)
            ) >= min_rare

        # Ràng buộc 4: Số TOTW/TOTS tối thiểu
        if min_totw_tots > 0:
            prob += pulp.lpSum(
                x[i] for i in range(n)
                if valid_players[i].get('totw', False) or valid_players[i].get('tots', False)
            ) >= min_totw_tots

        # Giải bài toán (ẩn log của solver)
        status = prob.solve(pulp.PULP_CBC_CMD(msg=False))

        if pulp.LpStatus[prob.status] != 'Optimal':
            continue

        # Thu thập nghiệm
        selected = [valid_players[i] for i in range(n) if pulp.value(x[i]) == 1]
        if len(selected) != sbc_size:
            continue

        # Verify rating bằng công thức chính xác của EA
        actual_rating = calculate_sbc_rating([p['rating'] for p in selected])
        if actual_rating >= min_rating:
            return selected  # ✅ Nghiệm hợp lệ

        # Rating không đạt → thử lại với bonus cao hơn

    return None  # Không tìm được nghiệm


# =============================================================================
# PHẦN 3: HEURISTIC FALLBACK SOLVER
# =============================================================================

def solve_sbc_heuristic(valid_players: list, min_rating: int, min_rare: int,
                        min_totw_tots: int, sbc_size: int,
                        players_by_rating: dict, search_ratings: list):
    """
    Giải SBC bằng đệ quy heuristic (brute-force có cắt nhánh).
    Dùng khi PuLP không được cài đặt.
    """
    best_solution = [None]
    best_cost = [float('inf')]

    def evaluate_combination(combination):
        """Gán cầu thủ rẻ nhất vào tổ hợp rating, xử lý ràng buộc Rare/TOTW."""
        selected = []
        for r, count in combination.items():
            if count > 0:
                selected.extend(players_by_rating[r][:count])

        rare_count    = sum(1 for p in selected if p.get('rare', False))
        special_count = sum(1 for p in selected if p.get('totw', False) or p.get('tots', False))

        # Tráo đổi để đáp ứng ràng buộc Rare/TOTW
        if rare_count < min_rare or special_count < min_totw_tots:
            current = list(selected)
            for _ in range(sbc_size):
                r_now = sum(1 for p in current if p.get('rare', False))
                s_now = sum(1 for p in current if p.get('totw', False) or p.get('tots', False))
                if r_now >= min_rare and s_now >= min_totw_tots:
                    break

                best_swap = None
                min_diff = float('inf')
                for idx, p_curr in enumerate(current):
                    r_curr = p_curr['rating']
                    if r_curr not in players_by_rating:
                        continue
                    for p_alt in players_by_rating[r_curr]:
                        if p_alt in current:
                            continue
                        need_rare    = not p_curr.get('rare', False) and p_alt.get('rare', False) and r_now < min_rare
                        need_special = (not p_curr.get('totw', False) and not p_curr.get('tots', False)) \
                                       and (p_alt.get('totw', False) or p_alt.get('tots', False)) \
                                       and s_now < min_totw_tots
                        if need_rare or need_special:
                            diff = p_alt['cost'] - p_curr['cost']
                            if diff < min_diff:
                                min_diff = diff
                                best_swap = (idx, p_alt)

                if best_swap:
                    current[best_swap[0]] = best_swap[1]
                else:
                    return None
            selected = current

        total_cost = sum(p['cost'] for p in selected)
        return {'players': selected, 'total_cost': total_cost,
                'rating': calculate_sbc_rating([p['rating'] for p in selected])}

    def search(idx, combo, remaining):
        if remaining == 0:
            temp_ratings = []
            for r, cnt in combo.items():
                temp_ratings.extend([r] * cnt)
            if calculate_sbc_rating(temp_ratings) >= min_rating:
                sol = evaluate_combination(combo)
                if sol and sol['total_cost'] < best_cost[0]:
                    best_cost[0] = sol['total_cost']
                    best_solution[0] = sol
            return
        if idx >= len(search_ratings):
            return
        r = search_ratings[idx]
        max_use = min(remaining, len(players_by_rating[r]))
        for count in range(max_use + 1):
            combo[r] = count
            search(idx + 1, combo, remaining - count)
            del combo[r]

    search(0, {}, sbc_size)
    return best_solution[0]['players'] if best_solution[0] else None


# =============================================================================
# PHẦN 4: HÀM GIẢI CHÍNH
# =============================================================================

def solve_sbc(players: list, requirements: dict, config: dict):
    """
    Tìm tổ hợp cầu thủ tối ưu nhất để hoàn thành SBC.

    Args:
        players:      List dict cầu thủ từ Web App (đã được mapPlayer)
        requirements: Dict đã parse bởi parse_sbc_requirements():
                      { min_rating, min_rare, min_totw_tots, size, name }
        config:       Dict cấu hình từ config.json:
                      { min_rating_to_use, max_rating_to_use, blacklist_ids, ... }

    Returns:
        Dict kết quả hoặc None nếu không tìm được nghiệm.
    """
    min_rating    = requirements.get("min_rating", 83)
    min_rare      = requirements.get("min_rare", 0)
    min_totw_tots = requirements.get("min_totw_tots", 0)
    sbc_size      = requirements.get("size", 11)

    min_use_rating = config.get("min_rating_to_use", 80)
    max_use_rating = config.get("max_rating_to_use", 88)
    blacklist_ids  = set(str(bid) for bid in config.get("blacklist_ids", []))

    print(f"[SOLVER] Mục tiêu: rating≥{min_rating}, rare≥{min_rare}, "
          f"totw≥{min_totw_tots}, size={sbc_size}")
    print(f"[SOLVER] Phạm vi rating dùng: {min_use_rating}–{max_use_rating}, "
          f"blacklist={len(blacklist_ids)} IDs")

    # -------------------------------------------------------------------------
    # Bước 1: Lọc cầu thủ hợp lệ
    # -------------------------------------------------------------------------
    valid_players = []
    for p in players:
        pid = str(p.get("id", ""))
        if pid in blacklist_ids:
            continue

        is_special = p.get("totw", False) or p.get("tots", False)
        r = p.get("rating", 0)

        # Thẻ đặc biệt: luôn được xét (dùng để gánh rating)
        if is_special:
            valid_players.append(p)
            continue

        # Chỉ dùng cầu thủ trong phạm vi rating cho phép
        if min_use_rating <= r <= max_use_rating:
            valid_players.append(p)

    if not valid_players:
        print(f"[SOLVER ERROR] Không có cầu thủ khả dụng nào trong phạm vi rating {min_use_rating}–{max_use_rating}!")
        return None

    # -------------------------------------------------------------------------
    # Bước 2: Tính chi phí ảo (Virtual Cost)
    #   - SBC Storage:   cost = 10         (ưu tiên cao nhất)
    #   - Untradeable:   cost = 100 + r*15 (ưu tiên thứ hai, rating thấp trước)
    #   - Tradeable:     cost = market + 1000 (tránh dùng nhầm thẻ có giá trị)
    # -------------------------------------------------------------------------
    for p in valid_players:
        if p.get("sbc_storage", False):
            p["cost"] = 10
        elif p.get("untradeable", False):
            p["cost"] = 100 + (p.get("rating", 80) * 15)
        else:
            p["cost"] = max(p.get("market_price", 1000), 400) + 1000

    # -------------------------------------------------------------------------
    # Bước 2.5: Lọc bỏ trùng lặp (Duplicate cards) có cùng definitionId
    # Nếu trùng definitionId (hoặc trùng tên nếu definitionId = 0), chỉ giữ lại thẻ rẻ nhất
    # -------------------------------------------------------------------------
    unique_players = {}
    for p in valid_players:
        def_id = p.get("definitionId", 0)
        # Fallback về tên cầu thủ nếu không có definitionId
        key = def_id if def_id > 0 else p.get("name", "Unknown")

        if key not in unique_players:
            unique_players[key] = p
        else:
            # So sánh cost để giữ lại thẻ tối ưu nhất
            if p["cost"] < unique_players[key]["cost"]:
                unique_players[key] = p

    valid_players = list(unique_players.values())
    print(f"[SOLVER] Cầu thủ hợp lệ sau lọc trùng lặp: {len(valid_players)}/{len(players)}")

    # -------------------------------------------------------------------------
    # Bước 3: Thử MILP Solver (Primary)
    # -------------------------------------------------------------------------
    try:
        import pulp
        pulp_available = True
    except ImportError:
        pulp_available = False
        print("[SOLVER] PuLP không được cài. Sử dụng heuristic fallback.")
        print("[SOLVER] Gợi ý: pip install pulp")

    selected_players = None

    if pulp_available:
        print("[SOLVER] Đang chạy MILP Solver (PuLP)...")
        selected_players = solve_sbc_milp(
            valid_players, min_rating, min_rare, min_totw_tots, sbc_size
        )
        if selected_players:
            print(f"[SOLVER] ✅ MILP tìm được nghiệm tối ưu.")
        else:
            print("[SOLVER] MILP không tìm được nghiệm. Thử heuristic fallback...")

    # -------------------------------------------------------------------------
    # Bước 4: Fallback Heuristic nếu MILP thất bại hoặc không có PuLP
    # -------------------------------------------------------------------------
    if not selected_players:
        # Phân nhóm theo rating và sắp xếp theo cost
        players_by_rating = {}
        for p in valid_players:
            r = p["rating"]
            if r not in players_by_rating:
                players_by_rating[r] = []
            players_by_rating[r].append(p)
        for r in players_by_rating:
            players_by_rating[r].sort(key=lambda p: p["cost"])

        available_ratings = sorted(players_by_rating.keys())
        # Giới hạn phạm vi tìm kiếm xung quanh target rating
        search_ratings = [r for r in available_ratings
                          if (min_rating - 4) <= r <= (min_rating + 5)]
        if not search_ratings:
            search_ratings = available_ratings

        print(f"[SOLVER] Chạy heuristic với {len(search_ratings)} mức rating: {search_ratings}")
        selected_players = solve_sbc_heuristic(
            valid_players, min_rating, min_rare, min_totw_tots,
            sbc_size, players_by_rating, search_ratings
        )

        if selected_players:
            print(f"[SOLVER] ✅ Heuristic tìm được nghiệm.")
        else:
            print("[SOLVER] ❌ Cả MILP lẫn heuristic đều không tìm được nghiệm.")
            return None

    # -------------------------------------------------------------------------
    # Bước 5: Định dạng kết quả đầu ra
    # -------------------------------------------------------------------------
    solved_rating = calculate_sbc_rating([p["rating"] for p in selected_players])

    # Tính chi phí thực tế (không tính thẻ SBC Storage vì đã trong tay)
    total_market_cost = sum(
        p.get("market_price", 500)
        for p in selected_players
        if not p.get("sbc_storage", False) and not p.get("untradeable", False)
    )

    result = {
        "sbc_name": requirements.get("name", "SBC Challenge"),
        "target_rating": min_rating,
        "solved_rating": solved_rating,
        "total_cost": total_market_cost,
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
            for p in selected_players
        ]
    }

    return result


# =============================================================================
# PHẦN 5: TEST OFFLINE VỚI FILE CSV
# =============================================================================

if __name__ == "__main__":
    import csv

    print("[SOLVER TEST] Chạy test solver với file club-analyzer-2.csv...")
    csv_path = "/Users/binhnguyenthanh/Documents/FC Ultimate/.agents/skills/fc_sbc_solve/Database/club-analyzer-2.csv"

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
                    "sbc_storage": row.get("Location", "").lower() == "storage",
                    "market_price": discard_val
                })

        print(f"[SOLVER TEST] Đã load {len(mock_players)} cầu thủ từ CSV.\n")

        # --- Test 1: SBC 83+ với 2 Rare ---
        print("=" * 50)
        print("TEST 1: SBC 83+ Player Pick (min_rating=83, min_rare=2)")
        reqs_1 = {"name": "83+ Player Pick", "min_rating": 83, "min_rare": 2, "min_totw_tots": 0, "size": 11}
        cfg_1  = {"min_rating_to_use": 80, "max_rating_to_use": 85, "blacklist_ids": []}
        result_1 = solve_sbc(mock_players, reqs_1, cfg_1)
        if result_1:
            print(f"✅ Thành công! Rating: {result_1['solved_rating']} (Mục tiêu: {result_1['target_rating']})")
            for i, p in enumerate(result_1["players"]):
                tags = (" [STORAGE]" if p["sbc_storage"] else "") + (" [RARE]" if p["rare"] else "")
                print(f"  {i+1:2}. [{p['rating']}] {p['name']}{tags}")
        else:
            print("❌ Không tìm được nghiệm.")

        # --- Test 2: SBC 84+ với 1 TOTW ---
        print("\n" + "=" * 50)
        print("TEST 2: SBC 84+ với 1 TOTW (min_rating=84, min_totw_tots=1)")
        reqs_2 = {"name": "84+ TOTW", "min_rating": 84, "min_rare": 0, "min_totw_tots": 1, "size": 11}
        cfg_2  = {"min_rating_to_use": 80, "max_rating_to_use": 86, "blacklist_ids": []}
        result_2 = solve_sbc(mock_players, reqs_2, cfg_2)
        if result_2:
            print(f"✅ Thành công! Rating: {result_2['solved_rating']} (Mục tiêu: {result_2['target_rating']})")
            for i, p in enumerate(result_2["players"]):
                tags = (" [STORAGE]" if p["sbc_storage"] else "") + (" [TOTW]" if p["totw"] else "") + (" [RARE]" if p["rare"] else "")
                print(f"  {i+1:2}. [{p['rating']}] {p['name']}{tags}")
        else:
            print("❌ Không tìm được nghiệm.")

    except FileNotFoundError:
        print(f"[TEST ERROR] Không tìm thấy file CSV: {csv_path}")
    except Exception as err:
        import traceback
        print(f"[TEST ERROR] {err}")
        traceback.print_exc()
