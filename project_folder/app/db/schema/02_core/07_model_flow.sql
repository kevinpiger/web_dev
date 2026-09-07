CREATE SCHEMA IF NOT EXISTS core;

CREATE TABLE IF NOT EXISTS core.model_flow (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        VARCHAR(200) NOT NULL,
    description TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    is_valid    BOOLEAN NOT NULL DEFAULT true,
    deleted_at  TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_model_flow_active_created
    ON core.model_flow (created_at DESC, id DESC) WHERE deleted_at IS NULL;
