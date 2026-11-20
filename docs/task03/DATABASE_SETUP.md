# Database setup — local Task03 development

**Do not expose this unauthenticated build online.** Authentication, emails, sharing and deployment are not implemented. The default remains local SQLite unless CTRLTEA_DB_BACKEND=postgres is explicitly exported. The supplied frontend is unchanged and built.

## Requirements

Python>=3.11 and original project dependencies/tools/fonts; PostgreSQL16; psycopg/Alembic. Task03 exercised Python3.12.14, PostgreSQL16.2, psycopg3.3.6, Alembic1.20.1 and SQLAlchemy2.1.6. PostgreSQL16 is the supported-major target of this task, replacing Task02's provisional17 choice. The old16.2 test binary is not a production security recommendation: qualify a currently patched16 image/toolchain before staging. Windows/NixOS and Docker execution were not available for certification here.

Run from the extracted ctrltea-studio directory. The snippets below use Bash/POSIX environment syntax; fish users can use `env NAME=value command` or `set -gx NAME value` for equivalent assignments. Keep secret values private; placeholders below are not passwords.

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[test,postgres]'
python -m pip install -r requirements-postgres-tested.txt
```

Use the existing Windows setup guide for Pandoc, LibreOffice/Math, Tesseract ara+eng and fonts, then install the postgres extra. Linux/Nix users retain the existing local setup. The migration files/assets require the source checkout and editable install; this is not a standalone wheel distribution.

## Optional Docker Compose database

compose.yaml contains only a local PostgreSQL service, loopback port and named volume. Copy .env.example privately to .env and supply POSTGRES_DB, POSTGRES_USER and a long random POSTGRES_PASSWORD. Compose reads .env; the Python application does not automatically load it. Never commit a populated .env.

```bash
docker compose up -d postgres
docker compose ps
```

Use separate database URLs: CTRLTEA_MIGRATION_URL for the offline schema/operator role; CTRLTEA_DATABASE_URL for the restricted ctrltea_app runtime role. Values have the standard form postgresql://USER:URL_ENCODED_PASSWORD@127.0.0.1:PORT/DATABASE. Inject actual values privately; do not put them in source or shell-history examples.

```bash
python -m ctrltea.database upgrade
python scripts/provision_runtime.py
python -m ctrltea.database create-workspace --workspace legacy_installation_01
```

The first command requires CTRLTEA_MIGRATION_URL. Runtime provisioning also requires a random CTRLTEA_RUNTIME_PASSWORD of at least20 characters and refuses to overwrite an existing role. It creates a **database infrastructure role**, not a platform account or Super Admin. It grants no account/profile or ownership-change access. Existing managed installations need an operator allowed to provision DB roles; do not use migration credentials in the API as a shortcut.

Set CTRLTEA_DATABASE_URL to the restricted role, CTRLTEA_WORKSPACE_ID to the explicitly provisioned workspace, CTRLTEA_DATA_DIR to an absolute private storage root, CTRLTEA_DB_BACKEND=postgres. An unclaimed imported/local workspace also requires CTRLTEA_ALLOW_UNCLAIMED=1 until04 provides verified claims. No client can select a workspace via HTTP.

Remove migration/admin/password-provisioning variables from the runtime shell after setup. Start with the existing launcher, which binds127.0.0.1:

```bash
unset CTRLTEA_MIGRATION_URL CTRLTEA_RUNTIME_PASSWORD POSTGRES_PASSWORD
python scripts/start.py
```

Only one API/worker process per configured workspace is supported in03. Do not use Uvicorn --workers, multiple reload instances or expose a shared operator session to members. A PostgreSQL advisory guard rejects a second worker for the same workspace. Full multi-user dispatch/retry/isolation is later work; this guard preserves the existing local worker architecture.

## Import a legacy installation copy

Stop the original app and workers and create a private consistent backup of studio.sqlite3 plus its sources/exports/caches. Never point the import at the only active installation. Nonempty WAL input is refused; use SQLite backup API or a stopped, checkpointed copy. The read-only inspector does not call store.init or rewrite the original database.

```bash
python -m ctrltea.database import-sqlite \
  --data-dir /PRIVATE/consistent-copy \
  --workspace legacy_installation_01 \
  --data-root /PRIVATE/new-storage \
  --dry-run --report /PRIVATE/inspection.json

python -m ctrltea.database import-sqlite \
  --data-dir /PRIVATE/consistent-copy \
  --workspace legacy_installation_01 \
  --data-root /PRIVATE/new-storage \
  --report /PRIVATE/import-report.json
```

Use the same /PRIVATE/new-storage as CTRLTEA_DATA_DIR when running the imported workspace. The resulting private path is new-storage/workspaces/legacy_installation_01. Import before first launching the app on this target root: import requires an unclaimed, empty database workspace and an absent destination file directory; it never overlays data. If an empty startup directory already exists, choose a new target root rather than overwriting it. Repeating the same complete import verifies rows/files and returns already_imported. A different input or incomplete target is rejected for deliberate recovery. Reports contain private filenames/provenance/job records and should remain private.

## Tests

```bash
PYTHONPATH=backend python -m pytest -q
cd frontend
npm ci
npm run build
```

The new PostgreSQL tests skip unless CTRLTEA_TEST_DATABASE_URL and CTRLTEA_MIGRATION_URL refer to disposable test databases with runtime/admin roles. Never use operational data. The test admin must create temporary workspaces/roles; the dump/restore test creates and drops a fresh randomly named database and needs native pg_dump/pg_restore. Run with PG client tools on PATH. The integration tests themselves never drop the supplied test database, but they intentionally write test records and create a synthetic trigger, so a dedicated disposable database is mandatory.

```bash
PYTHONPATH=backend python -m pytest -q tests/test_postgres.py
```

Set CTRLTEA_TESSDATA_DIR to a directory containing ara.traineddata and eng.traineddata if Arabic OCR is not installed system-wide. Full original regression fixtures under examples/ are private and omitted from UPDATED_PROJECT.zip; restore them locally from the verified Task01 private baseline to run the entire historical suite. The new database tests generate their own disposable scientific fixtures and need no private originals.

## Backup and restore

Follow ROLLBACK_GUIDE.md: stop writes/worker, capture full SQL plus the matching workspace tree and a digest manifest, restore into a new DB/root and validate before switching. Compose's named volume is persistence, not a backup; never use `docker compose down -v` on the only retained copy. No live-user database was supplied or migrated in this task.
