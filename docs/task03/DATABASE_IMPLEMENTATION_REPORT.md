# Database implementation report — Task03

23 October 2026. **Real source changes implemented; no authentication, mail, sharing UI or deployment.** The approved scope is private user workspaces in one PostgreSQL database, superseding default shared courses. Original project/backups remain untouched; work occurred in a separate implementation copy.

## What changed

PostgreSQL persistence now serves the existing application through its small store interface. psycopg handles parameterized queries; Alembic provides versioned migrations. The existing React layout, API paths, lecture/result/project JSON contracts and mathematics/OCR/export functions remain in place. No second rendering-engine copy, microservice or distributed queue was introduced, because the updated Task03 explicitly preserves the existing worker architecture.

| Area | Implementation / source evidence |
|---|---|
| Backend selection | persistence.backend and postgres_connection: explicit environment selection, no fallback on PG failure, restricted role checks, transaction-local workspace scope |
| Ownership | migrations/private_schema.sql: account/profile metadata, private/unclaimed workspace,16 domain tables with forced RLS and composite scope FKs; alembic_version adds the version bookkeeping table |
| Legacy SQL compatibility | PostgresConnection: bound placeholders, explicit legacy insert column mapping, only the two existing alias upsert dialects translated; returned rows hide internal workspace/is_legacy fields from v1 payloads |
| Transactions | store.connect/transaction: shared UnitOfWork for nested operations, rollback-only state after a nested failure; SQLite BEGIN IMMEDIATE and PG row locks |
| Atomic save | store.save_document: locked current head, expected-revision check, previous snapshot and guarded update in one transaction; response assembled from that transaction's own head |
| Import/append safety | authoring.import_result wraps candidate/save/task state; bundles.append_lecture locks/checks head; imported bundle history is marked legacy so duplicates are preserved |
| Files | ScopedDataPath resolves private workspace directories without changing engine modules; record_asset indexes relative paths/digests; source and export routes resolve scoped DB parents |
| Worker compatibility | Same in-process Worker/thread/poll/extract/export execution. Trusted context copied to thread; one PG advisory guard per workspace; recovery only after acquiring that guard; enqueue is transactionally serialized per lecture |
| Installation migration | database.inspect_sqlite/import_sqlite: read-only consistent copy, dry-run, integrity/relations/files/JSON validation, raw preservation, restricted ownership, fingerprint receipt and retry checks |
| Setup | compose.yaml, .env.example, optional postgres dependency group, tested persistence versions and offline runtime DB-role provisioning |

## Schema and compatibility decisions

Use PostgreSQL16 as the tested major. The environment supplied a native16.2 test binary; qualify a current patched16 reference image before staging. IDs and raw scientific/current/history/base_doc strings remain TEXT. JSON-object checks validate without JSONB rewriting. Ownership is relational metadata, not a required key injected into LectureDocument.

The ten legacy data domains are courses, lectures, revisions, sources, pages, jobs, author_runs, author_tasks, source_aliases and run_aliases. Added domains are accounts, profiles, workspaces, private_assets, import_receipts and import_provenance. Future workflow/grant tables are specified in DATA_OWNERSHIP_DESIGN rather than overbuilt now. Account tables contain no login flow or password/session implementation.

Scope-prefixed indexes cover course lecture lists, source lookup, revision history, job queue/lecture lookup and author-run lookup. New revisions have a scoped unique version constraint. Old duplicate/gapped numbers remain retained with is_legacy=1; no chronology/actor is fabricated. Existing bundle imports remain explicit independent copies with reference/alias remapping; cross-profile sharing is not exposed.

Legacy /api paths and body/result shapes remain unchanged, including409 stale-save errors. Internal ownership fields are omitted from legacy row responses/bundles. No frontend source changed; all68 rebuilt dist files match V1 exactly. Math, figure, schema, runtime, source-processing and export modules listed in evidence/SOURCE_VERIFICATION.json are byte-identical. The existing native/portable export path was exercised through PG and HTTP.

## Modified original files — complete list

| File | Reason |
|---|---|
| backend/ctrltea/store.py | Backend dispatch, nested transactions, atomic save, scoped paths and file index |
| backend/ctrltea/api.py | Scope checks for exports and private file indexing; original endpoints/layout retained |
| backend/ctrltea/authoring.py | Atomic result+task/run transaction |
| backend/ctrltea/bundles.py | Consistent PG reads, atomic append, preservation of imported legacy duplicate history |
| backend/ctrltea/jobs.py | Context propagation, single-workspace process guard, transactional enqueue and asset indexing; same worker architecture |
| pyproject.toml | Optional postgres dependency group |
| tests/test_theme.py | Select intended content table/header instead of the cover index; all original assertions retained |
| .gitignore | Exclude populated configuration and private database/dump files |

## Added source/configuration files

backend/ctrltea/persistence.py; backend/ctrltea/database.py; alembic.ini; migrations/env.py; migrations/private_schema.sql; migrations/versions/0001_private_persistence.py; compose.yaml; .env.example; requirements-postgres-tested.txt; scripts/provision_runtime.py; tests/test_postgres.py; tests/test_persistence_sqlite.py. Delivery documentation is additionally included under docs/task03. Full paths/hashes are recorded in the evidence inventory.

## Verification and limitations

See TEST_RESULTS and MIGRATION_REPORT for exact executed counts/failures and native database test conditions. The meaningful no-overwrite case uses two independent PostgreSQL connections synchronized before save; one wins and the other conflicts. Failure injection checks head/history/task rollback, import SQL rollback and loss of COMMIT acknowledgement without deleting possibly committed file bytes. Native dump/restore targets a new disposable database.

The original operational user database is absent. No real user dataset was migrated. This is a persistence foundation, not a production multi-user release. One trusted workspace per local process and the original worker remain intentional03 limits. The advisory guard is not distributed leasing or resilient exactly-once execution; worker scheduling, job-input snapshots, crash reconciliation, parser sandboxing and cloud storage stay later tasks. Export reads the head when execution begins as in V1, not a new snapshot-at-request feature.

New profile description text grants no privileges; platform roles, verified legacy claims, resource grants and immutable review release targets are future work. Existing previous-head history and mutable report paths must not be labelled certified immutable approvals. File cleanup/cascading deletion retains the local app's orphan-file limitation; private prefixes prevent it becoming cross-workspace access. Complete user-facing conflict comparison/rebase remains09.

One known baseline test still fails: statistics expects5 PDF pages and receives6 on this rendering environment. The preceding no-empty/end-marker-only-page assertions pass. This is unchanged from Task01 and unresolved; no mathematical/scientific/layout change was made to force a pass. Docker/Windows/Word/NixOS/native production deployment were not certified.

Task03's persistence requirements are implemented and tested with these explicit limits. Task04 and public staging remain unstarted.
