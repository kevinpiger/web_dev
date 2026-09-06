# TODO — 03A 暫存流程

## 目標

流程改成：**03 單純上傳** ／ **03A 新增任務時挑既有檔案 + 上傳新檔 + 當場匡選命名**，
**移除 04 候選內容確認**。03A 可邊做邊暫存，下次回來繼續；
按下派送後該任務底下的 parse_item 全部轉成送出解析，不再有暫存。

技術上歸結成一件事：`parse_item` 需要一個「還在編輯、先不要送」的狀態。
目前 `status` 只有 `READY` / `REJECTED`，新建一律 `READY`，無法表達「存著但還沒要跑」。

## 已確認決策

- 暫存存法 → **維持逐筆 API**（`POST` 批次新增 / `PATCH` / `DELETE`），不做整批覆蓋
- 派送後 → **即凍結**。不做增量派送、本輪不做單筆重新解析
- CHECK 約束 → **直接改 `.sql`**，不動 bootstrap
- PDF 頁面底圖 → **本輪不做**，只做 API

---

## 不用動（已經有了，別重造）

- [x] 02 檔案分頁：看所有上傳過的檔案 → `GET /assets`
- [x] 02 檔案分頁：上傳 / 軟刪 → `POST /assets`、`DELETE /assets/{id}`
- [x] 03 單純上傳 → `POST /assets`
- [x] 03A 既有可用檔案清單 → `GET /assets?status=READY`
- [x] 02 點細節看所有子任務狀態與 parse_item → `GET /tasks/{id}/detail`
      （每個 parse_item 帶 `latest_execution` / `latest_result`；未派送的為 `null`）
- [x] 主任務 → 多 parse_item → 多 execution → freeze schema 既有結構

---

## 要改的

### 1. 新增 `DRAFT` 狀態

- [x] `app/core/enums.py`：`ParseItemStatus` 加 `DRAFT = "DRAFT"`（放在 `READY` 前）
- [x] `app/db/schema/02_core/03_parse_item.sql`：
  - [x] `status ... DEFAULT 'DRAFT'`（原本 `'READY'`）
  - [x] `CHECK (status IN ('DRAFT', 'READY', 'REJECTED'))`（原本只有兩個值）
  - [x] 註明這是第五處 freeze 增補；`DRAFT` 是**編輯期**狀態、非執行狀態，
        不違反 freeze §8「執行狀態由 Execution 管理」

> ⚠️ bootstrap 只補欄位、不改既有約束（規格 §1「不動既有」，
> `_CONSTRAINT_KEYWORDS` 直接略過約束行）。
> 此變更**只對全新建立的資料庫生效**。目前無實體 DB 所以沒問題，
> 但日後有正式庫時這類約束演進要另外處理 —— 記進 README。

### 2. 新建的 ROI 一律是暫存

- [x] `app/services/parse_item_service.py` · `create_parse_items()`：
      建立時 `status = DRAFT`（原本 `READY`）
- [x] **移除任務自動 `DRAFT → READY` 的翻轉**（函式結尾那段 if）。
      新流程下任務整個編輯期停在 `DRAFT`，到派送才變 `DISPATCHED`

> `PATCH /parse-items/{id}` 的 status 驗證是從 enum 動態產生
> （`{s.value for s in ParseItemStatus}`），加了 DRAFT 自動生效，不用改。

### 3. 派送時把暫存全部轉成送出解析

- [x] `app/repositories/parse_item_repository.py`：
      新增 `list_dispatchable_for_task()`＝`DRAFT + READY`、排除 `REJECTED` 與軟刪，
      取代目前 dispatch 用的 `list_ready_for_task()`（別處沒人用，可直接換掉）
- [x] `app/services/execution_service.py` · `dispatch_task()`：
  - [x] 改呼叫 `list_dispatchable_for_task()`
  - [x] 建 execution 前，把其中 `DRAFT` 就地改成 `READY`
        （同一個 transaction，跟 execution／outbox 一起 commit）
  - [x] 錯誤訊息改為「沒有可派送的項目」，`error_code` 維持 `NO_PARSE_ITEM`

> 其餘不動：`get_owned_for_update()` 鎖列防重複派送、
> `DISPATCHABLE_TASK_STATUSES` 已含 `DRAFT`、
> 派送後 `_assert_editable()` 讓清單凍結（409 `PARSE_LIST_FROZEN`）—— 正好符合決策。

### 4. 編輯期的「解析項目」數字

- [x] `app/repositories/analysis_task_repository.py` · `item_counts()`：
      改成算 `DRAFT + READY`（仍排除 `REJECTED` 與軟刪）。
      否則暫存階段 02 總覽的「解析項目」會一直是 0

### 5. 文件

- [x] `README.md`：更新流程段（03 / 03A、移除 04）、
      補 `parse_item.status` 三種值與暫存語意、
      記下「bootstrap 不會改既有 CHECK 約束」的限制
- [ ] 對照表 artifact（`page-api-map.html`）步驟 03/04 的說明會失準，
      標註已被 03A 取代 —— **republish 同一個 URL**，不要另建

---

## 不在本輪範圍

- PDF 頁面底圖 / ROI 裁切圖（延後；在有底圖前 03A 匡選只能用單張圖片測）
- 單筆「重新解析」與增量派送（已決定派送後凍結）
- 人工簽核 `execution.review_status`（對照表列的最大缺口，仍未處理）
- `REJECTED` 新流程幾乎用不到（「不解析」＝不建立或直接刪除），但保留該值不動

---

## 驗證

```bash
cd project_folder
python3 -m py_compile $(find app scripts -name '*.py')   # 語法
python3 <scratchpad>/symcheck.py .                       # 跨模組符號解析
python3 <scratchpad>/unused.py .                         # 未使用 import
python3 <scratchpad>/parseall.py                         # 10 張表欄位解析
```

`parseall.py` 會用**真實的** `bootstrap._parse_declared_columns()` 跑過所有 schema 檔，
確認 `parse_item` 仍解析出 13 個欄位、沒被新註解行弄壞
（先前正是這個機制漏掉了帶註解的欄位）。

無法靜態驗證、要人工確認的：

1. 建任務 → 新增 ROI → 該筆 `status` 為 `DRAFT`，任務仍為 `DRAFT`
2. `GET /tasks/{id}/detail` → 暫存項目出現在 `items[]`，`latest_execution` 為 `null`
3. `POST /tasks/{id}/dispatch` → DRAFT 全轉 `READY`，
   每項各建一筆 execution ＋ 一筆 `outbox_event`(`PENDING`)
4. 派送後再 `POST /tasks/{id}/parse-items` → 409 `PARSE_LIST_FROZEN`
5. 派送後再 `dispatch` → 409 `TASK_NOT_DISPATCHABLE`
6. 暫存階段 02 總覽「解析項目」顯示暫存筆數，不是 0

> 本機只有 Python 3.9、沒有 PostgreSQL，真要跑起來需 Python 3.11 + PG。

## 本次實作紀錄（2026-09-06）

- 已完成上述 API、SQL、ORM 預設與 README 修改。
- 兩份 `image_analysis_platform_v2_demo.html` 已加入 03A 取代舊流程的說明；保留原示意畫面。
- `page-api-map.html` 與原發布 URL 未取得，原 URL 重新發布尚未完成。
- 已通過 67 個 Python 模組語法、專案 import 符號與 10 張表的實際 bootstrap 欄位解析；parse_item 仍為 13 欄。
- 未執行資料庫/API 整合驗證：本機 Python 缺專案依賴，Docker socket 無法存取；上述六項流程驗收仍待執行。

## 工作台內容與 Schema 延伸（2026-09-06，待討論）

- [x] v3 整合 anaylisis_demo.html 的 test_31–test_39，分頁對應同一主任務下的 parse_item。
- [x] 保留原圖、渲染版本、最終 JSON、驗證回圈、Per-Lane / Per-Reg 指標與 Verilog。
- [x] 新增工作台讀取與圖片內容 API 程式，人工版本清空舊衍生成果。
- [x] 定義 result_info.workbench JSON 契約與手動 CHECK migration。
- [x] 新增供未來 worker 呼叫的 generated_result_service，不接實體 queue/worker。
- [x] API / schema 設計與 JSON 範例置於 project_folder/docs/。
- [ ] 後端驗證與 DB migration：依使用者要求本次不執行。
- [ ] worker 產生渲染／verification／conversion；實體後端與 HTML 串接。

範圍更新：PDF 頁面縮圖與選頁已加入本機 v3 Demo；未增加伺服器 PDF 轉圖端點。
原先「PDF 本輪不做」僅描述前一輪 API 範圍。


## 主任務清單精簡（2026-09-06）

- [x] GET /tasks 改為全部主任務、外層 items；移除分頁與篩選參數。
- [x] 每項只回 id/name/status/finished_count/started_at/updated_at/item_count；後端先彙整。
- [ ] 正式前端改讀精簡 items，自行算 finished_count/item_count 與四張統計卡。
- [ ] 依使用者要求，後端驗證仍不執行。


## 單筆停止與PDF頁碼檢查（2026-09-06）

- 已確認單筆停止沿用cancel，不做暫停／恢復；再執行建立新execution，其建立端點尚未新增。
- [x] POST／PATCH共用PDF已知page_count上限檢查；超界422 PAGE_OUT_OF_RANGE。
- [ ] 後端驗證依使用者要求不執行。

---

## 下一階段：Publisher → RabbitMQ → Worker（2026-09-06）

本節為最新規劃待辦，尚未實作。先完成交付、執行生命週期與取消規則的設計；前端移植、工作台介接與實際解析流程串接留到移植階段。以下驗收情境先記錄，依使用者要求不執行後端驗證或migration。

### 已確認範圍與現況

- [x] 派送後允許軟刪子項；沿用取消該子項未結束execution及使待送outbox失效的行為。新增／修改ROI仍凍結，刪除是允許的操作。
- [x] 單筆停止沿用 `POST /executions/{execution_id}/cancel`，不做暫停／恢復。
- [x] 有需要再次執行時建立新的execution，不復活CANCELLED；建立新執行的入口與規則尚未實作。
- [x] 現有dispatch同一交易建立execution=CREATED與outbox=PENDING；目前尚未接通publisher／queue／worker。
- [x] 現有generated_result_service是成果寫入入口，不代表已有實體worker。
- [x] 前端、工作台及實際解析介接目前先不做；PDF縮圖仍由前端PDF.js產生。

### P1｜完成訊息與狀態規格

- [ ] 定義訊息最小契約：schema_version、event_id、execution_id；確認event_id對應哪個outbox識別，重送時沿用。
- [ ] 定義worker從DB取得execution.input_data快照的方式；來源、page_no、ROI、流程／模型設定不改讀可變的前端資料。
- [ ] 定義exchange、routing key、queue、持久化、publisher confirm、不可路由訊息處理、consumer manual ACK及prefetch策略。
- [ ] 明訂execution各狀態的更新責任與合法轉移：CREATED → QUEUED → RUNNING → SUCCEEDED／FAILED／TIMEOUT／CANCELLED。
- [ ] 定義outbox／inbox各狀態、識別鍵與交易邊界；收到訊息不等於已成功完成，不能一插入inbox就永久跳過重送。
- [ ] 區分傳輸重送、暫時性錯誤重試與使用者重新執行：傳輸重送不得新增execution；使用者重新執行建立新execution。自動執行重試是否沿用execution，寫入明確規則。
- [ ] 盤點租約、心跳、執行嘗試識別／fencing token是否需新增欄位或約束；確認設計後才修改Schema，不先套用migration。

### P2｜Publisher 可靠交付

- [ ] 定義多publisher原子領取outbox的機制與領取逾時回收，避免同一事件被無限制同時處理。
- [ ] 發送前檢查execution／parse_item／主任務是否已取消或刪除；不再送出失效事件。
- [ ] 發送持久化訊息，取得Broker confirm並確認可路由後，才標記outbox=PUBLISHED。
- [ ] confirm失敗、逾時或不可路由：記錄原因，依退避策略更新下一次可送時間及重試次數。
- [ ] Broker已收到但publisher尚未標記就死亡：允許重送相同event_id，交由worker去重；不宣稱exactly-once交付。
- [ ] execution轉QUEUED採條件更新，不能把已RUNNING／已取消／已結束的狀態改回QUEUED。
- [ ] 定義超過發布重試上限的outbox與execution處置，避免主任務永久等待。

### P3｜Worker 領取、去重與取消

- [ ] 收件後驗證訊息格式與版本；格式錯誤／不支援版本不無限重新入列。
- [ ] 從DB確認execution及其parse_item／主任務關聯；取消、軟刪或不存在時記錄跳過原因並ACK。
- [ ] 已完成／已終止或已完成處理的重複事件：跳過並ACK，不重複產生成果。
- [ ] 使用原子條件更新／列鎖與inbox識別領取執行權；同一execution只能有一個有效執行者。
- [ ] 遇到RUNNING需區分有效租約與已逾期工作，不能直接一律跳過或重新解析。
- [ ] 取得執行權後設定RUNNING／started_at與租約；心跳需驗證目前執行權。
- [ ] 在開始、主要步驟之間及提交結果前檢查取消／軟刪；已取消工作不得再寫SUCCEEDED。
- [ ] 定義不可立即中斷之外部模型呼叫如何處理：回來後丟棄失效結果，不覆寫取消狀態。
- [ ] 新增使用者重新執行規劃：入口、可用狀態、來源快照、並行限制；不直接重用已派送主任務的現有dispatch。

### P4｜結果落地與 ACK 順序

- [ ] 定義worker呼叫解析器的介面：輸入快照、取消檢查、輸出content／workbench／artifact；真實解析器介接留到移植階段。
- [ ] 規劃成果檔寫入流程與 `results/{execution_id}/{result_id}/…` 路徑，避免半成品當成已完成成果。
- [ ] 使用generated_result_service保存結果；保留JSON版本、渲染圖片版本、verification輪次各自的序列。
- [ ] 成果提交時重新驗證execution狀態與執行權；舊租約worker不得提交或覆寫新嘗試結果。
- [ ] 明訂result、execution終態、inbox完成紀錄的同一交易邊界；DB提交成功後才ACK。
- [ ] DB已提交但ACK前死亡：重送可由完成紀錄判斷，ACK且不重複新增result。
- [ ] 檔案已寫但DB未提交、取消或寫入失敗：規劃未引用檔案清理，不能刪除已引用的歷史成果。
- [ ] 定義主任務status／completed_at彙整更新時機，與各API的即時計數保持一致，避免只有execution結束但主任務主表永久停留舊狀態。

### P5｜重試、逾時與崩潰恢復

- [ ] 區分可重試錯誤（暫時網路／服務不可用）與不可重試錯誤（來源損壞／格式錯誤等）。
- [ ] 定義重試次數、退避間隔、執行逾時及超限終態；統一retry_count／max_retry_count語意，不與訊息重送次數混用。
- [ ] 重試工作必須有可靠重新交付機制；新的事件／延迟投遞與原訊息ACK順序需避免工作遺失。
- [ ] 規劃死信或失敗事件留存與人工處理入口；禁止無限nack/requeue循環。
- [ ] 規劃租約逾時掃描／回收與fencing；舊worker恢復後不得提交結果。
- [ ] worker正常關閉時停止收新件並處理手上工作；Broker斷線後重新領取不得造成並行重做。

### P6｜環境、可觀測性與移植交付

- [ ] 列出publisher、worker、RabbitMQ、DB與Storage的連線設定及啟動方式；明確區分開發與正式環境。
- [ ] 確認worker能存取API落地的來源檔案與成果儲存位置，避免只有API容器看得到本機檔案。
- [ ] 日誌統一帶task_id／parse_id／execution_id／event_id／執行嘗試識別；記錄取消跳過、重試及最終失敗原因。
- [ ] 指標涵蓋outbox待送量與延遲、queue積壓、RUNNING租約逾時、重試／取消／失敗數。
- [ ] 整理訊息樣例、狀態轉移表、交易邊界、失敗處理對照與啟動文件，作為移植交接依據。

### 待後續驗收的情境（現在不執行）

- [ ] 正常派送→publisher confirm→worker處理→result提交→ACK。
- [ ] 派送前取消／刪除：事件失效，worker不解析。
- [ ] 已發布但未領取時取消／刪除：worker收件查DB後跳過、ACK。
- [ ] RUNNING期間取消／刪除：後續成果不得把CANCELLED覆寫為成功。
- [ ] 重複訊息／多worker競爭：不產生兩個有效執行者或重複最終結果。
- [ ] publisher confirm前後死亡／worker領取後死亡／DB提交後ACK前死亡均可恢復。
- [ ] worker快於publisher更新DB：RUNNING／終態不被回寫QUEUED。
- [ ] 租約過期後舊worker復活：舊嘗試提交被拒絕。
- [ ] 暫時錯誤重試有上限；不可重試錯誤與毒訊息不無限循環。
- [ ] 成功／失敗／取消混合時，主任務狀態、finished_count、item_count與摘要一致。

執行順序：先完成P1規格，再依P2→P3→P4→P5→P6安排實作。此清單不是本次已完成實作的宣告；是否開始實作另依後續指示。
