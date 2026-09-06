CREATE SCHEMA IF NOT EXISTS iam;

CREATE TABLE IF NOT EXISTS iam.app_user (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    employee_no     VARCHAR(50),
    username        VARCHAR(100) NOT NULL,
    email           VARCHAR(255) NOT NULL,
    organization    VARCHAR(100),
    role_id         UUID NOT NULL REFERENCES iam.role(id) ON DELETE RESTRICT,
    is_active       BOOLEAN NOT NULL DEFAULT true,
    -- §3 增補：freeze 只有 token/token_expire_at，沒有密碼欄位；NULL 供日後 SSO-only 使用者
    password_hash   VARCHAR(255),
    token           VARCHAR(255),
    token_expire_at TIMESTAMPTZ,
    last_login_at   TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by      UUID REFERENCES iam.app_user(id) ON DELETE SET NULL,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_by      UUID REFERENCES iam.app_user(id) ON DELETE SET NULL,
    CONSTRAINT app_user_email_unique UNIQUE (email)
);

CREATE INDEX IF NOT EXISTS idx_app_user_role_id ON iam.app_user(role_id);
