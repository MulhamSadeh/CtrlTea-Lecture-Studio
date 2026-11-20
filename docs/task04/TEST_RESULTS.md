# Task04 — executed tests and regression comparison

24 October2026. Final counts below are generated from `evidence/task04_acceptance.xml`; read raw logs/JUnit for individual cases. Original backups/science were preserved; no operational data used.

| Run | Executed | Passed | Failed | Errors | Skipped |
|---|---:|---:|---:|---:|---:|
| Final combined acceptance (92.68s) |183|182|1|0|0|
| New account/security/upgrade cases within that run |46|46|0|0|0|
| Actual browser scenario groups (separate run) |11|11|0|0|0|

The46 cases are a subset of183, not additional executions to sum. Browser groups are not pytest cases.

## Baseline verified, not assumed

Task03 reported135 successes/one known statistics failure in its then-current136-case combined run, followed by a28-case PG delivery run containing an additional final import-acknowledgement case. Freshly running the actual delivered03 source for this task executed **137 cases:136 passed,1 failed,0 skipped**,49.13s (`task03_baseline.xml/log`). Thus the extra passing case is explained by the final03 source, not silently counted as a repaired failure.

## Unchanged failure

`tests/test_academic.py::test_statistics_does_not_end_with_a_page_containing_only_end_marker`: expected5 PDF pages, actual6 in this environment. The preceding content/no-marker-only-page assertions pass. Same known Task01/03 failure. No expected page count, scientific content, math engine, layout implementation or source fixture was changed to hide it. Cause remains reference-toolchain/layout-sensitive and unresolved; it is not a new account/persistence regression.

All other existing backend/SQLite/PostgreSQL tests, actual DOCX/PDF,100-native-formula, portable math, JSON/bundle/history/source/OCR and concurrent-save cases pass in the accepted combined run. New tests cover authentication/ownership/admin/profile and actual0001→0002 preservation. No skipped cases are counted as successes. Repeated runs are not added as distinct tests.

## Frontend and other checks

- `npm run build` (includes `tsc -b`) PASS, supplied lockfile, final frontend assets packaged. Existing font-resolution and >500kB bundle warnings remain; they are not hidden build failures.
- Actual Chromium account/admin E2E PASS; per-check list in `evidence/BROWSER_ACCEPTANCE.json` and log. Separate contexts verify privacy. No mock backend; SMTP transport contract test is explicitly fake and not external mail delivery.
- Backend Python compilation PASS; `pip check` PASS. Auth-specific tested pins recorded in requirements-auth-tested.txt and evidence/DEPENDENCIES.json.
-14 protected math/render/schema/source modules, Word import and original MathText region PASS byte comparison with03.148 scientific fixture/asset files retained unchanged in the private test tree. Original Task01 source347-file hashes and previous archives checked separately.
- Task03 UPDATED_PROJECT.zip matches its recorded SHA-256/CRC and every archived entry matches preserved03 source. Complete modified-file list distinguishes new/auth changes from that source.

## Commands and repeatability

Use isolated disposable PostgreSQL, migration/operator and separate runtime/auth roles, local mail and private temp storage. Never point test URLs at an operational database. The auth suite intentionally writes synthetic account/security records and bootstrap state. PG legacy tests create a synthetic trigger/temporary roles/database; account upgrade test creates/drops only its randomly named new test database.

```bash
CTRLTEA_AUTH_MODE=local PYTHONPATH=backend python -m pytest -q
npm --prefix frontend ci
npm --prefix frontend run build
```

For full tests set CTRLTEA_TEST_DATABASE_URL, CTRLTEA_MIGRATION_URL, CTRLTEA_AUTH_DATABASE_URL, random AUTH_SECRET, local mail/profile/data settings and runtime grants; apply head2 then provision_auth. Auth fixtures explicitly enable required authentication; legacy fixtures explicitly use local compatibility. Native pg_dump/pg_restore are required on PATH for03 recovery tests. Full historical suite needs the private examples restored from the preserved Task01 baseline; they are intentionally omitted from the shareable source archive just as in03. New auth/upgrade tests synthesize their own data.

Browser:

```bash
python -m playwright install chromium
CTRLTEA_E2E_DISPOSABLE=1 python scripts/e2e_accounts.py
```

The script requires the disposable DB/service configuration/local mail above, starts/stops one loopback server, writes internal QA under configured E2E_OUTPUT and refuses external mail. Optional E2E_BROWSER selects an installed executable. Test secret values are never fixed in the script. Reinitialize a disposable database for a fresh bootstrap scenario.

## Environment and qualification

Linux, Python3.12.14, native PostgreSQL16.2, psycopg3.3.6, Alembic1.20.1, FastAPI0.143.3, Pydantic2.14.1, Argon2-cffi25.1.0, email-validator2.3.0, Pillow12.3.0. Main Python Playwright package1.64 had unavailable browser downloads; a private QA-only Playwright1.51 overlay drove the actually downloaded Chromium134 headless shell. Node24, Vite6.4.4. Original Pandoc3.1.3/LibreOfficeDev26.8 alpha/Tesseract5.3.4 environment with checksum-recorded ara+eng from03.

This host maps only UID0, forbids Unix sockets, lacks Docker, and isolates loopback per command. A test-host-only UID shim bypasses the initial PG root guard; unmodified native SQL/role/RLS/locking behavior is exercised. DB and tests run in the same command namespace on loopback with trust authentication, then the server is terminated. The shim, binaries, databases, browser overlay/mail/screenshots are excluded from deliverables. This is not a recommended hosting configuration.

## Intermediate failures and corrections

Early authentication suite30/30 and expanded43/43 passed. An intermediate full run exposed a migration-test URL-format mistake (libpq keyword DSN supplied to SQLAlchemy); the test now uses a proper URI and the real upgrade passes. A newly added recovery test then exposed the private_assets restore scope omission; implementation fixed while retaining RLS. Browser QA caught same-tab mail-link handling and a selector/accessible-name mismatch in resource selects; implemented hashchange handling and explicit select labels. Current acceptance evidence supersedes these earlier failures without erasing them.

No native Windows/PowerShell/NixOS/Microsoft Word certification, production SMTP/DNS, cloud deployment, production load/backup drill or scientific correctness review was performed. Task04 is an implemented local/private account foundation ready for Task05 work subject to its documented gates.
