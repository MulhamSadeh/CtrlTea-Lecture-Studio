# Secure Super Admin setup — Task04

**No administrator password, reusable bootstrap secret or active invitation is included.** These instructions run the implemented commands; first public signup never becomes SuperAdmin. The privileged application account is distinct from PostgreSQL roles.

## Prerequisites

Use the extracted Task04 `ctrltea-studio` project, Python>=3.11 and the existing Pandoc/LibreOffice/Tesseract/fonts. PostgreSQL16 foundation from03 must be present; qualify a currently patched16 server before staging. Commands below are Bash; from fish, enter `bash` for this sequence or use `set -gx` equivalents. Work only on a verified private backup/new development installation. The source ZIP is not a database/file backup.

```bash
umask 077
python -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[postgres,test]'
python -m pip install -r requirements-postgres-tested.txt -r requirements-auth-tested.txt
export CTRLTEA_DB_BACKEND=postgres
export CTRLTEA_AUTH_MODE=required
export CTRLTEA_RUNTIME_ROLE=ctrltea_app
```

Privately inject the actual operator URL; this masked prompt avoids printing it or recording its value as a command. URL form is PostgreSQL URI with properly encoded credentials. Do not put the value in a report.

```bash
read -rs -p 'Offline migration PostgreSQL URL: ' CTRLTEA_MIGRATION_URL
export CTRLTEA_MIGRATION_URL
python -m ctrltea.database upgrade
```

This advances `0001_private` to `0002_accounts`, or initializes an empty DB. It preserves03 data. Capture a coordinated SQL+files backup before upgrading an actual installation. Destructive downgrade is refused.

## Restricted service roles

For an existing03 `ctrltea_app`, retain its existing restricted role/password; **skip** provision_runtime. On a new DB with no such role, provide a random password from your password manager through a masked prompt, then provision it:

```bash
read -rs -p 'New runtime DB role random password (at least20 chars): ' CTRLTEA_RUNTIME_PASSWORD
export CTRLTEA_RUNTIME_PASSWORD
python scripts/provision_runtime.py
```

Create the separate auth identity once. It refuses to overwrite an existing role or rotate silently. It seeds the role/permission catalog and grants runtime trash-table access, never creates a platform administrator:

```bash
read -rs -p 'New auth-service DB role random password (at least20 chars): ' CTRLTEA_AUTH_DB_PASSWORD
export CTRLTEA_AUTH_DB_PASSWORD
python scripts/provision_auth.py
```

Now privately configure the two service DSNs corresponding to those passwords (roles `ctrltea_app` and `ctrltea_auth`). Neither may use the migrator/superuser/table owner. Store them using your local protected environment/secret manager, not in a shared shell script:

```bash
read -rs -p 'Restricted ctrltea_app PostgreSQL URL: ' CTRLTEA_DATABASE_URL
read -rs -p 'Restricted ctrltea_auth PostgreSQL URL: ' CTRLTEA_AUTH_DATABASE_URL
export CTRLTEA_DATABASE_URL CTRLTEA_AUTH_DATABASE_URL
export CTRLTEA_AUTH_SECRET="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"
export CTRLTEA_DATA_DIR=/PRIVATE/ctrltea/data
export CTRLTEA_PROFILE_DIR=/PRIVATE/ctrltea/profiles
export CTRLTEA_MAIL_PROVIDER=local
export CTRLTEA_MAIL_SINK=/PRIVATE/ctrltea/mail
export CTRLTEA_PUBLIC_ORIGIN=http://localhost:8765
export CTRLTEA_COOKIE_SECURE=0
unset CTRLTEA_WORKSPACE_ID CTRLTEA_ALLOW_UNCLAIMED
```

Replace `/PRIVATE/...` with absolute owner-only paths. Existing03 installations must retain their actual data root so original files remain accessible. New signup creates only its own empty private workspace; it never receives unclaimed legacy data. AUTH_SECRET must persist privately across restarts and must never be printed by the application.

Remove operator/provisioning credentials from the API shell; retain them only through a separate protected operator session for subsequent offline commands:

```bash
unset CTRLTEA_MIGRATION_URL CTRLTEA_RUNTIME_PASSWORD CTRLTEA_AUTH_DB_PASSWORD POSTGRES_PASSWORD
python scripts/start.py
```

Open **http://localhost:8765** exactly. The launcher uses configured PUBLIC_ORIGIN. One API/worker process only; do not use Uvicorn --workers/reload duplicates. This is a loopback development setup, not online staging. HTTPS/secure cookies and infrastructure isolation are05 gates.

## Initial owner invitation and activation

1. In the app, register the owner's full name and real intended email, choose a private strong password and confirm it. For local testing use a temporary synthetic account; local sink does not prove delivery/control of a real external mailbox.
2. Open the intended verification message privately and activate it (60min, one use). Log in. External ownership must later be verified through actually delivered mail; no username/password shortcut is accepted.
3. In a separate operator shell with the same mail/auth settings and offline migration DSN, issue:

```bash
read -r -p 'Verified intended administrator email: ' CTRLTEA_OWNER_EMAIL
python -m ctrltea.bootstrap invite --email "$CTRLTEA_OWNER_EMAIL"
```

The CLI is protected by operator DB access, is not a public invitation-creation endpoint, and refuses nonexistent/unverified accounts. It stores only a token hash, issues a30min single-use mail-bound invitation and prints no token/password. If delivery fails, correct mail settings and run it again for a fresh invitation.

4. Follow that invitation, sign in as its matching verified account if necessary, and press the Arabic administrator-activation button. A recent password login/reauthentication (15min) is required.
5. Sign in again after activation invalidates old sessions. `/api/auth/me` must show `role: SuperAdmin`; the interface now shows **إدارة المنصة**. There is no way to select this role on signup.
6. Open member management, then a temporary member's workspace. Confirm the admin banner names the member and that courses/files open under the admin's own identity. Check **النشاط الإداري**. Never ask for or reset the member's password for this purpose.

Initial bootstrap locks a singleton and closes permanently on first success. Wrong account/expired/consumed links fail. Further SuperAdmins can be deliberately assigned only by an existing SuperAdmin with recent password confirmation, with session invalidation and audit. The last verified active SuperAdmin cannot be demoted/suspended, including simultaneous requests. Never share the same admin password between volunteers.

## Sensitive actions and recovery

After15min, re-confirm the current administrator password through **إعدادات الحساب → تأكيد الجلسة للعمليات الإدارية** before role/permission/grant/legacy changes. This is password step-up, not a claimed second factor. No TOTP/WebAuthn MFA implementation is included.

For an active verified admin who forgot their password, use the ordinary forgot/reset flow. It changes the password, revokes sessions and does not silently grant admin rights to another account.

If the existing admin is inaccessible/suspended, an accountable offline operator must verify the intended recovery identity out of band, use an already mailbox-verified account, and issue:

```bash
read -r -p 'Verified recovery account email: ' CTRLTEA_RECOVERY_EMAIL
read -r -p 'Accountable recovery reason (at least10 chars): ' CTRLTEA_RECOVERY_REASON
python -m ctrltea.bootstrap recover --email "$CTRLTEA_RECOVERY_EMAIL" --reason "$CTRLTEA_RECOVERY_REASON"
```

This records an operator recovery event/reason, reactivates that verified account if necessary, and sends a30min single-use recovery invitation. The recipient must still log in with their own password and consume the bound invitation; the CLI never reads/prints/sets that password. If necessary, use mailbox password reset after reactivation. Recovery is not a way to alter a mailbox address without verification. Retain operator access under separate protected procedures; a backend DB owner is more privileged than an application admin.

After suspected compromise: revoke affected sessions/tokens, review roles/grants/audit and coordinate secret rotation through the offline operator. Do not lower the last-admin protection or change bootstrap_state manually as a normal recovery step. Coordinated backup restoration must revoke restored sessions/tokens before reopening access.

Temporary bootstrap/replay/wrong-account/expiry/recovery and concurrent-last-admin cases were executed on disposable PG. Browser QA exercised the actual CLI invitation and Arabic activation screen. No active privileged account or credential is delivered in the ZIP.
