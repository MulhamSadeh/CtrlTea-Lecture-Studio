CREATE TABLE system_roles(name TEXT PRIMARY KEY);
INSERT INTO system_roles VALUES('SuperAdmin'),('Member'),('Reviewer');
ALTER TABLE accounts ADD COLUMN role TEXT NOT NULL DEFAULT 'Member' REFERENCES system_roles(name);
ALTER TABLE accounts ADD COLUMN auth_version BIGINT NOT NULL DEFAULT 0;
ALTER TABLE accounts ADD COLUMN created_at TIMESTAMPTZ NOT NULL DEFAULT now();
ALTER TABLE profiles ADD COLUMN avatar_path TEXT;
CREATE TABLE credentials(user_id TEXT PRIMARY KEY REFERENCES accounts(id),password_hash TEXT NOT NULL);
CREATE TABLE auth_tokens(
 token_hash TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES accounts(id),
 kind TEXT NOT NULL CHECK(kind IN ('verify','reset','bootstrap','admin_recovery')),
 expires_at TIMESTAMPTZ NOT NULL,consumed_at TIMESTAMPTZ,created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX auth_tokens_user ON auth_tokens(user_id,kind);
CREATE TABLE sessions(
 id TEXT PRIMARY KEY,token_hash TEXT UNIQUE NOT NULL,user_id TEXT NOT NULL REFERENCES accounts(id),
 auth_version BIGINT NOT NULL,created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 last_seen TIMESTAMPTZ NOT NULL DEFAULT now(),expires_at TIMESTAMPTZ NOT NULL,
 reauthenticated_at TIMESTAMPTZ NOT NULL DEFAULT now(),device TEXT NOT NULL DEFAULT ''
);
CREATE INDEX sessions_account ON sessions(user_id,expires_at);
CREATE TABLE permission_catalog(name TEXT PRIMARY KEY,group_name TEXT NOT NULL,label TEXT NOT NULL,future BOOLEAN NOT NULL DEFAULT false);
CREATE TABLE role_permissions(role TEXT REFERENCES system_roles(name),permission TEXT REFERENCES permission_catalog(name),PRIMARY KEY(role,permission));
CREATE TABLE permission_overrides(
 user_id TEXT REFERENCES accounts(id),permission TEXT REFERENCES permission_catalog(name),enabled BOOLEAN NOT NULL,
 granted_by TEXT REFERENCES accounts(id),updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),PRIMARY KEY(user_id,permission)
);
CREATE TABLE resource_grants(
 id TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES accounts(id),workspace_id TEXT NOT NULL REFERENCES workspaces(id),
 resource_kind TEXT NOT NULL CHECK(resource_kind IN ('course','lecture')),resource_id TEXT NOT NULL,
 permissions TEXT[] NOT NULL,granted_by TEXT NOT NULL REFERENCES accounts(id),
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(),expires_at TIMESTAMPTZ,revoked_at TIMESTAMPTZ
);
CREATE INDEX grants_recipient ON resource_grants(user_id,workspace_id) WHERE revoked_at IS NULL;
CREATE TABLE auth_rate_limits(key_hash TEXT NOT NULL,slot BIGINT NOT NULL,hits INTEGER NOT NULL,PRIMARY KEY(key_hash,slot));
CREATE TABLE security_audit(
 id BIGSERIAL PRIMARY KEY,actor_id TEXT,action TEXT NOT NULL,target TEXT NOT NULL DEFAULT '',
 workspace_id TEXT,outcome TEXT NOT NULL,created_at TIMESTAMPTZ NOT NULL DEFAULT now(),metadata JSONB NOT NULL DEFAULT '{}'
);
CREATE INDEX audit_recent ON security_audit(created_at DESC,id DESC);
CREATE TABLE bootstrap_state(id INTEGER PRIMARY KEY CHECK(id=1),completed BOOLEAN NOT NULL DEFAULT false);
INSERT INTO bootstrap_state(id) VALUES(1);
CREATE TABLE trash_records(
 id TEXT NOT NULL,workspace_id TEXT NOT NULL DEFAULT current_setting('ctrltea.workspace_id',true) REFERENCES workspaces(id),
 kind TEXT NOT NULL,resource_id TEXT NOT NULL,deleted_by TEXT,created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 expires_at TIMESTAMPTZ NOT NULL DEFAULT now()+interval '30 days',snapshot TEXT NOT NULL,restored_at TIMESTAMPTZ,
 PRIMARY KEY(workspace_id,id)
);
ALTER TABLE trash_records ENABLE ROW LEVEL SECURITY;
ALTER TABLE trash_records FORCE ROW LEVEL SECURITY;
CREATE POLICY trash_scope ON trash_records USING(workspace_id=current_setting('ctrltea.workspace_id',true)) WITH CHECK(workspace_id=current_setting('ctrltea.workspace_id',true));
ALTER TABLE jobs ADD COLUMN requested_by TEXT REFERENCES accounts(id);
-- The authentication service is a separate restricted DB identity. Content
-- access still uses the original runtime role/RLS with an authorized scope.
CREATE POLICY account_auth_service ON accounts USING(current_setting('ctrltea.auth_service',true)='1') WITH CHECK(current_setting('ctrltea.auth_service',true)='1');
CREATE POLICY profile_auth_service ON profiles USING(current_setting('ctrltea.auth_service',true)='1') WITH CHECK(current_setting('ctrltea.auth_service',true)='1');
CREATE POLICY workspace_auth_service ON workspaces USING(current_setting('ctrltea.auth_service',true)='1') WITH CHECK(current_setting('ctrltea.auth_service',true)='1');
-- No grants are made to PUBLIC. scripts/provision_auth.py grants the precise
-- service privileges and seeds the frozen permission catalog transactionally.

CREATE POLICY jobs_auth_dispatch ON jobs FOR SELECT USING(current_setting('ctrltea.auth_service',true)='1');
