# Task 02 Architecture Addendum — private workspaces

23 October 2026. This addendum is written before Task03 source changes and supersedes conflicting shared-course assumptions in the original eight Task02 documents, which remain preserved unchanged.

## Approved change

One PostgreSQL database serves **private user workspaces**. A workspace has one eventual owning account. Courses, lectures, sources, pages, history, runs, jobs and private filesystem objects inherit that workspace. Membership of the Ctrl+Tea team or a platform role does not reveal another workspace. A course is an organizational container inside its owner's workspace, not a shared workspace by default.

Legacy installations have no authenticated owner. They import into a separately identified **restricted, unclaimed workspace** with a durable import receipt. Task04 must verify a real account and an operator-authorized claim bound to that import; no arbitrary first signup, teacher name or email inferred from a document assigns ownership. Task03's local developer selects a workspace through trusted process configuration only; no client header/query can select another workspace. This is not authentication and remains loopback-only.

Prepare minimal account/profile metadata without registration, credentials, mail, sessions or bootstrap endpoints. The profile's self-written team_description is ordinary text; it has no authorization effect. Security roles and official reviewer assignments remain separate future structures.

Explicit sharing will be resource-scoped and deny-by-default. A future grant must distinguish read/download/copy and attachment scope. Independent imports create new IDs, copies of permitted attachments, their own revisions and destination ownership. Provenance records origin and authorized copy event; it is not a live write-through link or a foreign-key cascade that deletes copies after revocation. No sharing/cross-profile import endpoint is introduced in03.

Future review submissions bind an immutable content revision or external immutable file set; reviewer assignment grants access only to that submission. Decisions/comments/status events refer to that immutable target. Subsequent edits invalidate approval for the new head. Tasks10/14 implement the workflow;03 documents its migration-ready relationships without adding a premature review UI or transition engine.

## Scope decisions replacing parts of the old03 plan

| Previous proposal | Updated03 implementation direction |
|---|---|
| Organization/course membership is the default content boundary | Private workspace ownership; account ownership claimed explicitly in04 |
| Replace local worker and freeze a second engine copy behind a snapshot bridge now | Preserve existing in-process OCR/export worker and mathematics modules; adapt persistence under their existing store interface; single API process per configured private workspace only |
| SQLAlchemy Core repositories and broad service extraction | Small psycopg adapter for existing parameterized SQL, explicit transaction/UoW and Alembic migrations; no application rewrite |
| Postgres17 as a proposed target | Use the actually executable supported major and record it; local setup matches tested major before claiming support |
| All history must be renumbered into a new canonical table | Preserve old history including duplicate numbers; add unique integrity for new saves without rewriting old rows |
| Distributed workers/leases and full conflict product UX in03 | Transactional saves and tests now; distributed scheduling and full conflict UX remain later tasks |

RLS and composite workspace FKs backstop application scope; the runtime DB role must not be superuser, BYPASSRLS or migration owner. Scope is set transaction-locally and cleared by connection closure. SQL RLS is not a replacement for Task04 identity/permission checks. Private files use workspace directories and database-backed scope resolution; no public bucket/static DATA mount is introduced.

All existing scientific JSON/schema/math/formatting behavior stays compatible. The original V1 and verified backups are preserved. No public deployment, authentication, email or Task04 work is authorized here.
