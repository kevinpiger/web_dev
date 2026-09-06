CREATE SCHEMA IF NOT EXISTS core;

CREATE TABLE IF NOT EXISTS core.analysis_task (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id        UUID NOT NULL REFERENCES iam.app_user(id) ON DELETE RESTRICT,
    name           VARCHAR(255) NOT NULL,
    description    TEXT,
    status         VARCHAR(20) NOT NULL DEFAULT 'DRAFT',
    config         JSONB NOT NULL DEFAULT '{}'::jsonb,
    dispatched_at  TIMESTAMPTZ,
    completed_at   TIMESTAMPTZ,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at     TIMESTAMPTZ,
    CONSTRAINT analysis_task_status_allowed CHECK (
        status IN ('DRAFT', 'READY', 'DISPATCHED', 'RUNNING', 'COMPLETED', 'FAILED', 'CANCELLED')
    )
);

CREATE INDEX IF NOT EXISTS idx_analysis_task_user_id ON core.analysis_task(user_id);
CREATE INDEX IF NOT EXISTS idx_analysis_task_active ON core.analysis_task(user_id) WHERE deleted_at IS NULL;
