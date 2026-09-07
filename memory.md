# 專案操作記錄

- 建立日期：2026-09-06
- 專案路徑：/Users/kevinpiger/Desktop/Datasheet_backend_dev

---

## 操作紀錄

| 日期 | 操作類型 | 說明 | 備註 |
|------|----------|------|------|
| 2026-09-06 | 任務檢視與結果編輯 | 依 `test_31_result.html` 的資料結構實作：`GET /tasks`（加 `display_status` 等待/執行中/錯誤/完成/已中斷，即時聚合）、`GET /tasks/{id}/detail`（主任務下所有子任務 + 最新執行 + 最終解析程式）、`PATCH /tasks/{id}` 放寬為名稱／備註隨時可改（`config` 派送後凍結）、`GET/POST /parse-items/{id}/results`（編輯後 append 一筆 `core.result` round，不覆蓋）、`DELETE /parse-items/{id}` 改為軟刪 | **修掉 bootstrap 真 bug**：欄位上方有 `--` 註解時，欄位會被 column diff 漏掉，導致 `password_hash`／`page_no`／`review_status` 三處增補欄位在既有 DB 永遠不會被 ALTER 補上；已加註解剝除並用真檔案驗證 10 張表全數解析正確。新增第 4 處 schema 增補 `parse_item.deleted_at`（硬刪會 CASCADE 清掉 execution/result 稽核軌跡） |
| 2026-09-06 | 建置任務流程 | 實作 demo step 2/4-7：`tasks`（建立/清單/詳情/更新/**中斷**/**軟刪除**，進度即時聚合）、`parse_items`（ROI 匡選批次建立、清單、修改、刪除，派送後凍結）、`executions`（**送出任務** dispatch → 同一 transaction 寫 execution + outbox event、執行清單、單筆中斷）。Python 目標版本改為 3.11（Dockerfile `python:3.11-slim`） | 派送邊界止於 `runtime.outbox_event`（PENDING），不接 RabbitMQ；中斷會把未送出的 outbox 標 `FAILED`+`EXECUTION_CANCELLED`。本機只有 Python 3.9 無法 import 驗證，改用自製 AST 檢查（跨模組符號解析 64 模組全過 + unused import）與 SQLAlchemy 行為實測 |
| 2026-09-06 | 建置骨架 | 依 `script/backend_structure_and_api.md` 建立 `project_folder/` 完整目錄結構，實作 `auth`（login/refresh/logout/me）與 `assets`（多檔上傳/清單/詳情/下載/軟刪）完整 API，其餘子專案（users/tasks/parse_items/executions）僅掛 router 空殼；10 張表 schema `.sql`（含 §3 三處增補欄位）與 `db/bootstrap.py` 啟動檢查邏輯已寫好 | 未啟動程式、未接 DB/docker；本機僅有 Python 3.9，無法本地 import 驗證（程式碼採 3.10+ 語法，對應 Dockerfile 的 python:3.12-slim），已用 `py_compile` 過語法關 |
| 2026-09-06 | 03A 暫存流程 | 新建 ROI 改 DRAFT，任務維持 DRAFT；派送同交易將 DRAFT 轉 READY 並寫 execution/outbox；項目計數包含 DRAFT + READY；同步 SQL/ORM 預設與 README，兩份 demo 標註新版流程 | 67 模組語法與 import 符號、10 表 bootstrap 欄位解析通過；未跑 DB/API 整合測試；對照表原 URL 重新發布待補 |
| 2026-09-06 | 工作台與 schema 編輯 | v3 匯入 test_31–39，分離 render / verification / JSON 版本；新增 workbench、來源與 artifact API；人工版本失效衍生資料；JSONB 契約及手動 migration | 使用者要求：不驗證後端、不啟動、不套用 migration；HTML 未串接 DB，後續再討論 |

| 2026-09-06 | API 編輯 | GET /tasks 精簡為 items 包裝的全量主任務清單；七欄含 finished_count，移除分頁，後端彙整狀態與時間 | 同步 README/TODO/API契約；未執行後端驗證 |

| 2026-09-06 | 文件整理 | web_slide_v3.md依01/02/03/03A/07/08/09逐頁保存，完整列出API傳入傳出、巢狀型別、DB對應與缺口 | 同步outputs副本；記錄派送後DELETE與PATCH頁碼檢查差異；未執行後端驗證 |

| 2026-09-06 | 後端修正／決策 | POST及PATCH解析項目共用PDF頁碼上限檢查；單筆停止沿用cancel、不做resume | 更新web_slide_v3.md；新execution建立端點尚未新增；未執行後端驗證 |

| 2026-09-06 | HTML／可重用skill | web_slide_v3.md轉為單檔離線HTML，附章節搜尋、程式碼複製、Markdown下載與列印；建立page-api-spec skill及可攜轉換器 | 測試轉換器與文件內容，未執行後端驗證；skill提供ZIP |

| 2026-09-06 | 文件呈現 | web_slide_v3.html各頁API清單下加入Swagger風格可展開傳入、傳出與Schema；保留01至09原結構與Markdown內容 | 更新共用skill ZIP；只檢查文件轉換器，未執行後端驗證 |

| 2026-09-06 | API文件 | 補上31端點明確回應結構，50個逐頁API區塊各嵌入對應範例；區分JSON/204/binary，工作台包含未驗證與有衍生成果兩種示例 | 更新MD/HTML及共用skill；只做文件檢查，未改後端 |

| 2026-09-06 | 待辦規劃 | TODO.md新增Publisher→RabbitMQ→Worker六階段待辦、取消／去重／租約／重試／提交與ACK及恢復情境；確認派送後允許刪除子項 | 保留原TODO紀錄；前端與真實解析移植延後；未實作或驗證後端 |

| 2026-09-06 | 打包架構整理 | docs/package_structure.md盤點目前後端分層、SQL、Docker、交付文件與排除項；標示publisher/worker未完成 | 僅整理架構，未建置或產生後端ZIP，未驗證後端 |

| 2026-09-06 | 操作畫面與重編 | web_slide_v3各頁補10個由v3實際render函式輸出的靜態HTML畫面，02/08含分頁；更新Markdown、重編HTML與skill | 非瀏覽器截圖，無腳本sandbox嵌入；保留50個API細節；未驗證後端 |

| 2026-09-06 | 沙盒 Agent API | 定義 Worker/Agent 獨立憑證、execution attempt、租約、去重及取消規則，新增 internal routers、service、ORM 與 DDL，更新 Todo 與規格 | 僅編輯；未啟動／驗證後端或套用 DDL；Queue runtime 尚待實作 |
