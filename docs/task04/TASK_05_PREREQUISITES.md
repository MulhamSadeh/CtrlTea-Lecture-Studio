# Task05 prerequisites — planning only, no deployment

Task04 delivers the actual authenticated React/FastAPI/PostgreSQL application. No hosting resources, DNS, online staging, CI deployment or production mail were created. Task05 requires separate authorization.

## Required gates before team staging

| Priority | Concrete next work | Acceptance |
|---|---|---|
| P0 | Choose private staging host/region/budget and accountable primary/backup operators | Separate hostname/DB/objects/secrets; no operational data copied by default |
| P0 | Qualify current patched PostgreSQL16 and stable rendering/container/fonts/OCR toolchain | Rerun real PG/auth/legacy/native100/portable/OCR suite without test-host UID workaround; diagnose known5-versus6-page expectation without changing math/science |
| P0 | HTTPS ingress, trusted Host/proxy/origin configuration | Secure __Host cookie, exact origin/CSRF, restricted admin paths/network, no local-auth mode or backend DB exposed |
| P0 | Privileged account second-factor decision | Task04 password step-up works; choose maintained TOTP/WebAuthn/IdP or a verified staging access control and test owner recovery before wider exposure |
| P0 | Real mail sender/provider/DNS/delivery | SPF/DKIM/DMARC/provider setup, controlled real inbox verification/reset/admin invitation, bounce/failure support; synchronous resend reliability reviewed |
| P0 | Worker deployment and parser containment | Current one-process serial global guard is not distributed leases; choose safe claim/lease/retry/input snapshot/publication and credential-free execution isolation before multiple API/worker processes or untrusted uploads |
| P0 | Persistent file/object storage and private download proxy | Retain exact IDs/digests/private ownership; auth on every source/export/PDF-range request; no public DATA/static mount; explicit staged/ready lifecycle |
| P0 | Coordinated encrypted backups and restore drill | SQL+workspace+profile/secret recovery, new-target restore, session/token revocation, accepted RPO/RTO measured; account/provider-loss scenario |
| P1 | Secret/configuration management and least privilege | Separate runtime/auth/migration/backup credentials, migrations once per release, rotation runbook; no operator DSN in API/engine environment |
| P1 | Load/resource limits and abuse controls | Argon2 capacity/parallel login, large source/ZIP/avatar limits, queue age/OOM/scratch/disk; shared rate buckets/retention and reverse-proxy body limits |
| P1 | Logs/audit/monitoring | Redacted centralized application errors, failed mail alerts, auth/rate/anomaly events, queue/DB/storage/backup metrics, append-only audit archive/retention budget |
| P1 | Build/promotion/rollback | Locked image/deps, source/protected-engine hash checks, CI tests on real PG, private staging smoke and reviewed rollback; never treat release ZIP as a data backup |
| P1 | Browser/device QA and session lifecycle | Re-run included real account/admin E2E plus shared-computer drafts, stale tabs, permission changes and direct downloads on supported browsers |

## Current operational boundaries to preserve

- Authentication is required by default and missing PG/config fails startup. `AUTH_MODE=local` is a deliberate offline compatibility bypass, forbidden in staging. Keep one API/worker process until scheduling is redesigned/qualified; do not simply add Uvicorn workers.
- SuperAdmin has intentional global academic-content access under its own identity; ordinary accounts/reviewers remain private. Do not reintroduce the superseded02/03 no-read-all admin rule or disable RLS as a shortcut.
- Existing export loads current lecture at execution time, as before. It is not a certified immutable review snapshot. Jobs are serial and may rerun after restart; not exactly-once. Rights are rechecked, but already written OCR results/downloaded bytes are not reversed by revocation.
-34 capability flags include future review/publish/sharing actions; these are foundations, not implemented workflows. Do not label them functional review/cross-profile copy. Task06 workspace refinement,07 sharing/import and10/14 workflow/review remain separate.
- Recoverable SQL deletes retain files; no automatic irreversible purge is implemented. Define retention/reference-aware cleanup for orphan avatars/attempt outputs/expired trash and backups before long-running staging. Expired token/session/rate data need bounded offline maintenance/retention, never raw-link logging.
- Local mail tests do not prove control of a real external mailbox. No production SMTP credentials/DNS or actual user installation DB existed in this task.

## Suggested staging sequence after authorization

Build the accepted source/image once, provision isolated nonproduction infrastructure, apply migrations with separate operator rights, verify role/grant restrictions and engine hashes, configure HTTPS/private storage/mail, establish the owner through one-time verified bootstrap, run the complete tests/browser flows and backup/restore checks on synthetic accounts, then admit a small authorized pilot only after allP0 gates pass. Rollback must preserve acknowledged SQL/files rather than return silently to unauthenticated03 or old SQLite.

Task04 is ready to hand off implementation work to05; it does not claim public/production readiness or a green historical rendering suite. The unchanged statistics page-count failure and reference-host constraints remain explicit gates.
