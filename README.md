# 管院空間與課程｜學期專案骨架

三個模組放在同一個 Git 儲存庫，各組員分別開發自己的模組，共用登入與 SQLite 資料庫。全組使用 Python 3.10+（建議 Python 3.14.7）和 Flask 3.1.3，套件完整版本清單在 `requirements.txt`。

## 本機快速啟動

在專案目錄下執行以下指令：

```bash
python start.py
```

* Windows 亦可直接雙擊 `start.bat`。
* 啟動程式會自動建立 `.venv` 虛擬環境，並依 `requirements.txt` 安裝相依套件。
* 啟動完成後，在瀏覽器打開：`http://127.0.0.1:5000/`

### 內建測試帳號（各組員開發與測試直接使用）

| 身分 | 帳號 | 密碼 | 具備權限 / 適用功能 |
| --- | --- | --- | --- |
| **系統管理員** | `admin` | `admin1234` | 審核帳號、教室增刪修改、借用審核與物品領還註記、課表衝突調度 |
| **專任教師** | `teacher` | `teacher1234` | 填報與管理自己的排課志願 |
| **一般使用者/學生** | `demo` | `demo1234` | 查詢教室、登記借用教室與物品 |

亦支援前台自行註冊（需管理員至「帳號審核」頁面點擊通過）。

---

## 模組分工與責任邊界

| 模組名稱 | 負責人 | 程式入口 | 畫面範本 | 說明 |
| --- | --- | --- | --- | --- |
| **管院空間查詢模組** | 組員 A | `modules/spaces.py` | `templates/spaces.html` | 免登入瀏覽空間、360 全景瀏覽 (Pannellum)、管院平面圖標示、管理員教室 CRUD |
| **空間/物品預約借用模組** | 組員 B | `modules/bookings.py` | `templates/bookings.html` | 登入借用登記 (空間+多項物品)、週日曆狀況檢視、管理員審核與領用歸還註記 |
| **志願排課模組** | 組員 C | `modules/scheduling.py` | `templates/scheduling.html` | 教師志願登記、清單管理、管理員排課日曆檢視、衝突清單、拖曳調課 |

---

## 共用架構與開發規範

1. **權限控管 (`auth.py`)**：
   - `@login_required`：需登入頁面（未登入導向 `/login`）。
   - `@admin_required`：僅限管理員存取。
   - `@teacher_required`：僅限教師或管理員存取。
   - 取得當前使用者資訊：`g.user["id"]`, `g.user["username"]`, `g.user["name"]`, `g.user["role"]`。
2. **資料庫存取 (`db.get_db()`)**：
   - 資料庫定義於 `schema.sql`，第一次啟動會在 `instance/portal.sqlite3` 自動建表並注入真實教室與測試帳號。
   - `bookings` 表已有 `borrowed_items`, `reason`, `review_comment`, `is_picked_up`, `is_returned` 等完整欄位。
   - `course_preferences` 表已有 `day_of_week`, `starts_at`, `ends_at`, `status` 等完整欄位。
3. **時段格式統一**：
   - 日期：`YYYY-MM-DD`
   - 時間：`YYYY-MM-DD HH:MM`（或排課之每日時段 `HH:MM`）。

---

## Git 協同開發與 Commit 規範（助教評分重點）

1. **分支規範**：請勿直接往 `main` 分支 push！
   - 空間查詢：`feature/spaces-query`
   - 預約借用：`feature/spaces-booking`
   - 志願排課：`feature/course-scheduling`
2. **Commit 訊息格式**：
   - `feat(模組): 新增功能說明`
   - `fix(模組): 修復問題說明`
   - `docs: 更新文檔說明`
3. 完成階段性功能後推送到 GitHub，並開立 **Pull Request (PR)** 經組員審核後合併至 `main`。
