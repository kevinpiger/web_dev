# GET /api/v1/tasks：主任務總覽契約

依使用者確認更新；程式已編輯，未執行後端驗證。

- 不分頁、不收 page／page_size／status 篩選參數；一次回傳目前使用者全部未刪除主任務。
- 回應只包含 items；每筆只含 id、name、status、finished_count、started_at、updated_at、item_count。
- 無任務回 {"items": []}，不回 total、page、page_size、progress_percent 或詳細 progress。
- finished_count：每個有效 parse_item 最新 execution 已結束筆數；包含 SUCCEEDED、FAILED、TIMEOUT、CANCELLED。不是成功數。
- item_count：未刪除且 DRAFT／READY 的解析項目數，排除 REJECTED。
- 前端自行計算進度：item_count > 0 時 finished_count / item_count * 100，否則 0；四張統計卡由前端對全部 items 分類。
- status：單一彙整狀態，保留 DRAFT／READY；明確取消／失敗優先；有效項目全部結束時有失敗為 FAILED，其次有取消為 CANCELLED，否則 COMPLETED；仍在處理為 RUNNING，全部待執行為 DISPATCHED。
- started_at：主任務下歷次 execution 最早的實際 started_at；未開始為 null。
- updated_at：主任務及其 parse_item／execution／result 的最新更新，包含軟刪子項活動；不因檔案庫 metadata 更新而變動。
- 依彙整 updated_at 新到舊排序；同時間以 id 作穩定排序。
- 詳細資料仍用 GET /api/v1/tasks/{task_id}/detail；其他 TaskOut 回應不受清單精簡影響。

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
