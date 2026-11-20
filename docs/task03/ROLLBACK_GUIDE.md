# Rollback and restoration — Task03

The original uploaded ZIPs, Task01 backups and baseline directory remain unchanged. UPDATED_PROJECT.zip is code/configuration only, never a user-data backup. Destructive Alembic downgrade is deliberately refused; the initial migration does not pretend dropping tables preserves data.

## Before PostgreSQL accepts new work

1. Stop the new local API/worker and retain its logs/import receipt privately.
2. Keep the target PostgreSQL/database directory separate; do not overwrite the source SQLite.
3. Start the preserved V1 or updated SQLite mode on a **copy** of the consistent original SQLite+file checkpoint. Clear PG settings or explicitly set CTRLTEA_DB_BACKEND=sqlite.
4. Verify database integrity, file digests, lecture JSON, source pages and a representative unchanged-engine export.

The migration tests verify that original SQLite bytes remain unchanged, missing/invalid input does not create accepted rows, a target SQL failure rolls back metadata, and retries do not duplicate import. The original local backup remains the rollback point. Actual user installation data was absent, so this was exercised with synthetic fixtures.

## After accepted PostgreSQL writes

Do not replace PostgreSQL with the pre-import SQLite and discard new work. Freeze writes, retain a fresh PostgreSQL+file checkpoint, and roll the application forward or back to a compatible PG-capable release. A return to local V1 requires an explicit course-bundle export/re-import or a separate reverse-migration task, with identity/provenance metadata retained separately. No universal lossless PG-to-SQLite installation converter is claimed in03.

## Consistent private backup

For this single-process local architecture, stop the API/worker for the checkpoint. Dump all ownership/metadata tables using an audited backup/migration role that can read all RLS-protected rows. Runtime owner-scoped credentials are **not** a complete backup identity. pg_dump's normal row_security=off behavior should fail rather than silently make an incomplete RLS dump if the role lacks rights; do not enable row filtering to silence that failure.

Use private PGSERVICE/password-file/environment configuration, then:

```bash
pg_dump --format=custom --file /PRIVATE/checkpoint/studio.dump
```

Copy the matching CTRLTEA_DATA_DIR/workspaces tree and record every relative path/length/SHA-256, application source version, Alembic head, PG and rendering tool versions. Encrypt the checkpoint and keep an independently recoverable copy and key access. A DB dump without source/artifact bytes is incomplete. A release ZIP or Docker volume alone is not a coordinated recovery set.

## Restore into new targets

1. Provision a new empty database and new private file root; retain the prior targets.
2. Verify backup hashes and restore the SQL dump. Use an offline operator, not the API runtime role.
3. Restore the matching files preserving relative workspace paths and digests.
4. Re-provision the restricted runtime role/grants if `--no-owner --no-privileges` was used; verify FORCE RLS/policies and that runtime cannot own tables or access another workspace.
5. Verify row counts, raw doc/history/base_doc hashes, file digests, aliases and FK relationships. Check import receipts and distinguish old pending jobs from permitted work.
6. Start one local API/worker, inspect original/independent lecture content, source access, expected-revision conflict, DOCX/PDF and mathematical visibility.
7. Only switch the trusted local process configuration after checks pass. Future04/05 must additionally revoke restored sessions and reset worker execution epochs when those features exist.

The executed PG dump/restore test restores a native custom-format dump into a separate randomly named database, checks exact lecture TEXT, and drops only that disposable restored database afterward. It is not a real-data disaster-recovery certification or a measured production RPO/RTO.

## Interrupted import

Exceptions before file installation roll back SQL and remove only the import's newly staged copy. Once files are renamed into place they are retained even on error: a COMMIT acknowledgement can be lost after the database has accepted the transaction. A same-input retry resolves a committed receipt without deleting files. Originals are never removed. A process/host crash after filesystem rename but before SQL commit may leave a private unclaimed file directory without a receipt; a later import refuses to overlay it. Retain/quarantine that directory, verify that no receipt/accepted target rows exist, then retry into a **new workspace/root**. Automated crash reconciliation is reserved for a later storage/worker task; do not delete the directory blindly. The tests inject lost acknowledgement after COMMIT and verify that accepted file bytes remain recoverable.

If an already committed import is missing target files, a same-input retry reports recovery required. Restore exact missing bytes from the consistent original checkpoint, verify digests, then retry verification. The tests execute this recovery. Keep the import receipt/input fingerprint and document the operator action.

## Known remaining gates

The local worker guard is not distributed leasing/exactly-once publication, and the current exporter reads at execution time as in V1. Task03 does not introduce snapshot-at-request orchestration or promise multi-process failover. Full online worker reliability, private object storage, backup scheduling, runtime parser isolation and authenticated ownership checks are prerequisites before team staging in later tasks.
