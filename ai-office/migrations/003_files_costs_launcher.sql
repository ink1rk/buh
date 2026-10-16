CREATE TABLE IF NOT EXISTS stored_files (
 id uuid PRIMARY KEY, owner_id bigint NOT NULL REFERENCES users(id), task_id uuid REFERENCES tasks(id),
 kind text NOT NULL CHECK (kind IN ('document','voice','audio','photo')),
 mime text NOT NULL, size_bytes integer NOT NULL CHECK (size_bytes > 0 AND size_bytes <= 2000000),
 sha256 text NOT NULL, content bytea NOT NULL, unique_id text NOT NULL, transcript text,
 created_at timestamptz NOT NULL DEFAULT now(), UNIQUE (owner_id, unique_id)
);
CREATE INDEX IF NOT EXISTS stored_files_owner_idx ON stored_files(owner_id, created_at DESC);
CREATE TABLE IF NOT EXISTS cost_checks (
 id uuid PRIMARY KEY, owner_id bigint REFERENCES users(id),
 estimated_usd numeric(14,8), usage_api_status text NOT NULL,
 litellm_spend_usd numeric(14,8), actual_confirmed boolean NOT NULL DEFAULT false,
 created_at timestamptz NOT NULL DEFAULT now()
);
DO $$ BEGIN
 ALTER TABLE cost_checks ADD CONSTRAINT cost_checks_actual_chk CHECK (actual_confirmed = false OR usage_api_status = 'dashboard_confirmed');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
CREATE TABLE IF NOT EXISTS specialist_jobs (
 task_id uuid PRIMARY KEY REFERENCES tasks(id), owner_id bigint NOT NULL REFERENCES users(id),
 profile text NOT NULL, job_name text, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS specialist_results (
 task_id uuid PRIMARY KEY REFERENCES tasks(id), owner_id bigint NOT NULL REFERENCES users(id),
 profile text NOT NULL, body text NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE approvals ADD COLUMN IF NOT EXISTS payload jsonb;
ALTER TABLE approvals ADD COLUMN IF NOT EXISTS decision text;
INSERT INTO schema_migrations(version) VALUES (3) ON CONFLICT DO NOTHING;
