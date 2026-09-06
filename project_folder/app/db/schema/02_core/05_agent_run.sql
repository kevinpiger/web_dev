CREATE SCHEMA IF NOT EXISTS core;

CREATE TABLE IF NOT EXISTS core.agent_run (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    execution_id   UUID NOT NULL REFERENCES core.execution(id) ON DELETE CASCADE,
    model_id       VARCHAR(100),
    model_version  VARCHAR(50),
    status         VARCHAR(20) NOT NULL DEFAULT 'RUNNING',
    input_tokens   INTEGER,
    output_tokens  INTEGER,
    latency_ms     BIGINT,
    started_at     TIMESTAMPTZ,
    finished_at    TIMESTAMPTZ,
    error_code     VARCHAR(100),
    error_message  TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT agent_run_status_allowed CHECK (status IN ('RUNNING', 'SUCCEEDED', 'FAILED')),
    CONSTRAINT agent_run_execution_unique UNIQUE (execution_id)
);
