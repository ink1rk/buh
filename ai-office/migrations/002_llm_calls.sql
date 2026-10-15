CREATE TABLE IF NOT EXISTS llm_calls (
 id uuid PRIMARY KEY, task_id uuid NOT NULL UNIQUE REFERENCES tasks(id), owner_id bigint NOT NULL REFERENCES users(id),
 model text NOT NULL, state text NOT NULL CHECK(state IN ('reserved','finished','uncertain','failed')),
 reserve_usd numeric(14,8) NOT NULL CHECK(reserve_usd>0), estimated_usd numeric(14,8),
 usage jsonb, created_at timestamptz NOT NULL DEFAULT now(), finished_at timestamptz
);
CREATE INDEX IF NOT EXISTS llm_calls_budget_idx ON llm_calls(owner_id,created_at);
ALTER TABLE usage_costs ADD COLUMN IF NOT EXISTS billing_state text NOT NULL DEFAULT 'actual';
INSERT INTO schema_migrations(version) VALUES (2) ON CONFLICT DO NOTHING;

