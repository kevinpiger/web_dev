# AI Diagram Parsing Platform — DB Structure & Flow v1 Freeze

## 1. 設計原則

- PostgreSQL 為 Source of Truth
- RabbitMQ 僅負責 Queue / Dispatch
- 一個框（ROI）= 一個 ParseItem
- 一個 ParseItem 可建立多個 Execution
- 使用者重新解析 → New Execution
- System Retry → Same Execution
- 一個 Execution 可產生多輪 Result
- 每一輪 Result 為一筆資料
- IAM v1 採單一 User 對單一 Role
- 不建立 Page Table
- 不建立 TaskAsset
- 不建立 ParseType Registry
- `task_log / audit_log / asset_permission` 暫不納入 v1
- Flow / Model Registry v1 暫不獨立拆表

---

## 2. PostgreSQL Schema Structure

```text
PostgreSQL
├── iam
│   ├── role
│   └── app_user
├── core
│   ├── asset
│   ├── analysis_task
│   ├── parse_item
│   ├── execution
│   ├── agent_run
│   └── result
└── runtime
    ├── outbox_event
    └── inbox_event
```

總計：10 Tables

---

## 3. Main Domain Relationship

```text
iam.role
   │ 1:N
   ▼
iam.app_user
   ├───────────────> core.asset
   │                    ▲
   │                    │ N:1
   └───────────────> core.analysis_task
                          │ 1:N
                          ▼
                    core.parse_item
                          │
                          ├──────────> core.asset
                          │
                          │ 1:N
                          ▼
                    core.execution
                      ├── 1:1 → core.agent_run
                      └── 1:N → core.result
```

Runtime：

```text
core.execution
   ├──> runtime.outbox_event
   │          ↓
   │      RabbitMQ
   │          ↓
   └──> runtime.inbox_event
```

---

## 4. iam.role

用途：平台角色定義。

```text
iam.role
────────────────────────
id
code
name
description
created_at
updated_at
```

關係：

```text
Role 1 : N User
```

範例：

```text
ADMIN
USER
REVIEWER
```

---

## 5. iam.app_user

用途：平台使用者主表。

```text
iam.app_user
────────────────────────
id
employee_no
username
email
organization
role_id
is_active
token
token_expire_at
last_login_at
created_at
created_by
updated_at
updated_by
```

關係：

```text
role_id → iam.role.id
```

v1 一個 User 僅對應一個 Role。

---

## 6. core.asset

用途：保存使用者上傳的原始檔案與 Storage Metadata。

```text
core.asset
────────────────────────
id
user_id
file_name
mime_type
file_type
storage_type
storage_key
file_size
attributes
status
created_at
updated_at
deleted_at
```

關係：

```text
user_id → iam.app_user.id
```

Storage：

```text
storage_type
→ LOCAL / NAS / S3 / MINIO

storage_key
→ Storage Backend 中的 Object Key / Relative Path
```

範例：

```text
storage_type = MINIO
storage_key  = assets/{user_id}/{asset_id}/source.pdf
```

---

## 7. core.analysis_task

用途：代表使用者一次完整解析任務。

```text
core.analysis_task
────────────────────────
id
user_id
name
description
status
config
dispatched_at
completed_at
created_at
updated_at
deleted_at
```

關係：

```text
AnalysisTask N : 1 User
AnalysisTask 1 : N ParseItem
```

`config` 為派送前 Requested Configuration：

```json
{
  "model_id": "timing-parser-vlm",
  "model_version": "v1.3.2",
  "flow_id": "timing-default",
  "flow_version": "v2.1",
  "auto_detect": true,
  "default_parse_type": "TIMING",
  "language": "zh-TW"
}
```

不保存：

```text
item_count
completed_count
failed_count
running_count
progress
```

由 API 根據 `parse_item / execution` 即時聚合。

---

## 8. core.parse_item

用途：

```text
一個 ParseItem = 一個框 / ROI
```

```text
core.parse_item
────────────────────────
id
task_id
asset_id
name
status
x
y
width
height
created_at
updated_at
```

關係：

```text
task_id  → core.analysis_task.id
asset_id → core.asset.id
```

ROI 使用 normalized coordinate：

```text
0 <= x < 1
0 <= y < 1
0 < width <= 1
0 < height <= 1
x + width <= 1
y + height <= 1
```

全圖：

```text
x = 0
y = 0
width = 1
height = 1
```

Status：

```text
READY
REJECTED
```

`ParseItem` 不保存 `RUNNING / FAILED / COMPLETED`，執行狀態由 Execution 管理。

---

## 9. core.execution

用途：代表 ParseItem 的一次完整解析執行。

```text
core.execution
────────────────────────
id
parse_id
status
retry_count
max_retry_count
flow_id
flow_version
model_id
model_version
input_data
queued_at
started_at
finished_at
error_code
error_message
created_at
updated_at
```

關係：

```text
parse_id → core.parse_item.id
```

規則：

```text
User Re-run
→ New Execution

System Retry
→ Same Execution
→ retry_count + 1
```

Status：

```text
CREATED
→ QUEUED
→ RUNNING
→ SUCCEEDED

FAILED
TIMEOUT
CANCELLED
```

Retry：

```text
retry_count >= 0
max_retry_count >= 0
retry_count <= max_retry_count
```

`input_data` 保存派送當下輸入 Snapshot，例如：

```json
{
  "asset_id": "uuid",
  "roi": {
    "x": 0.1,
    "y": 0.2,
    "width": 0.5,
    "height": 0.3
  },
  "config": {
    "language": "zh-TW"
  }
}
```

---

## 10. core.agent_run

用途：保存 Agent Runtime 結構化執行紀錄。

v1 暫定：

```text
Execution 1 : 1 AgentRun
```

```text
core.agent_run
────────────────────────
id
execution_id
model_id
model_version
status
input_tokens
output_tokens
latency_ms
started_at
finished_at
error_code
error_message
created_at
```

關係：

```text
execution_id → core.execution.id
UNIQUE(execution_id)
```

用途：

```text
Model Trace
Token Usage
Latency
Runtime Failure
```

---

## 11. core.result

用途：保存單一 Execution 在 Agent Loop 中每一輪產生的結果。

關係：

```text
Execution 1 : N Result
```

```text
core.result
────────────────────────
id
execution_id
round_no
status
result_info
created_at
updated_at
```

Constraint：

```text
UNIQUE(execution_id, round_no)
round_no > 0
```

每一輪一筆：

```text
Execution #1
├── Result Round 1
├── Result Round 2
└── Result Round 3
```

`result_info` 保存單輪結果：

```json
{
  "type": "TIMING",
  "content_type": "WAVEDROM",
  "content": "...",
  "confidence": 0.94,
  "metadata": {
    "warning_count": 1
  }
}
```

---

## 12. runtime.outbox_event

用途：防止 PostgreSQL Commit 成功，但 RabbitMQ Publish 失敗造成任務漏送。

```text
runtime.outbox_event
────────────────────────
id
execution_id
event_type
status
retry_count
available_at
published_at
last_error
created_at
updated_at
```

關係：

```text
execution_id → core.execution.id
```

注意：

```text
outbox.retry_count
→ RabbitMQ Publish Retry

execution.retry_count
→ Worker / Agent Execution Retry
```

---

## 13. runtime.inbox_event

用途：避免 RabbitMQ Redelivery 造成 Worker 重複執行。

```text
runtime.inbox_event
────────────────────────
message_id
consumer_name
execution_id
processed_at
```

PK：

```text
(message_id, consumer_name)
```

關係：

```text
execution_id → core.execution.id
```

處理邏輯：

```text
Worker 收到 Message
        ↓
(message_id, consumer_name)
        ↓
查 inbox_event
   ┌────┴────┐
   │         │
存在       不存在
   │         │
 ACK       執行
             ↓
      INSERT inbox_event
```

---

## 14. Complete Runtime Flow

```text
User
 ↓
iam.app_user
 ↓
Upload Asset
 ↓
core.asset
 ↓
Create AnalysisTask
 ↓
core.analysis_task
 ↓
Create / Confirm ROI
 ↓
core.parse_item
 ↓
Dispatch
 ├──────────────────────────┐
 ▼                          ▼
core.execution       runtime.outbox_event
status = CREATED             ↓
                         RabbitMQ
                             ↓
                       Worker Consume
                             ↓
                    runtime.inbox_event
                             ↓
                     core.execution
                     status = RUNNING
                             ↓
                      core.agent_run
                             ↓
                        Agent Loop
                    ┌────┬────┴────┐
                    ▼    ▼         ▼
                 Result Result ... Result
                    ↓
              core.execution
              status = SUCCEEDED
```

---

## 15. User Re-run Flow

```text
ParseItem #1
├── Execution #1
│   ├── Result Round 1
│   └── Result Round 2
└── Execution #2
    ├── Result Round 1
    ├── Result Round 2
    └── Result Round 3
```

規則：

```text
ParseItem 不變
Execution 新增
Result 跟隨新的 Execution 重新產生
```

---

## 16. System Retry Flow

```text
Execution #1
status = RUNNING
retry_count = 0
       ↓
Temporary Error
       ↓
retry_count = 1
       ↓
Same Execution Retry
```

不建立 New Execution。

---

## 17. RabbitMQ Message

```json
{
  "message_id": "uuid",
  "event_type": "EXECUTION_CREATED",
  "execution_id": "uuid"
}
```

Worker 收到後：

```text
execution_id
 ↓
core.execution
 ↓
core.parse_item
 ↓
core.asset
```

PostgreSQL 為唯一 Source of Truth。

---

## 18. Removed Tables

已移除：

```text
iam.permission
iam.user_role
iam.role_permission
core.task_asset
core.parse_type
core.result_version
```

原因：

```text
permission / user_role / role_permission
→ IAM v1 改為 User 直接綁 Role

task_asset
→ Task 使用哪些 Asset 可由 ParseItem 反查

parse_type
→ Parse Type 由 AI 執行時判斷

result_version
→ Result 改為 Execution 1:N Result，每輪一筆
```

---

## 19. Deferred Tables

v1 暫不建立：

```text
core.task_log
audit.audit_log
core.asset_share
core.asset_permission
```

等 API Event、Audit Scope、Asset Sharing Requirement 明確後再設計。

---

## 20. v1 Final Domain Chain

```text
Role
 ↓
User
 ├── Asset
 └── AnalysisTask
       ↓
    ParseItem
       ↓
    Execution
      ├── AgentRun
      └── Result × N
```

Runtime：

```text
Execution
 ↓
Outbox
 ↓
RabbitMQ
 ↓
Inbox
 ↓
Worker
```

---

## 21. Current Freeze Tables

```text
iam.role
iam.app_user

core.asset
core.analysis_task
core.parse_item
core.execution
core.agent_run
core.result

runtime.outbox_event
runtime.inbox_event
```

下一階段：

```text
PK / FK Final Review
→ Enum Review
→ Index Review
→ ON DELETE Review
→ ERD
→ PostgreSQL DDL
→ Migration Order
```

---

## 22. PK / FK Final Review

型別慣例（沿用舊稿 `ai_diagram_platform_domain_schema_flow_v1.md` 已驗證過的慣例，
本節起全部欄位型別以此為準）：

```text
id 類主鍵          UUID DEFAULT gen_random_uuid()
一般字串／代碼       VARCHAR(N)
長文字／訊息         TEXT
結構化資料           JSONB
時間戳              TIMESTAMPTZ
整數計數／版本號      INTEGER
高頻寬計量（latency／file_size） BIGINT
座標／比例           DOUBLE PRECISION
布林旗標            BOOLEAN
```

10 張表的 PK／FK／`ON DELETE` 總表：

| 表 | PK | FK | ON DELETE |
|---|---|---|---|
| `iam.role` | `id` | — | — |
| `iam.app_user` | `id` | `role_id → iam.role.id` | `RESTRICT`（角色底下還有人就不准刪） |
| | | `created_by → iam.app_user.id`（自關聯，NULL） | `SET NULL` |
| | | `updated_by → iam.app_user.id`（自關聯，NULL） | `SET NULL` |
| `core.asset` | `id` | `user_id → iam.app_user.id` | `RESTRICT`（Asset 歸屬明確，不因刪 User 連坐） |
| `core.analysis_task` | `id` | `user_id → iam.app_user.id` | `RESTRICT` |
| `core.parse_item` | `id` | `task_id → core.analysis_task.id` | `CASCADE`（ROI 完全依附 Task，Task 沒了 ROI 也沒意義） |
| | | `asset_id → core.asset.id` | `RESTRICT`（Asset 還被框著就不准刪，需先解除或走 `deleted_at` 軟刪） |
| `core.execution` | `id` | `parse_id → core.parse_item.id` | `CASCADE`（`13. core.execution` 已明講「1 ParseItem 1:N Execution」，附屬關係） |
| `core.agent_run` | `id` | `execution_id → core.execution.id`，**`UNIQUE`**（`1:1`，原文已明講） | `CASCADE` |
| `core.result` | `id` | `execution_id → core.execution.id` | `CASCADE` |
| `runtime.outbox_event` | `id` | `execution_id → core.execution.id` | `CASCADE` |
| `runtime.inbox_event` | `(message_id, consumer_name)`（複合 PK，原文已明講） | `execution_id → core.execution.id` | `CASCADE` |

**`CASCADE` 的實務前提**：`core.execution` 目前沒有 `deleted_at`，正常運作下不會被硬刪除
（保留作稽核／Retry 依據）。上面對 `agent_run`／`result`／`outbox_event`／`inbox_event`
標的 `CASCADE` 是防禦性設計（萬一真的要清資料，子表跟著清乾淨），不是預期中會被觸發的路徑。

---

## 23. Enum Review

原文只有 `iam.role`（範例）、`core.parse_item.status`、`core.execution.status` 給了明確枚舉值；
其餘表的 `status` 欄位原文只列了欄位名、沒給值域。以下枚舉值取自舊稿
`ai_diagram_platform_domain_schema_flow_v1.md` 對應概念（標「沿用舊稿」），或本次依現有欄位與
Runtime Flow 反推補上（標「本次新定義」）——後者屬於本節要做的 Enum Review 本身，不是原文既有規則。

| 表.欄位 | 枚舉值 | 依據 |
|---|---|---|
| `iam.role.code` | `ADMIN` / `USER` / `REVIEWER` | 原文 §4 範例 |
| `core.asset.status` | `UPLOADING` / `READY` / `FAILED` | 沿用舊稿；**不設 `DELETED`**——刪除用既有的 `deleted_at` 軟刪表達，兩套刪除語意疊在一起會產生「`status=DELETED` 但 `deleted_at IS NULL`」這種不可能狀態 |
| `core.asset.file_type` | `PDF` / `IMAGE` / `SVG` / `OTHER` | 沿用舊稿；描述「檔案本身是什麼」，跟 `parse_item` 判讀出的圖型別（timing／bitfield／flowchart）是兩件事，不可混用 |
| `core.asset.storage_type` | `LOCAL` / `NAS` / `S3` / `MINIO` | 原文 §6 Storage 節已列 |
| `core.analysis_task.status` | `DRAFT` → `READY` → `DISPATCHED` → `RUNNING` → `COMPLETED`；另有 `FAILED` / `CANCELLED` | **本次新定義**——原文只給了 `dispatched_at`／`completed_at` 兩個時間戳暗示這條路徑，沒給枚舉值；`DISPATCHED` 對應 `dispatched_at` 寫入的那一刻，`RUNNING` 是至少一個子 Execution 進 `RUNNING` 後的聚合狀態 |
| `core.parse_item.status` | `READY` / `REJECTED` | 原文 §8 已明講，**不含** `RUNNING`／`FAILED`／`COMPLETED`（原文：「執行狀態由 Execution 管理」） |
| `core.execution.status` | `CREATED` → `QUEUED` → `RUNNING` → `SUCCEEDED`；另有 `FAILED` / `TIMEOUT` / `CANCELLED` | 原文 §9 已明講 |
| `core.agent_run.status` | `RUNNING` / `SUCCEEDED` / `FAILED` | **本次新定義**——取 `execution.status` 的執行期子集（拿掉 Queue 階段，AgentRun 建立時就已經在跑） |
| `core.result.status` | `PENDING` / `SUCCEEDED` / `FAILED` | **本次新定義**——每一輪 Result 對應一次 Agent Loop 迭代，該輪本身也可能失敗（例如驗證 Agent 判失敗、下一輪重來），需要獨立狀態，不能只靠 `execution.status` 反推 |
| `runtime.outbox_event.status` | `PENDING` / `PUBLISHED` / `FAILED` | 沿用舊稿 |
| `runtime.outbox_event.event_type` | `EXECUTION_CREATED` | 原文 §17 RabbitMQ Message 範例已示範 |

---

## 24. Index Review

依實際查詢路徑（Dispatch 輪詢、User 進入畫面看列表、Worker 消化 Outbox）配置：

```sql
-- FK 查詢路徑（父列表下的子項）
CREATE INDEX idx_app_user_role_id        ON iam.app_user(role_id);
CREATE INDEX idx_asset_user_id           ON core.asset(user_id);
CREATE INDEX idx_analysis_task_user_id   ON core.analysis_task(user_id);
CREATE INDEX idx_parse_item_task_id      ON core.parse_item(task_id);
CREATE INDEX idx_parse_item_asset_id     ON core.parse_item(asset_id);
CREATE INDEX idx_execution_parse_id      ON core.execution(parse_id);
CREATE INDEX idx_result_execution_id     ON core.result(execution_id);
CREATE INDEX idx_outbox_execution_id     ON runtime.outbox_event(execution_id);
CREATE INDEX idx_inbox_execution_id      ON runtime.inbox_event(execution_id);

-- Outbox Publisher 輪詢：WHERE status = 'PENDING' AND available_at <= now()
CREATE INDEX idx_outbox_dispatch_queue
  ON runtime.outbox_event(status, available_at)
  WHERE status = 'PENDING';

-- API 依 Task 即時聚合進度（§7「不保存 item_count 等，由 API 即時聚合」）
CREATE INDEX idx_parse_item_task_status  ON core.parse_item(task_id, status);
CREATE INDEX idx_execution_parse_status  ON core.execution(parse_id, status);

-- 軟刪表：只索引未刪列，避免索引膨脹
CREATE INDEX idx_asset_active
  ON core.asset(user_id) WHERE deleted_at IS NULL;
CREATE INDEX idx_analysis_task_active
  ON core.analysis_task(user_id) WHERE deleted_at IS NULL;
```

`core.agent_run(execution_id)` 與 `core.result(execution_id, round_no)`、
`runtime.inbox_event(message_id, consumer_name)` 已由 `UNIQUE`／`PRIMARY KEY` 約束
自動建立索引，不重複建。

---

## 25. ON DELETE Review

見 §22 表格最後一欄；統整成一句話：**依附子項（`parse_item`／`execution` 以下全部）用
`CASCADE`，跨聚合的擁有關係（`user_id`／`asset_id`）一律 `RESTRICT`**。理由：

```text
CASCADE 用在「刪了父項，子項就沒有存在意義」的關係
→ Task 沒了，ROI 沒了；ParseItem 沒了，Execution 沒了；
  Execution 沒了，AgentRun／Result／Outbox／Inbox 都沒了。

RESTRICT 用在「子項仍在使用父項」的關係
→ 不能刪一個還有 Asset／Task 的 User；
  不能刪一個還被 ParseItem 引用的 Asset（要刪就先軟刪或改走 deleted_at）。

SET NULL 只用在「純標註、不影響資料完整性」的自關聯
→ app_user.created_by / updated_by。
```

---

## 26. ERD

本文件的實體與關係已經用 `archify` 產出互動式 HTML 圖，位置：

```text
ai_diagram_db_structure_flow_v1_freeze.architecture.html
```

內容涵蓋 10 張表 ＋ RabbitMQ、依 `iam`／`core`／`runtime` 三個 schema 分框，主線
`role → app_user → analysis_task → parse_item → execution → result`，側支涵蓋
`asset` 引用與 Runtime 的 outbox→RabbitMQ→inbox 迴路——關係與本次 DDL（§27）逐條對應，
無新增或刪減實體，**這步驟視為已完成，不重畫**。它是元件關係圖而非嚴格的 crow's-foot
ERD 記法（沒有畫基數符號），若之後要交給不熟這套工具的人看，可以再補一版標準 ERD 記法。

---

## 27. PostgreSQL DDL

完整可執行 DDL 另存 `ai_diagram_db_structure_flow_v1_freeze.sql`（依 §28 遷移順序排列，
含本節以上所有 PK／FK／`ON DELETE`／`CHECK`／索引）。此處貼關鍵約束摘要：

```sql
-- core.parse_item：ROI Constraint（原文 §8 已明講的範圍，這裡轉成 CHECK）
ALTER TABLE core.parse_item ADD CONSTRAINT parse_item_roi_range CHECK (
  x >= 0 AND x < 1 AND
  y >= 0 AND y < 1 AND
  width  > 0 AND width  <= 1 AND
  height > 0 AND height <= 1 AND
  x + width  <= 1 AND
  y + height <= 1
);

-- core.execution：Retry 規則（原文 §9「retry_count <= max_retry_count」）
ALTER TABLE core.execution ADD CONSTRAINT execution_retry_bound
  CHECK (retry_count <= max_retry_count);

-- core.execution：User Re-run vs System Retry 兩條規則不是 DB 層約束，
-- 是應用邏輯（同一個 execution_id 更新 retry_count，或 INSERT 新的一列），
-- DDL 層只保證 retry_count 不超過上限，不保證「什麼時候該新增列」。

-- core.agent_run：1 Execution 1 AgentRun（原文 §10 明講）
ALTER TABLE core.agent_run ADD CONSTRAINT agent_run_execution_unique UNIQUE (execution_id);

-- core.result：每輪一筆（原文 §11 明講）
ALTER TABLE core.result ADD CONSTRAINT result_execution_round_unique UNIQUE (execution_id, round_no);
ALTER TABLE core.result ADD CONSTRAINT result_round_positive CHECK (round_no > 0);

-- runtime.inbox_event：複合主鍵防重複消費（原文 §13 明講）
ALTER TABLE runtime.inbox_event ADD CONSTRAINT inbox_event_pk PRIMARY KEY (message_id, consumer_name);
```

---

## 28. Migration Order

依 FK 依賴方向排列，前面的表要先建：

```text
1. iam.role
2. iam.app_user            (FK → iam.role)
3. core.asset               (FK → iam.app_user)
4. core.analysis_task       (FK → iam.app_user)
5. core.parse_item          (FK → core.analysis_task, core.asset)
6. core.execution           (FK → core.parse_item)
7. core.agent_run           (FK → core.execution)
8. core.result              (FK → core.execution)
9. runtime.outbox_event     (FK → core.execution)
10. runtime.inbox_event     (FK → core.execution)
```

`iam.app_user` 的 `created_by`／`updated_by` 自關聯 FK 必須在 `iam.app_user` 建表**之後**
用 `ALTER TABLE` 補上（同一張表不能在 `CREATE TABLE` 當下引用自己還沒存在的 PK 之外的東西——
實務上 `CREATE TABLE` 內寫自關聯 FK 是合法的，但為了遷移腳本可讀性，`§ ai_diagram_db_structure_flow_v1_freeze.sql`
仍拆成 `CREATE TABLE` + 後補 `ALTER TABLE ADD CONSTRAINT` 兩步，避免跟未來要加的 Seed Data
（例如先插入一筆 `SYSTEM` user 沒有 `created_by`）順序打架。
