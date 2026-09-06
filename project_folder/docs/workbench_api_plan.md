# 解析工作台：畫面、API 與 Schema 設計草案

依據：`anaylisis_demo.html`、v3 demo、現有 FastAPI 程式與 v1 freeze schema。

本次已編輯後端檔案，**未執行後端驗證、未啟動服務、未執行 migration，也未將參考資料匯入資料庫**。HTML 仍使用本機示範資料，沒有串接實體後端。以下為本次設計，可再討論修改。

## 1. 畫面與資料對應

| 畫面 | 資料來源 | 語意 |
|---|---|---|
| 主任務名稱 | `core.analysis_task.name` | 工作台的上層任務 |
| 上方 test_XX 分頁 | `core.parse_item.id/name` | 同一主任務下的解析項目；用 UUID 選取，不能解析名稱取得 ID |
| 來源檔案／頁碼／ROI | `parse_item.asset_id/page_no/x/y/width/height` | 同一 PDF 不同頁的 ROI 不得混用 |
| 執行狀態 | `core.execution.status` | CREATED / QUEUED / RUNNING / SUCCEEDED / FAILED / TIMEOUT / CANCELLED |
| JSON 結果版本 | `core.result.id/round_no/result_info.content` | 每次持久化的內容版本，包括 AI 產生與人工修改；append-only |
| 渲染版本 v01/v02/最終 | `result_info.workbench.render_versions[]` | 圖片版本；有對應 JSON 時帶 `result_id`，未知則 null |
| TRUE / PARTIAL / FALSE | `workbench.verification.match` | 比對結果，不是執行狀態，也不是人工簽核 |
| 驗證第 N 輪 | `workbench.verification.rounds[]` | 原始比對紀錄；可指向 input_result_id，未知則 null |
| Verilog Testbench | `workbench.conversion.kind=TESTBENCH` | 時序重現程式及 Per-Lane 指標 |
| Verilog 欄位定義 | `workbench.conversion.kind=REGISTER_DEFINITION` | 欄位定義程式及 Per-Reg 指標 |

`test_31` 有三張渲染圖、兩輪驗證；`test_32` 有四張渲染圖、兩輪驗證。不能把圖片數、驗證輪數和 `result.round_no` 視為同一序列。

參考報告只提供最終 JSON，因此 HTML 每個 test 匯入一個最終內容版本，另外保存所有歷史渲染圖；未偽造早期 JSON。歷史縮圖切換不會偷偷替換下方 JSON。

`test_33`–`test_38` 屬於暫存器欄位；demo 使用 `type=REGISTER`。資料庫既有 `result_info.type` 是開放字串，本次未新增資料庫 enum。`core.agent_run` 仍維持一個 execution 對一個 agent_run，不拿它存每輪驗證。

## 2. 已編輯的 API

以下路徑均加上既有前綴 `/api/v1`。

| Method / Path | 本次狀態 | 用途 |
|---|---|---|
| `GET /tasks/{task_id}/detail` | 沿用，調整結果序列化 | 回傳主任務與全部有效 parse_item；包含尚未派送或尚無結果的項目 |
| `GET /parse-items/{parse_id}/workbench` | 新增程式 | 工作台資料：parse_item、來源、execution、結果版本、渲染圖、驗證、轉換 |
| `GET /parse-items/{parse_id}/source/content` | 新增程式 | 透過既有任務讀原始檔；即使來源檔在檔案庫被軟刪，任務仍可存取原始檔 |
| `GET /results/{result_id}/artifacts/{artifact_id}/content` | 新增程式 | 經權限檢查讀來源裁切圖或渲染圖；回 PNG/JPEG/WebP |
| `GET /parse-items/{parse_id}/results` | 沿用，調整結果序列化 | 最新 execution 的 JSON 結果歷史；不回傳內部 storage_key |
| `POST /parse-items/{parse_id}/results` | 擴充程式 | append 人工版本，支援 execution_id、base_result_id，清空衍生結果 |
| `GET /executions?parse_id=...` | 沿用 | 如需選擇歷史執行，先取得執行 ID |

### 工作台讀取參數

- 省略 `execution_id`：選最新執行；指定則必須屬於這個 parse_item。
- 省略 `result_id`：選該次執行的最新結果；指定則必須屬於選定 execution。
- `result_id` 指向歷史執行時，需一起傳該 `execution_id`。
- 尚未派送或沒有結果仍回 200，分別為 `data_status=NO_EXECUTION`、`NO_RESULT`。
- 老資料沒有 workbench：`LEGACY`，JSON 仍可顯示，其他區塊顯示尚無資料。
- workbench 格式不符：`INVALID`；內容雜湊不符：`STALE`。兩者皆不顯示衍生成果。
- 有效 workbench：`AVAILABLE`。人工新版本也可為 AVAILABLE，但 verification 為 NOT_RUN，render_versions 為空、conversion 為 null。
- 跨使用者、錯誤 parse/execution/result 關聯、已軟刪 parse_item／主任務：404。

### 前端載入順序

1. `GET /tasks/{id}/detail` 建立分頁；key 用 `parse_item.id`，label 用 name，空名可顯示「未命名項目」。
2. 點選分頁後取得 workbench；切換項目時取消／忽略前一個請求，避免較慢的回應覆蓋目前頁面。
3. 原圖優先使用 `source.preview_artifact`；没有裁切圖時下載 `source.asset_content_url`。圖片直接預覽，PDF 使用瀏覽器 PDF.js 按 page_no 呈現。
4. 圖片端點沿用 Bearer token。前端用帶 Authorization 的 fetch 讀 Blob，再用 `URL.createObjectURL()` 設定 img；切換後釋放 Blob URL，不將 token 放進 query string。
5. 執行中的頁面可每 3–5 秒輪詢；terminal 狀態停止。後端本次未實作 SSE/WebSocket。
6. 切換 JSON 版本重新請求 workbench 的 result_id；渲染版本和驗證歷程均由該筆選定結果提供。

### 人工編輯

```json
{
  "execution_id": "目前選定的 execution UUID",
  "base_result_id": "開始編輯時的最新 result UUID",
  "content_type": "WAVEDROM",
  "type": "TIMING",
  "content": "{\"signal\":[]}",
  "note": "修正 adr_o 的時序"
}
```

- 仍使用 execution row lock 取得下一個 round_no。
- 新增 `RESULT_VERSION_CONFLICT` / `EXECUTION_CHANGED`：前端重新載入並讓使用者處理版本差異。
- 兩個新 ID 暫為 optional，保留舊客戶端相容性；**新版前端應固定傳入**。未傳 ID 的舊客戶端沒有過期編輯偵測保障。
- 新增 `EXECUTION_STILL_ACTIVE`：執行尚未結束時不接受人工寫入，避免 AI 與人工同時追加。
- 沒有可編輯的既有結果時回 `NO_RESULT`。
- WaveDrom 內容需可解析為 JSON，且具備 signal 或 reg 陣列；不在此端點執行 WaveDrom 渲染或 Verilog 轉換。
- 新 result 記錄 `base_result_id`、編輯者、時間、note；以前的結果完整保留。
- 新版本建立空 workbench：新 content_sha256、render_versions=[]、verification.status=NOT_RUN、conversion=null。不能複製舊的 TRUE、舊圖或舊 Verilog。

## 3. Schema 決策

### 保留十張表，在現有 JSONB 內擴充

本次沒有新增表或欄位，也不修改既有 FK / execution enum。選擇 `core.result.result_info` 的理由：工作台成果隨結果版本一起讀寫、不可拆開覆蓋；目前尚無依每筆 verification 或 metric 跨任務查詢的需求。

```text
core.result
  id / execution_id / round_no / status
  result_info
    schema_version: 2
    type / content_type / content / source / note
    base_result_id: UUID|null
    workbench
      schema_version: 1
      content_sha256
      source_artifact_id: UUID|null
      artifacts[]: {id, storage_key, media_type}
      render_versions[]: {id, label, artifact_id, note, result_id|null}
      verification: {status, match|null, rounds[]}
      conversion: {kind, language, code, metrics[], table, warnings|null}|null
```

詳細型別寫於 `app/schemas/workbench.py`。其中：

- 圖片只存 storage_key 與 metadata，**不存 base64**。
- 每筆 result 的檔案放在 `results/{execution_id}/{result_id}/...`；圖片服務驗證權限與路徑。
- content_sha256 使用實際 UTF-8 content 字串計算；不是依格式化後的 JSON 計算。
- `match` 和 `verification.status` 分離；PARTIAL 可以是一次成功執行的有效成果。
- `diff_count=0` 與 `diffs=null` 意義不同：前者無差異，後者沒有差異明細。參考檔未提供明細，不自行補造。
- 原報告時間沒有時區，demo 與範例保存 `checked_at_display`；未自行轉成 UTC。正式 worker 應提供含時區的 `checked_at`。
- metrics 使用 label/value，表格使用 columns/rows，同時支援 Per-Lane / Per-Reg。
- warnings=null 表示未提供警告明細；不可由警告數 > 0 推導實際文字。

### DB 層與應用層分工

新建資料庫的 `06_result.sql` 新增兩個 CHECK：result_info 必須是 object；如果有 workbench，它也必須是 object。詳細欄位與關聯由 Pydantic 和 service 檢查，不把多層 JSON schema 全寫進 PostgreSQL CHECK。

既有 DB 的 bootstrap 不修改既有 CHECK，因此另附手動 migration：
`app/db/migrations/20260906_workbench_json_contract.sql`。先以 NOT VALID 加約束，再 VALIDATE 歷史資料；不修改舊 result_info，不自動執行。正式套用前仍需你確認資料與部署窗口。

舊資料缺少 workbench 保持可讀，不能把它假裝成「已驗證」。舊 result_info 若不是 object，migration 會拒絕，需先檢視歷史資料。

### 未來需要拆表的條件

若要跨任務查詢每輪 diff、依訊號計算統計，或單筆結果 JSON 過大，再討論 result_artifact / verification_round / conversion 表。目前不預先增加新表，也不把 result_info 當成不受約束的任意字典。

## 4. Worker／資料寫入邊界

新增 `generated_result_service.record_generated_result()`，提供未來 worker 呼叫的內部寫入流程，**沒有新增可由一般使用者提交 AI 驗證結果的 HTTP 端點**。

1. 呼叫端預先配置 result UUID，產生內容與檔案。
2. 檔案放進此 result 的 storage 目錄；建立 WorkbenchData。
3. writer 鎖 execution，僅接受 RUNNING，檢查 digest、檔案位置與歷史 result 關聯。
4. 新增 result、取得下一個 round_no，flush。
5. caller 負責 commit 及執行完成／失敗狀態；失敗後的未引用檔案清理也屬 caller 責任。

現階段沒有實體 worker、實際 WaveDrom 渲染或 Verilog 轉換流程。這次新增的是資料契約、內部寫入入口與讀取 API，並未讓整個解析系統自動執行。

## 5. v3 Demo 的資料與限制

- 內嵌來源 HTML 的九個 test，包括全部 28 張去重後原圖／渲染圖、最終 JSON、驗證紀錄、指標與 Verilog 原文。
- 每個 test 建立穩定的 demo parse UUID；在同一示範主任務下切換。
- immutable 圖片內嵌於 HTML，localStorage 只保存 reference key、任務與編輯版本，避免圖片塞滿瀏覽器儲存。
- 其他任務只列出自己的 parse_item；尚無結果的項目仍可選取。
- PDF 選頁與 ROI 頁碼保存保留。
- 圖片可點選放大；Verilog 文字保留原參考檔的警告及註解。
- 手動 JSON 編輯只生成新內容版本；新版不顯示舊驗證／轉換。

## 6. 下一輪可討論

1. 是否把 execution_id / base_result_id 改成必填，全面啟用過期編輯偵測？
2. JSON 修改後，要自動排「僅渲染／轉換」工作，還是先保留草稿？目前沒有開放重新解析。
3. 最終成果是否需要人工簽核後才能匯出？本輪仍未做簽核。
4. 真實 worker 各輪 JSON、渲染圖與 verification 的可追溯關聯如何產生？目前不根據 vXX 名稱猜測。
5. 額外的 PDF 伺服器縮圖／ROI 裁切端點是否必要？目前 demo 由瀏覽器處理；後端提供原始檔與已有 artifact。
