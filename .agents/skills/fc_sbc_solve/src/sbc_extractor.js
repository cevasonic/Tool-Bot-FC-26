/**
 * sbc_extractor.js — v2.0
 *
 * Script JavaScript inject vào EA FC 26 Web App để:
 *   1. Tự động load danh sách cầu thủ qua 3-tầng Fallback
 *   2. Trích xuất thông tin SBC Challenge đang mở
 *   3. Trả kết quả về Python backend qua Playwright
 *   4. Tự động điền (Auto-fill) cầu thủ vào sân bóng
 *
 * CHIẾN LƯỢC LOAD CẦU THỦ (3 TẦNG):
 *   Tầng 1: Đọc thẳng từ repositories.Item cache (nếu cache đã có sẵn)
 *   Tầng 2: Tự động điều hướng sang tab Club, đợi load, quay về SBC
 *   Tầng 3: Dùng nút "Use duplicated players" / "Use unassigned players"
 *            để lấy ít nhất cầu thủ từ SBC Storage
 */

window.sbcSolveExtractor = {
    rawClubItems: [],

    // =========================================================================
    // PHẦN 1: TIỆN ÍCH TÌM VIEWCONTROLLER
    // =========================================================================

    /**
     * Tìm kiếm đệ quy từ ViewController gốc để tìm ViewController chứa SBC Challenge.
     */
    findChallengeViewController: function(vc) {
        if (!vc) return null;

        if (vc._challenge || vc.challenge) {
            return vc;
        }

        // Duyệt qua childViewControllers
        if (vc.childViewControllers && vc.childViewControllers.length > 0) {
            for (let child of vc.childViewControllers) {
                let found = this.findChallengeViewController(child);
                if (found) return found;
            }
        }

        // Duyệt qua _viewControllers
        let vcs = vc._viewControllers;
        if (!vcs && typeof vc.getViewControllers === 'function') {
            try { vcs = vc.getViewControllers(); } catch(e) {}
        }
        if (vcs && vcs.length > 0) {
            for (let child of vcs) {
                let found = this.findChallengeViewController(child);
                if (found) return found;
            }
        }

        // Duyệt qua presentedViewController
        let presented = null;
        if (typeof vc.getPresentedViewController === 'function') {
            try { presented = vc.getPresentedViewController(); } catch(e) {}
        }
        if (!presented) {
            presented = vc._presentedViewController || vc.presentedViewController;
        }
        if (presented && presented !== vc) {
            let found = this.findChallengeViewController(presented);
            if (found) return found;
        }

        return null;
    },

    // =========================================================================
    // PHẦN 2: TIỆN ÍCH UPDATE TRẠNG THÁI NÚT
    // =========================================================================

    /**
     * Cập nhật text và màu nút Solve theo từng bước xử lý.
     * @param {string} text - Nội dung hiển thị
     * @param {string} [color] - Màu border/nền (tùy chọn)
     */
    updateButtonStatus: function(text, color) {
        let btn = document.getElementById('sbc-solve-floating-btn');
        if (!btn) return;
        btn.innerText = text;
        if (color) {
            btn.style.borderColor = color;
            if (color === '#ff3366') {
                btn.style.background = '#4a0000';
            } else if (color === '#00f5d4') {
                btn.style.background = 'linear-gradient(135deg, #00b4d8 0%, #0077b6 100%)';
            } else {
                btn.style.background = '#444444';
            }
        }
    },

    // =========================================================================
    // PHẦN 3: LOGIC GOM CẦU THỦ — FC26 API (repositories.Item.club.items)
    // =========================================================================

    /**
     * Map một item object từ Web App FC26 sang format chuẩn của solver.
     * FC26 dùng: item._rating, item._rareflag, item.definitionId, item.loans
     */
    mapPlayerItem: function(item, source) {
        if (!item) return null;

        // Lấy tên: thử nhiều cách vì FC26 có thể encode khác nhau
        let name = 'Unknown';
        try {
            name = item.getStaticData?.()?.name
                || item._staticData?.name
                || item.displayName
                || item.name
                || 'Unknown';
        } catch(e) {}

        // Rating: FC26 dùng _rating
        let rating = item._rating || item.rating || 0;

        // Rarity: FC26 dùng _rareflag hoặc function isRare()
        let rareflag = item._rareflag || item.rareflag || 0;
        let isRare = false;
        if (typeof item.isRare === 'function') {
            isRare = item.isRare();
        } else {
            isRare = rareflag > 1 || rareflag === 1;
        }
        // TOTW: rareflag 12 (IF), 22, 53, 55, 56...
        let isTotw = [12, 22, 53, 55, 56, 63, 66, 71, 72].includes(rareflag);
        // TOTS: rareflag 41, 42
        let isTots = rareflag === 41 || rareflag === 42;

        // Untradeable: FC26 dùng !item.tradable hoặc item.untradeable
        let untradeable = item.untradeable === true || item.tradable === false;

        // Thẻ Loan
        let isLoan = item.loans != null && item.loans > 0;

        // Lấy definitionId để kiểm tra trùng lặp
        let defId = item.definitionId
            || (item.getStaticData?.()?.id)
            || item._staticData?.id
            || item.assetId
            || 0;

        let isEvolution = false;
        try {
            isEvolution = (typeof item.isEvolution === 'function' ? item.isEvolution() : (item.isEvolution || false))
                || (item.evolutionId != null && item.evolutionId !== 0 && item.evolutionId !== '')
                || (item.evolutionFlags != null && item.evolutionFlags !== 0)
                || (item.evolutionStatus != null && item.evolutionStatus !== 0)
                || (item.evolution !== undefined && item.evolution !== null && item.evolution !== false);
        } catch(e) {}

        let isFavorite = false;
        try {
            isFavorite = typeof item.isFavorite === 'function' ? item.isFavorite() : (item.favorite || false);
        } catch(e) {}

        let activeSquad = item.activeSquad === true;

        return {
            id: String(item.id),
            definitionId: Number(defId),
            name: name,
            rating: rating,
            position: item.preferredPosition || 'SUB',
            rare: isRare,
            totw: isTotw,
            tots: isTots,
            untradeable: untradeable,
            loan: isLoan,
            sbc_storage: source === 'storage',
            market_price: item._itemPriceData?.buyNowPrice
                || item.itemPriceData?.buyNowPrice
                || 500,
            active_squad: activeSquad,
            favorite: isFavorite,
            evolution: isEvolution
        };
    },

    /**
     * [FC26 API] Đọc cầu thủ từ cache hiện tại trong repositories.
     * Dùng repositories.Item.club.items.values() (FC26 dùng Map, không phải ._items)
     */
    gatherPlayersFromCache: function(clubPlayersFromServer) {
        const self = this;
        let allMap = new Map();

        // --- SBC Storage (ưu tiên cao nhất) ---
        try {
            let storageRepo = repositories.Item.storage;
            if (storageRepo && typeof storageRepo.values === 'function') {
                Array.from(storageRepo.values()).forEach(item => {
                    if (item && (item.type === 'player' || (item.isPlayer && item.isPlayer()))) {
                        let p = self.mapPlayerItem(item, 'storage');
                        if (p && p.rating >= 70) allMap.set(p.id, p);
                    }
                });
            } else if (repositories.Item.getStorageItems) {
                let si = repositories.Item.getStorageItems() || [];
                si.forEach(item => {
                    if (item && (item.type === 'player' || (item.isPlayer && item.isPlayer()))) {
                        let p = self.mapPlayerItem(item, 'storage');
                        if (p && p.rating >= 70) allMap.set(p.id, p);
                    }
                });
            }
        } catch(e) { console.warn('[SOLVER JS] Storage read error:', e.message); }

        // --- Unassigned ---
        try {
            if (repositories.Item.getUnassignedItems) {
                let ui = repositories.Item.getUnassignedItems() || [];
                ui.forEach(item => {
                    if (item && (item.type === 'player' || (item.isPlayer && item.isPlayer()))) {
                        let p = self.mapPlayerItem(item, 'unassigned');
                        if (p && p.rating >= 70 && !allMap.has(p.id)) allMap.set(p.id, p);
                    }
                });
            }
        } catch(e) {}

        // --- Club Players ---
        if (Array.isArray(clubPlayersFromServer) && clubPlayersFromServer.length > 0) {
            clubPlayersFromServer.forEach(p => {
                if (p && !allMap.has(p.id)) {
                    allMap.set(p.id, p);
                }
            });
        } else {
            try {
                // Fallback nếu không có clubPlayersFromServer: đọc từ cache hiện tại
                let clubItemsRepo = repositories.Item.club ? repositories.Item.club.items : null;
                if (clubItemsRepo && typeof clubItemsRepo.values === 'function') {
                    Array.from(clubItemsRepo.values()).forEach(item => {
                        if (item && (item.type === 'player' || (item.isPlayer && item.isPlayer()))) {
                            let p = self.mapPlayerItem(item, 'club');
                            if (p && p.rating >= 70 && !allMap.has(p.id)) allMap.set(p.id, p);
                        }
                    });
                } else {
                    let clubObj = repositories.Item.getClub ? repositories.Item.getClub() : null;
                    if (clubObj && clubObj._items) {
                        let ci = Array.isArray(clubObj._items) ? clubObj._items : Object.values(clubObj._items);
                        ci.forEach(item => {
                            if (item && (item.type === 'player' || (item.isPlayer && item.isPlayer()))) {
                                let p = self.mapPlayerItem(item, 'club');
                                if (p && p.rating >= 70 && !allMap.has(p.id)) allMap.set(p.id, p);
                            }
                        });
                    }
                }
            } catch(e) { console.warn('[SOLVER JS] Club read error:', e.message); }
        }

        return Array.from(allMap.values());
    },

    /**
     * Đếm số cầu thủ hiện có trong cache Club (FC26 API).
     */
    getClubCacheCount: function() {
        try {
            // FC26 API mới
            let clubItemsRepo = repositories.Item.club ? repositories.Item.club.items : null;
            if (clubItemsRepo && typeof clubItemsRepo.values === 'function') {
                return Array.from(clubItemsRepo.values()).filter(
                    item => item && (item.type === 'player' || (item.isPlayer && item.isPlayer()))
                ).length;
            }
            // Fallback cũ
            let clubObj = repositories.Item.getClub ? repositories.Item.getClub() : null;
            if (!clubObj || !clubObj._items) return 0;
            let items = clubObj._items;
            return Array.isArray(items) ? items.length : Object.keys(items).length;
        } catch(e) { return 0; }
    },

    /**
     * [FC26 API] Load đầy đủ cầu thủ từ server qua services.Club.search() phân trang.
     * Trả về Promise<number> (số cầu thủ đã load).
     * 
     * Phát hiện từ debug: dùng cacheable=false để bypass cache,
     * repositories.Item.club.items.reset() để xóa cache giữa các trang.
     */
    loadClubPlayersFromServer: function() {
        return new Promise((resolve) => {
            const self = this;

            // Kiểm tra xem services.Club.search có tồn tại không
            if (typeof services === 'undefined' || !services.Club || typeof services.Club.search !== 'function') {
                console.warn('[SOLVER JS] services.Club.search không khả dụng.');
                resolve([]);
                return;
            }

            if (typeof UTSearchCriteriaDTO === 'undefined') {
                console.warn('[SOLVER JS] UTSearchCriteriaDTO không tồn tại.');
                resolve([]);
                return;
            }

            self.rawClubItems = [];
            let accumulated = [];
            let offset = 0;
            const PAGE_SIZE = 90; // EA giới hạn tối đa 90/request
            let maxPages = 20;    // Giới hạn an toàn: tối đa 20 trang = 1800 cầu thủ

            const loadPage = () => {
                if (maxPages-- <= 0) {
                    console.log(`[SOLVER JS] Đã load ${accumulated.length} cầu thủ (đạt giới hạn trang).`);
                    resolve(accumulated);
                    return;
                }

                // Reset cache của club.items trước mỗi trang để ép request mới
                try {
                    if (repositories.Item.club && repositories.Item.club.items &&
                        typeof repositories.Item.club.items.reset === 'function') {
                        repositories.Item.club.items.reset();
                    }
                } catch(e) {}

                let criteria = new UTSearchCriteriaDTO();
                criteria.type = SearchType && SearchType.PLAYER ? SearchType.PLAYER : 'player';
                criteria.count = PAGE_SIZE;
                criteria.offset = offset;
                criteria.cacheable = false; // bypass cache

                try {
                    let obs = services.Club.search(criteria);
                    obs.observe(self, function(observer, response) {
                        if (response && response.success && response.response && response.response.items) {
                            let items = response.response.items;
                            let pagePlayersCount = 0;
                            items.forEach(item => {
                                if (item && (item.type === 'player' || (item.isPlayer && item.isPlayer()))) {
                                    // Lưu lại raw item instance để dùng khi điền đội hình
                                    self.rawClubItems.push(item);

                                    let p = self.mapPlayerItem(item, 'club');
                                    if (p && p.rating >= 70) {
                                        accumulated.push(p);
                                        pagePlayersCount++;
                                    }
                                }
                            });
                            console.log(`[SOLVER JS] Trang ${Math.floor(offset/PAGE_SIZE)+1}: ${items.length} items (${pagePlayersCount} cầu thủ), tổng tích lũy=${accumulated.length}`);

                            if (items.length < PAGE_SIZE || response.response.retrievedAll) {
                                // Đã hết dữ liệu
                                resolve(accumulated);
                            } else {
                                offset += PAGE_SIZE;
                                setTimeout(loadPage, 300); // Chờ 300ms giữa các trang
                            }
                        } else {
                            console.warn('[SOLVER JS] Trang không trả về dữ liệu hợp lệ.');
                            resolve(accumulated);
                        }
                    });
                } catch(searchErr) {
                    console.warn('[SOLVER JS] Lỗi gọi services.Club.search:', searchErr.message);
                    resolve(accumulated);
                }
            };

            console.log('[SOLVER JS] Bắt đầu load cầu thủ từ server (services.Club.search)...');
            loadPage();
        });
    },

    /**
     * [FC26 API] Load cầu thủ từ SBC Storage qua services.Item.searchStorageItems().
     */
    loadStoragePlayers: function() {
        return new Promise((resolve) => {
            if (typeof services === 'undefined' || !services.Item ||
                typeof services.Item.searchStorageItems !== 'function') {
                resolve(0);
                return;
            }
            try {
                let criteria = new UTSearchCriteriaDTO();
                criteria.type = SearchType && SearchType.PLAYER ? SearchType.PLAYER : 'player';
                criteria.count = 90;
                criteria.offset = 0;

                let obs = services.Item.searchStorageItems(criteria);
                obs.observe(this, function(observer, response) {
                    let count = response?.response?.items?.length || 0;
                    console.log(`[SOLVER JS] SBC Storage: ${count} cầu thủ.`);
                    resolve(count);
                });
            } catch(e) {
                resolve(0);
            }
        });
    },

    // =========================================================================
    // PHẦN 4: HÀM CHÍNH — TRÍCH XUẤT SBC + CẦU THỦ
    // =========================================================================

    /**
     * Hàm chính: Lấy thông tin SBC đang mở và danh sách cầu thủ khả dụng.
     * Trả về Promise để Playwright có thể await kết quả.
     *
     * FLOW (FC26):
     *   1. Đọc SBC Challenge info từ ViewController
     *   2. Tầng 1: Đọc cache hiện tại bằng repositories.Item.club.items.values()
     *   3. Nếu cache đủ (> 10 cầu thủ) → dùng luôn
     *   4. Nếu không đủ → Tầng 2: Gọi services.Club.search() phân trang (FC26 API)
     *   5. Song song: Tầng 3 load SBC Storage qua services.Item.searchStorageItems()
     *   6. resolve() với dữ liệu thu được
     */
    extractSbcAndPlayers: function() {
        return new Promise(async (resolve) => {
            const self = this;
            let result = { sbc_challenge: null, players: [], error: null };

            try {
                if (typeof getAppMain === 'undefined') {
                    throw new Error('Không tìm thấy hàm getAppMain của Web App.');
                }

                let rootVC = getAppMain().getRootViewController();
                if (!rootVC) throw new Error('Không thể truy cập RootViewController.');

                let topVC = self.findChallengeViewController(rootVC);
                if (!topVC) {
                    throw new Error(
                        'Không tìm thấy màn hình SBC. Vui lòng đảm bảo bạn đang ở giao diện SBC.'
                    );
                }

                console.log('[SOLVER JS] Định vị thành công SBC ViewController:', topVC.constructor.name);

                let challenge = topVC._challenge || topVC.challenge;
                if (!challenge) {
                    throw new Error('Không tìm thấy đối tượng SBC Challenge trên ViewController.');
                }

                // ── ĐỌC YÊU CẦU SBC (FALLBACK CHAIN CHẶT CHẼ) ──
                let rawReqs = [];
                let candidates = [];
                if (challenge.requirements && challenge.requirements.length > 0) {
                    candidates = challenge.requirements;
                } else if (challenge.eligibilityRequirements && challenge.eligibilityRequirements.length > 0) {
                    candidates = challenge.eligibilityRequirements;
                } else if (typeof challenge.getEligibilityRequirements === 'function') {
                    try { candidates = challenge.getEligibilityRequirements() || []; } catch(e) {}
                } else if (challenge._requirements && challenge._requirements.length > 0) {
                    candidates = challenge._requirements;
                } else if (challenge._eligibilityRequirements && challenge._eligibilityRequirements.length > 0) {
                    candidates = challenge._eligibilityRequirements;
                }

                // Lọc bỏ các requirement rỗng/vô nghĩa (value <= 0 và không có text mô tả)
                if (candidates && candidates.length > 0) {
                    rawReqs = Array.from(candidates).filter(r => {
                        if (!r) return false;
                        let val = r.value || 0;
                        let desc = '';
                        if (typeof r.getRequirementText === 'function') {
                            try { desc = r.getRequirementText() || ''; } catch(e) {}
                        }
                        if (!desc) {
                            desc = r.description || '';
                        }
                        desc = String(desc).trim();
                        return val > 0 || desc.length > 0;
                    });
                }

                // Tầng 2: Nếu API trống, tự động click mở popup "Requirements" và cào từ giao diện DOM
                if (!rawReqs || rawReqs.length === 0) {
                    console.log('[SOLVER JS] API trống → Thử cào điều kiện từ giao diện DOM...');
                    try {
                        let reqBtn = Array.from(document.querySelectorAll('div, button, span, p')).find(el => {
                            let txt = (el.innerText || el.textContent || '').trim();
                            return txt.startsWith('Requirements') && el.offsetWidth > 0;
                        });

                        if (reqBtn) {
                            console.log('[SOLVER JS] Click mở tab Requirements...');
                            try { reqBtn.click(); } catch(cErr) {}
                            await new Promise(r => setTimeout(r, 150)); // Chờ popup render
                        }

                        // Tìm popup "Challenge Requirements" bằng cách so khớp tiêu đề/nội dung
                        let popup = Array.from(document.querySelectorAll('div, section')).find(el => {
                            let html = el.innerHTML || '';
                            return html.includes('Challenge Requirements') && el.offsetWidth > 0;
                        });

                        if (popup) {
                            let domReqs = [];
                            let items = popup.querySelectorAll('li, div, p, span');
                            items.forEach(el => {
                                let text = (el.innerText || el.textContent || '').trim();
                                if (text && text.length > 5 && text.length < 100) {
                                    // Phân tích Rating
                                    let ratingMatch = text.match(/(?:rating|đánh\s*giá|valoración)\D*(\d+)/i);
                                    if (ratingMatch) {
                                        let val = parseInt(ratingMatch[1]);
                                        if (!domReqs.some(r => r.type === 'teamrating' && r.value === val)) {
                                            domReqs.push({
                                                type: 'teamrating',
                                                value: val,
                                                getRequirementText: () => text,
                                                description: text
                                            });
                                        }
                                    }
                                    // Phân tích Rare
                                    let rareMatch = text.match(/(?:rare|hiếm|únicos)\D*(\d+)/i);
                                    if (rareMatch) {
                                        let val = parseInt(rareMatch[1]);
                                        if (!domReqs.some(r => r.type === 'rare' && r.value === val)) {
                                            domReqs.push({
                                                type: 'rare',
                                                value: val,
                                                getRequirementText: () => text,
                                                description: text
                                            });
                                        }
                                    }
                                    // Phân tích TOTW/TOTS
                                    let specialMatch = text.match(/(?:totw|tots|week|tuần|especial|in-form|special)\D*(\d+)/i);
                                    if (specialMatch) {
                                        let val = parseInt(specialMatch[1]);
                                        if (!domReqs.some(r => r.type === 'totw' && r.value === val)) {
                                            domReqs.push({
                                                type: 'totw',
                                                value: val,
                                                getRequirementText: () => text,
                                                description: text
                                            });
                                        }
                                    }
                                }
                            });

                            if (domReqs.length > 0) {
                                console.log('[SOLVER JS] Đã cào được các yêu cầu từ DOM:', domReqs);
                                rawReqs = domReqs;
                            }
                        }

                        // Click đóng lại popup (để trả lại giao diện nguyên bản)
                        if (reqBtn) {
                            try { reqBtn.click(); } catch(cErr) {}
                        }
                    } catch (domErr) {
                        console.warn('[SOLVER JS] Lỗi khi cào DOM requirements:', domErr.message);
                    }
                }

                // Tầng 3: Nếu vẫn trống, fallback phân tích từ tên Challenge (chỉ khi có chữ -Rated)
                if ((!rawReqs || rawReqs.length === 0) && challenge.name) {
                    let match = challenge.name.match(/(\d+)-[rR]ated/);
                    if (!match) {
                        match = challenge.name.match(/(\d+)\s+[rR]ated/);
                    }
                    if (match) {
                        let ratingVal = parseInt(match[1]);
                        console.log('[SOLVER JS] Tự động parse rating từ tên challenge:', ratingVal);
                        rawReqs = [{
                            type: 'teamrating',
                            value: ratingVal,
                            getRequirementText: () => `Min. Team Rating: ${ratingVal}`,
                            description: `Min. Team Rating: ${ratingVal}`
                        }];
                    }
                }

                let mappedRequirements = rawReqs ? rawReqs.map(r => ({
                    type: r.type != null ? String(r.type) : '',
                    value: r.value != null ? r.value : 0,
                    desc: (typeof r.getRequirementText === 'function')
                        ? r.getRequirementText()
                        : (r.description || '')
                })) : [];

                // Đọc thông tin SBC
                result.sbc_challenge = {
                    name: challenge.name || 'SBC Challenge',
                    id: challenge.id ? String(challenge.id) : '',
                    size: challenge.squadSize || 11,
                    requirements: mappedRequirements
                };

                console.log('[SOLVER JS] SBC Challenge:', result.sbc_challenge.name,
                    '| Size:', result.sbc_challenge.size,
                    '| Yêu cầu:', JSON.stringify(result.sbc_challenge.requirements));

                // ------------------------------------------------------------------
                // LUÔN LOAD TỪ SERVER ĐỂ ĐẢM BẢO ĐỦ CẦU THỦ
                // ------------------------------------------------------------------
                console.log('[SOLVER JS] Bắt đầu đồng bộ danh sách cầu thủ từ Server EA...');
                self.updateButtonStatus('⏳ LOADING CLUB...');

                Promise.all([
                    self.loadClubPlayersFromServer(),
                    self.loadStoragePlayers()
                ]).then(([clubPlayers, storageCount]) => {
                    console.log(`[SOLVER JS] Tải xong: Club=${clubPlayers.length}, Storage=${storageCount}`);

                    // Thu thập và lọc cầu thủ từ cache và kết quả server
                    let allPlayers = self.gatherPlayersFromCache(clubPlayers);
                    
                    // Loại bỏ thẻ Loan (không được dùng trong SBC thông thường) và chỉ lấy cầu thủ có rating >= 70
                    result.players = allPlayers.filter(p => p && !p.loan && p.rating >= 70);
                    
                    console.log(`[SOLVER JS] Tổng hợp sau khi lọc (loại bỏ Loan): ${result.players.length} cầu thủ.`);

                    if (result.players.length === 0) {
                        result.error = 'Không tìm thấy cầu thủ khả dụng trong Club hoặc Storage của bạn.';
                        console.error('[SOLVER JS] ❌ Không có cầu thủ khả dụng nào sau khi load.');
                    } else {
                        console.log('[SOLVER JS] ✅ Load danh sách cầu thủ thành công.');
                    }

                    resolve(result);
                }).catch(err => {
                    result.error = 'Lỗi load danh sách cầu thủ: ' + err.message;
                    console.error('[SOLVER JS] ❌ Load error:', err.message);
                    resolve(result);
                });

            } catch(e) {
                result.error = e.message;
                console.error('[SOLVER JS] Lỗi trong extractSbcAndPlayers:', e.message);
                resolve(result);
            }
        });
    },


    // =========================================================================
    // PHẦN 5: AUTO-FILL CẦU THỦ VÀO SÂN
    // =========================================================================

    /**
     * Tự động điền các cầu thủ đã giải vào đội hình SBC.
     * @param {string[]} playerIds - Mảng các item ID cần điền
     * @returns {{ success: boolean, filled: number, error?: string }}
     */
    fillSquad: function(playerIds) {
        try {
            if (typeof getAppMain === 'undefined') {
                return { success: false, error: 'getAppMain not defined' };
            }

            let rootVC = getAppMain().getRootViewController();
            let topVC = this.findChallengeViewController(rootVC);
            if (!topVC) {
                return { success: false, error: 'Không tìm thấy màn hình SBC Builder khi điền cầu thủ' };
            }

            // Tìm đối tượng Squad
            let squad = topVC.squad
                || topVC._squad
                || (topVC._squadContext ? topVC._squadContext.squad : null)
                || (topVC._squadOverviewViewModel ? topVC._squadOverviewViewModel._squad : null);

            if (!squad) {
                return { success: false, error: 'Không tìm thấy đối tượng Squad của đội hình' };
            }

            // Xây dựng map tra cứu nhanh từ item ID → item object
            let itemRepo = (typeof repositories !== 'undefined') ? repositories.Item : null;
            if (!itemRepo) {
                return { success: false, error: 'Không tìm thấy repositories.Item' };
            }

            let playerMap = new Map();

            // 1. Storage (FC26 API)
            try {
                let storageRepo = itemRepo.storage;
                if (storageRepo && typeof storageRepo.values === 'function') {
                    Array.from(storageRepo.values()).forEach(item => {
                        if (item && item.id != null) playerMap.set(String(item.id), item);
                    });
                } else if (typeof itemRepo.getStorageItems === 'function') {
                    let si = itemRepo.getStorageItems() || [];
                    si.forEach(item => {
                        if (item && item.id != null) playerMap.set(String(item.id), item);
                    });
                }
            } catch(e) {}

            // 2. Unassigned
            try {
                if (typeof itemRepo.getUnassignedItems === 'function') {
                    let ui = itemRepo.getUnassignedItems() || [];
                    ui.forEach(item => {
                        if (item && item.id != null) playerMap.set(String(item.id), item);
                    });
                }
            } catch(e) {}

            // 3. Club (FC26 API: club.items.values())
            try {
                let clubItemsRepo = itemRepo.club ? itemRepo.club.items : null;
                if (clubItemsRepo && typeof clubItemsRepo.values === 'function') {
                    Array.from(clubItemsRepo.values()).forEach(item => {
                        if (item && item.id != null && !playerMap.has(String(item.id))) {
                            playerMap.set(String(item.id), item);
                        }
                    });
                } else {
                    let clubObj = itemRepo.getClub ? itemRepo.getClub() : null;
                    if (clubObj && clubObj._items) {
                        let ci = Array.isArray(clubObj._items) ? clubObj._items : Object.values(clubObj._items);
                        ci.forEach(item => {
                            if (item && item.id != null && !playerMap.has(String(item.id))) {
                                playerMap.set(String(item.id), item);
                            }
                        });
                    }
                }
            } catch(e) {}

            // 4. Các raw items đã được lưu từ server search
            try {
                let savedItems = window.sbcSolveExtractor.rawClubItems;
                if (Array.isArray(savedItems)) {
                    savedItems.forEach(item => {
                        if (item && item.id != null && !playerMap.has(String(item.id))) {
                            playerMap.set(String(item.id), item);
                        }
                    });
                }
            } catch(e) {}

            let filledCount = 0;
            let slots = typeof squad.getSlots === 'function' ? squad.getSlots() : null;

            for (let i = 0; i < playerIds.length; i++) {
                let pid = String(playerIds[i]);
                if (!pid || pid === '0' || pid === '') continue;

                let targetPlayer = playerMap.get(pid);
                if (!targetPlayer) continue;

                // Thử các API điền cầu thủ của Web App (FC26 tương tác qua Slots)
                if (slots && slots[i] && typeof slots[i].setItem === 'function') {
                    slots[i].setItem(targetPlayer);
                    filledCount++;
                } else if (typeof squad.setPlayer === 'function') {
                    squad.setPlayer(targetPlayer, i);
                    filledCount++;
                } else if (typeof squad.addPlayer === 'function') {
                    squad.addPlayer(targetPlayer, i);
                    filledCount++;
                } else if (squad._players && Array.isArray(squad._players)) {
                    squad._players[i] = targetPlayer;
                    filledCount++;
                }
            }

            // Đồng bộ cập nhật lên giao diện (FC26 dùng _overviewController._pushSquadToView)
            let overview = topVC._overviewController
                || topVC.overviewController
                || topVC._squadOverviewViewController;

            // Đặt cờ dirty và tính toán lại chemistry/rating của squad trước khi đồng bộ view
            try {
                if (typeof squad.setDirty === 'function') {
                    squad.setDirty(true);
                }
                if (typeof squad.updatePitchChemistry === 'function') {
                    squad.updatePitchChemistry();
                }
            } catch (err) {}

            if (overview && typeof overview._pushSquadToView === 'function') {
                overview._pushSquadToView(squad);
            } else {
                // Fallback các hàm notify/render cũ
                if (squad.onSquadChanged && typeof squad.onSquadChanged.notify === 'function') {
                    squad.onSquadChanged.notify();
                }
                if (typeof topVC.updateSquad === 'function') {
                    topVC.updateSquad();
                } else if (typeof topVC.render === 'function') {
                    topVC.render();
                } else if (typeof topVC.viewDidAppear === 'function') {
                    topVC.viewDidAppear();
                }
            }

            // Ép Web App chạy lại bộ đánh giá điều kiện SBC (Challenge Requirements) và render panel
            try {
                if (typeof squad.isValid === 'function') {
                    squad.isValid();
                }
                // Notify để các panel nhận diện thay đổi và vẽ lại
                if (squad.onSquadChanged && typeof squad.onSquadChanged.notify === 'function') {
                    squad.onSquadChanged.notify();
                }
                if (overview && typeof overview.render === 'function') {
                    overview.render();
                }
                if (overview && overview._panel && typeof overview._panel.render === 'function') {
                    overview._panel.render();
                }
                // Nếu topVC là UTSBCSquadSplitViewController, ta gọi render của nó để vẽ lại panel bên phải
                if (typeof topVC.render === 'function') {
                    topVC.render();
                }
            } catch (err) {}

            return { success: true, filled: filledCount };

        } catch(e) {
            return { success: false, error: e.message };
        }
    },

    // =========================================================================
    // PHẦN 6: NÚT GIAO DIỆN VÀ BỘ GIÁM SÁT
    // =========================================================================

    /**
     * Tạo và hiển thị nút "SBC Solve" trên giao diện Web App.
     * Nút xuất hiện ở bất kỳ màn hình nào liên quan đến SBC.
     */
    injectSolverButton: function() {
        if (document.getElementById('sbc-solve-floating-btn')) return;

        // Hiển thị ở mọi màn hình liên quan đến SBC
        let isSbcContext = document.querySelector('.ut-squad-pitch-view.sbc')       // Sân bóng SBC
            || document.querySelector('.ut-sbc-squad-split-view')                   // Split view
            || document.querySelector('.ut-sbc-set-list-view')                      // Danh sách SBC
            || (document.querySelector('.pitch') && document.querySelector('.ut-squad-slot-view')); // Generic

        if (!isSbcContext) return;

        console.log('[SOLVER JS] Đang tạo nút SBC Solve...');

        let btn = document.createElement('button');
        btn.id = 'sbc-solve-floating-btn';
        btn.innerText = '⚡ SBC SOLVE';

        Object.assign(btn.style, {
            position: 'fixed',
            bottom: '80px',
            right: '25px',
            zIndex: '9999999',
            padding: '12px 24px',
            background: 'linear-gradient(135deg, #7b2cbf 0%, #3a0ca3 100%)',
            color: '#ffffff',
            border: '2px solid #00f5d4',
            borderRadius: '30px',
            fontWeight: 'bold',
            fontSize: '14px',
            cursor: 'pointer',
            boxShadow: '0 8px 20px rgba(123, 44, 191, 0.4)',
            transition: 'all 0.3s ease',
            letterSpacing: '1px',
            fontFamily: 'system-ui, -apple-system, sans-serif',
            userSelect: 'none'
        });

        btn.onmouseover = () => {
            if (btn.disabled) return;
            btn.style.transform = 'translateY(-3px) scale(1.05)';
            btn.style.boxShadow = '0 12px 25px rgba(0, 245, 212, 0.5)';
            btn.style.background = 'linear-gradient(135deg, #9d4edd 0%, #7b2cbf 100%)';
        };
        btn.onmouseout = () => {
            if (btn.disabled) return;
            btn.style.transform = 'translateY(0) scale(1)';
            btn.style.boxShadow = '0 8px 20px rgba(123, 44, 191, 0.4)';
            btn.style.background = 'linear-gradient(135deg, #7b2cbf 0%, #3a0ca3 100%)';
        };

        btn.onclick = () => {
            if (btn.disabled) return;
            btn.disabled = true;
            btn.innerText = '⏳ STARTING...';
            btn.style.background = '#555555';
            btn.style.borderColor = '#999999';
            btn.style.transform = 'none';
            window.sbc_solver_trigger = true;
        };

        document.body.appendChild(btn);
    },

    /**
     * Xóa nút Solve khỏi DOM.
     */
    removeSolverButton: function() {
        let btn = document.getElementById('sbc-solve-floating-btn');
        if (btn) btn.remove();
    },

    /**
     * Reset nút về trạng thái ban đầu sau khi hoàn thành.
     */
    resetSolverButton: function() {
        let btn = document.getElementById('sbc-solve-floating-btn');
        if (!btn) return;
        btn.disabled = false;
        btn.innerText = '⚡ SBC SOLVE';
        btn.style.background = 'linear-gradient(135deg, #7b2cbf 0%, #3a0ca3 100%)';
        btn.style.borderColor = '#00f5d4';
        btn.style.transform = 'none';
    },

    /**
     * Khởi động bộ giám sát giao diện (kiểm tra mỗi 1.5s).
     * Tự động inject/remove nút theo ngữ cảnh màn hình.
     */
    startMonitoring: function() {
        if (window.sbc_monitor_interval) {
            clearInterval(window.sbc_monitor_interval);
        }

        window.sbc_solver_trigger = false;

        window.sbc_monitor_interval = setInterval(() => {
            try {
                let isSbcContext = document.querySelector('.ut-squad-pitch-view.sbc')
                    || document.querySelector('.ut-sbc-squad-split-view')
                    || document.querySelector('.ut-sbc-set-list-view')
                    || (document.querySelector('.pitch') && document.querySelector('.ut-squad-slot-view'));

                if (isSbcContext) {
                    this.injectSolverButton();
                } else {
                    this.removeSolverButton();
                }
            } catch(e) {
                console.error('[SOLVER JS] Lỗi trong sbc monitor:', e);
            }
        }, 1500);

        console.log('[SOLVER JS] Đã kích hoạt bộ giám sát giao diện solver.');
    }
};

// Khởi động bộ giám sát ngay khi script được inject
window.sbcSolveExtractor.startMonitoring();
