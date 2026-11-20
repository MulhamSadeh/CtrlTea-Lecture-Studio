# Private data ownership — Task 03

23 October 2026. **Implemented foundation; authentication/sharing/workflow remain future work.** The Task02 shared-course default is superseded by TASK_02_ARCHITECTURE_ADDENDUM.md.

## Implemented relationships

| Resource | Ownership / integrity |
|---|---|
| accounts | Stable account ID, full name, email/normalized unique email, verification timestamp and state. Metadata only: no password/session/registration flow exists |
| profiles | One account FK; self-written team_description plus version. No security role derived from description |
| workspaces | One eventual owner_user_id, unique per account; unclaimed/private/suspended state. Unclaimed requires NULL owner; private/suspended requires a real account FK |
| courses | Composite primary key(workspace_id,id); scoped to a private workspace |
| lectures | Composite workspace/id; same-workspace course FK; raw scientific doc TEXT and revision counter, existing theme |
| sources/pages | Same-workspace lecture/source FKs. Linked source must also be in the same lecture. Original digest/relative source path preserved |
| revisions | Scoped previous-document snapshots. Legacy duplicate revision numbers retained via is_legacy; unique version index applies to new saves |
| author_runs/tasks and aliases | Workspace-scoped parents/targets; aliases cannot point outside their lecture |
| jobs | Workspace/lecture FK; original in-process worker retained; one guarded worker process per configured workspace |
| private_assets | Workspace owner, optional lecture FK, portable relative path, digest/length/kind. Originals, exported files and figure files resolve under the private prefix |
| import_receipts/provenance | Restricted workspace, source fingerprint, verification record and lecture installation provenance; no automatic identity claim |

Files live at DATA_ROOT/workspaces/{workspace_id}/sources, exports, figures, math and bundles. There is no public DATA mount. Workspace IDs are constrained to safe path components; source paths and asset paths reject traversal. SQL queries resolve source IDs under the current workspace before returning a path. Export routes additionally resolve the report's lecture in that workspace. Figure/math caches inherit private prefix ownership without changing their algorithms.

Private assets can be indexed after source extraction/export/figure generation and after visual-review report updates. Transient authoring ZIP responses are not stored as durable files; their author_run/base_doc/tasks carry ownership. Legacy figure definitions remain inside the unchanged lecture JSON.

## Persistence privacy boundary

Every content table has enabled and forced PostgreSQL row-level security with both USING and WITH CHECK on the server's transaction-local workspace setting. Composite FKs prevent cross-workspace parent links even when IDs are guessed. IDs can deliberately coincide in different workspaces when preserving separate installations; the composite identity resolves them independently.

The runtime role is not a superuser, BYPASSRLS role, role administrator, table owner or member of the owner role. It cannot update workspace ownership or read account/profile metadata under the Task03 grants. A new DB connection sets one trusted scope; no nested transaction can switch it. Connection closure clears the transaction-local setting. Test evidence includes independent reads/writes, spoofed-owner inserts, parent references and independent copies with identical legacy IDs.

Task03 has **no authenticated principal**. Scope comes from trusted process configuration or an internal test/operator context manager, never an HTTP header/query/body. This is a local development boundary, not permission to host an unauthenticated app. Task04 must derive scope from a verified account's owner relationship and enforce action-level permissions. Unclaimed data requires an explicit local operator flag; suspended spaces fail closed. SQLite mode remains the original local installation model, not a multi-user authorization implementation.

## Legacy ownership assignment

1. Offline operator explicitly provisions an empty, unclaimed workspace.
2. A consistent SQLite installation copy and matching files are inspected without app initialization or scientific rewriting.
3. Import binds this workspace to one input fingerprint and durable receipt. Queued/running legacy jobs are quarantined rather than executed automatically.
4. A matching retry verifies target rows and files; a different input, nonempty destination or missing target files fails safely. No first signup receives these data.
5. Task04 supplies a single-use, expiring, hashed claim authorization issued by an accountable operator, bound to that workspace/import and a verified account. It must lock account/workspace and consume the claim transactionally with an audit event.

One account has one private workspace. If verification has already created an empty workspace, claim may replace that empty shell after a transaction proves it has no resources. If it contains work, do not overwrite it or merely bypass owner uniqueness: use a separately authorized import/merge with collision checks and provenance. Never infer ownership from teacher names, course text or an arbitrary email in a file.

## Future sharing and independent imports — design only

Proposed later tables: lecture_grants(resource workspace/lecture or immutable revision, grantee account, permissions read/download/copy, attachment allowlist, expiry/revocation, grantor and audit); copy_events(destination workspace/lecture, origin public opaque identity, origin revision/hash, grant/copy time and provenance). No sharing endpoints or cross-profile import command exists in03.

A grant concerns exactly its resource; it does not grant course/workspace browsing. Browsing joins current grants and excludes revoked/expired entries. Copy rechecks permission at acceptance, freezes the permitted revision and attachment list, creates new destination IDs and independent original-file copies, and remaps source/block references using the existing explicit exchange semantics. Content, themes, mathematics and provenance survive. Unauthorized original attachments are never silently included; unresolved references must block copy or require an explicit permitted packaging decision.

Origin provenance is not a write-through link. Origin deletion/revocation cannot cascade-delete an authorized independent copy. Revocation blocks future original reads/copies; it cannot recall already downloaded bytes. Cross-profile sharing later requires explicit RLS/policy/repository changes, not a shortcut that switches an arbitrary caller into the owner's workspace context.

## Future workflow/review relationships — migration-ready design

| Future entity | Required relationships / restrictions |
|---|---|
| lecture_workflow | Workspace/lecture FK, version and state draft/ready_for_review/under_review/changes_requested/approved/published; transition authorization separate from profile text |
| immutable_revision_snapshots | Exact raw content/hash + pinned source/figure/theme input manifest. Existing previous-head history is not yet a certified release snapshot store |
| review_submissions | Owner workspace, exact immutable revision OR immutable external submission asset set; submitter, status/version and provenance |
| external_submission_files | Private DOCX/PDF/structured originals with digest/size/type; owner workspace and submission FK; no requirement to re-author into JSON before review |
| reviewer_assignments | Submission FK + reviewer account + permitted actions/expiry/state. Access only to submitted snapshot/files, never all owner's courses |
| review_comments/decisions | Assignment/submission and exact snapshot identity, human actor/time/evidence; append-only decisions, separate from agent findings |
| workflow_events | Before/after state, actor/reason/time and transition version; conditional writes |

These entities are deliberately **not implemented** in03. Tasks08/10/14 add immutable release snapshots, source-version pinning and workflow actions. Existing revisions are useful historical copies; runtime SQL grants and parent deletion still permit their removal as in V1. Do not treat them or mutable export report paths as a certified immutable approval target yet. Subsequent edits must require a new approval; old approval remains attached to the old snapshot only. An agent cannot mint a human decision.

Super Admin manages platform membership/roles and operational moderation through future policies, with no implicit read-all workspace grant. Reviewer permission is a security role plus a resource assignment, never something a member obtains by typing “reviewer” in team_description. Ordinary task assignments and organizational responsibilities get their own later records.
