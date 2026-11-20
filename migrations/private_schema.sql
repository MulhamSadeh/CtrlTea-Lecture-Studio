CREATE TABLE accounts (
 id TEXT PRIMARY KEY, full_name TEXT NOT NULL, email TEXT NOT NULL,
 normalized_email TEXT NOT NULL UNIQUE, email_verified_at TIMESTAMPTZ,
 state TEXT NOT NULL DEFAULT 'pending' CHECK(state IN ('pending','active','disabled'))
);
CREATE TABLE profiles (
 user_id TEXT PRIMARY KEY REFERENCES accounts(id),
 team_description TEXT NOT NULL DEFAULT '', version BIGINT NOT NULL DEFAULT 0 CHECK(version>=0)
);
CREATE TABLE workspaces (
 id TEXT PRIMARY KEY CHECK(id ~ '^[A-Za-z0-9_-]{1,80}$'),
 owner_user_id TEXT UNIQUE REFERENCES accounts(id),
 state TEXT NOT NULL DEFAULT 'unclaimed' CHECK(state IN ('unclaimed','private','suspended')),
 created TIMESTAMPTZ NOT NULL DEFAULT now(),
 CHECK((state='unclaimed' AND owner_user_id IS NULL) OR (state IN ('private','suspended') AND owner_user_id IS NOT NULL))
);
CREATE TABLE courses (
 id TEXT NOT NULL, name TEXT NOT NULL, doctor TEXT NOT NULL DEFAULT '', created TEXT NOT NULL,
 workspace_id TEXT NOT NULL DEFAULT current_setting('ctrltea.workspace_id',true) REFERENCES workspaces(id),
 PRIMARY KEY(workspace_id,id)
);
CREATE TABLE lectures (
 id TEXT NOT NULL,course_id TEXT NOT NULL,title TEXT NOT NULL,doc TEXT NOT NULL CHECK(json_typeof(doc::json)='object'),
 revision BIGINT NOT NULL DEFAULT 0 CHECK(revision>=0),updated TEXT NOT NULL,
 theme TEXT NOT NULL DEFAULT 'cinnamon' CHECK(theme IN ('cinnamon','honey','olive')),
 workspace_id TEXT NOT NULL DEFAULT current_setting('ctrltea.workspace_id',true),
 PRIMARY KEY(workspace_id,id),
 FOREIGN KEY(workspace_id,course_id) REFERENCES courses(workspace_id,id) ON DELETE CASCADE
);
CREATE TABLE revisions (
 id TEXT NOT NULL,lecture_id TEXT NOT NULL,revision BIGINT NOT NULL CHECK(revision>=0),
 doc TEXT NOT NULL CHECK(json_typeof(doc::json)='object'),created TEXT NOT NULL,reason TEXT NOT NULL,
 workspace_id TEXT NOT NULL DEFAULT current_setting('ctrltea.workspace_id',true),is_legacy INTEGER NOT NULL DEFAULT 0 CHECK(is_legacy IN (0,1)),
 PRIMARY KEY(workspace_id,id),
 FOREIGN KEY(workspace_id,lecture_id) REFERENCES lectures(workspace_id,id) ON DELETE CASCADE
);
CREATE UNIQUE INDEX revisions_new_version ON revisions(workspace_id,lecture_id,revision) WHERE is_legacy=0;
CREATE INDEX lectures_course ON lectures(workspace_id,course_id,updated DESC);
CREATE INDEX revisions_history ON revisions(workspace_id,lecture_id,revision DESC);
CREATE TABLE sources (
 id TEXT NOT NULL,lecture_id TEXT NOT NULL,name TEXT NOT NULL,path TEXT NOT NULL,
 kind TEXT NOT NULL,priority INTEGER NOT NULL DEFAULT 1,role TEXT NOT NULL DEFAULT 'support',linked_id TEXT,digest TEXT NOT NULL,created TEXT NOT NULL,
 workspace_id TEXT NOT NULL DEFAULT current_setting('ctrltea.workspace_id',true),
 PRIMARY KEY(workspace_id,id),UNIQUE(workspace_id,lecture_id,id),
 FOREIGN KEY(workspace_id,lecture_id) REFERENCES lectures(workspace_id,id) ON DELETE CASCADE,
 FOREIGN KEY(workspace_id,lecture_id,linked_id) REFERENCES sources(workspace_id,lecture_id,id) DEFERRABLE INITIALLY DEFERRED,
 CHECK(linked_id IS NULL OR linked_id<>id),
 CHECK(path ~ '^sources/[A-Za-z0-9_-]+\.(pdf|docx|txt|md)$')
);
CREATE INDEX sources_lecture ON sources(workspace_id,lecture_id);
CREATE TABLE pages (
 source_id TEXT NOT NULL,number INTEGER NOT NULL CHECK(number>0),raw TEXT NOT NULL DEFAULT '',corrected TEXT,
 excluded INTEGER NOT NULL DEFAULT 0 CHECK(excluded IN (0,1)),method TEXT NOT NULL DEFAULT '',
 workspace_id TEXT NOT NULL DEFAULT current_setting('ctrltea.workspace_id',true),
 PRIMARY KEY(workspace_id,source_id,number),
 FOREIGN KEY(workspace_id,source_id) REFERENCES sources(workspace_id,id) ON DELETE CASCADE
);
CREATE TABLE jobs (
 id TEXT NOT NULL,lecture_id TEXT NOT NULL,kind TEXT NOT NULL,status TEXT NOT NULL,payload TEXT NOT NULL,
 result TEXT,error TEXT,progress INTEGER NOT NULL DEFAULT 0 CHECK(progress BETWEEN 0 AND 100),created TEXT NOT NULL,updated TEXT NOT NULL,
 workspace_id TEXT NOT NULL DEFAULT current_setting('ctrltea.workspace_id',true),
 PRIMARY KEY(workspace_id,id),
 FOREIGN KEY(workspace_id,lecture_id) REFERENCES lectures(workspace_id,id) ON DELETE CASCADE
);
CREATE INDEX jobs_status ON jobs(workspace_id,status,created);
CREATE INDEX jobs_lecture ON jobs(workspace_id,lecture_id,created DESC);
CREATE TABLE author_runs (
 id TEXT NOT NULL,lecture_id TEXT NOT NULL,section_ids TEXT NOT NULL,status TEXT NOT NULL,created TEXT NOT NULL,base_doc TEXT NOT NULL,
 workspace_id TEXT NOT NULL DEFAULT current_setting('ctrltea.workspace_id',true),
 PRIMARY KEY(workspace_id,id),UNIQUE(workspace_id,lecture_id,id),
 FOREIGN KEY(workspace_id,lecture_id) REFERENCES lectures(workspace_id,id) ON DELETE CASCADE
);
CREATE TABLE author_tasks (
 run_id TEXT NOT NULL,section_id TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'pending',
 workspace_id TEXT NOT NULL DEFAULT current_setting('ctrltea.workspace_id',true),
 PRIMARY KEY(workspace_id,run_id,section_id),
 FOREIGN KEY(workspace_id,run_id) REFERENCES author_runs(workspace_id,id) ON DELETE CASCADE
);
CREATE INDEX author_runs_lecture ON author_runs(workspace_id,lecture_id,created DESC);
CREATE TABLE source_aliases (
 lecture_id TEXT NOT NULL,original_id TEXT NOT NULL,source_id TEXT NOT NULL,
 workspace_id TEXT NOT NULL DEFAULT current_setting('ctrltea.workspace_id',true),
 PRIMARY KEY(workspace_id,lecture_id,original_id),
 FOREIGN KEY(workspace_id,lecture_id,source_id) REFERENCES sources(workspace_id,lecture_id,id) ON DELETE CASCADE
);
CREATE TABLE run_aliases (
 lecture_id TEXT NOT NULL,original_id TEXT NOT NULL,run_id TEXT NOT NULL,
 workspace_id TEXT NOT NULL DEFAULT current_setting('ctrltea.workspace_id',true),
 PRIMARY KEY(workspace_id,lecture_id,original_id),
 FOREIGN KEY(workspace_id,lecture_id,run_id) REFERENCES author_runs(workspace_id,lecture_id,id) ON DELETE CASCADE
);
CREATE TABLE import_receipts (
 workspace_id TEXT PRIMARY KEY REFERENCES workspaces(id), input_sha256 TEXT NOT NULL,
 report TEXT NOT NULL, created TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE private_assets (
 workspace_id TEXT NOT NULL REFERENCES workspaces(id),id TEXT NOT NULL,
 lecture_id TEXT,kind TEXT NOT NULL,relative_path TEXT NOT NULL,sha256 TEXT NOT NULL,bytes BIGINT NOT NULL CHECK(bytes>=0),
 PRIMARY KEY(workspace_id,id),UNIQUE(workspace_id,relative_path),
 FOREIGN KEY(workspace_id,lecture_id) REFERENCES lectures(workspace_id,id) ON DELETE CASCADE,
 CHECK(relative_path !~ '(^/|(^|/)\.\.(/|$)|\\)')
);
CREATE TABLE import_provenance (
 workspace_id TEXT NOT NULL,lecture_id TEXT NOT NULL,provenance TEXT NOT NULL,
 PRIMARY KEY(workspace_id,lecture_id),
 FOREIGN KEY(workspace_id,lecture_id) REFERENCES lectures(workspace_id,id) ON DELETE CASCADE
);
DO $$ DECLARE t TEXT; BEGIN
 FOREACH t IN ARRAY ARRAY['workspaces','courses','lectures','revisions','sources','pages','jobs','author_runs','author_tasks','source_aliases','run_aliases','import_receipts','private_assets','import_provenance'] LOOP
  EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY',t);
  EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY',t);
  EXECUTE format('CREATE POLICY private_workspace ON %I USING (%I = current_setting(''ctrltea.workspace_id'',true)) WITH CHECK (%I = current_setting(''ctrltea.workspace_id'',true))',t,CASE WHEN t='workspaces' THEN 'id' ELSE 'workspace_id' END,CASE WHEN t='workspaces' THEN 'id' ELSE 'workspace_id' END);
 END LOOP;
END $$;
ALTER TABLE accounts ENABLE ROW LEVEL SECURITY;
ALTER TABLE accounts FORCE ROW LEVEL SECURITY;
ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE profiles FORCE ROW LEVEL SECURITY;
-- No runtime policy/grant for accounts/profiles until Task04 identity integration.
