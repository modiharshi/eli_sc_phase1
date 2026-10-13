-- 0005: audit trail for human decisions made in the review queues.
CREATE TABLE review_audit (
    audit_id     bigserial PRIMARY KEY,
    actor        text        NOT NULL,
    acted_at     timestamptz NOT NULL DEFAULT now(),
    target_table text        NOT NULL,
    target_key   text        NOT NULL,
    action       text        NOT NULL,
    before_value jsonb,
    after_value  jsonb
);
