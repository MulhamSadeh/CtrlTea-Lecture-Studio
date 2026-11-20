# Task04 implementation prerequisites — no implementation in03

Task04 must implement email accounts, sessions, private profiles and ownership-based backend authorization on the new PostgreSQL foundation. It must read the architecture addendum: the old default shared-course model is not approved. No emails, login, token endpoint or Super Admin bootstrap were executed in03.

## Existing foundation to use

accounts(id,full_name,email,normalized_email,email_verified_at,state), profiles(user_id,team_description,version), workspaces(id,owner_user_id,state), scoped content tables, forced RLS, composite workspace FKs and restricted runtime DB roles. Existing JSON and mathematics modules remain frozen. The current process-selected workspace/unclaimed operator flag is development scaffolding, not a user session or a way for browser clients to choose owners.

## Account and mail sequence

1. Add versioned migrations for maintained password credentials (Argon2id, calibrated cost), hashed verification/reset tokens, opaque hashed server sessions, security roles/grants, invitation/claim records and append-only security audit. Preserve stable accounts.id and self-written profile text.
2. Registration accepts full name, normalized email and password only; it cannot accept role, verified state, workspace owner or reviewer grants. Normalize consistently and enforce email uniqueness transactionally. Keep verification pending until proof of mailbox control.
3. Implement verification resend with generic responses, token expiry and revocation of prior tokens; never log raw links/tokens. Use single-use cryptographically random tokens, store only hashes and consume under a lock. Proposed verification TTL24h and reset TTL30min need explicit tests/configuration.
4. Implement login/logout, forgot password and reset using maintained libraries. Generic account-existence responses, shared rate limits/backoff and secure account notifications. Password reset revokes sessions/auth version, but must not silently reset MFA or grant ownership/admin rights.
5. Add a transactional email outbox with idempotent delivery/retries and environment-specific credentials. Development uses a local mail sink; real verification/recovery mail is authorized only in Task04's scope, never as part of03. Use separate staging/production sender settings and verified domains later.

## Session and browser security

Same-origin opaque Secure/HttpOnly __Host- session cookie, SameSite policy plus session-bound CSRF token/Origin checks, rotation on login/recovery/privilege change, idle and absolute expiry, backend revocation on suspension/logout. Do not put passwords/session secrets in localStorage or lecture JSON. Require MFA/step-up for Super Admin and sensitive owner/security operations. Choose maintained implementations rather than writing cryptography.

Every request resolves the authenticated account, its active owned workspace and action permission. Set transaction-local RLS scope from that relationship only. Reject arbitrary X-Workspace-ID/body owner values. Refactor internal scope helpers as needed without disabling RLS or exposing a global unscoped query helper. Runtime account/profile access needs deliberately scoped policies/repositories; do not grant the current broad application connection table-owner privileges.

## Secure one-time Super Admin bootstrap

Database role provision_runtime.py is **not** this mechanism. Do not reuse database credentials as a platform password.

- Default bootstrap is closed. An explicit offline operator command creates one short-lived bootstrap request bound to a chosen real account/verified mailbox and stores only a random token hash, expiry and operator audit.
- Require matching verified identity plus the one-time token and MFA/step-up at completion; lock and consume the request in the same transaction that grants the platform role.
- An already consumed/expired request cannot be replayed or silently reopened. No permanent bootstrap secret, hardcoded email/password or “first registered user wins”.
- After success, ordinary privileged role-management/recovery procedures apply; document a separately audited operator recovery process. Platform administration must not imply automatic access to all private lecture content.

## Private profiles and legacy claims

Create/claim the account's private workspace explicitly after verification. Empty profiles do not share courses. The member alone edits their own free-text team_description using profiles.version; render as plain text and enforce a reasonable length. Changes to this description never modify roles, official assignments or reviewer eligibility. UI/directory visibility must separate public profile fields from private workspace content.

Legacy unclaimed data requires an operator-issued, expiring, single-use claim bound to import fingerprint/workspace and intended verified account. Never infer owner from a doctor field or allow any signed-in user to claim a guessed ID. Handle the existing-empty-workspace/one-owner uniqueness case transactionally; nonempty destinations need a deliberate merge/import, not overwrite. Preserve unknown historical actors rather than attributing old content to the claimant retroactively.

## Permission and review boundaries

Platform roles: Super Admin and reviewer eligibility are separate from workspace ownership and profile prose. Owners control their private resources. Review assignments later grant only submission/revision/file access. Read/copy grants later are explicit, revocable and attachment-scoped. Task04 prepares/enforces those boundaries without implementing Tasks10/14 workflows or broad cross-profile copying prematurely.

Map all48 legacy operations plus new account routes to a permission policy. Include sources/page images/files, figures/math utilities, author packages/runs/import, transfers and bundles, revision restore, jobs/retry, export pages/reports/review and static font diagnostics. Hiding buttons is not enforcement. Reject guessed IDs and mixed parent/body resource scope before reading filenames/revisions or queuing compute.

Partition browser drafts by deployment/account/workspace/lecture and preserve unsent drafts deliberately during sign-out/expiry; never attach another user's old local draft to a new account. Full comparison/rebase recovery stays Task09. Keep expected-revision transactions active from03.

## Worker and staging blockers to resolve before member access

The03 worker remains a single thread for one trusted process-selected workspace, guarded against duplicate processes for that workspace. Per-request authenticated workspaces cannot simply be enabled while assuming it consumes all users' jobs. A later worker/storage task must implement explicit trusted job scopes, multi-workspace scheduling, reliable claims/retries/publication and file isolation before online staging admits team traffic. Do not replace this with an unauthenticated operator flag or multiple Uvicorn workers.

Current local file directories are not public storage URLs. Cloud storage/download authorization, source-parser isolation, backup scheduling/recovery drills, a current patched PG/render toolchain and the outstanding page-count baseline require staging gates. Select email/hosting providers and privacy/retention policy under their later task authorization; no03 credentials were created for them.

## Task04 acceptance tests

| Concern | Required negative/positive evidence |
|---|---|
| Accounts/mail | Register/verify/resend/login/logout/recover/reset; duplicates; expiry/replay; email-failure outbox retry without duplicate privileges |
| Bootstrap | Closed by default, wrong account/token, race/replay, expired request, one grant only, no first-signup promotion |
| Ownership | Two accounts cannot list/read/write/download each other's courses/files/history/jobs, even with guessed IDs or forged workspace/role fields |
| Profiles | Only own description edits; XSS/plain-text rendering; concurrent profile version; “Super Admin” text grants nothing |
| Claims | Authorized one-time claim, wrong user/import, existing destination, concurrent/replayed claims; no retrospective fabricated authorship |
| Session | CSRF, origin, fixation, token rotation, logout/suspension/recovery revocation, MFA separation and shared rate limiting |
| Regression | Legacy endpoint contracts, expected-revision writes, DOCX/PDF/100-formula and source/bundle compatibility remain intact |

Task04 needs an explicit subsequent authorization. Task03 stops at this plan; no account or email workflow is implemented.
