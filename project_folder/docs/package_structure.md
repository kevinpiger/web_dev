# 目前程式碼打包架構

依2026-09-06本機檔案整理。本次只盤點與整理交付結構，未建置映像、啟動服務、執行後端驗證或打包執行資料。

## 1. 打包定位

目前可交付的是「FastAPI後端原始碼＋資料庫Schema＋Docker設定＋規格文件」。不是完整已串接的解析平台：publisher、RabbitMQ啟用設定、worker與實際AI解析流程尚未完成，前端仍為獨立Demo。

建議分為三份交付：

| 交付內容 | 來源 | 用途 |
|---|---|---|
| 後端程式 | project_folder/ | 移植、開發與部署API |
| 需求／介接參考 | 最新TODO、web_slide_v3、v3_demo與工作台範例 | 移植時逐頁確認，不放進API執行映像 |
| 可重用skill | page-api-spec資料夾／ZIP | 後续產生Markdown＋Swagger風格HTML文件，與應用程式獨立 |

## 2. 後端程式目前實際結構

```text
project_folder/
├─ app/
│  ├─ main.py                 # FastAPI入口、CORS、錯誤處理、bootstrap
│  ├─ config.py               # 環境設定
│  ├─ router/                 # HTTP路由
│  │  ├─ auth.py              # 登入、refresh、logout、me
│  │  ├─ assets.py            # 檔案庫、上傳、原檔讀取、軟刪
│  │  ├─ tasks.py             # 主任務、精簡全量清單、detail
│  │  ├─ parse_items.py       # ROI新增、修改、讀取、軟刪
│  │  ├─ executions.py        # dispatch、執行查詢、單筆cancel
│  │  ├─ results.py           # JSON版本查詢、確認編輯追加
│  │  ├─ workbench.py         # 工作台整合、來源與artifact讀取
│  │  ├─ health.py            # /health
│  │  └─ users.py             # 空路由骨架，尚無端點
│  ├─ schemas/                # 請求與公開回應模型
│  ├─ services/               # 業務規則與交易
│  │  ├─ task_service.py
│  │  ├─ parse_item_service.py
│  │  ├─ execution_service.py
│  │  ├─ result_service.py
│  │  ├─ workbench_service.py
│  │  ├─ generated_result_service.py  # 未來worker的成果writer
│  │  └─ auth/asset/user等service
│  ├─ repositories/           # DB查詢與資料存取
│  ├─ models/                 # 10張表的ORM
│  ├─ db/
│  │  ├─ base.py / session.py
│  │  ├─ bootstrap.py
│  │  ├─ schema/
│  │  │  ├─ 01_iam/           # role、app_user
│  │  │  ├─ 02_core/          # asset、analysis_task、parse_item
│  │  │  │                    # execution、agent_run、result
│  │  │  └─ 03_runtime/       # outbox_event、inbox_event
│  │  └─ migrations/
│  │     └─ 20260906_workbench_json_contract.sql
│  ├─ core/                   # 認證依賴、security、enum、例外、logging
│  └─ utils/                  # Storage、PDF頁數、ROI、時間工具
├─ scripts/
│  └─ seed_dev_user.py        # 開發使用者建立工具
├─ docs/                     # API、Schema與Demo參考
├─ requirements.txt
├─ requirements-dev.txt
├─ Dockerfile
├─ docker-compose.yml
├─ .env.example
├─ .dockerignore
├─ .gitignore
└─ README.md
```

以上省略各層__init__.py；實際打包須保留，不依這份簡化目錄手動漏檔。

## 3. 執行時的分層

```text
HTTP /api/v1
   ↓
router：接收path/query/body、認證依賴、回應序列化
   ↓
service：權限、業務規則、狀態與交易
   ↓
repository → ORM → PostgreSQL
   └─ utils.storage → 原始檔／成果檔

派送分支：execution_service → execution＋outbox_event
                                      ↓
                          publisher → RabbitMQ → worker
                          └─ 尚未實作／串接，詳TODO
```

公開工作台API會將内部storage_key換成授權content URL；result_info.workbench保存在DB，但不直接放進公開ResultOut。人工確認內容存入result_info.content，另建版本。

## 4. 需要附上的最新文件

| 文件 | 建議交付位置 | 說明 |
|---|---|---|
| 根目錄TODO.md | 交付包docs/TODO.md | 包含最新publisher→worker六階段待辦；保留歷史但以最新決策為準 |
| 根目錄web_slide_v3.md／html | docs/ | 最新七頁API傳入傳出與31端點回應範例 |
| 根目錄v3_demo.html | docs/demo/ | 離線示範；PDF縮圖前端產生，尚未正式API介接 |
| docs/task_list_api_contract.md | docs/ | GET /tasks＝items包裝、七欄、無分頁 |
| docs/workbench_api_plan.md | docs/ | 工作台JSONB契約與API邊界 |
| docs/workbench_api_example.json | docs/ | 儲存與公開回應範例 |
| docs/ai_diagram_db_structure_flow_v1_freeze.md | docs/reference/ | 基底Schema歷史參考，需配合後續增補 |
| anaylisis_demo.html、test_31_result.html | docs/reference/，需要時附 | 工作台原始呈現參考，不是正式後端服務 |

注意：project_folder/docs內已有部分Demo／規格，但最新web_slide_v3與TODO位於上一層。單純壓縮project_folder會漏掉這兩份最新文件。後續打包時應複製進交付目錄，不必搬動原始檔。

v2示範HTML屬歷史資料，若附上需放reference並標明舊版，不當成v3實作依據。現有AGENTS.md開頭仍描述「沒有程式碼」，交付前應更新其過時目錄說明。

## 5. 執行環境目前包含什麼

| 項目 | 目前設定 |
|---|---|
| API映像 | Dockerfile：python:3.11-slim，uvicorn app.main:app，port8000 |
| DB | docker-compose：postgres:16-alpine |
| API與DB啟動 | Compose目前只有backend與db服務 |
| RabbitMQ | Compose中只有註解範例，尚未啟用 |
| Publisher／Worker | 沒有獨立入口、容器服務或完整工作程序 |
| DB持久化 | db_data volume |
| 原始檔／成果檔 | storage_data掛載/data/storage |
| Schema初始化 | API啟動依DB_AUTO_BOOTSTRAP決定是否執行bootstrap |

目前Dockerfile只COPY requirements.txt與app/，因此app/db/schema與migrations會隨app進映像，但scripts/seed_dev_user.py不在映像內。原始碼包可包含scripts；若移植時要在容器內執行seed，需另外決定複製或掛載方式。

requirements.txt目前未鎖版本；是否鎖定移植依賴版本應在交付前決定。本次未更動或安裝依賴。

## 6. 不要混入原始碼交付包

- 真實.env與憑證；交付.env.example，由接收環境建立自己的設定。
- .DS_Store（目前多個目錄內存在）、__pycache__、*.pyc、.venv、node_modules、工具快取與.git。
- DB volume／資料庫實際資料、使用者上傳原始檔、實際成果Storage；需要移轉時另做資料交付，不混在程式碼ZIP。
- 重複的v2/v3 HTML副本與此工作對話的scratch scripts。

## 7. 已編輯但尚未驗證的重要功能

- GET /tasks一次回傳目前使用者全部未刪除主任務；每項只有id/name/status/finished_count/started_at/updated_at/item_count。
- DRAFT ROI暫存，dispatch建立execution＋outbox；派送後禁止新增／修改ROI，允許軟刪子項並取消其執行。
- 單筆停止沿用cancel，不做resume；新execution建立入口尚待規劃。
- POST／PATCH共用已知PDF總頁數上限檢查。
- 工作台來源、artifact及整合讀取；人工JSON追加版本、清空舊衍生成果。
- 原始SQL與workbench手動migration已編輯，未套用實際DB；bootstrap不替既有庫更新全部CHECK約束。

## 8. 後續新增位置（規劃，非現有檔案）

publisher、worker、訊息契約與租約／重試機制應依TODO先定規格，再決定目錄、依賴與Compose服務。不要在交付清單中把這些尚不存在的模組標成完成。

本輪先整理以上架構與打包範圍；尚未產生完整後端ZIP。
