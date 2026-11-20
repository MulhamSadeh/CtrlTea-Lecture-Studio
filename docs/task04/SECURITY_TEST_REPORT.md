# Task04 — security verification

All runs used synthetic accounts and isolated disposable PostgreSQL databases/private mail sinks. No operational user data or external recipient. This is implementation verification, not an independent penetration-test certificate. Final JUnit and browser evidence accompany this report; intermediate failures are retained as debugging evidence, not counted as passing executions.

## Identity and privilege cases

| Area | Executed positive/negative coverage |
|---|---|
| Registration | Valid signup; invalid email; normalized duplicate; weak/mismatched/oversized password; forged role/workspace; unverified account cannot log in or read content; password Argon2id hash |
| Verification | Correct token, expired, replay, resend replacement, provider failure with successful later resend; pending account remains unprivileged |
| Recovery | Generic existing/absent response, local reset mail, expired/replayed reset, old password failure, new login, all-session invalidation; password change/suspension consume outstanding links |
| Sessions | Bad password, unverified/disabled, current logout, absolute/idle expiry, current/other-session revocation, login rotation/fixation, hashed storage, Secure/HttpOnly/SameSite/Path cookies, shared rate limit |
| CSRF/origin | Missing/wrong session-bound CSRF denied; foreign Origin rejected; auth required by default; missing PG configuration fails closed |
| Bootstrap | No first-signup promotion; protected operator command; mailbox verification prerequisite; wrong account, replay, expired invitation, permanently closed initial guard; audited recovery |
| Administration | Member role/permission changes; recipient session revocation; suspension/reactivation; last-admin protection, including two simultaneous demotions |
| Profiles | Free-text “Super Admin” and script markup do not grant privileges; role injection rejected; stale version conflict; directory excludes email/private workspace; avatar type/size/reencoding and suspended-profile access boundaries |
| Database boundary | Restricted auth role cannot delete audit; content role RLS/FKs retained; service role checks; schema upgrade preserves old rows/raw documents/history |

## Cross-user resource tests

Every team fixture has SuperAdmin, Member A and Member B with separate real sessions/workspaces. A/B private course lists and guessed/forged workspace selections are denied. Parameterized reads cover document JSON, revisions, sources, jobs, exports, author runs and bundles. Write matrix covers course edit/delete, lecture create/save/delete/theme, authoring package, export enqueue, source edit/delete/correction/extract/upload and job retry. Direct source file/page/image and DOCX/PDF download attempts from the other member are denied.

SuperAdmin reads both workspaces under its own identity; edits a member document, reads sources/history, enqueues a real export and downloads actual DOCX/PDF. Its access is recorded with actor and target workspace. It needs neither the member password nor a stolen session. Admin cannot obtain password hashes/session hashes through member APIs; tests inspect safe projections and verify tokens/passwords are absent from audit metadata.

Exact lecture grants permit only assigned actions/resources. The recipient cannot list the whole source workspace, edit through a read grant, read a sibling lecture/source or smuggle its source ID in a document body. Revocation invalidates sessions and blocks subsequent access. Real browser QA additionally creates/revokes a grant through the resource picker and verifies200→404 behavior after fresh recipient authentication.

## Legacy ownership and recovery

Unclaimed fixtures retain original lecture/source IDs/raw JSON, corrected pages, aliases and history. Ordinary assignment is denied. Admin assignment requires verified active recipient and empty destination; nonempty destination is rejected. A repeated claim fails and concurrent claims yield one success/one conflict. Subsequent member login resolves the newly assigned workspace. No actual operational SQLite installation was supplied or migrated.

Course/lecture/source deletion snapshots and restore are tested for exact content/IDs/file bytes/source correction/exclusion/alias/history. Repeat/expired restores return409. SQL locks serialize snapshot capture with scientific saves and source mutations. A final added case caught a missing explicit workspace field when restoring private_assets; the fix supplies the authenticated scope for every restored row and preserves FORCE RLS rather than relaxing the policy. Unindexed partial export reports/files are hidden.

## Browser verification

Actual local Uvicorn/FastAPI + PostgreSQL + Chromium134, separate browser contexts. Arabic signup, verification, login, original course/lecture UI, profile/directory/plain-text XSS handling,390px RTL, operator bootstrap/activation, full admin workspace banner, permission matrix revocation, exact resource grant/revoke, suspension/reactivation/audit, password recovery and logout. No uncaught frontend JavaScript errors in the accepted run. Screenshots were reviewed internally and are excluded from deliverables. Headless shell was needed because this execution host forbids the regular browser's Unix process-singleton socket; no application functionality was mocked.

## Scope and remaining risk

- External SMTP/DNS/inbox delivery NOT RUN; local workflows and SMTP adapter contract tested. No automatic durable email outbox; failed sends require resend/reinvitation.
- Recent password confirmation protects sensitive administration; no second-factor implementation is claimed. Decide privileged MFA at staging readiness.
- Session/role revocation affects subsequent requests, not bytes already delivered or all effects of already-started OCR. Serial worker checks rights at start/completion, but is not a distributed lease/cancellation engine.
- Native PG16.2 tests used the documented test-host-only root-guard UID shim; SQL/RLS/MVCC/locking were real. Requalify on a normal nonroot/current-patched PostgreSQL environment before staging. Trust-auth loopback test setup is not shipped.
- No hostile-parser sandbox, sustained load/failover, external penetration test, native Windows/NixOS/Word or cloud deployment certification here. Task05 prerequisites identify these gates.
- Local drafts are account/workspace partitioned and cleared deliberately; downloaded files or a shared computer's disk cannot be recalled by backend authorization.

Latest acceptance counts and the single unchanged statistics page-count failure are in TEST_RESULTS. Existing mathematical/scientific modules and fixtures remained byte-identical.
