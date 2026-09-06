CREATE SCHEMA IF NOT EXISTS core;

CREATE TABLE IF NOT EXISTS core.result (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    execution_id UUID NOT NULL REFERENCES core.execution(id) ON DELETE CASCADE,
    round_no     INTEGER NOT NULL,
    status       VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    -- Workbench extension: result_info.schema_version=2; workbench.schema_version=1.
    -- result.round_no is the content version, NOT the render count or verify round.
    -- workbench contains content_sha256, artifacts, render_versions, verification,
    -- and conversion (TESTBENCH / REGISTER_DEFINITION). Images live in storage.
    result_info  JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT result_info_object CHECK (jsonb_typeof(result_info) = 'object'),
    CONSTRAINT result_workbench_object CHECK (
        NOT (result_info ? 'workbench') OR jsonb_typeof(result_info->'workbench') = 'object'
    ),
    CONSTRAINT result_status_allowed CHECK (status IN ('PENDING', 'SUCCEEDED', 'FAILED')),
    CONSTRAINT result_round_positive CHECK (round_no > 0),
    CONSTRAINT result_execution_round_unique UNIQUE (execution_id, round_no)
);

CREATE INDEX IF NOT EXISTS idx_result_execution_id ON core.result(execution_id);
