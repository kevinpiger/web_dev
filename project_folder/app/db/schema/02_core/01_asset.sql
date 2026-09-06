CREATE SCHEMA IF NOT EXISTS core;

CREATE TABLE IF NOT EXISTS core.asset (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      UUID NOT NULL REFERENCES iam.app_user(id) ON DELETE RESTRICT,
    file_name    VARCHAR(255) NOT NULL,
    mime_type    VARCHAR(100),
    file_type    VARCHAR(20) NOT NULL,
    storage_type VARCHAR(20) NOT NULL,
    storage_key  VARCHAR(500) NOT NULL,
    file_size    BIGINT,
    attributes   JSONB NOT NULL DEFAULT '{}'::jsonb,
    status       VARCHAR(20) NOT NULL DEFAULT 'UPLOADING',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at   TIMESTAMPTZ,
    CONSTRAINT asset_file_type_allowed CHECK (file_type IN ('PDF', 'IMAGE', 'SVG', 'OTHER')),
    CONSTRAINT asset_storage_type_allowed CHECK (storage_type IN ('LOCAL', 'NAS', 'S3', 'MINIO')),
    CONSTRAINT asset_status_allowed CHECK (status IN ('UPLOADING', 'READY', 'FAILED'))
);

CREATE INDEX IF NOT EXISTS idx_asset_user_id ON core.asset(user_id);
CREATE INDEX IF NOT EXISTS idx_asset_active ON core.asset(user_id) WHERE deleted_at IS NULL;
