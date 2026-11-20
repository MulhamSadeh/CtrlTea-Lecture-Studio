# SQLite migration implementation and evidence

23 October 2026. **No operational user database was supplied or migrated.** The original attachment contains source/examples only. All installation-import execution used synthetic stopped SQLite fixtures and disposable PostgreSQL workspaces; the shipped original scientific fixtures were retained unchanged for regression checks.

## Implemented process

database.py exposes upgrade, create-workspace and import-sqlite with distinct dry-run/report options. It never initializes the input with store.init. A nonempty WAL is refused; the caller must supply a consistent copy. Inspection uses a read-only immutable SQLite connection, checks database integrity/FKs/required columns, validates current/history/run JSON and scoped source-page references, detects missing/digest-mismatched attachments and rejects out-of-root/symlink assets.

Import requires an explicitly provisioned unclaimed workspace and an absent target file directory. Stage original bytes, verify them, insert rows in FK-safe order in one SQL transaction, force deferred constraints, compare counts and exact values, record portable asset metadata/provenance and the input receipt, then install files before the transaction's commit boundary. No original path is overwritten. After installation, an uncertain commit response never causes deletion of potentially accepted file bytes; the receipt resolves a retry, or the private directory is retained for operator recovery.

| Data | Preservation / intentional adjustment |
|---|---|
| Course/lecture IDs and metadata | Preserved within composite workspace identity; identical legacy IDs may exist independently in another workspace |
| doc/history/base_doc | Exact original TEXT, whitespace and Unicode included; validators inspect but do not dump/re-author imported strings |
| Theme | Existing value preserved; only missing old theme defaults to cinnamon |
| Source/file/page metadata | IDs, relative paths, linked source, raw/corrected/null/empty/excluded/method and digest/bytes preserved |
| Old revisions | Every row retained; duplicate revision numbers explicitly marked legacy; future saves use unique new version integrity |
| Author runs/tasks and aliases | All relationships retained and scoped; no run/source aliases resolve globally |
| Legacy pending jobs | queued/running changed to failed quarantine with explicit original-status diagnostic; original job records retained privately in import receipt/report. They are never automatically resumed |
| Generated files/caches/staged packages | Managed directory bytes copied and indexed under the private workspace; not exposed publicly or assumed scientifically approved |
| Ownership/actors | Workspace unclaimed, unknown historical authors remain unknown; no automatic claim or platform account created |

## Reproducible fixture checks executed

The comprehensive fixture contains one course, lecture, source/page, author run/task, source/run alias, queued job and **two historical rows with the same revision number**. It deliberately adds whitespace to lecture/history JSON and a corrected source page. The importer compares all ten legacy table counts and exact column values, excluding only the explicitly quarantined job status/error fields. Source SHA-256 and copied bytes match; original SQLite SHA-256 remains unchanged.

| Scenario | Expected and observed result |
|---|---|
| Dry-run | Verification report only; no destination directory or imported rows |
| Complete import | Raw IDs/text/files/aliases/history retained in an unclaimed workspace |
| Identical retry | already_imported after verifying target rows/files; no duplicate records |
| Changed SQLite input under same workspace | Rejected as different input; no overwrite |
| Missing/mutated source file | Inspection error; import does not publish ready metadata |
| Inconsistent legacy course relationship | SQLite FK violation reported before import |
| Invalid page constraint during insert | PG rejects the row; all prior target SQL rolls back and staged files are removed; original unchanged |
| Missing target file after a committed import | Retry reports recovery required; restoring exact original bytes permits verification |
| Lost acknowledgement after COMMIT | File bytes retained; same-input receipt resolves committed success without duplication/deletion |
| Same legacy IDs in two workspaces | Independent copies; modifying one does not change the other |
| V1 bundle duplicate history | All old duplicates preserved; subsequent conditional save succeeds |
| Restore old history | Creates a new monotonic revision; does not rewind the counter or replace the original |
| Native PG logical dump/restore | Dump restored to a separate new database; exact lecture TEXT verified; only the disposable restored database dropped |

Exact test nodes and executions: evidence/postgres_delivery.xml and TEST_RESULTS.md. These checks do not prove compatibility with every unknown historical schema; unsupported missing columns/invalid records are reported for deliberate handling, never silently deleted or paraphrased.

## Ownership and rollback

Import does not claim a verified account or make content visible to team members. Operator-local access to an unclaimed workspace requires an explicit flag. Task04 must bind a one-time claim to a real verified account/import and audit it. Teacher/course strings are not identity evidence.

Before accepting PG writes, rollback is the preserved SQLite+file checkpoint in local mode. After new PG writes, preserve them and use a compatible PG release or deliberate export/forward recovery; the old SQLite is no longer a complete rollback destination. ROLLBACK_GUIDE provides the exact boundaries and unknown-commit/crash-directory procedure. Automatic distributed crash reconciliation and a universal reverse installation migrator are not implemented in03.

## Original input integrity

The347 original project files, original uploaded archives and verified Task01 backup remain byte-identical. Task02 reports remain unchanged; the new architecture change is a separate addendum. Evidence/FINAL_VERIFICATION.json records final hashes and archive exclusions. No real data, secrets, database dump, test-host binary or private historical fixture is included in UPDATED_PROJECT.zip.
