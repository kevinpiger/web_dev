CREATE SCHEMA IF NOT EXISTS runtime;

CREATE TABLE IF NOT EXISTS runtime.execution_attempt (
    id UUID PRIMARY KEY,
    execution_id UUID NOT NULL REFERENCES core.execution(id) ON DELETE CASCADE,
    attempt_no INTEGER NOT NULL CHECK (attempt_no >= 1),
    status VARCHAR(20) NOT NULL CHECK (status IN ('RUNNING', 'SUCCEEDED', 'FAILED', 'TIMEOUT', 'CANCELLED', 'EXPIRED')),
    token_id UUID NOT NULL,
    token_expires_at TIMESTAMPTZ NOT NULL,
    lease_expires_at TIMESTAMPTZ NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ,
    retryable BOOLEAN NOT NULL DEFAULT false,
    artifacts JSONB NOT NULL DEFAULT '{}'::jsonb,
    receipts JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (execution_id, attempt_no)
);
CREATE INDEX IF NOT EXISTS idx_attempt_running_lease
    ON runtime.execution_attempt(lease_expires_at) WHERE status = 'RUNNING';
