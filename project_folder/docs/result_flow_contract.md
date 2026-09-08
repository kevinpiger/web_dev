# 單張圖片解析結果：DRAWER → VERIFY 契約

本文件定義已確認的交替解析歷程及 output。Python schema 為
`app/schemas/result_flow.py`，機器可讀定義為 `result_flow.schema.json`，
完整兩輪範例為 `result_flow.example.json`。

這是新契約定義，尚未接入現有 Agent ResultSubmission、ResultOut、工作台讀寫或 DB。
現有 API 仍採原本的 v2 契約；不會自動接受本文件的新 output。

## 結果與步驟的關係

一個 execution 對應一次單圖解析執行。每筆 result 可保存當下完整 steps 快照；
若保存中間結果，沿用新增 result 與遞增 result.round_no 的方式，不覆蓋舊 result。
同一步驟在不同快照中沿用相同 step.id，sequence 也不重新編號。
result.round_no 是快照版本，不是 drawer 次數或 verify 次數。
最新 result 仍保留從第一次 drawer 到當前步驟的完整流程。
跨快照的歷史不可變性須由接入時的 service 檢查，單份 schema 只檢查當前快照。

完整 result_info 組合方向：保留 source（AI／MANUAL 等來源）及編輯 metadata，
原圖資訊另稱 source_image，避免和既有 source 欄位衝突；新增 steps、
final_drawer_step_id、final_verify_step_id。圖片使用 artifacts 登錄表，
Verilog 與 metrics/table/warnings 保留 conversion，並須關聯 input_drawer_step_id。
ResultFlow schema 僅定義流程部分，不包含外層 result、source_image、artifacts 或 conversion。

## 每一步

| 欄位 | 型別 | 語意 |
|---|---|---|
| id | UUID | 此步驟固定 ID |
| sequence | integer | 整體順序，從 1 連續遞增 |
| type | DRAWER / VERIFY | 決定 output 的 schema |
| input_step_id | UUID / null | 第一個 DRAWER 為 null；其他指向緊接前一步 |
| status | PENDING / RUNNING / SUCCEEDED / FAILED / CANCELLED | 程序狀態 |
| created_at | 有時區 datetime | 建立步驟的時間 |
| started_at / finished_at | 有時區 datetime / null | 實際時間，未提供不可虛構 |
| output | DrawerOutput / VerifyOutput / null | 只有 SUCCEEDED 有完整 output |
| error | {code, message} / null | FAILED 必填，其餘 null |

步驟必須從 DRAWER 開始交替執行，只有 SUCCEEDED 步驟後能接下一步。
失敗／取消的鏈停止；重試應由新的 execution attempt 處理，不在本契約插入連續 DRAWER。
執行中可先保存 RUNNING、output=null；完成後的新快照沿用該 step.id。

## DRAWER output

| 欄位 | 型別 | 說明 |
|---|---|---|
| type | TIMING / REGISTER | 時序波形或暫存器圖 |
| content_type | WAVEDROM | 本版限定 WaveDrom |
| content | object | 完整 WaveDrom JSON，不是修改 patch，也不是 JSON 字串 |
| render_artifact_id | UUID | 此份 content 對應的完整渲染圖，成功時必填 |
| summary | string | 本次產生／修改摘要 |
| changes | DrawerChange[] | 首輪可為 []；後續記錄實際修改 |

DrawerChange：

| 欄位 | 型別 | 說明 |
|---|---|---|
| target | string | 修改位置，例如 signal:ack_i、register:CTRL.EN |
| description | string | 做了什麼修改 |
| suggestion_id | UUID / null | 對應前一 VERIFY 的建議；自行調整可為 null |

TIMING content 必須有 signal 陣列；REGISTER 必須有 reg 陣列。
schema 只驗證此基本結構，完整 WaveDrom 可渲染性仍需 renderer 檢查。
本契約 content 使用 object；目前 ResultSubmission.content 仍為 string，接入時須明確轉換。
artifact_id 對應登錄表中的圖片；公開 API 回傳受權限保護的 content_url，不能回傳 storage_key。
圖片存在性、所屬 execution/result 及內容和圖片是否一致需由 writer 驗證。

## VERIFY output

| 欄位 | 型別 | 說明 |
|---|---|---|
| match | TRUE / PARTIAL / FALSE | 比對結論，字串 enum，非 boolean |
| summary | string | 整體比對說明 |
| checked_at | 有時區 datetime / null | 比對時間 |
| checked_at_display | string / null | 原始報告只有無時區時間時保留原文 |
| diff_count | integer ≥ 0 / null | 差異總數；未知為 null |
| diffs | VerificationDifference[] / null | 完整差異明細；未提供為 null，確認零筆為 [] |
| suggestions | CorrectionSuggestion[] / null | 下次 drawer 的修正建議；未提供為 null，無建議為 [] |

VERIFY 的 input_step_id 指向被驗證的 DRAWER；使用同一原圖／ROI 和該 DRAWER 的 JSON、渲染圖。
沒有必要再存一份容易不同步的 input_drawer_step_id。

VerificationDifference：

| 欄位 | 型別 | 說明 |
|---|---|---|
| id | UUID | 差異 ID |
| category | MISSING / EXTRA / VALUE / TIMING / LAYOUT / OTHER | 差異分類 |
| target | string | 差異位置／訊號／欄位 |
| description | string | 差異說明 |
| expected | string / null | 原圖應呈現的內容描述，未知為 null |
| actual | string / null | 本次輸出的內容描述，未知為 null |

CorrectionSuggestion：

| 欄位 | 型別 | 說明 |
|---|---|---|
| id | UUID | 建議 ID，供下一次 drawer.changes 引用 |
| diff_id | UUID / null | 對應本輪差異；一般建議為 null |
| target | string | 建議修改位置 |
| instruction | string | 具體修正指示 |

提供 diffs 及 diff_count 時，筆數必須相符；只提供筆數時 diffs=null，不能補造明細。
TRUE 不可同時帶有非零差異。PARTIAL/FALSE 表示比對不完全通過，步驟 status 仍可為 SUCCEEDED。
模型崩潰、工具錯誤應是 FAILED + error，不可假裝成 match=FALSE。

## 最終採用與 08 畫面

- final_drawer_step_id：採用哪次成功 DRAWER 的 JSON 與渲染圖。
- final_verify_step_id：該 DRAWER 對應的成功 VERIFY；未驗證可為 null。
- 兩者未定案時可都為 null。最後成功驗證也可能是 PARTIAL/FALSE，不能視為通過。
- 停止條件（TRUE、最大輪數、取消等）由執行流程決定，此 schema 不新增重試／停止策略。
- 08 渲染版本列表來自成功 DRAWER；驗證歷程來自成功 VERIFY，依 sequence 排序。
- 切換 DRAWER 可顯示其 JSON、渲染圖與 changes；驗證依 input_step_id 配對。
- 上方驗證標籤來自所選 DRAWER 對應的 VERIFY，不借用另一版本的 TRUE。
- Verilog、指標、警告必須關聯產生它們的 DRAWER，改 JSON 後不可沿用舊轉換成果。
- 舊報告沒有完整步驟時沿用舊資料呈現，不根據三張圖／兩輪驗證虛構四個或五個步驟。

## 驗證範圍

測試：`python -m unittest discover -s tests -p test_result_flow.py`。
只驗證 Python／Pydantic 契約；未啟動後端、連線 DB、接入 worker 或執行圖片渲染。
