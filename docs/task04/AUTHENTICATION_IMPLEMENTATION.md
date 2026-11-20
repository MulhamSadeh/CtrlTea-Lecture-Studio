# Task04 — implemented authentication and account control

24 October 2026. Actual backend, Alembic and React changes built on **Task03 UPDATED_PROJECT.zip**, SHA-256 `3f2c65ca9c2fbc1306278fbcd5af04f8dbd2178933d5c70a899f48efe99e07a2`. The complete supplied Task04 specification and all Task03 reports were reviewed. `evidence/INPUT_VERIFICATION.json` records input identity. Original V1 is a regression reference, never the implementation starting point.

## Delivered behavior

| Capability | Actual implementation |
|---|---|
| Registration | Full name/email/password/confirmation; consistent email-validator normalization + casefold; database unique normalized email; role/owner injection rejected; pending account |
| Password storage | Maintained argon2-cffi Argon2id, time3/memory65536KiB/parallelism2; random salts; rehash-on-login; 15–128 characters, repeated/common weak strings rejected; no forced composition |
| Verification | Random32-byte URL-safe token, SHA-256 only in DB, 60min validity, single-use locked consumption, resend replaces old link; verification activates account and creates its private workspace |
| Login/logout | Generic credential/status failure; unverified/disabled denied; opaque random server session; rotate on login/reauth; logout deletes server record |
| Password recovery | Generic public response; verified active account only; 30min hashed single-use reset; all sessions invalidated; notification without password |
| Account settings | Change password after current-password verification; view/revoke own active sessions; password reauthentication for sensitive administration |
| Super Admin | Explicit global server-side override, without member passwords or impersonated sessions; every workspace including restricted legacy/suspended spaces is administratively accessible |
| Permissions | 34 named actions; role defaults + per-member allow/deny/inherit; live effective permissions and auth version; administration is checked separately from ordinary action grants |
| Profiles/directory | Own editable free-text team description; safe public directory projection; private optional reencoded avatar; description never grants security role |
| Administration | Member search/details/status/roles, grouped permission matrix, workspace selection/banner, exact resource grants/revocation, audit, explicit legacy assignment |
| Recovery of deleted academic resources | Course/lecture/source SQL snapshots and retained private files, 30day restore, exact IDs/history/source corrections/aliases; no destructive purge UI |

## Session and request boundary

Authentication is **required by default**; missing PostgreSQL/configuration fails startup rather than silently opening the old editor. Explicit `CTRLTEA_AUTH_MODE=local` remains the legacy offline regression/local mode; never expose them to members or the internet. The launcher still binds loopback. This task does not deploy anything.

`__Host-ct_session` is Secure/HttpOnly/Path=/, no Domain, SameSite=Lax. Explicit loopback HTTP development uses `ct_session_dev` with Secure disabled; startup refuses insecure cookies on non-loopback origins. Default absolute lifetime7days, idle12hours, sensitive-operation password reauthentication15min. These are project settings, not proof of capacity/security certification.

Only the SHA-256 session hash is stored; CSRF is HMAC-bound to the raw session using a separate random server secret. Authenticated unsafe methods require it. Exact canonical Origin and cross-site Fetch Metadata checks complement cookies. Login/public token operations accept JSON and reject foreign origins. Browser auth material is in HttpOnly cookies and in-memory CSRF state, never localStorage. Cookies are rotated after login and reauthentication; state/role/permission changes revoke relevant sessions.

Registration/login/recovery/verification use atomic shared PostgreSQL rate buckets, HMAC keys and429/Retry-After, not per-process counters. Login budget5/account/15min and15/IP/15min; recovery/resend3/account/hour and9/IP/hour; registration5/account/hour and15/IP/hour. Buckets count attempts, including successes. A small current-password/registration phrase policy is not a comprehensive breached-password service. Generic response bodies do not claim constant-time SMTP delivery.

## Backend enforcement and database separation

`access.authorize` is a global dependency. All48 Task03 operations are mapped (health is public); new account routes are explicitly allowlisted and administrative routes require SuperAdmin. Unknown resource routes fail closed. Session identity determines own workspace; a header/query is only a selection request that is checked against ownership, admin status or an active exact-resource grant. RLS and composite workspace FKs from03 remain enabled/forced.

Resolve source/job/export parents before returning data. Action and scope checks precede file responses, queueing and scientific processing. Nested source references cannot smuggle an unauthorized sibling resource. Legacy transfers/author imports retain their scoped validators. Authenticated exports are discoverable only after their report is indexed in the successful job transaction; unindexed partial attempts remain hidden. Admin acts under their own account; audit records the target owner/workspace, route/action, time and outcome.

The restricted `ctrltea_app` DB identity accesses scoped academic content. A distinct `ctrltea_auth` identity accesses account/session/permission tables and append-only audit (SELECT/INSERT only), workspace metadata and three queue metadata columns. It has no permission to SELECT scientific job payloads or lecture documents. Neither service identity is a superuser, BYPASSRLS, role administrator or table owner. Migration credentials must be removed from the application environment after setup. These are trusted backend service credentials, not exposed to SuperAdmin APIs.

## Files, jobs and scientific preservation

Private files remain in the03 workspace directories; profile images are in a separate private configured directory. No DATA static mount was added. Avatars accept at most2MiB PNG/JPEG/WebP and16M pixels, then decode/reencode RGB PNG up to512px; SVG/executable data rejected. Old avatar files are retained privately for later lifecycle cleanup.

The existing serial in-process OCR/export worker is preserved, extended to enumerate queued workspace IDs through restricted metadata access, enter trusted scope, and retain the requesting account. One global advisory guard prevents two authenticated worker instances. Requester role/actions/scope are checked at job start and before completion; completed export file indexing and job state commit together. Legacy jobs without a requester fail until an authorized explicit retry. Rechecks do not undo already executed OCR page writes or transferred bytes. Durable leases, parser sandboxing, cancellation guarantees, snapshots-at-request and cloud object storage remain Task05 gates.

14 protected scientific/render/source/schema modules and MathText are byte-identical to03; old lecture/result/project schemas and scientific fixtures are unchanged. Backend persistence and orchestration were adapted around them. Existing atomic revision-based saves remain active. No Task05 implementation, full sharing/copy workflow, AI authoring redesign or scientific review/publish workflow was added.

## Explicit design changes and limits

The latest Task04 requirement **supersedes** earlier02/03 statements that platform administrators lack automatic private-content access. SuperAdmin now intentionally has global academic access; ordinary members/reviewers remain private. Password hashes, session/reset/verification tokens, DB credentials and API secrets have no admin read endpoint.

Mail is sent after token transaction commit through a synchronous replaceable provider. Raw tokens exist only transiently and in the private intended message, never as recoverable plaintext DB outbox payloads. If delivery fails, a generic public response and failed audit are recorded; resend/operator reinvitation issues a fresh token. There is no durable automatic email retry/outbox. This explicitly replaces the03 prerequisite proposal; delivery reliability/monitoring is a staging gate rather than a claimed completed outbox.

Sensitive administration uses recent password step-up. TOTP/WebAuthn MFA is not implemented or claimed; decide and verify privileged MFA before public exposure. CSP/nosniff/frame/no-referrer/no-store headers are enabled in auth mode; deployment TLS/HSTS/proxy hardening remains05. Dependencies/build/security tests are evidence, not an independent penetration-test certificate.

See SUPER_ADMIN_SETUP, EMAIL_SETUP, SECURITY_TEST_REPORT and TEST_RESULTS. The modified/added/deleted file list is complete in MODIFIED_FILES.md and machine-readable evidence/SOURCE_VERIFICATION.json.
