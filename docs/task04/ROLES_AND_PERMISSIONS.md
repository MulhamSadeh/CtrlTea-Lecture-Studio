# Roles, capabilities and private-resource authorization

Task04 implemented model. Latest full-access SuperAdmin requirement supersedes conflicting02/03 restricted-admin proposals.

## Rules

Effective ordinary actions = role defaults, overridden by per-member allow/deny/inherit. Resource scope is **also** required: own private workspace or an active exact course/lecture grant containing that action. Neither team membership, a Reviewer label, a directory entry nor a self-written description reveals another workspace. SuperAdmin has all application capabilities plus explicit global academic-content access. Per-member denies cannot reduce SuperAdmin; demote the system role deliberately if needed.

Only a recent-password-confirmed SuperAdmin can change role/status/overrides/grants/legacy assignment. No ordinary action override confers administrative API access. All changes invalidate affected sessions; subsequent requests authenticate against fresh state. A request already authorized before revocation may complete; running OCR side effects and already downloaded bytes cannot be recalled. The worker checks eligibility again at start/completion. No permanent client-side permission claims are trusted.

## Complete permission catalog and defaults

| Permission | SuperAdmin | Member own scope | Reviewer own/explicit scope |
|---|---|---|---|
| courses.view | All workspaces | Yes | Yes |
| courses.create | All workspaces | Yes | No |
| courses.edit | All workspaces | Yes | No |
| courses.delete | All workspaces | Yes | No |
| lectures.view | All workspaces | Yes | Yes |
| lectures.create | All workspaces | Yes | No |
| lectures.edit | All workspaces | Yes | No |
| lectures.delete | All workspaces | Yes | No |
| lectures.import | All workspaces | Yes | No |
| lectures.export | All workspaces | Yes | Yes |
| sources.view | All workspaces | Yes | Yes |
| sources.upload | All workspaces | Yes | No |
| sources.edit | All workspaces | Yes | No |
| sources.delete | All workspaces | Yes | No |
| sources.extract | All workspaces | Yes | No |
| files.download | All workspaces | Yes | Yes |
| revisions.view | All workspaces | Yes | Yes |
| revisions.restore | All workspaces | Yes | No |
| authoring.create | All workspaces | Yes | No |
| authoring.import | All workspaces | Yes | No |
| jobs.view | All workspaces | Yes | Yes |
| jobs.retry | All workspaces | Yes | Yes, actual job action still required |
| theme.edit | All workspaces | Yes | No |
| figures.preview | All workspaces | Yes | Yes |
| math.check | All workspaces | Yes | Yes |
| transfers.export | All workspaces | Yes | No |
| transfers.import | All workspaces | Yes | No |
| resources.restore | All workspaces | Yes | No |
| review.submit | Future capability | No | No |
| review.inspect | Future capability | No | Yes, no implemented workflow |
| review.approve | Future capability | No | Yes, no implemented workflow |
| review.assign | Future capability | No | No |
| publish | Future capability | No | No |
| sharing.manage | Future capability | No | No |

Future flags appear as such in the matrix; enabling them does not create a review/publish/sharing workflow or reveal private resources. Current reviewer defaults are deliberately read/export oriented; SuperAdmin can grant additional existing actions per member. Role defaults are seeded by the offline provisioner, never a public endpoint.

## Route/action details

All48 legacy routes plus trash use the explicit POLICY map. Health and account initiation/token endpoints are public subject to rate/origin rules. Account/profile/session routes operate only on authenticated identity. Administrative routes require SuperAdmin even if a member has every ordinary capability.

Existing import and authoring operations retain independent permissions (`transfers.import`, `authoring.import`, `lectures.import` for append destinations). Upload/Word preview also requires sources.extract because the existing flow may extract/compute. Retry checks jobs.retry **and** lectures.export or sources.extract according to stored job kind. Math/figure utilities are authenticated compute actions.

A lecture grant can allow exact document/history/download actions but does not allow listing all courses or reading sibling lectures. Child source/file/job/export scope is resolved through its actual DB/report parent; a mismatching supplied lecture ID cannot authorize it. Course grants apply to resources in that course. Broad utility endpoints without an identifiable resource cannot use a lecture grant as a whole-workspace grant. Grants never copy data or change ownership. Revocation invalidates recipient sessions and blocks later reads. Recipient grant-list API exists; the complete shared-resource browsing/import product remainsTask07.

Unknown/out-of-scope resources return404; denied actions in one's own scope may return403. Backend permission checks are authoritative. The legacy editor retains its layout/buttons; a denied action displays a server error rather than falsely succeeding. Account/admin navigation is guarded and does not mount the editor while unauthenticated.

## Administrative rights and exclusions

Admin may read/edit/export/delete/restore all academic resources, manage any member/status/permission, assign exact grants, inspect audit and explicitly assign unclaimed data. This is not member impersonation; audit retains admin actor and target workspace. Admin cannot retrieve password hashes, raw sessions, reset/verification tokens or infrastructure secrets; APIs use explicit safe projections. Permanent account erasure and retention purge have no UI; suspend/reactivate is implemented. Academic deletes use30day recoverable SQL snapshots and retain private files; original source reference/history protections still apply.
