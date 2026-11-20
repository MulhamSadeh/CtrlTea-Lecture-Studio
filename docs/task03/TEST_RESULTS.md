# Task03 — executed tests and limitations

23 October 2026. Tests used only isolated working copies, synthetic SQLite installations and disposable PostgreSQL databases. Original project/science/backups were not modified. Counts below are actual executions, not planned acceptance cases.

## Final results

| Execution | Executed | Passed | Failed | Skipped | Evidence |
|---|---:|---:|---:|---:|---|
| Final full regression candidate: original backend + new SQLite + then-current27 PG cases |136|135|1|0|acceptance.xml/log;50.64s |
| Final PostgreSQL delivery suite after last import-acknowledgement hardening/schema indexes |28|28|0|0|postgres_delivery.xml/log;7.18s |
| Original backend on first Task03 run, before targeted QA/environment corrections |108|102|6|0|sqlite_regression.xml; same six unresolved Task01 cases |

The last full run preceded the additional lost-COMMIT-acknowledgement test. After the narrow final migration change, **all28 PostgreSQL tests** were run again on the delivered persistence/schema code. Do not sum repeat executions as additional distinct tests or call the full suite green. Earlier SQLite-only runs intentionally skipped PG cases when no test URL was present; the final combined and PG delivery runs have no skipped cases.

## One unresolved baseline failure

`tests/test_academic.py::test_statistics_does_not_end_with_a_page_containing_only_end_marker`

- Assertion: expected5 PDF pages, received6 at line263.
- Earlier assertions requiring body content and preventing an end-marker-only blank page passed.
- Same failure was recorded in Task01 and in the unchanged-baseline environment. Cause remains **uncertain**: reference font/LibreOffice/layout sensitivity versus a pre-existing output expectation. It is not evidence that the new PG save path lost equations or scientific text.
- Severity: Medium; future reference rendering/visual QA must diagnose it. No expected page count, scientific content, math code or renderer was changed to hide the failure.

## Resolved Task01 cases

Four theme/header tests selected the first bidiVisual table, which was the cover index. tests/test_theme.py now selects the intended content table by actual header text or header math. Every original color, OOXML and math assertion remains. All four pass in the full run; no renderer patch or weakened assertion was used.

The actual OCR/cache test now passes with ara+eng available in private test configuration. No OCR implementation changed. The test image contains Latin text/digits, so this proves the pipeline/model availability and corrected-cache preservation, not the accuracy of arbitrary Arabic scientific pages.

The earlier subprocess validator import failure is absent with the correct PYTHONPATH, as already established in Task01. Existing source contracts/schema validation, partial authoring/bundle aliases, restored themes and100-formula native release tests pass.

## PostgreSQL coverage actually executed

28 cases in tests/test_postgres.py cover migration initialization/repetition; CRUD/raw TEXT/history; RLS read/update/spoofed-owner isolation; same-workspace composite FKs; profile text distinct from roles; missing scope/unsafe role/unclaimed restrictions; simultaneous saves on independent connections; nested/head/history/author-task rollback; independent bundle copies/aliases/append; exact SQLite import, missing files/relationships, retry/input-change and duplicate legacy history; target file recovery and conditional restore; single worker guard/concurrent enqueue deduplication; future owner constraints; real runtime-role provisioning without an application account; native pg_dump/pg_restore into a new database; native and portable HTTP worker DOCX/PDF export; and lost acknowledgement after COMMIT retaining accepted files.

The synchronized native PG save test accepts exactly one of two base-revision0 candidates, returns a conflict for the other, increments once and retains one correct previous snapshot. It is not a mocked/in-memory-SQLite substitute for PostgreSQL locks. tests/test_persistence_sqlite.py separately proves the new local atomic save invariant with two writers.

## Other checks

| Check | Result / exact scope |
|---|---|
| TypeScript + Vite build | PASS, npm run build includes tsc -b;1,584 modules; frontend_build.log |
| Rebuilt frontend | PASS,68/68 dist files byte-identical to supplied V1 |
| Python compilation | PASS for backend modules |
| Dependency consistency | PASS, pip check: No broken requirements found |
| Original math/schema/OCR/render modules | PASS,14 protected modules match baseline SHA-256; SOURCE_VERIFICATION.json |
| Original inputs/backup | PASS,347 original source files and preserved archive hashes verified separately |
| Native DOCX/PDF | PASS through PG/TestClient HTTP job flow and existing100-formula suite; native math XML retained |
| Portable DOCX/PDF | PASS through PG worker; unchanged pipeline verifies output; expected native/portable mode and equation count checked |
| API startup/background work | PASS via real FastAPI lifespan/TestClient; same worker thread handles PG jobs and downloads |
| Logical dump/recovery | PASS on native PG clients into a separate fresh database; exact doc TEXT verified |

Build warnings are unchanged: Cairo URLs resolve at runtime and the JS bundle exceeds the default500kB chunk warning. Starlette/HTTPX emits the existing deprecation warning. These are documented warnings, not unexecuted tests or new rendering failures.

## Test environment and native-server qualification

Linux/Ubuntu24.04, Python3.12.14, native PostgreSQL16.2, psycopg3.3.6, Alembic1.20.1, SQLAlchemy2.1.6, pytest9.1.1, Node24.19.0, Vite6.4.4; original Pandoc3.1.3, LibreOfficeDev26.8 alpha and Tesseract5.3.4 environment. Full package/tool metadata is in evidence/RUNTIME_VERSIONS.json.

This execution host maps only OS UID0, has no Docker daemon and isolates loopback per command. For **disposable native database tests only**, an external test launcher supplied an OS-identity shim for the initial PostgreSQL root guard and started unmodified native PG binaries in the same isolated command as the tests. SQL, MVCC, row locks, RLS and database role attributes were not replaced or mocked. The test server used loopback/trust authentication with synthetic data only and was stopped after each run. No launcher/shim/server binary/data/password is in UPDATED_PROJECT.zip. This is not a recommended deployment setup; rerun the included tests under an ordinary nonroot PostgreSQL/Docker reference environment before staging.

Arabic traineddata SHA-256: ara=e3206d3dc87fd50c24a0fb9f01838615911d25168f4e64415244b67d2bb3e729, fetched from official tesseract-ocr/tessdata_fast; eng=7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2 from the installed model. This records the bytes tested, not a claim about OCR scientific correctness.

## NOT RUN / not implemented

- Docker Compose execution, native Windows/PowerShell/Word and NixOS environments: unavailable. Compose/source configuration supplied; no platform certification inferred.
- Complete browser Playwright E2E: browser runtime not provisioned; HTTP/TypeScript checks are not a replacement.
- Real installation migration: no operational SQLite/source tree supplied; all migration execution was synthetic.
- Current patched production PostgreSQL/render reference toolchain, load/failover/security penetration testing: not certified here.
- Authentication/email/bootstrap/sharing/review workflows/public deployment: intentionally unimplemented, not passing features.
- Multi-workspace online worker dispatch, distributed leases/publication and full09 conflict-resolution UI: future task scope; one local process-selected workspace remains the supported03 runtime.

The persistence task is delivered with its tested boundaries and the remaining known rendering expectation. No claim of full collaborative editing or production readiness is made.
