# Backend Container 建置規格 — 目錄結構與第一批 API

> **真實程式碼一律放在 `project_folder/` 之下。**
> 本文件位於 `script/`，只是規格，不是程式碼；`project_folder/` 是可整包搬走的專案根，
> 搬到任何地方 `docker compose up` 就能跑，不依賴外層任何東西。

---

## 1. 用途與範圍

本文件是 AI 圖像解析平台 **backend container** 的建置規格。

系統由 docker 啟動多個 container（DB / backend / RabbitMQ / …），本規格**只涵蓋 backend**，
RabbitMQ 與 worker 留待後續階段。

規格來源：

| 文件 | 內容 |
|---|---|
| `ai_diagram_db_structure_flow_v1_freeze.md` | 10 張表的 v1 凍結 schema、型別慣例、PK/FK/ON DELETE、Enum、Index、遷移順序 |
| `image_analysis_platform_v2_demo.html` | 前端 9 步操作流程（登入 → 任務總覽 → 上傳 → 候選內容確認 → 編輯 ROI → 確認清單 → 執行解析 → 解析工作台 → 任務完成/匯出） |

**本階段實作範圍**：專案骨架 + `auth`（登入）與 `assets`（多檔上傳／清單／刪除）兩支子專案的完整 API。
其餘子專案（`users` / `tasks` / `parse_items` / `executions`）只建立 router 檔案並掛進
`api_router`，端點留空殼，下一階段再依 demo 流程逐一實作。

### 已定案的技術決策

| 項目 | 決策 |
|---|---|
| 專案根 | `project_folder/`，整包可移植；真實程式碼全放這底下 |
| 框架 | FastAPI（async） |
| 資料庫 | PostgreSQL + SQLAlchemy 2.0 async（asyncpg） |
| 套件管理 | pip + `requirements.txt` |
| 分層 | `router → service → repository`；`utils/` 降為純工具函式 |
| Schema 管理 | 不用 Alembic。`db/schema/` 一表一 `.sql`，啟動時檢查並補建 |
| 啟動檢查嚴格度 | 建缺少的表／欄位／索引，**不動既有**；型別差異只記 WARN |
| 認證 | JWT access token + refresh token 存 DB（`app_user.token`） |
| 檔案儲存 | 本機路徑，root 由 `.env` 的 `STORAGE_PATH` 指定 |
| 刪除語意 | 軟刪（寫 `deleted_at`），實體檔保留 |
| 多檔上傳失敗 | 逐檔獨立，回傳 `succeeded` / `failed` 兩組 |
| 解析類型 | 不存欄位，前端顯示「自動偵測」，實際類型從 `result_info.type` 讀 |

---

## 2. 目錄結構

```text
Datasheet_backend_dev/          # 工作區（不隨專案移植）
├── CLAUDE.md
├── memory.md
├── ai_diagram_db_structure_flow_v1_freeze.md   # 原始設計文件（暫留原位）
├── image_analysis_platform_v2_demo.html        # 原始設計文件（暫留原位）
├── script/
│   └── backend_structure_and_api.md    # ← 本文件
└── project_folder/             # ★ 專案根，真實程式碼全在這底下，整包可移植
    ├── .env                    # 實際值，不進版控
    ├── .env.example            # 變數範本（見 §4）
    ├── .gitignore
    ├── .dockerignore
    ├── README.md               # 啟動方式與環境變數說明
    ├── docker-compose.yml      # db + backend（rabbitmq 先註解留位）
    ├── Dockerfile
    ├── requirements.txt
    ├── requirements-dev.txt    # ruff / ipython 等，不進 production image
    ├── scripts/
    │   └── seed_dev_user.py    # 開發用種子：一筆 role + 兩筆 app_user
    ├── docs/
    │   ├── ai_diagram_db_structure_flow_v1_freeze.md   ← 從外層移入
    │   └── image_analysis_platform_v2_demo.html        ← 從外層移入
    └── app/
        ├── __init__.py
        ├── main.py             # FastAPI 實例、lifespan、掛 router / middleware / handler
        ├── config.py           # pydantic-settings，唯一讀 .env 的地方
        │
        ├── core/               # 跨子專案的基礎設施
        │   ├── enums.py        # 全部 status 枚舉，對照 freeze §23
        │   ├── security.py     # JWT 簽發/解碼、密碼雜湊
        │   ├── deps.py         # get_db / get_current_user / require_role
        │   ├── exceptions.py   # 自訂例外階層 + 全域 handler
        │   └── logging.py      # 結構化 JSON log 設定
        │
        ├── db/
        │   ├── session.py      # async engine / async_sessionmaker
        │   ├── base.py         # DeclarativeBase + TimestampMixin / SoftDeleteMixin
        │   ├── bootstrap.py    # ★ 啟動時的 schema 檢查與補建（見 §5）
        │   └── schema/         # ★ 一表一 .sql，依 freeze §28 遷移順序命名
        │       ├── 01_iam/
        │       │   ├── 01_role.sql
        │       │   └── 02_app_user.sql
        │       ├── 02_core/
        │       │   ├── 01_asset.sql
        │       │   ├── 02_analysis_task.sql
        │       │   ├── 03_parse_item.sql
        │       │   ├── 04_execution.sql
        │       │   ├── 05_agent_run.sql
        │       │   └── 06_result.sql
        │       └── 03_runtime/
        │           ├── 01_outbox_event.sql
        │           └── 02_inbox_event.sql
        │
        ├── models/             # SQLAlchemy ORM，一表一檔，檔名對應 schema/
        │   ├── role.py  app_user.py  asset.py  analysis_task.py
        │   ├── parse_item.py  execution.py  agent_run.py  result.py
        │   └── outbox_event.py  inbox_event.py
        │
        ├── schemas/            # Pydantic request/response，依子專案分檔
        │   ├── auth.py  user.py  asset.py  task.py
        │   ├── parse_item.py  execution.py  result.py
        │   └── common.py       # 分頁、統一錯誤格式、共用 response 外殼
        │
        ├── router/             # ★ 各子專案的 API 入口
        │   ├── __init__.py     # api_router：把下面全部 include 起來
        │   ├── health.py       # /health（Docker healthcheck 用）
        │   ├── auth.py         # ★ 本次實作            → demo step 1
        │   ├── assets.py       # ★ 本次實作            → demo step 3
        │   ├── users.py        # 空殼
        │   ├── tasks.py        # 空殼                  → demo step 2, 9
        │   ├── parse_items.py  # 空殼                  → demo step 4-6
        │   └── executions.py   # 空殼                  → demo step 7-8
        │
        ├── services/           # 商業邏輯，一子專案一檔，與 router 同名
        │   ├── auth_service.py   asset_service.py      # ★ 本次實作
        │   └── user_service.py   task_service.py
        │       parse_item_service.py  execution_service.py
        │
        ├── repositories/       # DB 查詢封裝，一表一檔
        │   ├── base.py         # 泛型 CRUD 基底
        │   └── {role,app_user,asset,analysis_task,parse_item,execution,…}_repository.py
        │
        └── utils/              # 純工具函式，不碰 DB、不含商業規則
            ├── storage.py      # 檔案讀寫，root = settings.STORAGE_PATH
            ├── pdf.py          # PDF 頁數、頁面轉圖（候選內容確認用）
            ├── roi.py          # normalized 座標驗證與換算（freeze §8 規則）
            └── datetime.py     # TZ 處理
```

### 結構上的取捨

- **用 `app/` 套件而非平鋪在 `project_folder/` 下**：`Dockerfile` 只要 `COPY app/ ./app/` 一行，
  import 路徑一律 `from app.core...`，不會跟同層的設定檔混淆。
- **`router/` 用單數**，底下**檔名用複數**對應資源集合。
- **`services/` 是重點**：RabbitMQ worker 之後要重用同一套邏輯。所有商業規則寫在這裡，
  router 只做 HTTP 與驗證，worker 直接呼叫 service，不必從 router 複製。
- **`utils/` 降為純工具**：不接 DB session、不含狀態機規則。判斷標準是
  「這個函式抽出來放到別的專案能不能直接用」。
- **兩份設計文件搬進 `project_folder/docs/`**：它們是 schema 與流程的規格來源，搬專案時要跟著走。

---

## 3. 對 freeze schema 的三處增補

demo 流程有三個需求在 v1 凍結 schema 裡無處可放。**其餘欄位完全照 freeze，不做任何更動。**

```sql
-- 1. iam.app_user
--    freeze §5 只有 token / token_expire_at，沒有存密碼的地方，
--    但 demo 有帳密登入表單。NULL 供日後 SSO-only 使用者。
password_hash VARCHAR(255)

-- 2. core.parse_item
--    demo 有「Page 4 - ROI 1」，PDF 多頁 ROI 需要頁碼定位，
--    但 freeze 明確「不建立 Page Table」且 parse_item 無頁碼欄位。
--    單張圖片一律存 1。不違反「不建立 Page Table」原則。
page_no INTEGER NOT NULL DEFAULT 1
CONSTRAINT parse_item_page_positive CHECK (page_no > 0)
CREATE INDEX idx_parse_item_asset_page ON core.parse_item(asset_id, page_no);

-- 3. core.execution
--    demo 有「確認此結果」與「已確認 5 / 需要確認 1」，但
--    result.status(PENDING/SUCCEEDED/FAILED) 表達的是 AI 該輪成敗，不是人工簽核。
review_status VARCHAR(20) NOT NULL DEFAULT 'PENDING'   -- PENDING / CONFIRMED / REJECTED
reviewed_by   UUID REFERENCES iam.app_user(id) ON DELETE SET NULL
reviewed_at   TIMESTAMPTZ
CREATE INDEX idx_execution_review ON core.execution(parse_id, review_status);
```

> **注意**：freeze §26/§27 提到的 `ai_diagram_db_structure_flow_v1_freeze.sql` 與
> `ai_diagram_db_structure_flow_v1_freeze.architecture.html` **在資料夾中不存在**，只有 `.md`。
> DDL 需依 freeze §22–§27 的規格自行寫出。

---

## 4. `.env` 變數清單

`.env.example` 內容（`.env` 由此複製後填實際值，不進版控）：

```bash
# --- App ---
APP_NAME=ai-diagram-backend
APP_ENV=development            # development | production
LOG_LEVEL=INFO
API_PREFIX=/api/v1
BACKEND_PORT=8000
CORS_ORIGINS=http://localhost:3000

# --- PostgreSQL ---
POSTGRES_HOST=db               # docker-compose 的服務名
POSTGRES_PORT=5432
POSTGRES_DB=ai_diagram
POSTGRES_USER=app
POSTGRES_PASSWORD=change-me
DB_POOL_SIZE=10
DB_MAX_OVERFLOW=20
DB_ECHO=false

# --- Schema 啟動檢查 ---
DB_AUTO_BOOTSTRAP=true         # production 可關掉改手動執行

# --- JWT ---
JWT_SECRET_KEY=change-me
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7

# --- 檔案儲存 ---
STORAGE_PATH=/data/storage     # container 內路徑，compose 掛 volume 進來
MAX_UPLOAD_SIZE_MB=200         # 對齊 demo「200MB 內」
ALLOWED_UPLOAD_EXTENSIONS=pdf,png,jpg,jpeg

# --- RabbitMQ（預留，本階段不使用）---
# RABBITMQ_HOST=rabbitmq
# RABBITMQ_PORT=5672
```

規則：

- `POSTGRES_*` 由 `Settings` 組成 `database_url` property，`docker-compose.yml` 的 db 服務
  直接共用同一組變數，不重複維護。
- **`app/config.py` 是唯一讀 `.env` 的地方**。其他模組一律 `from app.config import settings`，
  不允許任何地方直接讀 `os.environ`。

---

## 5. `db/schema/*.sql` 與 `db/bootstrap.py`

### schema 檔案規則

每個 `.sql` 是一張表的完整定義，**必須可重複執行**：

```sql
CREATE SCHEMA IF NOT EXISTS core;

CREATE TABLE IF NOT EXISTS core.parse_item ( ... );

CREATE INDEX IF NOT EXISTS idx_parse_item_task_id ON core.parse_item(task_id);
```

DDL 逐條依 freeze 撰寫：

| freeze 章節 | 內容 |
|---|---|
| §22 | PK / FK / `ON DELETE`（依附子項用 `CASCADE`，跨聚合擁有關係用 `RESTRICT`） |
| §23 | Enum 值域 |
| §24 | 索引，含 partial index |
| §27 | `CHECK` 約束（ROI 範圍、retry 上限、round_no > 0…） |
| §28 | 遷移順序 → 對應檔名前綴 |

**Enum 用 `VARCHAR` + `CHECK`，不用 PostgreSQL `ENUM` 型別**（避免日後加值要 `ALTER TYPE`）。

### bootstrap 流程

`bootstrap.run()` 由 `main.py` 的 lifespan 呼叫：

1. 依檔名排序讀取所有 `.sql`（`01_iam/01_role.sql` → … → `03_runtime/02_inbox_event.sql`）
2. 逐檔在 transaction 內執行——全部 `IF NOT EXISTS`，缺的補、有的跳過
3. 查 `information_schema.columns` 比對每張表的實際欄位：
   - 檔案有、DB 沒有 → `ALTER TABLE … ADD COLUMN`（§3 的三處增補靠這步落地）
   - DB 有、檔案沒有 → 只記 **WARN**，**不刪**
   - 兩邊都有但型別不同 → 只記 **WARN**，**不改**
4. 印出摘要 log：建了幾張表、加了幾個欄位、幾筆 WARN
5. `DB_AUTO_BOOTSTRAP=false` 時整段跳過，只做連線檢查

**要求：第二次啟動應為零變更、零 WARN（冪等）。**

---

## 6. API 規格 — auth（`router/auth.py`）

路徑前綴一律 `settings.API_PREFIX`（預設 `/api/v1`）。

| Method | Path | 說明 |
|---|---|---|
| POST | `/auth/login` | `{email, password}` → `{access_token, refresh_token, token_type, expires_in, user}` |
| POST | `/auth/refresh` | `{refresh_token}` → 新的 access + refresh（refresh 輪替） |
| POST | `/auth/logout` | 清掉 `app_user.token`，使 refresh 立即失效 |
| GET | `/auth/me` | 回傳目前登入者（含 role code） |

### 實作要點

- **access token** 為無狀態 JWT：`sub` = user id、`role` = role code、`exp`。驗證不查 DB。
- **refresh token** 雜湊後存 `app_user.token`，到期時間寫 `token_expire_at`；
  `logout` 清空該欄位；`refresh` 時**輪替**（發新的並覆寫，舊的立即失效）。
- 登入成功更新 `last_login_at`。
- **帳號不存在 / 密碼錯誤 / `is_active = false` → 一律 401 且訊息一致**，
  不洩漏帳號是否存在。
- `core/deps.py` 的 `get_current_user`：解 JWT → 查 `app_user` → 檢查 `is_active`。

### 回應範例

```json
// POST /api/v1/auth/login
{
  "access_token": "eyJhbGciOi...",
  "refresh_token": "eyJhbGciOi...",
  "token_type": "bearer",
  "expires_in": 1800,
  "user": {
    "id": "uuid",
    "username": "kevin",
    "email": "kevin@example.com",
    "employee_no": "A12345",
    "organization": "RD",
    "role": "USER"
  }
}
```

---

## 7. API 規格 — assets（`router/assets.py`）

| Method | Path | 說明 |
|---|---|---|
| POST | `/assets` | **多檔上傳**（multipart，`files: list[UploadFile]`） |
| GET | `/assets` | 目前登入者的檔案清單（分頁，可依 `file_type` / `status` 過濾） |
| GET | `/assets/{asset_id}` | 單筆詳情 |
| GET | `/assets/{asset_id}/content` | 下載原始檔（`FileResponse`） |
| DELETE | `/assets/{asset_id}` | 軟刪除 |

### 7.1 上傳 — `POST /assets`

**逐檔獨立處理，一檔失敗不影響其他檔。** 每個檔案依序：

1. 驗副檔名（`ALLOWED_UPLOAD_EXTENSIONS`）與大小（`MAX_UPLOAD_SIZE_MB`）
2. 先 INSERT 一筆 `status='UPLOADING'` 取得 `asset_id`
3. **串流**寫入 `{STORAGE_PATH}/assets/{user_id}/{asset_id}/{safe_filename}`
   （不整份讀進記憶體）
4. 成功 → 更新 `status='READY'` 與實際 `file_size`
   失敗 → 更新 `status='FAILED'` 並**清掉半成品檔案**

回應**恆為 200**，逐檔標示結果：

```json
{
  "succeeded": [
    {
      "id": "uuid",
      "file_name": "datasheet.pdf",
      "file_type": "PDF",
      "mime_type": "application/pdf",
      "file_size": 2516582,
      "status": "READY",
      "attributes": { "page_count": 12 },
      "created_at": "2026-09-06T10:32:00+08:00"
    }
  ],
  "failed": [
    { "file_name": "big.pdf",   "error_code": "FILE_TOO_LARGE",        "message": "檔案超過 200MB" },
    { "file_name": "setup.exe", "error_code": "UNSUPPORTED_EXTENSION", "message": "不支援的副檔名" }
  ]
}
```

### 7.2 欄位對應（freeze §6 / §23）

| 欄位 | 值 |
|---|---|
| `user_id` | 登入者 |
| `storage_type` | 固定 `LOCAL` |
| `storage_key` | **相對於 `STORAGE_PATH` 的相對路徑**（換儲存後端時不用改資料） |
| `file_type` | 由副檔名映射 `PDF` / `IMAGE` / `SVG` / `OTHER` |
| `mime_type` | 取自 `UploadFile.content_type` |
| `file_size` | 實際落地後的位元組數 |
| `status` | `UPLOADING` → `READY` / `FAILED` |
| `attributes` | PDF 存 `{"page_count": 12}`，之後 demo step 3「候選內容確認」要用 |

### 7.3 `utils/storage.py`

提供四個函式，全部以 `settings.STORAGE_PATH` 為 root：

| 函式 | 說明 |
|---|---|
| `save_stream(rel_path, upload_file)` | 串流寫檔，回傳實際位元組數 |
| `open(rel_path)` | 開檔供下載 |
| `delete(rel_path)` | 刪實體檔（上傳失敗清半成品用；正常刪除**不呼叫**） |
| `resolve(rel_path)` | 相對路徑 → 絕對路徑 |

**必須擋 path traversal**：檔名 sanitize（去掉路徑分隔符與 `..`）+ 解析後確認結果仍在 root 內。

### 7.4 清單 — `GET /assets`

只回 `user_id = 當前使用者` 且 `deleted_at IS NULL`，走 freeze §24 的 `idx_asset_active`
partial index。支援 `page` / `page_size` 分頁與 `file_type` / `status` 過濾。

```json
{
  "items": [ /* asset 物件 */ ],
  "total": 24,
  "page": 1,
  "page_size": 20
}
```

### 7.5 刪除 — `DELETE /assets/{asset_id}`

- 只寫 `deleted_at = now()`，**不刪磁碟檔案**——可還原、可稽核，
  也不影響已解析過的 `parse_item` 引用（`parse_item.asset_id` 是 `RESTRICT`）。
- 重複刪除視為**冪等**，回 204。
- 磁碟清理之後另寫排程處理，不在本階段。

### 7.6 權限

本階段所有 asset 端點以「**只能存取自己的檔案**」為界（比對 `user_id`）。

**非本人擁有的 asset 一律回 404**（不用 403，不洩漏他人資源是否存在）。
`ADMIN` 的跨使用者視角等 `users` 子專案再處理。

---

## 8. 依賴清單

`requirements.txt` 至少需要：

```text
fastapi
uvicorn[standard]
pydantic-settings
sqlalchemy[asyncio]
asyncpg
python-jose[cryptography]     # JWT
passlib[bcrypt]               # 密碼雜湊
python-multipart              # multipart 上傳
pypdf                         # PDF 頁數
```

`requirements-dev.txt`（不進 production image）：`ruff`、`ipython` 等。

---

## 9. 驗收清單

實作完成後照這份逐項驗（本階段只寫規格，不執行）：

**bootstrap 與環境**

- [ ] 10 張表全建、0 WARN
- [ ] 重啟後零變更、零 WARN（冪等）
- [ ] §3 三處增補欄位在 `\d` 中可見
- [ ] `/health` 回 200 且含 DB 連線狀態
- [ ] `STORAGE_PATH` 目錄存在且可寫

**auth**

- [ ] 登入成功拿到 access + refresh token
- [ ] 錯密碼／不存在帳號／`is_active=false` 三者回應**訊息一致**（皆 401）
- [ ] `/auth/me` 帶 token 200、不帶 401、竄改一個字元的 token 401
- [ ] refresh 輪替：拿舊的 refresh 再打一次回 401
- [ ] logout 後該 refresh token 再打回 401

**assets**

- [ ] 多檔上傳 3 檔全成功，磁碟檔案大小與回應 `file_size` 一致
- [ ] 混合上傳（正常檔 + `.exe` + 超大檔）→ `succeeded` 1 / `failed` 2，
      `error_code` 分別對應副檔名與大小，磁碟**無殘留**
- [ ] PDF 的 `attributes.page_count` 與實際頁數相符
- [ ] 清單只回自己的檔案；第二個使用者看到 0 筆
- [ ] 下載回來的檔案 `md5` 與原檔相同
- [ ] 刪除後清單少一筆、DB `deleted_at` 有值、**磁碟檔案仍在**、重複刪除回 204
- [ ] 跨使用者的 `GET` / `GET content` / `DELETE` 全部回 **404**
- [ ] 上傳檔名 `../../etc/passwd` 不會寫到 `STORAGE_PATH` 之外

---

## 10. 後續階段（不在本規格範圍）

1. 依 demo step 2、4–9 實作其餘子專案（`users` / `tasks` / `parse_items` / `executions`）
2. `runtime.outbox_event` 的 publisher 與 RabbitMQ container
3. worker container（消費 → 寫 `inbox_event` → 跑 agent → 寫 `result`）
4. 匯出功能（Mermaid / WaveDrom / PNG / HTML / ZIP）
5. SSO 接入（demo 有按鈕，第一版只做帳密登入）
