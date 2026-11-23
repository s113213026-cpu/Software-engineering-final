-- ========================================================
-- 管院空間與課程系統 - 全域資料庫結構 (schema.sql)
-- 涵蓋三模組共用需求：
-- 1. 共用帳號與權限審核 (users)
-- 2. 管院空間查詢模組 (rooms)
-- 3. 空間/物品預約借用模組 (bookings)
-- 4. 志願排課模組 (course_preferences)
-- ========================================================

-- 1. 使用者資料表 (共用登入、審核與角色控制)
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    name TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'user',        -- 'admin': 管理員, 'teacher': 教師, 'user': 學生/一般使用者
    status TEXT NOT NULL DEFAULT 'approved',  -- 'pending': 待審核, 'approved': 已核准, 'rejected': 駁回/停用
    email TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now', 'localtime'))
);

-- 2. 空間/教室資料表 (管院空間查詢模組核心，並供借用與排課模組關聯)
CREATE TABLE IF NOT EXISTS rooms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,                -- 教室代號，例如：管268、管115、A101
    name TEXT NOT NULL,                       -- 空間名稱，例如：階梯演講廳、個案研討室
    floor TEXT NOT NULL,                      -- 樓層，例如：1 樓、2 樓、3 樓
    capacity INTEGER NOT NULL DEFAULT 40,     -- 容納人數
    room_type TEXT NOT NULL DEFAULT '一般教室',-- 類型：一般教室、階梯教室、電腦教室、研討室、個案教室
    equipment TEXT DEFAULT '',                -- 設備清單 (投影機、麥克風、電腦數等)
    description TEXT DEFAULT '',              -- 詳細說明與借用規範
    image_url TEXT DEFAULT '',                -- 教室主要照片
    panorama_url TEXT DEFAULT '',             -- 360 全景照片路徑或 pannellum 配置
    floor_plan_x REAL DEFAULT 50.0,           -- 管院平面圖標記 X 座標百分比 (0-100)
    floor_plan_y REAL DEFAULT 50.0,           -- 管院平面圖標記 Y 座標百分比 (0-100)
    is_active INTEGER NOT NULL DEFAULT 1      -- 是否開放使用 (1: 開放, 0: 關閉維護)
);

-- 3. 空間與物品預約借用資料表 (空間/物品預約借用模組)
CREATE TABLE IF NOT EXISTS bookings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    room_id INTEGER NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,
    booking_date TEXT NOT NULL,               -- 借用日期 (YYYY-MM-DD)
    starts_at TEXT NOT NULL,                  -- 開始時段 (YYYY-MM-DD HH:MM)
    ends_at TEXT NOT NULL,                    -- 結束時段 (YYYY-MM-DD HH:MM)
    borrowed_items TEXT DEFAULT '',           -- 借用物品，逗號分隔 (如：鑰匙, 簡報筆, 筆電, 轉接頭)
    reason TEXT DEFAULT '',                   -- 借用目的/事由
    status TEXT NOT NULL DEFAULT '待審核',    -- '待審核', '已核准', '已退件', '已取消'
    review_comment TEXT DEFAULT '',           -- 管理員審核意見
    is_picked_up INTEGER NOT NULL DEFAULT 0,  -- 是否已領用物品/鑰匙 (0: 未領, 1: 已領)
    picked_up_at TEXT DEFAULT NULL,           -- 領用登記時間
    picked_up_by TEXT DEFAULT NULL,           -- 登記借出的管理員
    is_returned INTEGER NOT NULL DEFAULT 0,   -- 是否已歸還 (0: 未還, 1: 已還)
    returned_at TEXT DEFAULT NULL,            -- 歸還確認時間
    returned_by TEXT DEFAULT NULL,            -- 確認歸還的管理員
    created_at TEXT DEFAULT (datetime('now', 'localtime'))
);

-- 4. 志願排課與課程規劃資料表 (志願排課模組)
CREATE TABLE IF NOT EXISTS course_preferences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, -- 教師帳號
    room_id INTEGER REFERENCES rooms(id) ON DELETE SET NULL,         -- 志願/指派教室
    course_name TEXT NOT NULL,                                       -- 課程名稱
    course_code TEXT DEFAULT '',                                     -- 課程代碼
    day_of_week INTEGER NOT NULL DEFAULT 1,                          -- 星期 (1-7)
    starts_at TEXT NOT NULL,                                         -- 開始時段 (HH:MM 或 YYYY-MM-DD HH:MM)
    ends_at TEXT NOT NULL,                                           -- 結束時段 (HH:MM 或 YYYY-MM-DD HH:MM)
    status TEXT NOT NULL DEFAULT '待確認',                            -- '待確認', '已確認', '衝堂衝突'
    created_at TEXT DEFAULT (datetime('now', 'localtime'))
);

-- ========================================================
-- 初始化預設資料 (管院真實教室範本，參考暨大管院/國企系空間)
-- ========================================================
INSERT INTO rooms (code, name, floor, capacity, room_type, equipment, description, image_url, panorama_url, floor_plan_x, floor_plan_y) VALUES
    ('管268', '階梯演講廳', '2 樓', 120, '階梯教室', '雙槍投影機、無線麥克風2支、簡報筆、專業錄音設備、電子講桌', '管理學院大型階梯國際演講廳，適合舉辦學術研討會、專題演講及跨班大型課程。', '/static/images/rooms/r268.jpg', 'https://pannellum.org/images/cerro-toco-0.jpg', 65.5, 30.2),
    ('管115', '專業研討室', '1 樓', 45, '研討室', '單槍高畫質投影機、電動布幕、無線麥克風、白板、活動折合課桌椅', '適合各系所專題討論、研究所研討課程或小組會議，桌椅可彈性調整排法。', '/static/images/rooms/r115.jpg', 'https://pannellum.org/images/alma.jpg', 25.0, 42.0),
    ('管116', '個案研討室', '1 樓', 40, '研討室', '高階投影機、環繞音響、互動電子白板、分組圓桌', '管院特色個案教學空間，配備多向白板與分組討論設施。', '/static/images/rooms/r116.jpg', 'https://pannellum.org/images/bma-1.jpg', 38.0, 42.0),
    ('管218', '專業電腦教室', '2 樓', 65, '電腦教室', '雙投影幕、廣播教學系統、高效能學生電腦65台、教師主控台', '供統計軟體、大數據分析、程式設計與專業證照考試教學使用。', '/static/images/rooms/r218.jpg', 'https://pannellum.org/images/cerro-toco-0.jpg', 72.0, 60.5),
    ('管318', '碩士班研討教室', '3 樓', 35, '研討室', '單槍投影機、大型玻璃白板、多功能影音擴大機、會議型長桌', '提供研究所專題研究、論文口試及碩專班夜間課程專用。', '/static/images/rooms/r318.jpg', 'https://pannellum.org/images/alma.jpg', 50.0, 35.0),
    ('管418', '多功能個案討論室', '4 樓', 50, '個案教室', '雙投影機、U型弧形發言階梯桌椅、發言鵝頸麥克風', '標準哈佛式個案討論教室，階梯視角良好，適合高互動性教學。', '/static/images/rooms/r418.jpg', 'https://pannellum.org/images/bma-1.jpg', 45.0, 70.0),
    ('A101', '一般大教室', '1 樓', 80, '一般教室', '高流明投影機、固定課桌椅、雙無線麥克風', '管院基礎核心必修課程大班教室。', '/static/images/rooms/a101.jpg', 'https://pannellum.org/images/alma.jpg', 15.0, 20.0),
    ('A201', '多功能研討室', '2 樓', 30, '研討室', '液晶電視顯示器、白板、自由移動桌椅', '適合學生社團會議、學生專案討論及教師諮詢時間。', '/static/images/rooms/a201.jpg', 'https://pannellum.org/images/cerro-toco-0.jpg', 20.0, 75.0)
ON CONFLICT(code) DO NOTHING;
