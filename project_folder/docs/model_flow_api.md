# Model flow API

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

## 清單

`GET /api/v1/model-flows`

回傳 200，格式為 `{"items": [...]}`。各項含上列七欄。
回傳所有 `deleted_at IS NULL` 的項目，包含 `is_valid=false`，不分頁；
依 `created_at DESC, id DESC` 排序。無資料回傳 `{"items": []}`。

## 新增

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

## 刪除

`DELETE /api/v1/model-flows/{flow_id}`

成功回傳 204，無 body。設定 deleted_at 與 updated_at 為同一時間，is_valid=false。
資料不存在或已刪除回傳 404，UUID 格式不符回傳 422。

## 既有 DB 部署

手動執行 `app/db/schema/02_core/07_model_flow.sql` 即可建立新表與索引。
若啟用 `DB_AUTO_BOOTSTRAP=true`，後端啟動時也會讀取此檔案。
若已關閉自動初始化，需先手動套用 SQL，再使用新 API。
本次未連線或修改部署中的 DB。

## 驗證

在已安裝 requirements.txt 與 requirements-dev.txt 的 Python 3.11 環境，
於 project_folder 執行 `python -m pytest tests/test_model_flows.py -q`。
此測試涵蓋輸入驗證；實際 PostgreSQL 與 API 整合仍需部署環境驗證。
