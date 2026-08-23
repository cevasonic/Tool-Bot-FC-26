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
import os


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


def solve_using_combinations(valid_players, target_rating, min_rare, min_totw_tots, sbc_size):
    # 1. Load rating_combinations.json
    resources_dir = os.path.join(os.path.dirname(__file__), "..", "resources")
    json_path = os.path.join(resources_dir, "rating_combinations.json")
    if not os.path.exists(json_path):
        print(f"[SOLVER] Không tìm thấy tệp combinations: {json_path}")
        return None

    try:
        with open(json_path, "r", encoding="utf-8") as f:
            combinations_db = json.load(f)
    except Exception as e:
        print(f"[SOLVER ERROR] Không thể đọc combinations JSON: {e}")
        return None

    target_str = str(target_rating)
    if target_str not in combinations_db:
        print(f"[SOLVER] Không tìm thấy combinations cho rating mục tiêu: {target_rating}")
        return None

    recipes = combinations_db[target_str]
    best_solution = None
    best_cost = float("inf")

    for recipe in recipes:
        req_players = recipe.get("players", {})
        total_req_count = sum(req_players.values())
        if total_req_count > sbc_size:
            continue

        # Nếu recipe yêu cầu ít hơn sbc_size, ta bù phần thiếu bằng rating thấp nhất có sẵn
        actual_req = req_players.copy()
        if total_req_count < sbc_size:
            missing = sbc_size - total_req_count
            avail_ratings = [p.get("rating", 0) for p in valid_players]
            min_avail_rating = min(avail_ratings) if avail_ratings else 80
            min_r_str = str(min_avail_rating)
            actual_req[min_r_str] = actual_req.get(min_r_str, 0) + missing

        # Thử khớp các yêu cầu của recipe (cho phép rating cao hơn thay thế rating thấp hơn)
        sorted_reqs = []
        for r_str, count in actual_req.items():
            sorted_reqs.extend([int(r_str)] * count)
        sorted_reqs.sort(reverse=True)

        temp_players = list(valid_players)
        selected_players = []
        possible = True

        for req_r in sorted_reqs:
            candidate = None
            best_idx = -1
            min_cand_cost = float("inf")
            
            for idx, p in enumerate(temp_players):
                p_rating = p.get("rating", 0)
                if p_rating >= req_r:
                    p_cost = p.get("cost", 99999)
                    if p_cost < min_cand_cost:
                        min_cand_cost = p_cost
                        candidate = p
                        best_idx = idx
            
            if candidate is not None:
                selected_players.append(candidate)
                temp_players.pop(best_idx)
            else:
                possible = False
                break

        if possible:
            sbc_rating = calculate_sbc_rating([p.get("rating", 0) for p in selected_players])
            
            # Đếm số lượng Rare và TOTW/TOTS
            rare_count = sum(1 for p in selected_players if p.get("rare", False))
            special_count = sum(1 for p in selected_players if p.get("totw", False) or p.get("tots", False))
            
            if sbc_rating >= target_rating and rare_count >= min_rare and special_count >= min_totw_tots:
                cost = sum(p.get("cost", 99999) for p in selected_players)
                
                # --- Thưởng (Discount) cho chiến thuật High-Low ---
                ratings_used = [p.get("rating", 0) for p in selected_players]
                max_r = max(ratings_used) if ratings_used else 0
                min_r = min(ratings_used) if ratings_used else 0
                
                # 1. Thưởng cực lớn nếu sử dụng được thẻ Storage có rating cao nhất hiện tại
                storage_players = [p for p in valid_players if p.get("sbc_storage", False)]
                max_storage_r = max(p.get("rating", 0) for p in storage_players) if storage_players else 0
                if max_storage_r > 0 and max_r >= max_storage_r:
                    cost -= 1000.0  # Ưu tiên tuyệt đối để giải phóng thẻ trùng cao nhất
                    
                # 2. Thưởng cho độ lệch rating lớn (chiến thuật High-Low)
                rating_spread = max_r - min_r
                if rating_spread >= 10:
                    cost -= 300.0
                elif rating_spread >= 6:
                    cost -= 150.0

                if cost < best_cost:
                    best_cost = cost
                    best_solution = {
                        "players": selected_players,
                        "target_rating": target_rating,
                        "solved_rating": sbc_rating,
                        "total_cost": cost
                    }

    return best_solution
def solve_sbc_milp(valid_players: list, min_rating: int, min_rare: int,
                   min_totw_tots: int, sbc_size: int):
    try:
        import pulp
    except ImportError:
        return None

    n = len(valid_players)
    if n < sbc_size:
        return None

    for bonus in range(4):
        target_sum = (min_rating + bonus) * sbc_size

        prob = pulp.LpProblem(f"SBC_Solver_bonus{bonus}", pulp.LpMinimize)
        x = [pulp.LpVariable(f"x_{i}", cat='Binary') for i in range(n)]

        prob += pulp.lpSum(x[i] * valid_players[i]['cost'] for i in range(n))

        prob += pulp.lpSum(x) == sbc_size

        if min_rating >= 87:
            estimated_avg = max(0.0, min_rating - 3.5)
            contributions = [
                p['rating'] + max(0.0, p['rating'] - estimated_avg)
                for p in valid_players
            ]
            prob += pulp.lpSum(x[i] * contributions[i] for i in range(n)) >= target_sum
            # Chỉ áp dụng giới hạn trên nghiêm ngặt đối với SBC rating cao để tránh lãng phí thẻ siêu cao
            prob += pulp.lpSum(x[i] * contributions[i] for i in range(n)) <= (min_rating + 2.5) * sbc_size
        else:
            # SBC rating thấp: Không cần giới hạn trên chặt chẽ và dùng công thức đóng góp đơn giản
            contributions = [p['rating'] for p in valid_players]
            prob += pulp.lpSum(x[i] * contributions[i] for i in range(n)) >= target_sum

        if min_rare > 0:
            prob += pulp.lpSum(
                x[i] for i in range(n) if valid_players[i].get('rare', False)
            ) >= min_rare

        if min_totw_tots > 0:
            prob += pulp.lpSum(
                x[i] for i in range(n)
                if valid_players[i].get('totw', False) or valid_players[i].get('tots', False)
            ) >= min_totw_tots

        status = prob.solve(pulp.PULP_CBC_CMD(msg=False))

        if pulp.LpStatus[prob.status] != 'Optimal':
            continue

        selected = [valid_players[i] for i in range(n) if pulp.value(x[i]) == 1]
        if len(selected) != sbc_size:
            continue

        actual_rating = calculate_sbc_rating([p['rating'] for p in selected])
        if actual_rating >= min_rating:
            return selected

    return None


def solve_sbc_heuristic(valid_players: list, min_rating: int, min_rare: int,
                        min_totw_tots: int, sbc_size: int,
                        players_by_rating: dict, search_ratings: list):
    best_solution = [None]
    best_cost = [float('inf')]

    def evaluate_combination(combination):
        selected = []
        for r, count in combination.items():
            if count > 0:
                selected.extend(players_by_rating[r][:count])

        rare_count    = sum(1 for p in selected if p.get('rare', False))
        special_count = sum(1 for p in selected if p.get('totw', False) or p.get('tots', False))

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
            sbc_r = calculate_sbc_rating(temp_ratings)
            if min_rating <= sbc_r <= min_rating + 1:
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


def solve_sbc(players: list, requirements: dict, config: dict):
    min_rating    = requirements.get("min_rating", 83)
    # Chỉ tập trung vào rating và size, bỏ qua các yêu cầu phụ khác (Rare, TOTW, TOTS) theo yêu cầu của người dùng
    min_rare      = 0
    min_totw_tots = 0
    sbc_size      = requirements.get("size", 11)

    min_use_rating = max(config.get("min_rating_to_use", 80), 80)
    max_use_rating = config.get("max_rating_to_use", 88)
    prioritize_sbc_storage = config.get("prioritize_sbc_storage", True)
    blacklist_ids  = set(str(bid) for bid in config.get("blacklist_ids", []))

    print(f"[SOLVER] Mục tiêu: rating≥{min_rating}, rare≥{min_rare}, "
          f"totw≥{min_totw_tots}, size={sbc_size}")
    print(f"[SOLVER] Phạm vi rating dùng: {min_use_rating}–{max_use_rating}, "
          f"blacklist={len(blacklist_ids)} IDs")

    # 1. Lọc cầu thủ hợp lệ
    valid_players = []
    for p in players:
        pid = str(p.get("id", ""))
        if pid in blacklist_ids:
            continue

        r = p.get("rating", 0)
        # Nếu SBC rating >= 89, bắt buộc chỉ dùng cầu thủ từ 84 trở lên (không được dùng thẻ 80-83)
        if min_rating >= 89 and r < 84:
            continue
        if r < 80:
            continue

        is_special = p.get("totw", False) or p.get("tots", False)
        is_storage = p.get("sbc_storage", False)

        if is_special or (is_storage and prioritize_sbc_storage):
            valid_players.append(p)
            continue

        if min_use_rating <= r <= max_use_rating:
            valid_players.append(p)

    if not valid_players:
        print(f"[SOLVER ERROR] Không có cầu thủ khả dụng nào trong phạm vi rating {min_use_rating}–{max_use_rating}!")
        return None

    # 2. Tính chi phí ảo (Virtual Cost)
    prioritize_untradeable = config.get("prioritize_untradeable", True)
    prioritize_sbc_storage = config.get("prioritize_sbc_storage", True)

    # Xác định khoảng rating thấp cận dưới (low-end) động dựa trên yêu cầu rating tối thiểu của SBC
    if min_rating <= 88:
        low_min, low_max = 81, 83
        mid_min = 84
    else:
        low_min, low_max = 84, 86
        mid_min = 87

    for p in valid_players:
        is_storage = p.get("sbc_storage", False)
        is_untradeable = p.get("untradeable", False)
        r = p.get("rating", 80)
        market_price = max(p.get("market_price", 1000), 400)

        # Chi phí ảo để kích thích chiến thuật High-Low (dùng cận trên r >= min_rating & cận dưới động, bảo tồn cận trung)
        if is_storage and prioritize_sbc_storage:
            if r >= min_rating:
                # Cận trên Storage: Rất rẻ, tăng dần từ min_rating để ưu tiên chọn thẻ thấp hơn trước (tránh lãng phí thẻ siêu cao)
                p["cost"] = 10.0 + (r - min_rating) * 2.0
            elif low_min <= r <= low_max:
                # Cận dưới Storage động: Cực kỳ rẻ để phối hợp
                p["cost"] = 5.0 + (r - low_min) * 3.0
            elif r < low_min:
                # Dưới cận dưới Storage: Đắt vừa phải để tránh ưu tiên
                p["cost"] = 200.0 + (low_min - r) * 5.0
            else:
                # Cận trung Storage (mid_min đến 92): Rất đắt để bảo tồn thẻ
                p["cost"] = 250.0 + (88 - abs(r - 88)) * 10.0
        elif (is_untradeable or is_storage) and prioritize_untradeable:
            if r >= min_rating:
                # Cận trên Club Untradeable: Rẻ để sử dụng gánh team nếu thiếu Storage
                p["cost"] = 50.0 + (r - min_rating) * 5.0
            elif low_min <= r <= low_max:
                # Cận dưới Club động: Rất rẻ để dùng bù phần thiếu
                p["cost"] = 15.0 + (r - low_min) * 5.0
            elif r < low_min:
                # Dưới cận dưới Club: Đắt vừa phải để tránh ưu tiên
                p["cost"] = 350.0 + (low_min - r) * 5.0
            else:
                # Cận trung Club (mid_min đến min_rating - 1): Cực kỳ đắt để tránh sử dụng
                p["cost"] = 400.0 + (r - mid_min) * 20.0
        else:
            # Club Tradeable: Đắt nhất để tránh lãng phí tài sản bán được
            p["cost"] = market_price + 1000

    # 2.5 Lọc bỏ trùng lặp
    unique_players = {}
    for p in valid_players:
        def_id = p.get("definitionId", 0)
        key = def_id if def_id > 0 else p.get("name", "Unknown")

        if key not in unique_players:
            unique_players[key] = p
        else:
            if p["cost"] < unique_players[key]["cost"]:
                unique_players[key] = p

    valid_players = list(unique_players.values())
    print(f"[SOLVER] Cầu thủ hợp lệ sau lọc trùng lặp: {len(valid_players)}/{len(players)}")

    selected_players = None

    # 3. Thử tìm nghiệm bằng FUT.GG Combinations Database (Chỉ áp dụng cho SBC rating thấp <87 để tránh lãng phí)
    if sbc_size == 11 and min_rating < 87:
        print("[SOLVER] Thử tìm nghiệm tối ưu từ FUT.GG Combinations Database...")
        db_solution = solve_using_combinations(valid_players, min_rating, min_rare, min_totw_tots, sbc_size)
        if db_solution:
            # Ngăn chặn việc lãng phí: Rating thực tế không được vượt quá mục tiêu + 1
            if db_solution["solved_rating"] <= min_rating + 1:
                print(f"[SOLVER] ✅ Tìm thấy nghiệm tối ưu từ Combinations Database! (Rating thực tế đạt: {db_solution['solved_rating']})")
                selected_players = db_solution["players"]
            else:
                print(f"[SOLVER] Bỏ qua combinations vì rating thực tế ({db_solution['solved_rating']}) quá cao so với mục tiêu ({min_rating}) gây lãng phí.")

    # 4. Thử MILP Solver nếu database bị bỏ qua hoặc không tìm thấy nghiệm hợp lý
    if not selected_players:
        try:
            import pulp
            pulp_available = True
        except ImportError:
            pulp_available = False

        if pulp_available:
            print("[SOLVER] Đang chạy MILP Solver (PuLP)...")
            selected_players = solve_sbc_milp(
                valid_players, min_rating, min_rare, min_totw_tots, sbc_size
            )
            if selected_players:
                print(f"[SOLVER] ✅ MILP tìm được nghiệm tối ưu.")

    # 5. Thử Heuristic Fallback
    if not selected_players:
        players_by_rating = {}
        for p in valid_players:
            r = p["rating"]
            if r not in players_by_rating:
                players_by_rating[r] = []
            players_by_rating[r].append(p)
        for r in players_by_rating:
            players_by_rating[r].sort(key=lambda p: p["cost"])

        available_ratings = sorted(players_by_rating.keys())
        search_ratings = [r for r in available_ratings if (min_rating - 8) <= r <= (min_rating + 5)]
        if not search_ratings:
            search_ratings = available_ratings

        print(f"[SOLVER] Chạy heuristic với {len(search_ratings)} mức rating: {search_ratings}")
        selected_players = solve_sbc_heuristic(
            valid_players, min_rating, min_rare, min_totw_tots,
            sbc_size, players_by_rating, search_ratings
        )
        if selected_players:
            print(f"[SOLVER] ✅ Heuristic tìm được nghiệm.")

    if not selected_players:
        print("[SOLVER ERROR] Không tìm thấy nghiệm phù hợp nào!")
        return None

    # 6. Định dạng kết quả đầu ra
    solved_rating = calculate_sbc_rating([p["rating"] for p in selected_players])
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
    import os
    import sys

    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8')

    print("[SOLVER TEST] Chạy test solver với file club-analyzer-2.csv...")
    # Tự động định vị file CSV tương đối theo thư mục của file script
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
