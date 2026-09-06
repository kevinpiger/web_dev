CREATE SCHEMA IF NOT EXISTS core;

CREATE TABLE IF NOT EXISTS core.parse_item (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id    UUID NOT NULL REFERENCES core.analysis_task(id) ON DELETE CASCADE,
    asset_id   UUID NOT NULL REFERENCES core.asset(id) ON DELETE RESTRICT,
    name       VARCHAR(255),
    -- 第五處 freeze 增補：DRAFT 為編輯期暫存狀態；執行狀態仍由 Execution 管理（§8）。
    status     VARCHAR(20) NOT NULL DEFAULT 'DRAFT',
    x          DOUBLE PRECISION NOT NULL,
    y          DOUBLE PRECISION NOT NULL,
    width      DOUBLE PRECISION NOT NULL,
    height     DOUBLE PRECISION NOT NULL,
    -- §3 增補：PDF 多頁 ROI 需要頁碼定位；單張圖片一律存 1
    page_no    INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- 增補：刪除子任務用軟刪。硬刪會沿 FK CASCADE 清掉 execution / result /
    -- agent_run，跟 freeze §22「execution 保留作稽核／Retry 依據」相衝突。
    deleted_at TIMESTAMPTZ,
    CONSTRAINT parse_item_status_allowed CHECK (status IN ('DRAFT', 'READY', 'REJECTED')),
    CONSTRAINT parse_item_page_positive CHECK (page_no > 0),
    CONSTRAINT parse_item_roi_range CHECK (
        x >= 0 AND x < 1 AND
        y >= 0 AND y < 1 AND
        width  > 0 AND width  <= 1 AND
        height > 0 AND height <= 1 AND
        x + width  <= 1 AND
        y + height <= 1
    )
);

CREATE INDEX IF NOT EXISTS idx_parse_item_task_id ON core.parse_item(task_id);
CREATE INDEX IF NOT EXISTS idx_parse_item_asset_id ON core.parse_item(asset_id);
CREATE INDEX IF NOT EXISTS idx_parse_item_task_status ON core.parse_item(task_id, status);
CREATE INDEX IF NOT EXISTS idx_parse_item_asset_page ON core.parse_item(asset_id, page_no);
CREATE INDEX IF NOT EXISTS idx_parse_item_active
    ON core.parse_item(task_id) WHERE deleted_at IS NULL;
