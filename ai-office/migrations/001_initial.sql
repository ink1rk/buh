CREATE TABLE IF NOT EXISTS schema_migrations (version integer PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS users (
 id bigint PRIMARY KEY, timezone text NOT NULL DEFAULT '', paused boolean NOT NULL DEFAULT false,
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS tasks (
 id uuid PRIMARY KEY, owner_id bigint NOT NULL REFERENCES users(id), correlation_id uuid NOT NULL,
 kind text NOT NULL, title text NOT NULL, state text NOT NULL CHECK (state IN ('created','queued','running','waiting_approval','waiting_external','succeeded','failed','cancelled')),
 version integer NOT NULL DEFAULT 1, schema_version integer NOT NULL DEFAULT 1,
 created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS tasks_owner_idx ON tasks(owner_id, created_at DESC);
CREATE TABLE IF NOT EXISTS telegram_updates (update_id bigint PRIMARY KEY, owner_id bigint, processed_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS poll_state (id integer PRIMARY KEY CHECK(id=1), next_offset bigint NOT NULL DEFAULT 0);
INSERT INTO poll_state(id) VALUES (1) ON CONFLICT DO NOTHING;
CREATE TABLE IF NOT EXISTS scheduled_triggers (
 id uuid PRIMARY KEY, owner_id bigint NOT NULL REFERENCES users(id), task_id uuid NOT NULL REFERENCES tasks(id),
 due_at_utc timestamptz NOT NULL, timezone text NOT NULL, local_time text NOT NULL,
 state text NOT NULL DEFAULT 'pending' CHECK(state IN ('pending','enqueued','missed','cancelled')),
 dedupe_key text NOT NULL UNIQUE
);
CREATE INDEX IF NOT EXISTS triggers_due_idx ON scheduled_triggers(due_at_utc) WHERE state='pending';
CREATE TABLE IF NOT EXISTS outbox_events (
 id uuid PRIMARY KEY, owner_id bigint NOT NULL REFERENCES users(id), chat_id bigint NOT NULL,
 payload jsonb NOT NULL, dedupe_key text NOT NULL UNIQUE,
 state text NOT NULL DEFAULT 'pending' CHECK(state IN ('pending','sending','sent','uncertain','failed')),
 attempts integer NOT NULL DEFAULT 0, available_at timestamptz NOT NULL DEFAULT now(),
 created_at timestamptz NOT NULL DEFAULT now(), sent_at timestamptz
);
CREATE TABLE IF NOT EXISTS audit_events (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, owner_id bigint,
 action text NOT NULL, resource_id text, correlation_id uuid,
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS approvals (
 id uuid PRIMARY KEY, owner_id bigint NOT NULL REFERENCES users(id), task_id uuid NOT NULL REFERENCES tasks(id),
 token_hash text NOT NULL UNIQUE, payload_hash text NOT NULL, expires_at timestamptz NOT NULL, consumed_at timestamptz,
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS artifacts (
 id uuid PRIMARY KEY, owner_id bigint NOT NULL REFERENCES users(id), task_id uuid NOT NULL REFERENCES tasks(id),
 content jsonb NOT NULL, content_hash text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(task_id)
);
CREATE TABLE IF NOT EXISTS execution_tokens (
 token_hash text PRIMARY KEY, owner_id bigint NOT NULL REFERENCES users(id), task_id uuid NOT NULL UNIQUE REFERENCES tasks(id),
 expires_at timestamptz NOT NULL, consumed_at timestamptz
);
CREATE TABLE IF NOT EXISTS agent_profiles (
 name text PRIMARY KEY, capabilities jsonb NOT NULL DEFAULT '[]', enabled boolean NOT NULL DEFAULT false
);
INSERT INTO agent_profiles(name) VALUES ('assistant'),('researcher'),('planner'),('developer'),('technical_expert') ON CONFLICT DO NOTHING;
CREATE TABLE IF NOT EXISTS usage_costs (
 id uuid PRIMARY KEY, owner_id bigint REFERENCES users(id), task_id uuid REFERENCES tasks(id),
 provider text NOT NULL, amount_usd numeric(14,8) NOT NULL CHECK (amount_usd >= 0), created_at timestamptz NOT NULL DEFAULT now()
);
INSERT INTO schema_migrations(version) VALUES (1) ON CONFLICT DO NOTHING;

