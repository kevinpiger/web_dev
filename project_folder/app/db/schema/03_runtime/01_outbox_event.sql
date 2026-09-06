CREATE SCHEMA IF NOT EXISTS runtime;

CREATE TABLE IF NOT EXISTS runtime.outbox_event (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    execution_id  UUID NOT NULL REFERENCES core.execution(id) ON DELETE CASCADE,
    event_type    VARCHAR(50) NOT NULL,
    status        VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    retry_count   INTEGER NOT NULL DEFAULT 0,
    available_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    published_at  TIMESTAMPTZ,
    last_error    TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT outbox_event_type_allowed CHECK (event_type IN ('EXECUTION_CREATED')),
    CONSTRAINT outbox_event_status_allowed CHECK (status IN ('PENDING', 'PUBLISHED', 'FAILED'))
);

CREATE INDEX IF NOT EXISTS idx_outbox_execution_id ON runtime.outbox_event(execution_id);
CREATE INDEX IF NOT EXISTS idx_outbox_dispatch_queue
    ON runtime.outbox_event(status, available_at)
    WHERE status = 'PENDING';
