# Implemented member profiles

Accounts reuse the03 stable accounts/profiles/workspaces relationships. No second ownership system or scientific JSON identity fields were added.

| Field | Editable by member | Visibility |
|---|---|---|
| Full name | Own profile | Own, team directory, admin |
| Verified email | No arbitrary profile edit | Own and admin; excluded from ordinary directory |
| Profile picture | Own upload | Authenticated team members while active, own/admin account access policy |
| team_description | Own free text, up to3000 characters | Own, ordinary directory, extended admin view |
| Created date/status/system role | Server/admin controlled | Own; appropriate role in directory; full account details to admin |
| Academic content/workspace | Through authorized academic routes | Private by default; SuperAdmin override or explicit resource grant |

The Arabic profile asks **شو شغلتك ضمن Ctrl+Tea؟**. Members write and revise their own description, rather than an administrator selecting their profession. It is ordinary React text, not rendered HTML. Typing “Super Admin”, script markup or “Reviewer” does not change a role or grant access. Job description, security role and future lecture assignment are independent concepts.

Profile saves compare profiles.version and update text/full name transactionally. A stale save receives409; UI retains the typed candidate and offers explicit reload. Avatar upload increments the same version; UI reloads after successful save/upload. A valid small image is decoded/reencoded and stripped of original metadata. JPEG/PNG/WebP only; no arbitrary executable upload/path. Avatar files are separate private configured data, not lecture content. Replaced orphan images currently remain private until later retention cleanup.

`GET/PUT /api/account/profile` always use the server principal, not a submitted user ID. Extra role/workspace fields are rejected. No endpoint lets an admin rewrite another member's self-description. Admin can inspect it in member management. `GET /api/members` returns active verified members' name/role/description/avatar availability only, with name search and a bounded200-item response; it does not return email, workspace ID, private lecture counts or file links. Large-directory pagination is a later refinement; current team sizing is small. Admin member search has page loading beyond200.

Browser drafts and remembered course/lecture/source correction state are partitioned by deployment origin + user + workspace. Manual logout offers download before clearing that account's private caches. Expiry/password-security revocation hides the editor and preserves only the same account's local draft namespace until it logs in again. Shared computers still require deliberate local logout and private-browser hygiene; server backups cannot capture unsubmitted browser drafts.

Automated tests cover version conflicts, unauthorized role input, script text without privilege escalation, safe directory projection and avatar rejection/reencoding. Real browser QA verifies escaped description display and mobile390px RTL without horizontal overflow. No mathematical preview component was modified.

Legacy-date qualification:03 did not record account creation time; existing metadata accounts receive the migration timestamp in created_at. New04 registrations record actual creation time. No older date is invented.
