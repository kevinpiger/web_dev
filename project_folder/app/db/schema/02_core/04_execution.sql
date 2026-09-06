CREATE SCHEMA IF NOT EXISTS core;

CREATE TABLE IF NOT EXISTS core.execution (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    parse_id        UUID NOT NULL REFERENCES core.parse_item(id) ON DELETE CASCADE,
    status          VARCHAR(20) NOT NULL DEFAULT 'CREATED',
    retry_count     INTEGER NOT NULL DEFAULT 0,
    max_retry_count INTEGER NOT NULL DEFAULT 0,
    flow_id         VARCHAR(100),
    flow_version    VARCHAR(50),
    model_id        VARCHAR(100),
    model_version   VARCHAR(50),
    input_data      JSONB NOT NULL DEFAULT '{}'::jsonb,
    queued_at       TIMESTAMPTZ,
    started_at      TIMESTAMPTZ,
    finished_at     TIMESTAMPTZ,
    error_code      VARCHAR(100),
    error_message   TEXT,
    -- §3 增補：人工簽核狀態，跟 result.status（AI 該輪成敗）分開
    review_status   VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    reviewed_by     UUID REFERENCES iam.app_user(id) ON DELETE SET NULL,
    reviewed_at     TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT execution_status_allowed CHECK (
        status IN ('CREATED', 'QUEUED', 'RUNNING', 'SUCCEEDED', 'FAILED', 'TIMEOUT', 'CANCELLED')
    ),
    CONSTRAINT execution_review_status_allowed CHECK (
        review_status IN ('PENDING', 'CONFIRMED', 'REJECTED')
    ),
    CONSTRAINT execution_retry_bound CHECK (retry_count <= max_retry_count)
);

CREATE INDEX IF NOT EXISTS idx_execution_parse_id ON core.execution(parse_id);
CREATE INDEX IF NOT EXISTS idx_execution_parse_status ON core.execution(parse_id, status);
CREATE INDEX IF NOT EXISTS idx_execution_review ON core.execution(parse_id, review_status);
