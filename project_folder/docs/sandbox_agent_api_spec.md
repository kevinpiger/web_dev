# 沙盒 Agent API 契約 v1

本版與既有 FastAPI 部署在一起，獨立 `/internal/worker` 與 `/internal/agent` router。使用者 API 不變。此文件描述本次實作範圍；不代表已啟動、執行測試或套用資料表。

## 01｜憑證與執行識別

- Worker 使用 `X-Worker-Key`；僅可信任排程／Worker 主程式持有，禁止傳進沙盒。
- Agent 使用 `Authorization: Bearer <token>`。獨立 HS256 密鑰、issuer `datasheet-backend`、audience `sandbox-agent`、type `agent_attempt`。
- JWT 包含 `sub=execution_id`、`attempt_id`、`jti`、`iat`、`exp`。DB 同時比對三個識別並確認執行權；一般登入 token 不能呼叫內部端點。
- 一次 execution 可以有多次 attempt；Worker 為每次嘗試產生 UUID，建立請求重送必須使用相同 UUID。新 UUID 不代表可以搶走尚有效的租約。
- 預設 token 有效 3600 秒，租約 120 秒，建議每 30 秒送心跳。心跳不延長 token 有效期限。所有時間為 UTC ISO 8601。
- 兩組密鑰均需至少 32 字元且與使用者 JWT 密鑰互異，未設定時內部 API 拒絕服務。部署時使用 HTTPS、限制內部路由可達範圍，日誌不記錄憑證。

## 02｜Worker API

| Method / Path | 傳入 | 回傳 |
|---|---|---|
| POST `/internal/worker/executions/{execution_id}/attempts` | `{"attempt_id":"UUID"}` | execution_id、attempt_id、attempt_no、execution_status、attempt_status、lease_expires_at、token_expires_at、retry_allowed、stop、reason，加上 access_token、token_type、heartbeat_interval_seconds |
| GET `/internal/worker/executions/{execution_id}` | path execution_id | 同上狀態欄位（沒有 token），另含 latest_result_id |

第一次領取僅接受 CREATED／QUEUED。有效 RUNNING attempt 不允許被另一個 attempt 取代。同 attempt_id 重送回傳原憑證及租約，不算重試、不延長期限。

Worker 狀態查詢與領取會將逾期 RUNNING attempt 轉 EXPIRED、execution 轉 TIMEOUT。僅 FAILED／TIMEOUT 且 attempt.retryable=true、retry_count < max_retry_count 才能建立新 attempt；每次真正建立後續嘗試 retry_count + 1。首次 attempt_no=1，不增加 retry_count。成功、取消及刪除不得重新啟動。

本版提供原子領取、期限判斷及重試資格，尚未實作排程器、退避、Broker ACK、inbox 或租約掃描器。沒有後續 Worker 查詢／領取時，DB 可能仍保留 RUNNING，但過期憑證／租約已不能寫入。

## 03｜Agent API

所有路徑均由 token 決定 execution，不接受任意 execution_id 或資料庫路徑。

| Method / Path | 傳入 | 回傳 |
|---|---|---|
| GET `/internal/agent/context` | 無 | task_id、parse_id、execution_id、attempt_id、name、source {asset_id,file_name,content_url,page_no,roi}、flow {id,version}、model {id,version}、租約與憑證期限 |
| GET `/internal/agent/source` | 無 | 原始 PDF／圖片二進位，僅允許此 execution 的 asset |
| POST `/internal/agent/heartbeat` | 無 | execution_id、attempt_id、attempt_no、execution_status、attempt_status、lease_expires_at、token_expires_at、retry_allowed、stop、reason |
| POST `/internal/agent/artifacts` | multipart：result_id、artifact_id（UUID）、file（PNG/JPEG/WebP） | artifact_id、result_id、media_type、size、sha256 |
| POST `/internal/agent/results` | 下列 ResultSubmission | request_id、result_id、round_no、execution_status、attempt_status |
| POST `/internal/agent/complete` | 下列 ResultSubmission（最終成果） | 同上；結果、execution=SUCCEEDED、attempt=SUCCEEDED、去重收據同一 DB 交易提交 |
| POST `/internal/agent/fail` | `{"request_id":"UUID","status":"FAILED","error_code":"MODEL_UNAVAILABLE","message":"...","retryable":true}`；status 可 FAILED/TIMEOUT | request_id、execution_status、attempt_status、retry_allowed |

Context 刻意不直接傳整份 task.config/input_data，以免任意 config 夾帶服務密鑰；只提供明確欄位及派送時的 page/ROI 快照。進階 Schema／解析器設定需另定可公開的型別後擴充，現階段不宣稱已涵蓋任意解析器參數。

### ResultSubmission

```json
{
  "request_id": "UUID",
  "result_id": "UUID",
  "type": "WAVEDROM",
  "content_type": "application/json",
  "content": "{\"signal\": []}",
  "note": null,
  "workbench": {
    "artifact_ids": [],
    "source_artifact_id": null,
    "render_versions": [],
    "verification": {"status": "NOT_RUN", "match": null, "rounds": []},
    "conversion": null
  }
}
```

`type`、`content_type` 是非空字串；content 上限 2,000,000 字元，須有非空白內容。`workbench` 可省略，預設空資料。render_versions／verification／conversion 沿用既有 Workbench 型別。後端計算 content_sha256，根據本 attempt 的 artifact_ids 建立檔案 manifest，寫入 `core.result.result_info.workbench`，不接受用戶指定 storage_key。

先產生 result_id，再上傳此結果需要的 artifacts，最後提交結果。同一結果 ID 不可覆寫；中間版本和最終版本使用不同 result_id。相同 request_id + 相同操作與內容可重送；不同內容或不同操作回 409。不同 request_id 重用 result_id 也回 409。

檔案上限預設 20 MiB／檔、100 個／attempt。檔名由伺服器產生，限制 PNG/JPEG/WebP 簽章，不接受 SVG 或任意路徑。此檢查不是完整影像解碼驗證。相同 artifact_id 與內容重送回原 metadata；不同內容回 409。尚未被結果引用的檔案清理列為後續工作。

## 04｜取消、逾時及交易規則

1. 沿用既有取消 execution／主任務與軟刪 parse_item API。派送後可刪除；不提供 resume，使用者有需要建立新工作。
2. 每次讀取／寫入檢查主任務、子項、execution 與 attempt。取消或刪除之後 context／source／成果回 409；heartbeat 回 `stop=true` 與原因。JWT 過期仍回 401，Agent 應停止。
3. Agent 不得自行 PATCH 任意狀態；只透過 heartbeat、complete、fail。不能把 CANCELLED 寫回 RUNNING/SUCCEEDED。
4. 提交與取消競爭以取得鎖並提交的順序決定；取消先完成，後續成果必須拒絕。已成功提交的歷史結果不因之後刪除而物理移除。
5. 舊 attempt 即使 JWT 尚有效，也不能回報到新 attempt。取消／刪除／被取代優先於收據重放。
6. 同 attempt 結束後，在 token 尚有效且未取消／刪除／被取代時，允許相同 request_id 重取成功收據。不可提交新的成果。
7. Worker 必須以後端提交結果為準再 ACK；本版未接 RabbitMQ，收據不是 inbox 完成記錄。重試前可能已有中間成果，保留原有版本。
8. 主任務依未刪除、可執行子項的最新 execution 彙整：全部終止後 FAILED/TIMEOUT 優先，再 CANCELLED，否則 COMPLETED；仍有工作則 RUNNING／DISPATCHED。已取消的主任務不被覆寫。

## 05｜錯誤與部署

AppError 回應：`{"error":{"code":"...","message":"..."}}`。401：憑證缺少／錯誤／到期；404：execution/來源不存在；409：取消、刪除、attempt 被取代、租約逾期、重複 ID 不同內容、狀態衝突；422：輸入或 workbench／artifact 不合法；503：內部憑證未設定。FastAPI 請求欄位驗證使用原生 `detail` 回應。

新增 `runtime.execution_attempt`，DDL 在 `app/db/schema/03_runtime/03_execution_attempt.sql`。不改寫既有表。現有 bootstrap 可載入新表；本次未執行，部署時由你決定 bootstrap 或手動套用 DDL。

實作順序：契約 → 設定與獨立認證 → attempt 資料表 → 鎖與生命週期 service → 端點 → 文件與 Todo。依要求不執行後端測試、import／編譯檢查、服務啟動或資料庫操作。

## 06｜呼叫順序與回應範例

1. Worker 收到 execution_id，使用 Worker Key 呼叫建立 attempt。
2. Worker 將 access_token 交給該次沙盒，保留 Worker Key 在宿主。
3. Agent GET context → GET source → 解析過程定期 POST heartbeat。
4. 若有圖片，先為結果產生 result_id，逐一 POST artifacts。
5. 視需要 POST results 保存中間版本；以新的 result_id POST complete 保存最終版本並完成 execution。
6. Worker GET execution 確認 SUCCEEDED；未來接上 Broker 後，再依 inbox／ACK 契約處理訊息。
7. 若失敗，Agent POST fail；是否重試由 Worker 依 retry_allowed 決定，不能由 Agent 自行簽發下一次憑證。

建立 attempt 回應範例（UUID 以字串示意）：

```json
{
  "execution_id": "UUID",
  "attempt_id": "UUID",
  "attempt_no": 1,
  "execution_status": "RUNNING",
  "attempt_status": "RUNNING",
  "lease_expires_at": "2026-09-06T04:02:00Z",
  "token_expires_at": "2026-09-06T05:00:00Z",
  "retry_allowed": false,
  "stop": false,
  "reason": null,
  "access_token": "<僅交付給這一次沙盒>",
  "token_type": "bearer",
  "heartbeat_interval_seconds": 30
}
```

完成回應：

```json
{
  "request_id": "UUID",
  "result_id": "UUID",
  "round_no": 2,
  "execution_status": "SUCCEEDED",
  "attempt_status": "SUCCEEDED"
}
```

取消後心跳回應：

```json
{
  "execution_id": "UUID",
  "attempt_id": "UUID",
  "attempt_no": 1,
  "execution_status": "CANCELLED",
  "attempt_status": "CANCELLED",
  "lease_expires_at": "2026-09-06T04:02:00Z",
  "token_expires_at": "2026-09-06T05:00:00Z",
  "retry_allowed": false,
  "stop": true,
  "reason": "EXECUTION_CANCELLED"
}
```

Agent 收到 stop=true、401，或 ATTEMPT_REPLACED／ATTEMPT_EXPIRED／TASK_OR_ITEM_DELETED／EXECUTION_CANCELLED 時停止後續工作。已開始的檔案下載或外部模型請求無法收回已傳出的內容；取消後不接受其新成果。

Worker 狀態查詢會回收期限已過的嘗試，因此不是單純讀取快取。回應一律 no-store。精確重送同一 request_id 取得的是原提交收據，其中的狀態是當次提交結果，不是目前狀態；目前狀態請讀 Worker 查詢端點。

## 07｜本次程式碼範圍

- `app/core/agent_auth.py`：Worker／Agent 認證與簽發。
- `app/models/execution_attempt.py`、`app/db/schema/03_runtime/03_execution_attempt.sql`：嘗試、租約、artifact manifest 與收據。
- `app/schemas/agent.py`：Swagger 請求／回應模型。
- `app/services/agent_service.py`：領取、fencing、去重、來源、檔案與結果交易。
- `app/router/internal_agent.py`：兩組 router，共九個端點。
- `app/config.py`、`app/main.py`、`app/models/__init__.py`、`.env.example`、`README.md`：整合及部署設定。

這份實作尚未經執行驗證。後續驗收應涵蓋同 execution 並行領取、不同 execution 重用 ID、token 範圍隔離、取消與提交競爭、租約／token 邊界、提交成功但 HTTP 回應遺失、逾時後舊 Agent 復活、成果與檔案越權及 DB 提交不確定等情境。
