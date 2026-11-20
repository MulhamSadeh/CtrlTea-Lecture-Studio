# Implemented Super Admin dashboard

This is actual React UI in Accounts.tsx calling the implemented FastAPI routes, not a prototype or mock API. The existing lecture editor remains the editor inside an account shell.

| Screen/tab | Implemented behavior |
|---|---|
| Member management | List/search by name/email; verification/activation/suspension/role; extended profile description; load more after200; member selection |
| Role/status controls | Explicit role selection; confirmations for role and suspend/reactivate; password step-up; last-admin guard; session invalidation |
| Grouped permission matrix | All34 actions with group/Arabic label, default role and allow/deny/inherit override; future flags clearly labelled |
| Workspaces/legacy | Every owned/restricted/unclaimed workspace; open with explicit admin identity; select verified recipient and assign an unclaimed workspace only if destination is empty |
| Exact resource grants | Select recipient/source workspace/course or lecture/resource ID/action list; create or revoke grant with audit; no copy/sharing workflow |
| Administrative activity | Actor/action/target/workspace/outcome/time, refresh and paginated older audit entries |
| Academic workspace | Existing course/lecture/source/history/authoring/export operations under admin's own identity; banner names target member/workspace; return-to-dashboard action |
| Recoverable trash | Scoped deleted course/lecture/source records, retention timestamp, confirmed restore preserving IDs/history/files |

The admin can perform these actions without obtaining or changing another member's password. Workspace choice is only a request selector, validated by the backend; it never confers privilege on an ordinary user. Safe member DTOs omit credential/session/token tables. There are no “show password” or arbitrary database/secret panels.

A role/permission update revokes the recipient's sessions and records an audit event. Updating one's own admin role may force a fresh login. A SuperAdmin always has full effective application actions; UI prevents pretending that an ordinary permission deny removes that global role. Another active SuperAdmin is required before demoting/suspending the last one.

Member descriptions are visible but self-edited from that member's profile. Future lecture assignments, publishing, scientific approvals and cross-profile copy are not fabricated as operational buttons. Exact-resource grants are the authorized foundation only; shared browsing/import refinement stays in later tasks.

Administrative content requests log intent before access and response outcome, including workspace/owner for foreign access. Important account/role/grant changes also have semantic events. Ordinary sensitive mutations have outcome events. The auth service can append/read but not update/delete security_audit. Database owners remain outside that threat boundary; this is not cryptographic tamper-proof storage.

Real Chromium QA exercised bootstrap, management, opening Alice's workspace with its banner, denying a member capability, automatic session rejection, suspension/reactivation and audit display. Backend tests additionally exercise actual DOCX/PDF exports/downloads, source/history access, recoverable deletes, resource grants, owner assignment and last-admin races.
