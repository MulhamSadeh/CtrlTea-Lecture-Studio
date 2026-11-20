# Task04 email setup and tested status

## Status

**Complete local registration/verification/resend/reset/password-notification/bootstrap flows were exercised. External SMTP delivery, sender DNS and real mailbox receipt were NOT verified.** No production credentials were available and no real recipient was contacted. The SMTP adapter contract was tested with a fake transport; it is not counted as external delivery.

`backend/ctrltea/mailer.py` is the replaceable email boundary. Every message has Ctrl+Tea-branded Arabic HTML plus plain text. Generated links use the configured canonical origin and a URL fragment; the React app reads/clears the fragment and submits the token in a JSON POST. Raw links/tokens do not enter HTTP access paths. Treat the whole message as secret until its link expires.

## Configuration

| Variable | Meaning |
|---|---|
| CTRLTEA_PUBLIC_ORIGIN | Exact browser origin, no path/query; HTTP only for explicit loopback development |
| CTRLTEA_MAIL_PROVIDER | `local` or `smtp`; never silently substitute local delivery for failed SMTP |
| CTRLTEA_MAIL_SINK | Absolute private local message directory; required for local mode |
| CTRLTEA_MAIL_FROM | Verified authorized sender, e.g. your provider's domain; example.invalid is rejected for SMTP |
| CTRLTEA_SMTP_HOST / PORT | SMTP submission server; default port587 |
| CTRLTEA_SMTP_USER / PASSWORD | Provider-specific submission credentials supplied privately; omitted login only if server deliberately permits it |

SMTP always starts TLS with the default verifying SSL context before optional authentication/send. The adapter does not support implicit port465; use STARTTLS587. Connection timeout15s. Provider exceptions produce failed delivery audit without logging body/credential/exception text. SMTP delivery success means the transport accepted the message, not proof of final inbox receipt.

## Local test/development

Use an absolute private folder outside frontend/public, source release paths and shared/synced document directories. The sender creates directory0700 and unique `.eml` files0600; keep parent directories and existing folders restricted too.

```bash
export CTRLTEA_MAIL_PROVIDER=local
export CTRLTEA_MAIL_SINK=/PRIVATE/ctrltea/mail
export CTRLTEA_PUBLIC_ORIGIN=http://localhost:8765
export CTRLTEA_COOKIE_SECURE=0
```

Run the account application with PostgreSQL/auth roles as SUPER_ADMIN_SETUP describes. Register a temporary account, open its `.eml` with a local mail viewer, follow the verification link, and log in. “Resend verification” replaces the prior active link. Forgot password returns the same public message for unknown/eligible accounts; open the new reset message, choose a strong new password and confirm old sessions fail. Do not publish or paste the `.eml` into logs/reports.

The automated tests extract only synthetic tokens from their disposable private sink. Browser `scripts/e2e_accounts.py` requires `CTRLTEA_E2E_DISPOSABLE=1` and `MAIL_PROVIDER=local`; it refuses to run an external-email scenario. Browser screenshots are internal QA only and excluded from reports/source archive.

## Future real SMTP setup — configuration instructions, not a deployment

1. Select a provider supporting verified sender domains and STARTTLS submission. Use an organization-owned domain/mailbox with a recovery owner, not a volunteer's disposable address.
2. Follow that provider's exact DNS records for domain verification and DKIM. Add its authorized SPF include to the domain's single SPF record. Configure DMARC with an owned reporting address and an initially monitored policy; review alignment before tightening policy. Values are provider/domain-specific and are not invented here.
3. Create a least-privilege submission credential; inject into the service secret store. Set MAIL_FROM to the verified sender and PUBLIC_ORIGIN to the final HTTPS origin; use COOKIE_SECURE=1. Do not place secrets in frontend Vite variables, .env.example, ZIP or shell history.
4. Test message receipt in a controlled owner mailbox: verification/resend, expired/replayed link rejection, reset, password-change notification and admin invite. Verify links point only at the intended origin and do not follow Host headers.
5. Check bounce/suppression/spam behavior and provider limits. Retain minimal diagnostic IDs, never message links. Decide who receives delivery-failure alerts and how resend is supported before admitting team members.

Synchronous send-after-commit is intentional in this release: only token hashes are stored. A failed send does not grant verification/admin status; it records failure and requires resend/reinvitation. No automatic durable email retries are claimed. If later adding an encrypted short-retention delivery outbox, explicitly review key handling and the only-hashed-token requirement; do not quietly persist raw reset messages in the DB.

Provider/domain/DNS setup and external receipt remain Task05 prerequisites. This document creates no account, DNS record, secret or external message.
