# Task04 database migration and compatibility

## Implemented migration

Alembic `0002_accounts`, parent `0001_private`. Source: migrations/versions/0002_accounts.py and migrations/accounts.sql. PostgreSQL16 is retained from03. Migration does not rewrite lecture JSON, formulas, raw historical/base documents, source files or ownership IDs.

| Change | Purpose |
|---|---|
| accounts.role/auth_version/created_at | Initial Member default, live session invalidation and account metadata |
| profiles.avatar_path | Private optional image pointer; existing description/version retained |
| credentials | Argon2id hash only, one FK per stable account |
| auth_tokens | Secure token hash, kind, user, expiry and single-use timestamps |
| sessions | Opaque session hash, auth version, idle/absolute/recent-login metadata |
| system_roles/permission_catalog/role_permissions/permission_overrides | Three roles,34 actions, explicit per-member overrides |
| resource_grants | Recipient + exact course/lecture + workspace/action list, expiry/revocation foundation |
| auth_rate_limits | Shared atomic rate buckets using HMAC identifiers |
| security_audit | Actor/action/target/scope/time/outcome/limited metadata, indexed append-only service grants |
| bootstrap_state | Singleton permanently closed initial-admin guard |
| trash_records | Scoped recoverable academic snapshots,30day expiry, restore marker |
| jobs.requested_by | Stable requester identity for execution authorization |
| Additional RLS policies | Restricted auth identity reads account/profile/workspace metadata; queue metadata SELECT only; content RLS remains forced |

No duplicate user/workspace model. Existing03 account and profile IDs/relationships are reused. New auth tables receive no PUBLIC grants. `scripts/provision_auth.py` separately creates a nonowner/NOSUPERUSER/NOBYPASSRLS auth DB role, grants only required privileges, seeds34 permission defaults and grants trash access to the existing content role. It refuses silent password rotation. It creates no platform user/admin. Existing runtime role provisioning remains separate.

## Actual upgrade test

`test_task03_to_task04_preserves_existing_science_metadata_and_duplicates` creates an isolated new database at the actual0001 migration, populates account/profile/workspace and all ten legacy data domains, exact whitespace-bearing lecture/history/base JSON, duplicate legacy revisions, source/page correction, aliases and a job. It upgrades to0002 twice and compares every original column/row exactly. New Member/auth-version defaults and absence of invented credential/password rows are checked. An attempted destructive downgrade is refused and data remain present. This is a real Alembic/PostgreSQL test, not a metadata-only simulation.

New-source-only migration smoke and full existing PG integration tests also pass. Real account/mail activation tests prove a credential-less03 metadata identity can keep its stable ID/profile: resend verification → verify its mailbox → forgot/reset → credential upsert → login. Registration cannot silently replace its name/password by supplying a duplicate email. Never infer mailbox ownership from the doctor field or a legacy document.

## Legacy ownership assignment

Admin recent-password action selects a real verified active recipient and an unclaimed workspace, locks them under a global assignment guard, rejects nonempty destination data/files, replaces only its empty shell and changes the owner atomically with audit/session invalidation. Exact original course/lecture/source/history/alias/file identities are retained. Duplicate/raced claims fail. This is the **authorized administrative assignment** option in04, not a public self-claim token or first-user promotion. No real operational SQLite DB was present; tests used synthetic unclaimed fixtures.

## Upgrade procedure

1. Stop the03 API/worker and prevent writes. Back up the whole SQL DB plus matching private workspace files and separate new profile directory if upgrading a later04 installation. Preserve source version, current Alembic head and digest manifest. Test a new-target restore before treating a backup as verified.
2. Use an offline migration role, never the API role: `python -m ctrltea.database upgrade`. It runs under the existing release advisory lock. Application startup verifies the exact required head and refuses incomplete configuration.
3. Retain the existing restricted content role/password. Provision the auth-service role/catalog once through `python scripts/provision_auth.py`; it also grants the runtime role the new trash table. An existing auth role requires explicit operator credential/grant maintenance, not rerunning a hidden password reset.
4. Configure required authentication, separate service DSNs, persistent private roots, canonical origin/cookies/mail/secret. Remove operator credentials from application environment. Follow SUPER_ADMIN_SETUP to register/verify and bootstrap the chosen owner.
5. Validate own/admin/cross-user access, exact content/files/history and unchanged-engine export before later staging. Existing unclaimed data stay restricted until an explicit admin assignment.

## Rollback and restoration

`alembic downgrade` intentionally refuses to drop authentication data. Before accepting04 writes, roll back by retaining the failed target and restoring the verified pre-upgrade checkpoint into a **new DB/file root**, with preserved03 code in loopback/private mode. Never overlay or delete the only existing copy.

After04 accepts new accounts/content, prefer a compatible04 release or forward repair. An unmodified03 binary is not a safe public fallback: it has no authentication and a different schema-head expectation. Do not roll SQL back to an old dump and silently lose acknowledged work. A coordinated incident rollback must preserve/export new content and security metadata and define the accepted recovery point.

For a04 restore: stop all API/worker instances; restore a consistent SQL+workspace+profile checkpoint into new targets; verify raw document/history/source/file hashes/FKs; revoke restored sessions and pending verification/reset/admin tokens through an offline operator; review current admin roles/grants; inject fresh operational secrets; then run synthetic access/export checks before routing. Database owners/backup operators can read sensitive tables; encrypt backups and restrict access accordingly. Audit service append-only privileges do not protect against a compromised database owner.

No actual user cutover, automatic backup scheduler, destructive migration, online restoration or Task05 deployment was executed. Existing03 native dump/restore regression continues to pass, but is not a production RPO/RTO certification.

Legacy-date qualification:03 did not record account creation time; existing metadata accounts receive the migration timestamp in created_at. New04 registrations record actual creation time. No older date is invented.
