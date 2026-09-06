CREATE SCHEMA IF NOT EXISTS runtime;

CREATE TABLE IF NOT EXISTS runtime.inbox_event (
    message_id    UUID NOT NULL,
    consumer_name VARCHAR(100) NOT NULL,
    execution_id  UUID NOT NULL REFERENCES core.execution(id) ON DELETE CASCADE,
    processed_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT inbox_event_pk PRIMARY KEY (message_id, consumer_name)
);

CREATE INDEX IF NOT EXISTS idx_inbox_execution_id ON runtime.inbox_event(execution_id);
