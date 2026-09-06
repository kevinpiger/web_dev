# AI Diagram Backend

FastAPI (async) backend for the AI diagram parsing platform. Self-contained under
this folder — copy `project_folder/` anywhere and `docker compose up` will run it.

## 啟動方式

```bash
cp .env.example .env   # 依需要修改 JWT_SECRET_KEY / POSTGRES_PASSWORD 等
docker compose up --build
```

- `db`：PostgreSQL 16
- `backend`：FastAPI，啟動時依 `app/db/schema/*.sql` 自動檢查並補建 schema
  （`DB_AUTO_BOOTSTRAP=false` 可關閉，改手動執行）

啟動後：

- API：`http://localhost:${BACKEND_PORT:-8000}${API_PREFIX:-/api/v1}`
- Health check：`GET /health`

## 本機開發（不用 docker）

```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
uvicorn app.main:app --reload
```

需要本機有一個可連線的 PostgreSQL，並在 `.env` 填對應的 `POSTGRES_*`。

## 環境變數

見 `.env.example`，唯一讀取這些變數的模組是 `app/config.py`
（`Settings`，pydantic-settings）。

## 種子資料

```bash
python -m scripts.seed_dev_user
```

建立一筆 `role`（`ADMIN`）與兩筆 `app_user`（`admin@example.com` / `user@example.com`，
密碼皆為 `Passw0rd!`），供本機測試登入用。

## 目錄結構

```text
app/
├── main.py           FastAPI 實例、lifespan、掛 router
├── config.py          Settings（唯一讀 .env 的地方）
├── core/               JWT、密碼雜湊、依賴注入、例外處理、log 設定
├── db/                 async engine、ORM base、啟動時 schema bootstrap
│   └── schema/         一表一 .sql，依遷移順序命名，皆可重複執行
├── models/             SQLAlchemy ORM，一表一檔
├── schemas/            Pydantic request/response
├── router/             FastAPI router，一子專案一檔
├── services/           商業邏輯（worker 之後會重用）
├── repositories/       DB 查詢封裝，一表一檔
└── utils/              純工具函式（storage / pdf / roi / datetime）
```

## 目前已完整實作

路徑皆以 `API_PREFIX`（預設 `/api/v1`）為前綴。

### auth

| Method | Path | 說明 |
|---|---|---|
| POST | `/auth/login` | 帳密登入，回 access + refresh token |
| POST | `/auth/refresh` | refresh 輪替 |
| POST | `/auth/logout` | 清掉 refresh token |
| GET | `/auth/me` | 目前登入者 |

### assets（步驟 03：單純上傳）

| Method | Path | 說明 |
|---|---|---|
| POST | `/assets` | 多檔上傳，逐檔獨立成敗 |
| GET | `/assets` | 自己的檔案清單（分頁 / 過濾） |
| GET | `/assets/{id}` | 詳情 |
| GET | `/assets/{id}/content` | 下載原始檔 |
| DELETE | `/assets/{id}` | 軟刪除 |

### tasks（demo step 2、9）

| Method | Path | 說明 |
|---|---|---|
| POST | `/tasks` | 建立任務（status = `DRAFT`） |
| GET | `/tasks` | **該員所有任務**：名稱、`display_status`、進度，分頁 |
| GET | `/tasks/{id}` | 單筆（同上欄位） |
| GET | `/tasks/{id}/detail` | **主任務下所有子任務細節**（ROI + 最新執行 + 最終解析程式） |
| PATCH | `/tasks/{id}` | 編輯**任務名稱**與**任務整體備註**（`description`），任何狀態皆可 |
| POST | `/tasks/{id}/cancel` | **中斷**：連同未結束的 execution 一起取消 |
| DELETE | `/tasks/{id}` | **軟刪除**（進行中的任務要先中斷） |

`display_status` 是即時算出來的（不存欄位），對應畫面上的四種狀態：

| 值 | 畫面 | 判定 |
|---|---|---|
| `PENDING` | 等待 | 尚未派送，或已派送但還沒有任何一筆開始 |
| `RUNNING` | 執行中 | 有 execution 在跑，或部分已完成但尚未全部結束 |
| `FAILED` | 錯誤 | 全部結束且至少一筆失敗／逾時 |
| `COMPLETED` | 完成 | 全部結束且沒有失敗 |
| `CANCELLED` | 已中斷 | 任務被中斷 |

因為 freeze §7 不存進度欄位，判定以 execution 的即時聚合為準，
`analysis_task.status` 落後時不影響顯示。

`PATCH` 只有 `config` 受限：它在派送當下已被 snapshot 進每一筆 execution，
之後再改就會描述一次「從未發生的執行」，所以派送後改 `config` 會回 409
`TASK_CONFIG_FROZEN`；名稱與備註不受限制。

### parse_items — ROI 匡選與暫存（步驟 03A）

| Method | Path | 說明 |
|---|---|---|
| POST | `/tasks/{id}/parse-items` | 批次建立 ROI（`DRAFT` 暫存）；任務維持 `DRAFT` |
| GET | `/tasks/{id}/parse-items` | 確認解析清單（含來源檔名） |
| GET | `/parse-items/{id}` | 單筆 |
| PATCH | `/parse-items/{id}` | 調整 ROI / 名稱 / 狀態（派送前） |
| DELETE | `/parse-items/{id}` | **刪除子任務**（軟刪，任何狀態皆可） |

03 僅上傳檔案；03A 新增任務時挑選既有檔案（`GET /assets?status=READY`）、
上傳新檔，並當場匡選命名。原 04 候選內容確認步驟已移除，由 03A 取代。
暫存沿用批次新增、逐筆 PATCH / DELETE，下次可讀取任務詳情繼續編輯。

`parse_item.status`：`DRAFT` 表示編輯期暫存、`READY` 表示可送出解析、
`REJECTED` 表示排除解析。項目數包含未軟刪的 `DRAFT` 與 `READY`。
派送時排除 `REJECTED` 與軟刪項目，將所有暫存項目轉成 `READY`，
與 execution、outbox 一起提交；任務轉為 `DISPATCHED`，不支援增量派送。
PDF 頁面底圖與 ROI 裁切圖留待後續實作。

ROI 用 normalized 座標。`整張解析` 省略 `x/y/width/height` 即可（預設為整頁），
`選擇區域` 帶入實際座標，`不解析此頁` 就不要送該頁的項目。
任務一旦派送，解析清單即凍結（回 409 `PARSE_LIST_FROZEN`）。

### executions — 送出任務（demo step 7）

| Method | Path | 說明 |
|---|---|---|
| POST | `/tasks/{id}/dispatch` | **送出任務**：將 `DRAFT` 項目轉為 `READY`，為所有可派送項目建立 execution 與 outbox event |
| GET | `/executions` | 執行清單（可依 `task_id` / `parse_id` / `status` 過濾） |
| GET | `/executions/{id}` | 單筆 |
| POST | `/executions/{id}/cancel` | 中斷單筆執行 |

### 派送邊界

`dispatch` 在**同一個 transaction** 內寫入 `core.execution`（`status = CREATED`）與
`runtime.outbox_event`（`status = PENDING`），到此為止——本階段沒有 RabbitMQ，
之後的 publisher 才會把 outbox 事件送進 queue 並把 execution 推進 `QUEUED`。
這就是 freeze §12 的 transactional outbox：DB commit 成功就不會漏送。

中斷時，還沒送出的 outbox event 會被標成 `FAILED` + `last_error=EXECUTION_CANCELLED`
（凍結的 enum 沒有 `CANCELLED`），確保它不會再被 publisher 撿走。
已經在跑的 execution 只會在 DB 標成 `CANCELLED`，worker 需自行在寫回結果前檢查狀態。

### results — 最終解析程式（demo step 8）

| Method | Path | 說明 |
|---|---|---|
| GET | `/parse-items/{id}/results` | 版本演進：該子任務最新一次執行的每一輪，由舊到新 |
| POST | `/parse-items/{id}/results` | **編輯後存檔**：append 一筆新的 round，不覆蓋 |

`test_31_result.html` 的 `v01 / v02 / 最終` 三個版本各帶一則備註，對應
`core.result` 的三筆 round。所以編輯採 **append-only**：

```jsonc
POST /parse-items/{id}/results
{
  "content": "{ \"signal\": [ ... ] }",   // 修改後的 wavedrom JSON
  "content_type": "WAVEDROM",             // 省略則沿用上一輪
  "type": "TIMING",                       // 省略則沿用上一輪
  "note": "修正 adr_o：刪除 gap 後多出的一個 '.'"
}
```

存進 `core.result`：`round_no = max + 1`、`status = SUCCEEDED`，
`result_info` 內另記 `source: "MANUAL"`、`note`、`edited_by`、`edited_at`，
所以人改的跟 AI 產的分得出來，歷史也不會被蓋掉。
`round_no` 在 execution 內唯一，append 前會先鎖住 execution 該列，避免兩個並行存檔撞號。

### 尚未實作

`users` 子專案、解析結果的人工簽核（`execution.review_status`）、
outbox publisher 與 RabbitMQ、worker、匯出功能。

## 對 freeze schema 的增補

`script/backend_structure_and_api.md` §3 已列三處（`app_user.password_hash`、
`parse_item.page_no`、`execution.review_status`／`reviewed_by`／`reviewed_at`）。
本階段再加第四處：

```sql
-- core.parse_item：刪除子任務用軟刪
deleted_at TIMESTAMPTZ
CREATE INDEX idx_parse_item_active ON core.parse_item(task_id) WHERE deleted_at IS NULL;
```

理由：`execution.parse_id` 是 `ON DELETE CASCADE`，硬刪 parse_item 會連帶清掉
`execution` / `result` / `agent_run`，跟 freeze §22「execution 保留作稽核／Retry 依據、
正常運作下不會被硬刪除」直接衝突。軟刪也跟 `asset` / `analysis_task` 的既有語意一致。
欄位由啟動時的 bootstrap 自動 `ALTER TABLE ADD COLUMN` 補上。

第五處增補：`parse_item.status` 新增 `DRAFT`，SQL 與 ORM 預設皆改為 `DRAFT`。
這是編輯期狀態，執行狀態仍由 Execution 管理。
**bootstrap 不會修改既有 CHECK 約束或既有欄位的預設值**；新版 SQL 的約束與預設
只在新建表時生效。既有資料庫需另行遷移後，才能寫入 `DRAFT`。

## 解析工作台（本次編輯，未驗證）

工作台新增 `GET /parse-items/{id}/workbench`、
`GET /parse-items/{id}/source/content`、
`GET /results/{result_id}/artifacts/{artifact_id}/content`。
`POST /parse-items/{id}/results` 支援 `execution_id` / `base_result_id`，
人工新版清空衍生渲染、驗證與 Verilog。

完整資料對應、API 參數、JSONB 結構與待討論事項見
[工作台 API 與 Schema 設計](docs/workbench_api_plan.md)，
[JSON 範例](docs/workbench_api_example.json)，
[本機 v3 Demo](docs/v3_demo.html)。

維持十張表，擴充 `result_info.workbench` 的 JSON 契約。
新建 DB 有 object CHECK；既有 DB 另附手動 migration
`app/db/migrations/20260906_workbench_json_contract.sql`，bootstrap 不會執行它。
本次依要求未跑後端驗證、未啟動服務、未執行 migration。


## 主任務總覽 API 精簡（2026-09-06）

GET /api/v1/tasks 改為 {"items": [...]}，一次回傳目前使用者全部未刪除主任務，不分頁、不篩選。每項只回 id、name、status、finished_count、started_at、updated_at、item_count。finished_count 包含成功／失敗／逾時／取消，百分比與全域統計由前端計算。清單的 updated_at 納入子項目、執行與結果變動。詳細契約見 docs/task_list_api_contract.md；GET /tasks/{task_id}/detail 不變。這是取代舊 Page[TaskOut] 的回應契約，前端需同步調整；本次未執行後端驗證。
