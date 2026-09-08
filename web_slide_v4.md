# 解析平台 v4：畫面 × API × DRAWER／VERIFY 結果契約

更新日期：2026-09-07。由 web_slide_v3 延伸，保留既有頁面與 API 對照。

v4 已移除 09 任務摘要／列印頁，操作流程到 08 解析工作台。

v4 更新重點：08 納入完整 DRAWER → VERIFY → DRAWER → VERIFY 歷程，定義每一步 output、差異／建議／修改關聯與最終結果配對；文末補上模型 flow 基本資料 API。

**狀態請分開閱讀：現有 API 已編輯但未完成整合驗證；v4 流程 schema 已完成契約測試，尚未接入既有 API／worker。**
本次只整理文件與靜態示意畫面，未修改後端、啟動服務或套用 DB。

## 逐頁完成進度

- [x] 01 登入
- [x] 02 任務與檔案
- [x] 03 上傳檔案
- [x] 03A 建立任務／PDF 選頁／ROI／暫存與派送
- [x] 07 執行解析
- [x] 08 解析工作台

04 候選確認移除；05 ROI 編輯與06確認清單併入03A，不恢復獨立頁。

## 共通約定

- 以下路徑省略 `/api/v1`；只有 `/health` 不加此前綴。
- 除 login／refresh／logout 外，業務 API 帶 `Authorization: Bearer <access_token>`。使用者歸屬由 token 決定，不從 body 傳 user_id。
- JSON 寫入帶 `Content-Type: application/json`；上傳用 multipart/form-data，由瀏覽器自行設定 boundary。
- UUID 參數為 UUID 字串；datetime 為日期時間字串。範例僅說明格式，不代表資料庫實際資料。
- 「可省略」表示請求可不送；「可為 null」表示值可空，兩者不同。GET 與 DELETE 下文若未列 body，代表無 body。
- 業務錯誤格式：`{"error":{"code":"…","message":"…"}}`。Pydantic／FastAPI 的請求格式錯誤仍可能使用預設 `{"detail":[…]}`，不可假設所有422都同格式。
- 本轮只有 GET /tasks 取消分頁；GET /assets 和 GET /executions 保留 page／page_size。
- 下列型別定義是實際欄位清單；引用型別時依同文定義展開，不代表 API 只回型別名稱。


## 01｜登入

### 對應操作畫面

以下直接由目前 v3 Demo 的畫面產生函式輸出，為靜態HTML展示，並非截圖或已串接後端的操作介面。

[操作畫面：01 登入](screen_previews_v4/01.html)

### 畫面與觸發

電子郵件＋密碼 → 登入成功 → 02總覽。v3 的登入目前只跳轉畫面，沒有真實身分驗證；SSO／忘記密碼／記住我不在目前畫面。

### API 傳入／傳出

| 操作 | API | 傳入 | 成功回傳 |
|---|---|---|---|
| 按登入 | POST /auth/login | body：email:string（必填，Email格式）、password:string（必填）；無path/query | 200 TokenResponse |
| access到期 | POST /auth/refresh | body：refresh_token:string（必填）；無path/query | 200 TokenResponse，包含新的refresh token |
| 載入目前使用者 | GET /auth/me | Bearer；無path/query/body | 200 UserOut |
| 登出（全站操作） | POST /auth/logout | body：refresh_token:string（必填）；無path/query | 204，無body |

```json
{
  "email": "demo@example.com",
  "password": "使用者輸入的密碼"
}
```

**TokenResponse 完整欄位**

| 欄位 | 型別 | 意義 |
|---|---|---|
| access_token | string | 後續 API 使用 |
| refresh_token | string | 更新登入憑證使用 |
| token_type | string | 預設 bearer |
| expires_in | integer | access token 有效秒數 |
| user | UserOut | 使用者與角色資料 |

**UserOut 完整欄位**：`id:UUID`、`username:string`、`email:string`、`employee_no:string|null`、`organization:string|null`、`role:string`（角色代碼，如 ADMIN／USER／REVIEWER）。

### 欄位對應與交互

| 畫面／行為 | 資料來源／寫入 |
|---|---|
| 登入帳號 | iam.app_user.email |
| 密碼比對 | iam.app_user.password_hash，不回傳hash |
| 使用者角色 | iam.app_user.role_id → iam.role.code |
| 登入／refresh成功 | app_user.token保存refresh token雜湊；token_expire_at保存效期 |
| 登入時間 | app_user.last_login_at |

### 異常與缺口

- 帳號不存在、停用或密碼錯誤：401 UNAUTHORIZED；不要向使用者區分帳號是否存在。
- refresh無效／到期：401；前端回登入頁。新refresh token會取代舊值。
- v3 尚需接 login／refresh／me／logout 與 token生命週期；不在此規格追加SSO等端點。
- 本文件描述既有行為；尚未執行後端驗證。

依據：`router/auth.py`、`schemas/auth.py`、`services/auth_service.py`、v3 `login()`。


## 02｜任務與檔案

### 對應操作畫面

以下直接由目前 v3 Demo 的畫面產生函式輸出，為靜態HTML展示，並非截圖或已串接後端的操作介面。

[操作畫面：02 解析任務](screen_previews_v4/02.html)

[操作畫面：02 檔案庫](screen_previews_v4/02_files.html)

### 畫面與觸發

解析任務／檔案庫兩個分頁。主任務總覽每列以analysis_task為主體，不是把parse_item攤平成任務列表。四卡由前端對全部主任務分類；備註不再包含於精簡清單，Demo若保留備註顯示需另取detail或移除。

### 02-A 解析任務：API 傳入／傳出

| 操作 | API | 傳入 | 成功回傳 |
|---|---|---|---|
| 載入全部主任務 | GET /tasks | Bearer；無path、query、body；不再有page/page_size/status參數 | 200 TaskListResponse，只有items |
| 新增主任務 | POST /tasks | body：TaskCreate，見下表 | 201 TaskOut |
| 點入／繼續編輯 | GET /tasks/{task_id}/detail | path task_id:UUID（必填）；無query/body | 200 TaskDetail |
| 只讀主任務資料（備用） | GET /tasks/{task_id} | path task_id:UUID（必填）；無query/body | 200 TaskOut；沒有子項目清單 |
| 改名／備註（03A也用） | PATCH /tasks/{task_id} | path task_id:UUID；body：TaskUpdate | 200 TaskOut |
| 中斷（目前主要在07） | POST /tasks/{task_id}/cancel | path task_id:UUID；無query/body | 200 TaskOut |
| 刪除（API有，v3總覽尚無完整選單） | DELETE /tasks/{task_id} | path task_id:UUID；無query/body | 204，無body；軟刪 |

**GET /tasks 已確認的完整回應**

```json
{
  "items": [
    {
      "id": "f44ec0a2-f980-4a19-a695-69f0f26c7aa1",
      "name": "Datasheet 解析任務",
      "status": "RUNNING",
      "finished_count": 7,
      "started_at": "2026-09-06T10:00:00+08:00",
      "updated_at": "2026-09-06T10:05:00+08:00",
      "item_count": 10
    }
  ]
}
```

| items[]欄位 | 型別 | 後端彙整／前端用途 |
|---|---|---|
| id | UUID | analysis_task.id；點進detail |
| name | string | analysis_task.name |
| status | string | 單一彙整狀態：DRAFT、READY、DISPATCHED、RUNNING、COMPLETED、FAILED、CANCELLED |
| finished_count | integer | 有效parse_item最新execution為SUCCEEDED／FAILED／TIMEOUT／CANCELLED的筆數 |
| started_at | datetime|null | 主任務下歷次execution最早的實際started_at；未開始null |
| updated_at | datetime | 主任務及parse_item／execution／result最新更新，納入軟刪子項活動 |
| item_count | integer | 未軟刪且DRAFT／READY項目數，排除REJECTED |

- 只回目前使用者全部未刪除主任務，依彙整updated_at由新到舊排序；空清單為`{"items":[]}`。
- 不回total／page／page_size／progress_percent／config／description／display_status等欄位。
- 前端百分比＝`item_count > 0 ? finished_count / item_count * 100 : 0`；四捨五入由前端處理。
- 建議四卡映射：全部＝items.length；暫存中＝DRAFT；等待／執行中＝READY＋DISPATCHED＋RUNNING；已完成＝COMPLETED。FAILED／CANCELLED仍在全部中，但不算成功完成，因此四卡不是四個互斥分類相加。
- 彙整status規則：DRAFT／READY保留；主任務明確FAILED／CANCELLED優先；全部有效項目結束時，有失敗→FAILED，其次有取消→CANCELLED，否則COMPLETED；尚未全部結束但已有執行／結束項目→RUNNING；全待執行→DISPATCHED。

**TaskCreate／TaskUpdate 請求欄位**

| 欄位 | 型別 | POST建立 | PATCH修改 |
|---|---|---|---|
| name | string | 必填，1–255字元 | 可省略；提供字串時1–255字元 |
| description | string|null | 可省略，預設null | 可省略；現有service忽略null，清空可送空字串 |
| config | object | 可省略，預設{} | 可省略；只有DRAFT／READY可改，派送後凍結 |

**TaskOut 完整回應欄位**（建立、修改、單任務讀取、中斷與detail.task仍使用；未跟清單一起精簡）

| 欄位 | 型別 |
|---|---|
| id、name | UUID、string |
| description | string|null |
| status、display_status | string、string（後者PENDING／RUNNING／FAILED／COMPLETED／CANCELLED） |
| config | object |
| dispatched_at、completed_at | datetime|null |
| created_at、updated_at | datetime |
| progress | TaskProgress |

**TaskProgress 完整欄位**：`item_count`、`pending`、`running`、`succeeded`、`failed`、`cancelled`、`percent`，皆integer。failed包含TIMEOUT；percent按成功＋失敗＋取消計。這是detail等端點的型別，不是精簡清單額外回傳的欄位。

**TaskDetail 完整結構**

```text
TaskDetail
├─ task: TaskOut
└─ items: TaskItemDetail[]（指定主任務全部有效、未軟刪子項，不分頁）
   ├─ parse_item: ParseItemOut（完整欄位見03A）
   ├─ latest_execution: ExecutionOut|null（完整欄位見07）
   ├─ result_round_count: integer（最新execution的JSON結果筆數）
   └─ latest_result: ResultOut|null（完整欄位見08）
```

### 02-B 檔案庫：API 傳入／傳出

| 操作 | API | 傳入 | 成功回傳 |
|---|---|---|---|
| 載入檔案庫 | GET /assets | query：page:int=1（≥1）、page_size:int=20（1–100）、file_type:string可省略、status:string可省略；無body | 200 `{items:AssetOut[],total:int,page:int,page_size:int}` |
| 看單檔資訊（需要時） | GET /assets/{asset_id} | path asset_id:UUID；無query/body | 200 AssetOut |
| 上傳 | POST /assets | multipart files:檔案陣列，詳03 | 200 AssetUploadResponse |
| 移除來源 | DELETE /assets/{asset_id} | path asset_id:UUID；無query/body | 204，無body |

AssetOut完整欄位見03。檔案庫分頁維持既有契約；只有主任務清單取消分頁。

### 資料來源、異常與缺口

- analysis_task → parse_item → 各項最新execution → result；清單只回彙整七欄，點detail才取子項內容。
- 進行中刪除主任務：409 TASK_STILL_ACTIVE，先取消。派送後改config：409 TASK_CONFIG_FROZEN。不存在／無權存取：404。
- 任務名稱與備註可在派送後修改，解析清單不能。
- 待前端串接：精簡items、四卡與百分比、沒有description的列表呈現，以及檔案庫分頁。
- 當目前只有部份成功、有失敗或取消時，07顯示任務摘要；不把finished_count標為「成功數」。

依據：`router/tasks.py`、`schemas/task.py`、`services/task_service.py`、`repositories/analysis_task_repository.py`、`router/assets.py`、v3 `overview()`／`fileTable()`。


## 03｜上傳檔案

### 對應操作畫面

以下直接由目前 v3 Demo 的畫面產生函式輸出，為靜態HTML展示，並非截圖或已串接後端的操作介面。

[操作畫面：03 上傳檔案](screen_previews_v4/03.html)

### 畫面與觸發

單純加入檔案庫，尚不綁主任務。asset直到03A建立parse_item時才經asset_id與task_id產生關聯。03A中的「上傳新檔」使用同一支API。

### API 傳入／傳出

| 操作 | API | 傳入 | 成功回傳 |
|---|---|---|---|
| 上傳已選檔案 | POST /assets | multipart欄位`files`（必填，list[UploadFile]，同名欄位重複送各檔）；無path/query，不送task_id | 200 AssetUploadResponse |
| 移除已上傳檔案 | DELETE /assets/{asset_id} | path asset_id:UUID；無query/body | 204，無body |
| 重新載入檔案庫 | GET /assets | query同02：page=1、page_size=20、file_type/status可省略 | 200 Page[AssetOut] |

前端上傳示意：

```javascript
const form = new FormData();
for (const file of selectedFiles) form.append('files', file);
// fetch('/api/v1/assets', {method:'POST', headers:{Authorization:...}, body:form})
// 不自行設定 multipart Content-Type，讓瀏覽器加入 boundary。
```

**AssetUploadResponse 完整結構**

```text
{
  succeeded: AssetOut[],
  failed: [{file_name:string, error_code:string, message:string}]
}
```

**AssetOut 完整欄位**

| 欄位 | 型別 | 說明 |
|---|---|---|
| id | UUID | 後續使用的asset_id |
| file_name | string | 原始檔名 |
| file_type | string | 如PDF／IMAGE；不代表所有enum格式都開放上傳 |
| mime_type | string|null | 檔案媒體型別 |
| file_size | integer|null | 位元組；前端轉成KB／MB |
| status | string | UPLOADING／READY／FAILED |
| attributes | object | PDF可包含page_count；其他內容依來源類型 |
| created_at | datetime | 建立時間 |

回應例（格式示意）：

```json
{
  "succeeded": [
    {
      "id": "21e27b47-4cc8-487a-94d0-524e229f25e9",
      "file_name": "datasheet.pdf",
      "file_type": "PDF",
      "mime_type": "application/pdf",
      "file_size": 120000,
      "status": "READY",
      "attributes": {"page_count": 12},
      "created_at": "2026-09-06T10:00:00+08:00"
    }
  ],
  "failed": [
    {"file_name":"notes.txt","error_code":"UNSUPPORTED_EXTENSION","message":"不支援的副檔名（示意）"}
  ]
}
```

### 資料流與異常

- 使用者選檔 → API逐檔處理 → Storage保存原檔＋core.asset保存metadata → 前端以succeeded與failed更新清單。
- 多檔可部分成功；HTTP 200不能直接顯示「全部上傳成功」。即使全部失敗也要看failed內容。
- 已識別的逐檔錯誤碼：UNSUPPORTED_EXTENSION、UPLOAD_FAILED、FILE_TOO_LARGE；請求本身格式錯誤仍可能422。
- 尚未上傳的檔案取消選取只改前端狀態；已上傳檔案移除才用DELETE。
- DELETE為軟刪，既有任務不因此失去來源內容；後續從工作台source/content讀取，詳08。
- 後端預設允許pdf/png/jpg/jpeg、每檔200MB（可配置）；Demo目前每檔2MB。正式前端需對齊限制。
- PDF縮圖、頁面底圖由前端PDF.js產生，不新增後端頁面預覽API。

依據：`router/assets.py`、`schemas/asset.py`、`services/asset_service.py`、`config.py`、v3 `addFiles()`。


## 03A｜建立任務／選頁／ROI／暫存與派送

### 對應操作畫面

以下直接由目前 v3 Demo 的畫面產生函式輸出，為靜態HTML展示，並非截圖或已串接後端的操作介面。

[操作畫面：03A 圖片预覽與ROI編輯](screen_previews_v4/03A.html)

### 畫面與觸發

選既有檔或上傳新檔 → 圖片直接在右側預覽；PDF先顯示前端PDF.js縮圖 → 點頁面 → 框選／命名 → 逐筆暫存 → 確認派送全部。

### API 傳入／傳出

| 操作 | API | 傳入 | 成功回傳 |
|---|---|---|---|
| 初始化主任務 | POST /tasks | body TaskCreate，詳02 | 201 TaskOut |
| 恢復任務 | GET /tasks/{task_id}/detail | path task_id:UUID；無query/body | 200 TaskDetail，完整欄位詳02 |
| 既有可用檔案 | GET /assets | query status=READY；page=1、page_size=20；file_type可省略 | 200 Page[AssetOut]，詳02／03 |
| 上傳新檔 | POST /assets | multipart files，詳03 | 200 AssetUploadResponse |
| 取得檔案資訊 | GET /assets/{asset_id} | path asset_id:UUID；無query/body | 200 AssetOut |
| 取得預覽原檔 | GET /assets/{asset_id}/content | path asset_id:UUID；Bearer；無query/body | 200 binary stream；Content-Type依mime_type（缺省application/octet-stream）；Content-Disposition為attachment |
| 更新名稱／備註 | PATCH /tasks/{task_id} | path task_id:UUID；body TaskUpdate，詳02 | 200 TaskOut |
| 新增一批ROI | POST /tasks/{task_id}/parse-items | path task_id:UUID；body `{items:ParseItemCreate[]}`，items至少1筆 | 201 ParseItemOut[]，裸陣列 |
| 只讀子項清單（detail替代方案） | GET /tasks/{task_id}/parse-items | path task_id:UUID；無query/body | 200 ParseItemOut[]，無分頁 |
| 讀單一ROI | GET /parse-items/{parse_item_id} | path parse_item_id:UUID；無query/body | 200 ParseItemOut |
| 修改ROI | PATCH /parse-items/{parse_item_id} | path parse_item_id:UUID；body ParseItemUpdate | 200 ParseItemOut |
| 刪除ROI | DELETE /parse-items/{parse_item_id} | path parse_item_id:UUID；無query/body | 204，無body；軟刪 |
| 派送全部 | POST /tasks/{task_id}/dispatch | path task_id:UUID；無query/body；不送ROI清單 | 202 DispatchResult |

**ParseItemCreate 完整請求欄位**

| 欄位 | 型別 | 必填／預設 |
|---|---|---|
| asset_id | UUID | 必填 |
| page_no | integer ≥1 | 可省略，預設1；圖片前端固定1，PDF填選定頁 |
| name | string|null | 可省略，預設null；最多255字元 |
| x、y | number | 可省略，預設0、0 |
| width、height | number | 可省略，預設1、1 |

座標為整頁正規化0–1；寬高須大於0且ROI不能超出頁面。整張解析為0,0,1,1。不要送畫面像素值；Demo的w/h需轉成width/height。

```json
{
  "items": [
    {
      "asset_id": "21e27b47-4cc8-487a-94d0-524e229f25e9",
      "page_no": 2,
      "name": "test_31",
      "x": 0.1,
      "y": 0.2,
      "width": 0.8,
      "height": 0.3
    }
  ]
}
```

**ParseItemUpdate 完整欄位**：`name:string|null`（最多255）、`status:string|null`、`page_no:int|null`（非null時≥1）、`x/y/width/height:number|null`。全部可省略；目前service對null視為不修改。status若提供只能DRAFT／READY／REJECTED；API型別仍為string。不能PATCH asset_id／task_id。

**ParseItemOut 完整欄位**

| 欄位 | 型別 |
|---|---|
| id、task_id、asset_id | UUID |
| asset_file_name | string |
| name | string|null |
| status | string |
| page_no | integer |
| x、y、width、height | number |
| created_at | datetime |

**DispatchResult 完整欄位**：`task_id:UUID`、`task_status:string`、`dispatched_count:int`、`executions:ExecutionOut[]`。ExecutionOut完整欄位見07。202表示已寫入派送資料，不代表AI已開始。

### 資料流與保存規則

1. 名稱／備註存analysis_task；頁碼／ROI／名稱存parse_item，新建status=DRAFT，主任務不自動轉READY。
2. 按暫存不是新的save-all API：前端呼叫POST批次新增、PATCH、DELETE逐筆保存；全部成功才顯示已暫存。
3. 派送前等待所有暫存請求完成；dispatch以DB現有項目為準，不接受前端臨時清單。
4. dispatch取未刪除DRAFT＋READY，排除REJECTED；同一交易把DRAFT轉READY、建立execution=CREATED與outbox=PENDING，主任務轉DISPATCHED。
5. 原檔由帶Bearer的fetch讀Blob；PDF.js在前端產生縮圖／底圖。選頁不打伺服器PDF縮圖API。

### 異常與待確認差異（本次只記錄，未修改）

- 409 PARSE_LIST_FROZEN：派送後POST／PATCH解析項目禁止。
- **DELETE例外**：現有delete_parse_item允許任務任何狀態刪除子項，並取消其未結束execution、使待送事件失效。v3畫面派送後隱藏刪除，但API沒有同樣凍結。需另決定是否保留此管理能力。
- 422 INVALID_ROI／INVALID_STATUS；建立時已知PDF頁數超界為PAGE_OUT_OF_RANGE。
- **頁碼檢查已補齊（未驗證）**：POST與PATCH共用PDF已知總頁數上限檢查；超界回422 PAGE_OUT_OF_RANGE，page_no≥1仍由schema檢查。來源缺少有效page_count時無法據此判斷上限，沿用既有新增行為。
- 409 TASK_NOT_DISPATCHABLE／NO_PARSE_ITEM；404來源或主任務不存在／無權。
- 大量縮圖、加密PDF、损壞檔案、縮圖載入失敗是前端處理範圍。单筆停止沿用cancel，不做暫停／恢復；若需再次執行，建立新execution，不復活CANCELLED。建立新執行的端點尚未新增；增量派送不在本輪。

依據：`router/parse_items.py`、`schemas/parse_item.py`、`services/parse_item_service.py`、`router/executions.py`、`services/execution_service.py`、v3 `editor()`／PDF helpers。


## 07｜執行解析

### 對應操作畫面

以下直接由目前 v3 Demo 的畫面產生函式輸出，為靜態HTML展示，並非截圖或已串接後端的操作介面。

[操作畫面：07 執行解析](screen_previews_v4/07.html)

### 畫面與觸發

派送後讀取主任務全部子項最新狀態，執行中輪詢、全部結束後顯示任務摘要。正式前端不保留Demo的「推進解析」模擬按鈕。

### API 傳入／傳出

| 操作 | API | 傳入 | 成功回傳 |
|---|---|---|---|
| 首次／輪詢進度 | GET /tasks/{task_id}/detail | path task_id:UUID；無query/body | 200 TaskDetail，完整結構見02；含task.progress及每項latest_execution/latest_result |
| 派送（由03A觸發） | POST /tasks/{task_id}/dispatch | path task_id:UUID；無query/body | 202 DispatchResult，詳03A |
| 查執行歷史（需要時） | GET /executions | query：page:int=1（≥1）、page_size:int=20（1–100）、task_id:UUID可省略、parse_id:UUID可省略、status:string可省略 | 200 `{items:ExecutionOut[],total:int,page:int,page_size:int}` |
| 查單次執行（需要時） | GET /executions/{execution_id} | path execution_id:UUID；無query/body | 200 ExecutionOut |
| 中斷主任務 | POST /tasks/{task_id}/cancel | path task_id:UUID；無query/body | 200 TaskOut，包含更新後progress；不是CancelResult |
| 中斷單次執行（已確認沿用） | POST /executions/{execution_id}/cancel | path execution_id:UUID；無query/body | 200 CancelResult |

**ExecutionOut 完整欄位**

| 欄位 | 型別 | 用途 |
|---|---|---|
| id、parse_id | UUID | 執行ID與對應解析項目 |
| status | string | CREATED／QUEUED／RUNNING／SUCCEEDED／FAILED／TIMEOUT／CANCELLED |
| retry_count、max_retry_count | integer | 重試資訊 |
| flow_id、flow_version | string|null | 流程版本 |
| model_id、model_version | string|null | 模型版本 |
| input_data | object | 派送時輸入快照；此欄在schema是開放object，非前端進度必需欄位 |
| queued_at、started_at、finished_at | datetime|null | 排隊、實際開始、結束時間 |
| error_code、error_message | string|null | 失敗說明 |
| review_status | string | PENDING／CONFIRMED／REJECTED；目前已可讀，尚無簽核寫入API |
| created_at | datetime | 建立時間 |

**CancelResult 完整欄位**：`task_id:UUID|null`、`task_status:string|null`、`cancelled_executions:int`。目前單筆取消回應示意：

```json
{
  "task_id": null,
  "task_status": null,
  "cancelled_executions": 1
}
```

### 前端如何使用回應

| 畫面 | 來源 |
|---|---|
| 主任務名稱／狀態 | detail.task.name／status／display_status |
| 項目名稱／來源檔／頁碼 | items[].parse_item.name／asset_file_name／page_no |
| 每項執行狀態 | items[].latest_execution.status；null代表尚未派送 |
| 處理進度 | detail.task.progress.percent；成功＋失敗＋取消，不是成功率 |
| 成功／失敗／取消数 | progress.succeeded／failed／cancelled，failed含TIMEOUT |
| 查看結果 | latest_result存在時可進08；無結果仍可顯示08空狀態 |
| 錯誤原因 | latest_execution.error_code／error_message |

輪詢3–5秒是建議前端策略，不是API參數。停止條件看各項execution是否全部terminal，並處理主任務取消／失敗；不要只等task.status=COMPLETED。GET /tasks的精簡清單用finished_count/item_count算進度；本頁detail仍保留完整TaskProgress。

### 真正解析流程與缺口

- dispatch只建立execution=CREATED及runtime.outbox_event=PENDING；publisher／RabbitMQ／worker尚待串接。
- worker未接通時狀態不會自己變為RUNNING／SUCCEEDED。
- generated_result_service是內部writer，不是HTTP端點，也不是已完成的worker。
- 取消會更新DB狀態及待送事件；是否停止已在外部運行的運算，仍需worker配合檢查。
- 409 EXECUTION_NOT_CANCELLABLE／TASK_NOT_CANCELLABLE：已結束等不可取消狀態；404不存在或无權。
- v3目前只模擬成功進度；失敗／timeout／取消的完整呈現與任務摘要入口待前端調整。

依據：`router/executions.py`、`schemas/execution.py`、`services/execution_service.py`、`services/task_service.py`、v3 `run()`／`advance()`。


## 08｜解析工作台

### v4 已確認：完整解析歷程屬於 result

本章前半是 **v4 新契約（已定義 schema，尚未接入 API／worker）**；後半保留現有 API 與 v3 畫面作為接入對照。
v4 是文件版本，不代表現有 `/api/v1` 已升版，也不代表既有 ResultOut 已回傳 steps。

[操作畫面：08 v4 DRAWER／VERIFY output 示意](screen_previews_v4/08_v4_flow.html)

### 08 畫面與 result 資料對應

| 畫面區塊 | v4 資料來源 | 顯示／切換規則 |
|---|---|---|
| 原圖／解析範圍 | source_image：asset_id、file_name、page_no、roi、asset_content_url、preview_artifact_id | 同一次 execution 共用原始輸入；圖片讀取仍須權限 |
| 渲染版本 | steps 中成功的 DRAWER.output.render_artifact_id | 依 sequence 排序，從 artifacts 找圖片連結 |
| WaveDrom JSON | 所選 DRAWER.output.content | 新契約為 object，與該步渲染圖配對 |
| 修改說明 | DRAWER.output.summary、changes[] | 可追溯前一 VERIFY 的 suggestion_id |
| 驗證結論 | 指向所選 DRAWER 的 VERIFY.output.match | TRUE／PARTIAL／FALSE；沒有驗證顯示未驗證 |
| 驗證歷程 | steps 中成功的 VERIFY.output | 顯示時間、差異數、差異及修正建議 |
| 執行錯誤 | step.status、step.error | 工具失敗與比對 FALSE 分開顯示 |
| 最終成果 | final_drawer_step_id、final_verify_step_id | 必須是相互配對的成功步驟，不推測最後一筆就是驗證通過 |
| Verilog／指標 | conversion，需關聯 input_drawer_step_id | 沿用下方 Conversion 的 code／metrics／table／warnings；未產生為 null |
| 歷史結果版本 | result.round_no | 完整 steps 快照版本；不是 drawer 或 verify 的輪數 |

上述 source_image 與 conversion 關聯是接入目標；本次強型別 schema 範圍為 steps 及最終步驟指標。
source_image 的 roi 沿用 normalized x/y/width/height；artifacts 沿用公開 ArtifactOut（id、media_type、content_url）。
既有 result_info.source 保留 AI／MANUAL 來源語意，原圖資訊不用同名 source 欄位。

### latest_result 與現有 API 的差異

| 項目 | 現有程式 | v4 接入目標 |
|---|---|---|
| latest_result | ResultOut，僅公開 result_info，移除內部 workbench | 最新結果快照中包含完整交替歷程及最終指標 |
| content | result_info.content 是 JSON 字串 | 每次 DRAWER.output.content 是完整 JSON object |
| 渲染與驗證 | render_versions 與 verification.rounds 分開存放 | 依 steps.sequence 與 input_step_id 明確配對 |
| Agent 寫入 | ResultSubmission 接受現有 content／workbench | 待接入新 steps 契約、artifact 與跨快照檢查 |
| 人工編輯 | ResultAppend 新增 result 並清空衍生成果 | 保留既有行為；如何表達成新步驟尚未定義，不冒充 AI DRAWER |
| 舊資料 | 可顯示歷史圖、最終 JSON、驗證紀錄 | 保留舊契約讀取，不虛構不存在的 drawer／verify 步驟 |

目前沒有新增 API 路徑，也沒有變更現有 API 的成功回應；下方 Swagger 展開卡與文末回應範例仍是現行契約。

### 結果與步驟的關係

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

### 每一步

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

### DrawerOutput 完整欄位

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

### VerifyOutput 完整欄位

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

### 最終採用與 08 畫面

- final_drawer_step_id：採用哪次成功 DRAWER 的 JSON 與渲染圖。
- final_verify_step_id：該 DRAWER 對應的成功 VERIFY；未驗證可為 null。
- 兩者未定案時可都為 null。最後成功驗證也可能是 PARTIAL/FALSE，不能視為通過。
- 停止條件（TRUE、最大輪數、取消等）由執行流程決定，此 schema 不新增重試／停止策略。
- 08 渲染版本列表來自成功 DRAWER；驗證歷程來自成功 VERIFY，依 sequence 排序。
- 切換 DRAWER 可顯示其 JSON、渲染圖與 changes；驗證依 input_step_id 配對。
- 上方驗證標籤來自所選 DRAWER 對應的 VERIFY，不借用另一版本的 TRUE。
- Verilog、指標、警告必須關聯產生它們的 DRAWER，改 JSON 後不可沿用舊轉換成果。
- 舊報告沒有完整步驟時沿用舊資料呈現，不根據三張圖／兩輪驗證虛構四個或五個步驟。

### 驗證範圍

測試：`python -m unittest discover -s tests -p test_result_flow.py`。
只驗證 Python／Pydantic 契約；未啟動後端、連線 DB、接入 worker 或執行圖片渲染。


### 完整兩輪 steps 範例（v4 契約示意）

以下是 ResultFlow 的完整 JSON，可直接通過本次 Pydantic schema。schema_version=1 是流程子契約版本，
不代表既有 result_info.schema_version=2 已改版。接入整體 result_info 時需另處理版本封裝。

```json
{
  "schema_version": 1,
  "steps": [
    {
      "id": "00000000-0000-0000-0000-000000000001",
      "sequence": 1,
      "input_step_id": null,
      "status": "SUCCEEDED",
      "created_at": "2026-09-07T00:00:00Z",
      "started_at": null,
      "finished_at": null,
      "error": null,
      "type": "DRAWER",
      "output": {
        "type": "TIMING",
        "content_type": "WAVEDROM",
        "content": {
          "signal": [
            {
              "name": "ack_i",
              "wave": "0.....1."
            }
          ]
        },
        "render_artifact_id": "00000000-0000-0000-0000-00000000000a",
        "summary": "Initial extraction",
        "changes": []
      }
    },
    {
      "id": "00000000-0000-0000-0000-000000000002",
      "sequence": 2,
      "input_step_id": "00000000-0000-0000-0000-000000000001",
      "status": "SUCCEEDED",
      "created_at": "2026-09-07T00:01:00Z",
      "started_at": null,
      "finished_at": null,
      "error": null,
      "type": "VERIFY",
      "output": {
        "match": "FALSE",
        "summary": "ack_i is one beat early",
        "checked_at": null,
        "checked_at_display": null,
        "diff_count": 1,
        "diffs": [
          {
            "id": "00000000-0000-0000-0000-000000000014",
            "category": "TIMING",
            "target": "signal:ack_i",
            "description": "Rising edge is early",
            "expected": "Rise at beat 7",
            "actual": "Rise at beat 6"
          }
        ],
        "suggestions": [
          {
            "id": "00000000-0000-0000-0000-000000000015",
            "diff_id": "00000000-0000-0000-0000-000000000014",
            "target": "signal:ack_i",
            "instruction": "Move rising edge one beat later"
          }
        ]
      }
    },
    {
      "id": "00000000-0000-0000-0000-000000000003",
      "sequence": 3,
      "input_step_id": "00000000-0000-0000-0000-000000000002",
      "status": "SUCCEEDED",
      "created_at": "2026-09-07T00:03:00Z",
      "started_at": null,
      "finished_at": null,
      "error": null,
      "type": "DRAWER",
      "output": {
        "type": "TIMING",
        "content_type": "WAVEDROM",
        "content": {
          "signal": [
            {
              "name": "ack_i",
              "wave": "0......1"
            }
          ]
        },
        "render_artifact_id": "00000000-0000-0000-0000-00000000000b",
        "summary": "Corrected ack_i timing",
        "changes": [
          {
            "target": "signal:ack_i",
            "description": "Moved rising edge one beat later",
            "suggestion_id": "00000000-0000-0000-0000-000000000015"
          }
        ]
      }
    },
    {
      "id": "00000000-0000-0000-0000-000000000004",
      "sequence": 4,
      "input_step_id": "00000000-0000-0000-0000-000000000003",
      "status": "SUCCEEDED",
      "created_at": "2026-09-07T00:04:00Z",
      "started_at": null,
      "finished_at": null,
      "error": null,
      "type": "VERIFY",
      "output": {
        "match": "TRUE",
        "summary": "Matches source",
        "checked_at": null,
        "checked_at_display": null,
        "diff_count": 0,
        "diffs": [],
        "suggestions": []
      }
    }
  ],
  "final_drawer_step_id": "00000000-0000-0000-0000-000000000003",
  "final_verify_step_id": "00000000-0000-0000-0000-000000000004"
}
```

### 接入待辦與驗證邊界

- 已完成：DRAWER／VERIFY output 定義、流程 schema、最終配對規則、9 項契約測試、兩輪範例。
- 待接入：Agent 寫入、完整 result_info 封裝、跨快照不可變性、artifact 檔案驗證、latest_result 公開序列化與工作台讀取。
- 待接入：conversion 與 drawer 關聯、前端 step 切換、舊資料雙格式讀取、人工編輯與新流程的銜接。
- 未部署：未修改 DB，未啟動後端／worker，未執行 API 或模型整合測試。

### 以下為現行 API／v3 畫面对照

下列原圖、歷史渲染與驗證圖是既有 v3 Demo。三張歷史渲染圖不表示三次已知 DRAWER；
以下規格只描述現在的程式，與上方 v4 接入目標分開閱讀。

### 對應操作畫面

以下直接由目前 v3 Demo 的畫面產生函式輸出，為靜態HTML展示，並非截圖或已串接後端的操作介面。

[操作畫面：08 原圖與渲染](screen_previews_v4/08.html)

[操作畫面：08 驗證歷程](screen_previews_v4/08_verify.html)

[操作畫面：08 Verilog與指標](screen_previews_v4/08_convert.html)

### 畫面與觸發

同一主任務下，以parse_item.id作分頁key、name顯示test_XX。選項目／JSON版本 → 取得工作台 → 原圖與渲染／驗證歷程／Verilog與指標。編輯JSON由前端即時渲染；按「確認」才寫入新result版本。

### API 傳入／傳出

| 操作 | API | 傳入 | 成功回傳 |
|---|---|---|---|
| 建立上方test_XX分頁 | GET /tasks/{task_id}/detail | path task_id:UUID；無query/body | 200 TaskDetail，詳02；items包括無execution/result項目 |
| 選項目／JSON版本 | GET /parse-items/{parse_id}/workbench | path parse_id:UUID；query execution_id:UUID可省略、result_id:UUID可省略；無body | 200 WorkbenchOut，完整欄位如下 |
| 選歷史執行（API有，Demo未提供選擇器） | GET /executions | query parse_id:UUID、page=1、page_size=20；其他query見07 | 200 Page[ExecutionOut] |
| 只讀結果列表（workbench已帶，可省略重複呼叫） | GET /parse-items/{parse_item_id}/results | path parse_item_id:UUID；無query/body；此端點不能帶execution_id切換歷史執行 | 200 ResultOut[]；最新execution，由舊到新 |
| 讀來源原檔 | GET /parse-items/{parse_id}/source/content | path parse_id:UUID；Bearer；無query/body | 200 binary FileResponse；媒體型別依原檔 |
| 讀裁切／渲染圖 | GET /results/{result_id}/artifacts/{artifact_id}/content | path result_id:UUID、artifact_id:UUID；Bearer；無query/body | 200 binary FileResponse；PNG/JPEG/WebP |
| 編輯時即時預覽 | 前端渲染，無API | 編輯器當前JSON | 前端SVG／畫面；不寫DB、不代表比對驗證 |
| 按確認儲存 | POST /parse-items/{parse_item_id}/results | path parse_item_id:UUID；body ResultAppend | 201 ResultOut，新版本 |

source／artifact回應帶`Cache-Control: private, no-store`與`X-Content-Type-Options: nosniff`。前端用帶Authorization的fetch讀Blob，再建立Object URL；不要把token放網址。切換後釋放不用的Object URL。

### WorkbenchOut 完整回應欄位

| 欄位 | 型別 | 說明 |
|---|---|---|
| parse_item | ParseItemOut | 完整欄位見03A |
| source | WorkbenchSource | 原始來源資訊，見下表 |
| execution | ExecutionOut|null | 選定執行；完整欄位見07 |
| selected_result | ResultOut|null | 選定JSON內容版本 |
| results | ResultOut[] | 選定execution全部結果版本 |
| data_status | string | NO_EXECUTION／NO_RESULT／LEGACY／AVAILABLE／STALE／INVALID |
| artifacts | ArtifactOut[] | 該結果可讀圖片清單 |
| render_versions | RenderVersion[] | 圖片版本清單，與JSON版本獨立 |
| verification | Verification | 比對摘要與各輪紀錄 |
| conversion | Conversion|null | Verilog與轉換指標 |

**WorkbenchSource完整欄位**：`asset_id:UUID`、`file_name:string`、`page_no:int`、`asset_content_url:string`、`preview_artifact:ArtifactOut|null`。

**ArtifactOut完整欄位**：`id:UUID`、`media_type:string`（image/png、image/jpeg、image/webp）、`content_url:string`。不包含storage_key。

**RenderVersion完整欄位**：`id:UUID`、`label:string`、`artifact_id:UUID`、`note:string|null`、`result_id:UUID|null`。artifact_id用於找到ArtifactOut；result_id不明時null，不按v01名稱猜測JSON關聯。

**Verification完整欄位**

| 欄位 | 型別 | 說明 |
|---|---|---|
| status | string | NOT_RUN／RUNNING／COMPLETED／FAILED |
| match | string|null | TRUE／PARTIAL／FALSE；只有COMPLETED才有最終match |
| rounds | VerificationRound[] | 獨立驗證紀錄序列 |

**VerificationRound完整欄位**：`round_no:int≥1`、`match:TRUE|PARTIAL|FALSE`、`checked_at:datetime|null`、`checked_at_display:string|null`、`diff_count:int|null`（非負）、`diffs:object[]|null`、`input_result_id:UUID|null`。時間原文沒有時區時保存checked_at_display，不虛構UTC；diffs=null表示未提供明細。

**Conversion完整欄位**

| 欄位 | 型別 | 說明 |
|---|---|---|
| kind | string | TESTBENCH或REGISTER_DEFINITION |
| language | string | VERILOG |
| code | string | Verilog程式內容 |
| metrics | Metric[] | 每筆`{label:string,value:string|integer|number|null}` |
| table | MetricTable | `{columns:string[],rows:(string|integer|number|null)[][]}`；Per-Lane或Per-Reg |
| warnings | string[]|null | null代表未提供，不等於無警告 |

### 選版本與空狀態

- 不送execution_id：選此parse_item最新execution。不送result_id：選該execution最新result。
- 要看歷史execution中的result，必須一起帶那次execution_id；result_id不能跨選定execution。
- 沒有執行：200 NO_EXECUTION，execution/selected_result=null，results/artifacts/render_versions=[]，conversion=null，verification預設NOT_RUN。
- 有執行但無結果：200 NO_RESULT；若指定不屬於此execution的result_id則404。
- LEGACY：舊JSON沒有workbench；仍可顯示JSON，衍生區塊顯示尚無資料。
- INVALID：workbench格式不符；STALE：content_sha256與內容不符。兩者不顯示衍生資料。
- AVAILABLE：資料契約有效；不等於「已驗證」。人工新版本可AVAILABLE且verification=NOT_RUN。

### 確認編輯：ResultAppend 請求

```json
{
  "execution_id": "e3952bc8-c47b-4617-a8b1-9f708f87efc0",
  "base_result_id": "6c37bca3-d5d8-4bfb-9d14-bc435e3c808c",
  "content_type": "WAVEDROM",
  "type": "TIMING",
  "content": "{\"signal\":[]}",
  "note": "修改時序後確認儲存"
}
```

| 欄位 | 型別 | 必填／預設與用途 |
|---|---|---|
| content | string，至少1字元 | 必填；JSON序列化後的字串，不是直接傳object |
| execution_id | UUID|null | schema可省略；新前端固定送，避免跨執行儲存 |
| base_result_id | UUID|null | schema可省略；新前端固定送編輯前最新result.id，偵測過期編輯 |
| content_type | string|null | 可省略，沿用前一版；目前使用WAVEDROM |
| type | string|null | 可省略，沿用前一版；示範TIMING／REGISTER |
| note | string|null | 可省略，版本修改說明 |

**ResultOut完整回應欄位**：`id:UUID`、`execution_id:UUID`、`round_no:int`、`status:string`、`result_info:object`、`created_at:datetime`。

**本次人工儲存的公開result_info key**

| key | 寫入值／語意 |
|---|---|
| content | 共用的解析結果內容字串；AI與人工版本都用此key |
| type、content_type | 請求值或沿用分類 |
| schema_version | 2 |
| base_result_id | 前一個最新result UUID字串 |
| source | MANUAL |
| note | 使用者備註或null |
| edited_by | 登入使用者UUID字串；後端填，不由前端指定 |
| edited_at | 後端時間字串 |

舊資料或其他來源的result_info是開放object，不能保證都有上述所有key。`ResultOut`公開回應會移除內部`result_info.workbench`，工作台資料改由WorkbenchOut頂層欄位提供。若存完需要完整工作台，再用回傳id呼叫workbench的result_id。

### DB寫入與三種版本的區別

```text
core.result（每次確認新增一筆，不覆蓋舊筆）
├─ execution_id：目前執行
├─ round_no：下一個JSON結果版本序號
└─ result_info
   ├─ content：確認儲存的共用結果key
   ├─ source、base_result_id、edited_by、edited_at、note…
   └─ workbench（內部保存；不直接放進公開ResultOut）
      ├─ schema_version：1
      ├─ content_sha256：新content的UTF-8 SHA256
      ├─ artifacts：[]；source_artifact_id：null
      ├─ render_versions：[]
      ├─ verification：{status:NOT_RUN,match:null,rounds:[]}
      └─ conversion：null
```

- 前端即時渲染是目前內容的預覽，不需渲染API；不是重新驗證，也不冒用原版本TRUE／PARTIAL／Verilog。
- 「確認」是確認儲存編輯內容，不更新execution.review_status，不是人工簽核API。
- JSON結果版本＝result.round_no；圖片版本＝render_versions；驗證輪次＝verification.rounds。test_31有3張圖、2輪驗證，不能據此產生3筆歷史JSON。
- 原報告只提供最終JSON；歷史渲染圖切換不替換下方JSON。未提供的差異明細不虛構。
- 來源優先preview_artifact；沒有就讀source.asset_content_url，前端選PDF頁並標ROI。來源在檔案庫軟刪後，仍可經有效任務取得。

### 錯誤與目前缺口

| 情境 | 回應／處理 |
|---|---|
| 編輯時已有新版本 | 409 RESULT_VERSION_CONFLICT；重載後讓使用者處理差異，不自動覆蓋 |
| 最新execution已改變 | 409 EXECUTION_CHANGED |
| execution尚未結束 | 409 EXECUTION_STILL_ACTIVE |
| 尚未派送或無既有結果可改 | 409 NO_EXECUTION／NO_RESULT |
| WaveDrom不是合法JSON或缺signal/reg陣列 | 422 INVALID_RESULT_CONTENT |
| 跨使用者／關聯錯誤／已軟刪項目／圖片不存在 | 404 |

- 即時渲染、確認按鈕與正式存檔需前端串接；現有Demo主要展示內嵌歷史渲染圖與localStorage追加JSON。
- 歷史JSON是否可作為新版本起點、未儲存離頁提示、版本衝突細節另行討論；不能把舊result_id當成最新基準偷偷提交。
- 切換test／版本需取消或忽略舊請求，避免慢回應覆蓋新頁。
- 真正worker產生渲染、verification、conversion與裁切artifact尚待串接；前端即時預覽不補足這些背景流程。
- 不新增rerun／review端點。本次只整理既有契約。

依據：`router/workbench.py`、`router/results.py`、`schemas/workbench.py`、`schemas/result.py`、`services/workbench_service.py`、`services/result_service.py`、v3 `result()`／`appendResult()`。


## 跨頁檢查清單與範圍

| 項目 | 分頁 | 現況／下一步 |
|---|---|---|
| 主任務精簡清單 | 02 | API已編輯為items＋七欄；前端尚未串接，無分頁 |
| 真實登入／檔案／暫存API介接 | 01／02／03／03A | Demo仍為本機資料，需替換資料來源 |
| 派送與背景解析 | 07／08 | outbox已寫；publisher／queue／worker未接通 |
| 凍結清單的DELETE例外 | 03A | API仍允許派送後軟刪並取消執行；與UI凍結描述有差異，待討論 |
| PATCH頁碼上限 | 03A | 已改為與POST共用已知PDF頁數上限檢查；超界422 PAGE_OUT_OF_RANGE，未執行驗證 |
| 前端即時渲染＋確認儲存 | 08 | 已確認方案；既有POST results保存result_info.content，前端待接 |
| 版本衝突／歷史編輯／未儲存提示 | 08 | API已有部分拒絕規則，前端細節另議 |
| 任務摘要包含失敗與取消 | 07 | 已確認；Demo入口與數字待調整 |
| PDF頁面縮圖 | 03A | 已確認由前端PDF.js產生，不是缺少後端API |
| 上傳限制 | 03／03A | Demo 2MB；後端預設200MB可配置，待對齊 |
| 工作台JSONB／DB約束 | 08 | 契約／手動migration已編輯，未執行migration與後端驗證 |
| 單筆重跑／增量派送／人工簽核 | 03A／08 | 本輪不恢復；不依v2舊表列為必補 |

另有`GET /health`（不加/api/v1）供服務健康檢查，不是任何業務分頁必須呼叫的API。`users` router目前沒有端點。

本文件描述目前契約與已確認目標，未改動原Claude Artifact的發布內容。


## 決策更新：單筆停止與PDF頁碼（2026-09-06）

- 單筆停止沿用POST /executions/{execution_id}/cancel；不做暫停／恢復。若要再次執行，建立新的execution，不復用已取消的一筆。新執行建立端點尚未新增，不能將目前dispatch當成重跑端點。
- PATCH頁碼已與POST共用PDF已知總頁數檢查，超界回422 PAGE_OUT_OF_RANGE。未改schema或執行後端驗證。

## 各 API 建議回傳結構（現行契約；未接入 v4 steps）

以下建議沿用目前已整理的成功回應契約，不代表新增後端變更。所有值都是示意；JSON範例可直接複製，空值與陣列包裝保留實際語意。HTTP 204沒有body，檔案端點回binary而非JSON。

### 回應結構｜POST /auth/login

HTTP 200 · 目前契約／建議沿用。 建議沿用目前TokenResponse；範例token僅為佔位，不是真實憑證。

```json
{
  "access_token": "EXAMPLE_ACCESS_TOKEN",
  "refresh_token": "EXAMPLE_REFRESH_TOKEN",
  "token_type": "bearer",
  "expires_in": 1800,
  "user": {
    "id": "00000000-0000-4000-8000-000000000007",
    "username": "demo",
    "email": "demo@example.com",
    "employee_no": null,
    "organization": null,
    "role": "USER"
  }
}
```

### 回應結構｜POST /auth/refresh

HTTP 200 · 目前契約／建議沿用。 建議沿用目前TokenResponse；範例token僅為佔位，不是真實憑證。

```json
{
  "access_token": "EXAMPLE_ACCESS_TOKEN",
  "refresh_token": "EXAMPLE_REFRESH_TOKEN",
  "token_type": "bearer",
  "expires_in": 1800,
  "user": {
    "id": "00000000-0000-4000-8000-000000000007",
    "username": "demo",
    "email": "demo@example.com",
    "employee_no": null,
    "organization": null,
    "role": "USER"
  }
}
```

### 回應結構｜POST /auth/logout

HTTP 204 · 目前契約／建議沿用。 

```http
HTTP/1.1 204 No Content
```

無Response body，不回 `{}`、`null` 或成功訊息。

### 回應結構｜GET /auth/me

HTTP 200 · 目前契約／建議沿用。 

```json
{
  "id": "00000000-0000-4000-8000-000000000007",
  "username": "demo",
  "email": "demo@example.com",
  "employee_no": null,
  "organization": null,
  "role": "USER"
}
```

### 回應結構｜POST /assets

HTTP 200 · 目前契約／建議沿用。 多檔部分成功示意；failed.message實際文字由後端決定。

```json
{
  "succeeded": [
    {
      "id": "00000000-0000-4000-8000-000000000002",
      "file_name": "datasheet.pdf",
      "file_type": "PDF",
      "mime_type": "application/pdf",
      "file_size": 120000,
      "status": "READY",
      "attributes": {
        "page_count": 12
      },
      "created_at": "2026-09-06T10:00:00+08:00"
    }
  ],
  "failed": [
    {
      "file_name": "notes.txt",
      "error_code": "UNSUPPORTED_EXTENSION",
      "message": "Unsupported extension: .txt"
    }
  ]
}
```

### 回應結構｜GET /assets

HTTP 200 · 目前契約／建議沿用。 檔案庫保留分頁；不跟主任務清單一起移除。

```json
{
  "items": [
    {
      "id": "00000000-0000-4000-8000-000000000002",
      "file_name": "datasheet.pdf",
      "file_type": "PDF",
      "mime_type": "application/pdf",
      "file_size": 120000,
      "status": "READY",
      "attributes": {
        "page_count": 12
      },
      "created_at": "2026-09-06T10:00:00+08:00"
    }
  ],
  "total": 1,
  "page": 1,
  "page_size": 20
}
```

### 回應結構｜GET /assets/{asset_id}

HTTP 200 · 目前契約／建議沿用。 

```json
{
  "id": "00000000-0000-4000-8000-000000000002",
  "file_name": "datasheet.pdf",
  "file_type": "PDF",
  "mime_type": "application/pdf",
  "file_size": 120000,
  "status": "READY",
  "attributes": {
    "page_count": 12
  },
  "created_at": "2026-09-06T10:00:00+08:00"
}
```

### 回應結構｜GET /assets/{asset_id}/content

HTTP 200 · 目前契約／建議沿用。 原始PDF示例；若為圖片，Content-Type依實際檔案改變。

```http
HTTP/1.1 200 OK
Content-Type: application/pdf
Content-Disposition: attachment; filename="datasheet.pdf"

<binary file bytes>
```

### 回應結構｜DELETE /assets/{asset_id}

HTTP 204 · 目前契約／建議沿用。 

```http
HTTP/1.1 204 No Content
```

無Response body，不回 `{}`、`null` 或成功訊息。

### 回應結構｜GET /tasks

HTTP 200 · 目前契約／建議沿用。 使用者已確認的七欄精簡契約。沒有total/page/page_size；空集合回 {"items":[]}。

```json
{
  "items": [
    {
      "id": "00000000-0000-4000-8000-000000000001",
      "name": "Datasheet 解析任務",
      "status": "RUNNING",
      "finished_count": 7,
      "started_at": "2026-09-06T10:00:00+08:00",
      "updated_at": "2026-09-06T10:05:00+08:00",
      "item_count": 10
    }
  ]
}
```

### 回應結構｜POST /tasks

HTTP 201 · 目前契約／建議沿用。 

```json
{
  "id": "00000000-0000-4000-8000-000000000001",
  "name": "Datasheet 解析任務",
  "description": "解析第2頁時序圖",
  "status": "DRAFT",
  "display_status": "PENDING",
  "config": {},
  "dispatched_at": null,
  "completed_at": null,
  "created_at": "2026-09-06T10:00:00+08:00",
  "updated_at": "2026-09-06T10:05:00+08:00",
  "progress": {
    "item_count": 0,
    "pending": 0,
    "running": 0,
    "succeeded": 0,
    "failed": 0,
    "cancelled": 0,
    "percent": 0
  }
}
```

### 回應結構｜GET /tasks/{task_id}

HTTP 200 · 目前契約／建議沿用。 沿用目前TaskOut；僅清單GET /tasks精簡，不連帶刪除此回應欄位。

```json
{
  "id": "00000000-0000-4000-8000-000000000001",
  "name": "Datasheet 解析任務",
  "description": "解析第2頁時序圖",
  "status": "COMPLETED",
  "display_status": "COMPLETED",
  "config": {},
  "dispatched_at": "2026-09-06T10:00:00+08:00",
  "completed_at": "2026-09-06T10:05:00+08:00",
  "created_at": "2026-09-06T10:00:00+08:00",
  "updated_at": "2026-09-06T10:05:00+08:00",
  "progress": {
    "item_count": 1,
    "pending": 0,
    "running": 0,
    "succeeded": 1,
    "failed": 0,
    "cancelled": 0,
    "percent": 100
  }
}
```

### 回應結構｜PATCH /tasks/{task_id}

HTTP 200 · 目前契約／建議沿用。 沿用目前TaskOut；僅清單GET /tasks精簡，不連帶刪除此回應欄位。

```json
{
  "id": "00000000-0000-4000-8000-000000000001",
  "name": "Datasheet 解析任務",
  "description": "解析第2頁時序圖",
  "status": "COMPLETED",
  "display_status": "COMPLETED",
  "config": {},
  "dispatched_at": "2026-09-06T10:00:00+08:00",
  "completed_at": "2026-09-06T10:05:00+08:00",
  "created_at": "2026-09-06T10:00:00+08:00",
  "updated_at": "2026-09-06T10:05:00+08:00",
  "progress": {
    "item_count": 1,
    "pending": 0,
    "running": 0,
    "succeeded": 1,
    "failed": 0,
    "cancelled": 0,
    "percent": 100
  }
}
```

### 回應結構｜GET /tasks/{task_id}/detail

HTTP 200 · 目前契約／建議沿用。 一個主任務的完整子項內容；公開ResultOut不帶內部workbench。

```json
{
  "task": {
    "id": "00000000-0000-4000-8000-000000000001",
    "name": "Datasheet 解析任務",
    "description": "解析第2頁時序圖",
    "status": "COMPLETED",
    "display_status": "COMPLETED",
    "config": {},
    "dispatched_at": "2026-09-06T10:00:00+08:00",
    "completed_at": "2026-09-06T10:05:00+08:00",
    "created_at": "2026-09-06T10:00:00+08:00",
    "updated_at": "2026-09-06T10:05:00+08:00",
    "progress": {
      "item_count": 1,
      "pending": 0,
      "running": 0,
      "succeeded": 1,
      "failed": 0,
      "cancelled": 0,
      "percent": 100
    }
  },
  "items": [
    {
      "parse_item": {
        "id": "00000000-0000-4000-8000-000000000003",
        "task_id": "00000000-0000-4000-8000-000000000001",
        "asset_id": "00000000-0000-4000-8000-000000000002",
        "asset_file_name": "datasheet.pdf",
        "name": "test_31",
        "status": "READY",
        "page_no": 2,
        "x": 0.1,
        "y": 0.2,
        "width": 0.8,
        "height": 0.3,
        "created_at": "2026-09-06T10:00:00+08:00"
      },
      "latest_execution": {
        "id": "00000000-0000-4000-8000-000000000004",
        "parse_id": "00000000-0000-4000-8000-000000000003",
        "status": "SUCCEEDED",
        "retry_count": 0,
        "max_retry_count": 3,
        "flow_id": null,
        "flow_version": null,
        "model_id": null,
        "model_version": null,
        "input_data": {
          "asset_id": "00000000-0000-4000-8000-000000000002",
          "page_no": 2,
          "roi": {
            "x": 0.1,
            "y": 0.2,
            "width": 0.8,
            "height": 0.3
          },
          "config": {}
        },
        "queued_at": "2026-09-06T10:00:00+08:00",
        "started_at": "2026-09-06T10:00:00+08:00",
        "finished_at": "2026-09-06T10:05:00+08:00",
        "error_code": null,
        "error_message": null,
        "review_status": "PENDING",
        "created_at": "2026-09-06T10:00:00+08:00"
      },
      "result_round_count": 2,
      "latest_result": {
        "id": "00000000-0000-4000-8000-000000000005",
        "execution_id": "00000000-0000-4000-8000-000000000004",
        "round_no": 2,
        "status": "SUCCEEDED",
        "result_info": {
          "type": "TIMING",
          "content_type": "WAVEDROM",
          "content": "{\"signal\":[]}",
          "schema_version": 2,
          "base_result_id": "00000000-0000-4000-8000-000000000006",
          "source": "MANUAL",
          "note": "修正後確認儲存",
          "edited_by": "00000000-0000-4000-8000-000000000007",
          "edited_at": "2026-09-06T10:05:00+08:00"
        },
        "created_at": "2026-09-06T10:05:00+08:00"
      }
    }
  ]
}
```

### 回應結構｜POST /tasks/{task_id}/cancel

HTTP 200 · 目前契約／建議沿用。 整任務取消回TaskOut；勿與單筆execution取消回應混用。

```json
{
  "id": "00000000-0000-4000-8000-000000000001",
  "name": "Datasheet 解析任務",
  "description": "解析第2頁時序圖",
  "status": "CANCELLED",
  "display_status": "CANCELLED",
  "config": {},
  "dispatched_at": "2026-09-06T10:00:00+08:00",
  "completed_at": "2026-09-06T10:05:00+08:00",
  "created_at": "2026-09-06T10:00:00+08:00",
  "updated_at": "2026-09-06T10:05:00+08:00",
  "progress": {
    "item_count": 1,
    "pending": 0,
    "running": 0,
    "succeeded": 0,
    "failed": 0,
    "cancelled": 1,
    "percent": 100
  }
}
```

### 回應結構｜DELETE /tasks/{task_id}

HTTP 204 · 目前契約／建議沿用。 

```http
HTTP/1.1 204 No Content
```

無Response body，不回 `{}`、`null` 或成功訊息。

### 回應結構｜POST /tasks/{task_id}/parse-items

HTTP 201 · 目前契約／建議沿用。 目前回裸陣列，不新增items包裝。

```json
[
  {
    "id": "00000000-0000-4000-8000-000000000003",
    "task_id": "00000000-0000-4000-8000-000000000001",
    "asset_id": "00000000-0000-4000-8000-000000000002",
    "asset_file_name": "datasheet.pdf",
    "name": "test_31",
    "status": "DRAFT",
    "page_no": 2,
    "x": 0.1,
    "y": 0.2,
    "width": 0.8,
    "height": 0.3,
    "created_at": "2026-09-06T10:00:00+08:00"
  }
]
```

### 回應結構｜GET /tasks/{task_id}/parse-items

HTTP 200 · 目前契約／建議沿用。 

```json
[
  {
    "id": "00000000-0000-4000-8000-000000000003",
    "task_id": "00000000-0000-4000-8000-000000000001",
    "asset_id": "00000000-0000-4000-8000-000000000002",
    "asset_file_name": "datasheet.pdf",
    "name": "test_31",
    "status": "READY",
    "page_no": 2,
    "x": 0.1,
    "y": 0.2,
    "width": 0.8,
    "height": 0.3,
    "created_at": "2026-09-06T10:00:00+08:00"
  }
]
```

### 回應結構｜GET /parse-items/{parse_item_id}

HTTP 200 · 目前契約／建議沿用。 

```json
{
  "id": "00000000-0000-4000-8000-000000000003",
  "task_id": "00000000-0000-4000-8000-000000000001",
  "asset_id": "00000000-0000-4000-8000-000000000002",
  "asset_file_name": "datasheet.pdf",
  "name": "test_31",
  "status": "DRAFT",
  "page_no": 2,
  "x": 0.1,
  "y": 0.2,
  "width": 0.8,
  "height": 0.3,
  "created_at": "2026-09-06T10:00:00+08:00"
}
```

### 回應結構｜PATCH /parse-items/{parse_item_id}

HTTP 200 · 目前契約／建議沿用。 

```json
{
  "id": "00000000-0000-4000-8000-000000000003",
  "task_id": "00000000-0000-4000-8000-000000000001",
  "asset_id": "00000000-0000-4000-8000-000000000002",
  "asset_file_name": "datasheet.pdf",
  "name": "test_31",
  "status": "DRAFT",
  "page_no": 2,
  "x": 0.1,
  "y": 0.2,
  "width": 0.8,
  "height": 0.3,
  "created_at": "2026-09-06T10:00:00+08:00"
}
```

### 回應結構｜DELETE /parse-items/{parse_item_id}

HTTP 204 · 目前契約／建議沿用。 

```http
HTTP/1.1 204 No Content
```

無Response body，不回 `{}`、`null` 或成功訊息。

### 回應結構｜POST /tasks/{task_id}/dispatch

HTTP 202 · 目前契約／建議沿用。 202表示建立execution與outbox，不代表worker已開始。

```json
{
  "task_id": "00000000-0000-4000-8000-000000000001",
  "task_status": "DISPATCHED",
  "dispatched_count": 1,
  "executions": [
    {
      "id": "00000000-0000-4000-8000-000000000004",
      "parse_id": "00000000-0000-4000-8000-000000000003",
      "status": "CREATED",
      "retry_count": 0,
      "max_retry_count": 3,
      "flow_id": null,
      "flow_version": null,
      "model_id": null,
      "model_version": null,
      "input_data": {
        "asset_id": "00000000-0000-4000-8000-000000000002",
        "page_no": 2,
        "roi": {
          "x": 0.1,
          "y": 0.2,
          "width": 0.8,
          "height": 0.3
        },
        "config": {}
      },
      "queued_at": null,
      "started_at": null,
      "finished_at": null,
      "error_code": null,
      "error_message": null,
      "review_status": "PENDING",
      "created_at": "2026-09-06T10:00:00+08:00"
    }
  ]
}
```

### 回應結構｜GET /executions

HTTP 200 · 目前契約／建議沿用。 

```json
{
  "items": [
    {
      "id": "00000000-0000-4000-8000-000000000004",
      "parse_id": "00000000-0000-4000-8000-000000000003",
      "status": "SUCCEEDED",
      "retry_count": 0,
      "max_retry_count": 3,
      "flow_id": null,
      "flow_version": null,
      "model_id": null,
      "model_version": null,
      "input_data": {
        "asset_id": "00000000-0000-4000-8000-000000000002",
        "page_no": 2,
        "roi": {
          "x": 0.1,
          "y": 0.2,
          "width": 0.8,
          "height": 0.3
        },
        "config": {}
      },
      "queued_at": "2026-09-06T10:00:00+08:00",
      "started_at": "2026-09-06T10:00:00+08:00",
      "finished_at": "2026-09-06T10:05:00+08:00",
      "error_code": null,
      "error_message": null,
      "review_status": "PENDING",
      "created_at": "2026-09-06T10:00:00+08:00"
    }
  ],
  "total": 1,
  "page": 1,
  "page_size": 20
}
```

### 回應結構｜GET /executions/{execution_id}

HTTP 200 · 目前契約／建議沿用。 

```json
{
  "id": "00000000-0000-4000-8000-000000000004",
  "parse_id": "00000000-0000-4000-8000-000000000003",
  "status": "SUCCEEDED",
  "retry_count": 0,
  "max_retry_count": 3,
  "flow_id": null,
  "flow_version": null,
  "model_id": null,
  "model_version": null,
  "input_data": {
    "asset_id": "00000000-0000-4000-8000-000000000002",
    "page_no": 2,
    "roi": {
      "x": 0.1,
      "y": 0.2,
      "width": 0.8,
      "height": 0.3
    },
    "config": {}
  },
  "queued_at": "2026-09-06T10:00:00+08:00",
  "started_at": "2026-09-06T10:00:00+08:00",
  "finished_at": "2026-09-06T10:05:00+08:00",
  "error_code": null,
  "error_message": null,
  "review_status": "PENDING",
  "created_at": "2026-09-06T10:00:00+08:00"
}
```

### 回應結構｜POST /executions/{execution_id}/cancel

HTTP 200 · 目前契約／建議沿用。 目前單筆取消只有cancelled_executions有值；其餘兩欄為null，不擅自新增或刪除。

```json
{
  "task_id": null,
  "task_status": null,
  "cancelled_executions": 1
}
```

### 回應結構｜GET /parse-items/{parse_item_id}/results

HTTP 200 · 目前契約／建議沿用。 示意結果列表；實際每一筆JSON版本由舊到新，數量依資料。

```json
[
  {
    "id": "00000000-0000-4000-8000-000000000005",
    "execution_id": "00000000-0000-4000-8000-000000000004",
    "round_no": 2,
    "status": "SUCCEEDED",
    "result_info": {
      "type": "TIMING",
      "content_type": "WAVEDROM",
      "content": "{\"signal\":[]}",
      "schema_version": 2,
      "base_result_id": "00000000-0000-4000-8000-000000000006",
      "source": "MANUAL",
      "note": "修正後確認儲存",
      "edited_by": "00000000-0000-4000-8000-000000000007",
      "edited_at": "2026-09-06T10:05:00+08:00"
    },
    "created_at": "2026-09-06T10:05:00+08:00"
  }
]
```

### 回應結構｜POST /parse-items/{parse_item_id}/results

HTTP 201 · 目前契約／建議沿用。 確認後新增結果版本；共用內容key為result_info.content，公開回應不帶workbench。

```json
{
  "id": "00000000-0000-4000-8000-000000000005",
  "execution_id": "00000000-0000-4000-8000-000000000004",
  "round_no": 2,
  "status": "SUCCEEDED",
  "result_info": {
    "type": "TIMING",
    "content_type": "WAVEDROM",
    "content": "{\"signal\":[]}",
    "schema_version": 2,
    "base_result_id": "00000000-0000-4000-8000-000000000006",
    "source": "MANUAL",
    "note": "修正後確認儲存",
    "edited_by": "00000000-0000-4000-8000-000000000007",
    "edited_at": "2026-09-06T10:05:00+08:00"
  },
  "created_at": "2026-09-06T10:05:00+08:00"
}
```

### 回應結構｜GET /parse-items/{parse_id}/workbench

HTTP 200 · 目前契約／建議沿用。 主範例為人工確認後：AVAILABLE但尚未驗證。下方另附已具備衍生成果的結構示例。

```json
{
  "parse_item": {
    "id": "00000000-0000-4000-8000-000000000003",
    "task_id": "00000000-0000-4000-8000-000000000001",
    "asset_id": "00000000-0000-4000-8000-000000000002",
    "asset_file_name": "datasheet.pdf",
    "name": "test_31",
    "status": "READY",
    "page_no": 2,
    "x": 0.1,
    "y": 0.2,
    "width": 0.8,
    "height": 0.3,
    "created_at": "2026-09-06T10:00:00+08:00"
  },
  "source": {
    "asset_id": "00000000-0000-4000-8000-000000000002",
    "file_name": "datasheet.pdf",
    "page_no": 2,
    "asset_content_url": "/api/v1/parse-items/00000000-0000-4000-8000-000000000003/source/content",
    "preview_artifact": null
  },
  "execution": {
    "id": "00000000-0000-4000-8000-000000000004",
    "parse_id": "00000000-0000-4000-8000-000000000003",
    "status": "SUCCEEDED",
    "retry_count": 0,
    "max_retry_count": 3,
    "flow_id": null,
    "flow_version": null,
    "model_id": null,
    "model_version": null,
    "input_data": {
      "asset_id": "00000000-0000-4000-8000-000000000002",
      "page_no": 2,
      "roi": {
        "x": 0.1,
        "y": 0.2,
        "width": 0.8,
        "height": 0.3
      },
      "config": {}
    },
    "queued_at": "2026-09-06T10:00:00+08:00",
    "started_at": "2026-09-06T10:00:00+08:00",
    "finished_at": "2026-09-06T10:05:00+08:00",
    "error_code": null,
    "error_message": null,
    "review_status": "PENDING",
    "created_at": "2026-09-06T10:00:00+08:00"
  },
  "selected_result": {
    "id": "00000000-0000-4000-8000-000000000005",
    "execution_id": "00000000-0000-4000-8000-000000000004",
    "round_no": 2,
    "status": "SUCCEEDED",
    "result_info": {
      "type": "TIMING",
      "content_type": "WAVEDROM",
      "content": "{\"signal\":[]}",
      "schema_version": 2,
      "base_result_id": "00000000-0000-4000-8000-000000000006",
      "source": "MANUAL",
      "note": "修正後確認儲存",
      "edited_by": "00000000-0000-4000-8000-000000000007",
      "edited_at": "2026-09-06T10:05:00+08:00"
    },
    "created_at": "2026-09-06T10:05:00+08:00"
  },
  "results": [
    {
      "id": "00000000-0000-4000-8000-000000000005",
      "execution_id": "00000000-0000-4000-8000-000000000004",
      "round_no": 2,
      "status": "SUCCEEDED",
      "result_info": {
        "type": "TIMING",
        "content_type": "WAVEDROM",
        "content": "{\"signal\":[]}",
        "schema_version": 2,
        "base_result_id": "00000000-0000-4000-8000-000000000006",
        "source": "MANUAL",
        "note": "修正後確認儲存",
        "edited_by": "00000000-0000-4000-8000-000000000007",
        "edited_at": "2026-09-06T10:05:00+08:00"
      },
      "created_at": "2026-09-06T10:05:00+08:00"
    }
  ],
  "data_status": "AVAILABLE",
  "artifacts": [],
  "render_versions": [],
  "verification": {
    "status": "NOT_RUN",
    "match": null,
    "rounds": []
  },
  "conversion": null
}
```

已具備渲染／驗證／轉換的另一種回應形狀（欄位示意，不是本次真的執行成果）：

```json
{
  "parse_item": {
    "id": "00000000-0000-4000-8000-000000000003",
    "task_id": "00000000-0000-4000-8000-000000000001",
    "asset_id": "00000000-0000-4000-8000-000000000002",
    "asset_file_name": "datasheet.pdf",
    "name": "test_31",
    "status": "READY",
    "page_no": 2,
    "x": 0.1,
    "y": 0.2,
    "width": 0.8,
    "height": 0.3,
    "created_at": "2026-09-06T10:00:00+08:00"
  },
  "source": {
    "asset_id": "00000000-0000-4000-8000-000000000002",
    "file_name": "datasheet.pdf",
    "page_no": 2,
    "asset_content_url": "/api/v1/parse-items/00000000-0000-4000-8000-000000000003/source/content",
    "preview_artifact": null
  },
  "execution": {
    "id": "00000000-0000-4000-8000-000000000004",
    "parse_id": "00000000-0000-4000-8000-000000000003",
    "status": "SUCCEEDED",
    "retry_count": 0,
    "max_retry_count": 3,
    "flow_id": null,
    "flow_version": null,
    "model_id": null,
    "model_version": null,
    "input_data": {
      "asset_id": "00000000-0000-4000-8000-000000000002",
      "page_no": 2,
      "roi": {
        "x": 0.1,
        "y": 0.2,
        "width": 0.8,
        "height": 0.3
      },
      "config": {}
    },
    "queued_at": "2026-09-06T10:00:00+08:00",
    "started_at": "2026-09-06T10:00:00+08:00",
    "finished_at": "2026-09-06T10:05:00+08:00",
    "error_code": null,
    "error_message": null,
    "review_status": "PENDING",
    "created_at": "2026-09-06T10:00:00+08:00"
  },
  "selected_result": {
    "id": "00000000-0000-4000-8000-000000000005",
    "execution_id": "00000000-0000-4000-8000-000000000004",
    "round_no": 2,
    "status": "SUCCEEDED",
    "result_info": {
      "type": "TIMING",
      "content_type": "WAVEDROM",
      "content": "{\"signal\":[]}",
      "schema_version": 2,
      "base_result_id": "00000000-0000-4000-8000-000000000006",
      "source": "AI",
      "note": "修正後確認儲存"
    },
    "created_at": "2026-09-06T10:05:00+08:00"
  },
  "results": [
    {
      "id": "00000000-0000-4000-8000-000000000005",
      "execution_id": "00000000-0000-4000-8000-000000000004",
      "round_no": 2,
      "status": "SUCCEEDED",
      "result_info": {
        "type": "TIMING",
        "content_type": "WAVEDROM",
        "content": "{\"signal\":[]}",
        "schema_version": 2,
        "base_result_id": "00000000-0000-4000-8000-000000000006",
        "source": "AI",
        "note": "修正後確認儲存"
      },
      "created_at": "2026-09-06T10:05:00+08:00"
    }
  ],
  "data_status": "AVAILABLE",
  "artifacts": [
    {
      "id": "00000000-0000-4000-8000-000000000008",
      "media_type": "image/png",
      "content_url": "/api/v1/results/00000000-0000-4000-8000-000000000005/artifacts/00000000-0000-4000-8000-000000000008/content"
    }
  ],
  "render_versions": [
    {
      "id": "00000000-0000-4000-8000-000000000009",
      "label": "最終",
      "artifact_id": "00000000-0000-4000-8000-000000000008",
      "note": null,
      "result_id": "00000000-0000-4000-8000-000000000005"
    }
  ],
  "verification": {
    "status": "COMPLETED",
    "match": "TRUE",
    "rounds": [
      {
        "round_no": 1,
        "match": "TRUE",
        "checked_at": "2026-09-06T10:05:00+08:00",
        "checked_at_display": null,
        "diff_count": 0,
        "diffs": [],
        "input_result_id": "00000000-0000-4000-8000-000000000005"
      }
    ]
  },
  "conversion": {
    "kind": "TESTBENCH",
    "language": "VERILOG",
    "code": "module tb;\nendmodule",
    "metrics": [
      {
        "label": "訊號數",
        "value": 0
      }
    ],
    "table": {
      "columns": [
        "名稱",
        "結果"
      ],
      "rows": [
        [
          "示意訊號",
          "一致"
        ]
      ]
    },
    "warnings": null
  }
}
```

### 回應結構｜GET /parse-items/{parse_id}/source/content

HTTP 200 · 目前契約／建議沿用。 原始PDF示例；支援既有任務來源，檔案庫軟刪不等於移除此端點。

```http
HTTP/1.1 200 OK
Content-Type: application/pdf
Cache-Control: private, no-store
X-Content-Type-Options: nosniff

<binary file bytes>
```

### 回應結構｜GET /results/{result_id}/artifacts/{artifact_id}/content

HTTP 200 · 目前契約／建議沿用。 圖片示例；實際為image/png、image/jpeg或image/webp。

```http
HTTP/1.1 200 OK
Content-Type: image/png
Cache-Control: private, no-store
X-Content-Type-Options: nosniff

<binary file bytes>
```

### 回應結構｜GET /health

HTTP 200 · 目前契約／建議沿用。 健康檢查不加/api/v1；DB不可用時db為unavailable，HTTP仍為200。

```json
{
  "status": "ok",
  "db": "ok"
}
```

### 共通錯誤回應範例

業務錯誤如409：

```json
{"error":{"code":"RESULT_VERSION_CONFLICT","message":"Result has changed; reload before saving"}}
```

請求欄位格式錯誤可能採FastAPI預設422 detail陣列；不要一律解析成error。各端點適用錯誤仍依原頁面說明，未宣告所有端點都會產生同一錯誤。


## 模型 flow 基本資料 API（新增）

資料表：`core.model_flow`。清單由登入使用者共用；三個 API 都需要既有登入 Bearer token。
此階段僅儲存基本資料，不儲存流程 JSON，也不提供修改 API。

| 欄位 | DB 型別 | 規則 |
|---|---|---|
| id | UUID | 系統產生，主鍵 |
| name | VARCHAR(200) | 必填，API 去除前後空白後不可為空，允許同名 |
| description | TEXT | 可為 null |
| created_at | TIMESTAMPTZ | 系統產生 |
| updated_at | TIMESTAMPTZ | 系統產生，API 刪除時更新 |
| is_valid | BOOLEAN | 預設 true，新增時可指定 false |
| deleted_at | TIMESTAMPTZ | 預設 null，軟刪除時間 |

### 清單

`GET /api/v1/model-flows`

回傳 200，格式為 `{"items": [...]}`。各項含上列七欄。
回傳所有 `deleted_at IS NULL` 的項目，包含 `is_valid=false`，不分頁；
依 `created_at DESC, id DESC` 排序。無資料回傳 `{"items": []}`。

### 新增

`POST /api/v1/model-flows`

```json
{
  "name": "預設模型流程",
  "description": "測試用流程",
  "is_valid": true
}
```

只有 name 必填。成功回傳 201 與完整七欄資料。
格式不符、空白名稱、名稱超過 200 字或額外欄位回傳 422。
id 與所有時間欄位由伺服器管理，不接受客戶端指定。

### 刪除

`DELETE /api/v1/model-flows/{flow_id}`

成功回傳 204，無 body。設定 deleted_at 與 updated_at 為同一時間，is_valid=false。
資料不存在或已刪除回傳 404，UUID 格式不符回傳 422。

### 既有 DB 部署

手動執行 `app/db/schema/02_core/07_model_flow.sql` 即可建立新表與索引。
若啟用 `DB_AUTO_BOOTSTRAP=true`，後端啟動時也會讀取此檔案。
若已關閉自動初始化，需先手動套用 SQL，再使用新 API。
本次未連線或修改部署中的 DB。

### 驗證

在已安裝 requirements.txt 與 requirements-dev.txt 的 Python 3.11 環境，
於 project_folder 執行 `python -m pytest tests/test_model_flows.py -q`。
此測試涵蓋輸入驗證；實際 PostgreSQL 與 API 整合仍需部署環境驗證。


### API 清單

| 操作 | API | 傳入 | 成功回傳 |
|---|---|---|---|
| 查詢整體清單 | GET /model-flows | Bearer；無 query/body，不分頁 | 200 ModelFlowListResponse |
| 新增 | POST /model-flows | Bearer；body name 必填，description／is_valid 可省略 | 201 ModelFlowOut |
| 軟刪除 | DELETE /model-flows/{flow_id} | Bearer；path flow_id:UUID；無 body | 204，無 body |

**ModelFlowOut 完整欄位**

| 欄位 | 型別 | 說明 |
|---|---|---|
| id | UUID | 系統產生 |
| name | string | 名稱 |
| description | string 或 null | 說明 |
| created_at | datetime | 建立時間 |
| updated_at | datetime | 最後更新時間 |
| is_valid | boolean | 是否有效 |
| deleted_at | datetime 或 null | 軟刪除時間 |

**ModelFlowListResponse 完整欄位**

| 欄位 | 型別 | 說明 |
|---|---|---|
| items | ModelFlowOut[] | 全部未刪除項目，包含 is_valid=false |

模型 flow 基本資料與單張圖片的 steps 執行歷程用途不同，目前沒有自動把此表 ID 接到 execution.flow_id。
