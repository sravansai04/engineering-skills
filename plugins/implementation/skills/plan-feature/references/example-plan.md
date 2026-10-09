# Example: A Filled-In Full Plan

A calibration example for the plan-feature skill. The product, paths, commands, and numbers are fictional; the shape, depth, and reasoning are what to copy. The SQL is PostgreSQL-flavored because a concrete dialect makes the concurrency point clearer; the planning moves apply to any stack.

Notice in particular:
- the consumer search turns up Billing, which the first draft missed (see the change log), and the deploy order puts Billing's new handler live before anything can emit the event it reads;
- the purge *claims* a project before touching any of its children, so a restore can never bring back a half-deleted project (section 9);
- read-path filtering is structural (a default-scoped query path plus a CI check), not just a one-time inventory, because the earlier attempt failed on a missed read path;
- schema expansion ships in its own slice, ahead of the behavior that uses it;
- the purge job is deliberately *not* behind the UI flag;
- every implementation slice has a real command and a rollback, and the AC matrix has no gaps.

---

# Plan: Add soft delete and 30-day restore for projects

| Field | Value |
|---|---|
| Status | In review |
| Size | Full |
| Author | A. Developer |
| Date | 2026-03-02 |
| Ticket / spec | PROJ-1432 |
| Reviewers | Projects team, Billing, Data platform (migration), Security (deletion policy) |

## 1. Summary
Deleting a project today removes it and all its tasks, files, and comments immediately and permanently, and support restores roughly two projects a week from backups. We will mark projects as deleted instead, hide them everywhere, let workspace admins restore them for 30 days, and purge them permanently after that. Rollout is behind a release flag; the schema change follows expand, migrate, contract, and billing follows the project through delete and restore.

## 2. Problem and goals
Accidental deletes cost customers work and cost support about four hours per restore. Goal: self-service recovery within 30 days with no change to what users see for live projects, no change to how live projects are billed, and no loss of our ability to honor erasure requests promptly.

## 3. Acceptance criteria
- AC-1: Deleting a project hides it from every list, search, direct link, API response, and cross-project view (for example "my tasks") within one request.
- AC-2: A workspace admin can see deleted projects in a Trash view and restore any of them within 30 days of deletion; the project returns with all tasks, files, and comments. After 30 days, restore is refused even if the purge has not run yet.
- AC-3: Projects deleted more than 30 days ago are permanently removed, including their files in object storage.
- AC-4: A user cannot list, view, or restore a deleted project in a workspace where they are not an admin (returns 404, not 403, to avoid revealing existence).
- AC-5: A verified erasure request permanently removes a project immediately, bypassing the 30-day window.
- AC-6: The existing `DELETE /v1/projects/{id}` keeps its current response (204) and a subsequent `GET` keeps returning 404.
- AC-7: A project in the trash does not count toward billed seats; a restored project counts again from the moment of restore.

## 4. Non-goals
- Soft delete for individual tasks or comments (separate ticket PROJ-1490).
- Restoring from backups older than 30 days (support process unchanged).
- Changing how long backups are retained.

## 5. Assumptions and open questions
| ID | Assumption or question | Recommended default | Impact if wrong | Owner | Status |
|---|---|---|---|---|---|
| Q-1 | Should a deleted project still reserve its name? | No: names are unique among live projects only; restoring into a taken name returns 409 asking the admin to rename first | If "yes", users cannot reuse names for 30 days and support tickets follow | Product | open |
| Q-2 | Who may restore? | Workspace admins only, same as who may delete today | If owners may restore too, the authorization check and tests change | Product | answered: admins only |
| Q-3 | When does a trashed project stop counting toward billed seats? | At delete, as today; seats resume on restore | If seats should count until purge, Billing moves its trigger from `project.deleted` to `project.purged` and nothing resumes on restore | Product, Billing | answered: default (2026-03-03) |
| A-1 | The 30-day window satisfies our published retention policy | Security confirms in review | If not, the window shortens; only a config value changes | Security | assumed |

## 6. Context and prior art
| What exists | Where | How this plan uses it |
|---|---|---|
| `ProjectRepository` and the `Project.objects` query path used by most project reads | `app/projects/repository.py:12`, `app/projects/models.py:30` | Becomes the live-only default (7.4); trash, restore, and purge opt out explicitly |
| Direct project queries bypassing the repository | 14 call sites (command below this table; full list in slice 0 output) | Each moves to the default path or filters explicitly; this is the main risk |
| Cross-project task queries ("my tasks", due-soon digest) | `app/tasks/queries.py:88`, `app/digest/build.py:41` | Must join on live projects |
| Search indexer and its `remove`/`reindex` hooks | `app/search/indexer.py:30` | Driven by the lifecycle events: remove on delete, reindex on restore |
| Transactional outbox and relay (event rows written in the caller's transaction, published with retries) | `app/events/outbox.py:20` | All three lifecycle events go through it |
| Billing's `project.deleted` subscriber, which stops seat usage | `services/billing/handlers/projects.py:15` | Found by searching for subscribers; needs a `project.restored` counterpart (Q-3, slice 4) |
| Batched background-job base class with checkpointing | `app/jobs/batched.py:1` | Reused for the purge job |
| Object-storage delete helper with retries | `app/storage/client.py:64` | Reused; deletions recorded in a purge-queue table first |
| Existing hard delete with `ON DELETE CASCADE` to tasks, files, comments | `migrations/0042_projects.sql` | Kept for the purge path, but children are deleted in batches before the parent to avoid one huge cascade |

Inventory command (case-insensitive, covering joins as well as the ORM path): `rg -n -i -e 'from projects' -e 'join projects' -e 'Project\.objects'`

Conventions to follow: service-layer authorization via `require_workspace_admin()`; errors as problem-details JSON; tests under `tests/` mirroring `app/`.
Related decisions: ADR-0019 "Prefer flags for multi-PR features"; commit `a1b2c3d` removed an earlier soft-delete attempt because one read path leaked deleted rows. This plan addresses that failure with the slice 0 inventory, a structural filter, and a CI check that catches read paths added later.

## 7. Proposed design
### 7.1 Components affected
| Component | Change | Owner |
|---|---|---|
| Projects service and API | Modified (delete semantics), new restore and trash endpoints | Projects |
| Project query path | Modified (live-only by default) | Projects |
| Tasks queries, digest | Modified (filter live projects) | Projects |
| Search indexer | Modified (remove on delete, reindex on restore) | Search |
| Billing seat handler | Modified (new `project.restored` handler) | Billing |
| Purge job and erasure command | New | Projects |
| Web app trash view | New | Projects (frontend) |

### 7.2 Data model changes
- `projects.deleted_at timestamptz NULL` (new; null means live).
- `projects.deleted_by uuid NULL` (new; who deleted it, for the trash view and audit).
- `projects.purge_started_at timestamptz NULL` (new; set when the purge or an erasure claims the project, after which it can no longer be restored).
- Index for the trash view and purge scan: `(workspace_id, deleted_at) WHERE deleted_at IS NOT NULL`, built online.
- Replace `UNIQUE (workspace_id, name)` with a unique index on `(workspace_id, name) WHERE deleted_at IS NULL` (per Q-1 default): build the new index online, then drop the old constraint in a follow-up migration. While no row is soft-deleted the two enforce the same rule, so the swap is safe before soft delete ships; leaving the old constraint in place would make a trashed project silently reserve its name during rollout.
- New `purge_queue(object_key, enqueued_at)` table so object deletions survive crashes.

### 7.3 Contract changes
| Contract | Change | Consumers | Compatibility strategy |
|---|---|---|---|
| `DELETE /v1/projects/{id}` | Soft delete instead of hard delete | Web app, mobile apps, public API users | Same status and same 404 afterwards (AC-6); no client change |
| `GET /v1/workspaces/{id}/trash` | New, admin only, paginated by cursor | Web app | Additive |
| `POST /v1/projects/{id}/restore` | New, admin only | Web app | Additive; 409 on name conflict, 404 when outside the window or already claimed |
| `project.deleted` event | Now means "moved to trash" | Billing (stops seats; unchanged per Q-3), search, analytics | Meaning is unchanged for Billing, since seats already stop at delete |
| `project.restored` event | New | Billing (resumes seats), search (reindex), analytics | Billing's handler deploys before restore can emit it (slice 4 before slice 5) |
| `project.purged` event | New | Analytics | Additive; analytics notified |

### 7.4 Key flows
Reads: `Project.objects` becomes a live-only default (`deleted_at IS NULL`); trash, restore, and purge use an explicit `Project.all_objects`. A CI check (`tests/lint/test_no_raw_project_sql.py`, new) fails when raw SQL naming `projects` appears outside the repository and those three modules, so a read path added after this plan cannot skip the filter silently. Many ORMs resolve foreign-key traversals such as `task.project` without the default scope, so the slice 0 inventory still covers those.

Delete: authorize admin; in one transaction, set `deleted_at` and `deleted_by` and write `project.deleted` to the outbox. Search removal and the Billing seat change follow from the event, so they retry with it.

Restore: authorize admin; in one transaction, run `UPDATE projects SET deleted_at = NULL, deleted_by = NULL WHERE id = $1 AND deleted_at IS NOT NULL AND deleted_at >= now() - interval '30 days' AND purge_started_at IS NULL` and, if a row was updated, write `project.restored` to the outbox. If no row was updated, return the project when it is already live (a concurrent restore won) and 404 otherwise. A unique violation returns 409. The trash view uses the same window and claim conditions, so it never lists a project that restore would refuse.

Purge (hourly):
1. Claim: pick up to 500 candidate ids, then in its own short transaction run `UPDATE projects SET purge_started_at = now() WHERE id = ANY($1) AND deleted_at < $cutoff AND purge_started_at IS NULL RETURNING id`, with `$cutoff = now() - interval '30 days'`. Only the returned ids go further.
2. Children: for claimed projects (including any claimed by an earlier run that did not finish), delete tasks, files, and comments in chunks of 5,000, enqueueing object keys in `purge_queue` in the same transaction as each chunk.
3. Parent: `DELETE FROM projects WHERE id = ANY($1) AND purge_started_at IS NOT NULL`, writing `project.purged` to the outbox.

The claim column doubles as the checkpoint: a crashed run resumes claimed projects first. In dry-run mode the job logs the ids it would claim and claims nothing, so dry runs never block a restore.

Erasure: in one transaction, soft-delete the project if it is live (writing `project.deleted`) and claim it by id without the cutoff; then run steps 2 and 3 immediately.

### 7.5 Alternatives considered
| Option | Pros | Cons | Why not chosen |
|---|---|---|---|
| Filter each call site by hand, no structural default | Smallest diff | The next read path written after this plan leaks, which is exactly how commit `a1b2c3d` failed | Repeats a known failure |
| Database row-level security policy hiding deleted rows | Enforced below the application, catches raw SQL too | The app connects with one role; trash and purge would need a second role and connection pool, and the policy adds a predicate to every query plan | Too heavy for one table today; revisit if the CI check proves leaky |
| Move deleted projects to archive tables | Live tables stay clean, no read-path filtering | Copying a project with 100k tasks is a large, slow transaction; restore is equally heavy | Cost and risk at large project sizes |
| Rely on backups plus a restore tool | No product change | Restores are slow, all-or-nothing, and still need support | Does not meet the self-service goal |

## 8. Edge cases and failure modes
| Case | Expected behavior | Covered by |
|---|---|---|
| Restore when a live project has the same name | 409 with rename guidance | AC-2, slice 5 test |
| Restore after day 30 but before the purge has run | 404; the trash view no longer lists it | AC-2, slice 5 test |
| Restore after the purge has claimed the project | 404; no project is ever live with some of its children removed | AC-2, slice 6 race test |
| Delete an already-deleted project | 404 (as today) | AC-6, slice 3 test |
| Deep link to a task in a deleted project | 404 | AC-1, slice 2 read-path test |
| Event publish fails after a delete or restore commits | The outbox relay retries until the broker accepts; Billing and search deduplicate on event id | AC-7, slice 3 test (outbox row written in the same transaction) and slice 4 test |
| Purge job crashes mid-batch | Next run finishes claimed projects first; queued object keys still deleted | Slice 6 test |
| Object storage delete fails | Key stays in `purge_queue`, retried; alert after 24 h | Slice 6 test |
| Project deleted, flag later turned off | Stays hidden (readers do not check the flag) and is still purged on schedule | Slice 2 and 6 design; rollback rehearsal in section 12 |

## 9. Concurrency
- Restore racing the purge: the purge claims each project (`purge_started_at`) in a short transaction before it touches any child row, and restore requires `purge_started_at IS NULL`. Both are single-row conditional updates, so whichever commits first wins. Under PostgreSQL's default READ COMMITTED level, a second statement that overlaps the first waits for the row lock and then re-evaluates its WHERE clause against the committed row; one that starts later simply reads the committed row. Either way it matches nothing. A restore therefore lands either before the claim (the project is skipped and keeps all its children) or after it (refused with 404). Re-checking `deleted_at` only in the final parent DELETE would not be enough: by then the children are already gone. Covered by a two-connection test, in both orders, in slice 6.
- Two admins restoring at once: the second update matches no row, finds the project already live, and returns it, so the call is idempotent and only one `project.restored` event is written.
- Lifecycle events duplicated or reordered (delete, restore, delete in quick succession): the outbox relay publishes in commit order with the project id as the partition key, so one project's events stay in order; Billing's handler deduplicates on event id.
- Delete racing an edit: edits to a deleted project fail with 404 because write paths load through the live-only default.

## 10. Security and privacy
- Entry points: delete (existing), trash list, restore, purge job (system actor), erasure command (operators with the erasure role). All user entry points call `require_workspace_admin()` and look up the project scoped to the caller's workspace, returning 404 otherwise (AC-4).
- Sensitive data: projects can contain personal data in tasks and files. Soft-deleted data is retained up to 30 days; erasure requests use the immediate purge path (AC-5). Security to confirm the window against policy (A-1).
- Audit: delete, restore, purge, and erasure each write an audit entry with actor and project id.
- Needs dedicated security review: yes, for the deletion-policy change and the erasure path.

## 11. Scale and performance
| Dimension | Today | 10x | 100x | Breaks first | Mitigation | Now / later |
|---|---|---|---|---|---|---|
| Projects rows | 400k | 4M | 40M | Read paths without an index that covers the new filter | Partial indexes include `deleted_at IS NULL` where hot queries need them | Now, for the 3 hot queries |
| Project deletes per day | 1.5k | 15k | 150k | Hourly purge falls behind | Batches of 500 projects with the claim as checkpoint; children deleted in chunks | Now |
| Tasks per large project | 100k | 1M | 10M | A single cascade delete holds locks for minutes | Delete children in chunks of 5,000 before the parent | Now |
| Trash size per workspace | about 5 | 50 | 500 | Unpaginated trash list | Cursor pagination from day one | Now |

Source of "today": row counts and a 30-day delete average from count queries with a statement timeout on the reporting replica, which serves no user traffic; growth multipliers are assumptions.

## 12. Rollout and rollback
- Feature flag: `project_soft_delete`, release type, default off, owned by the Projects team; stages: internal workspaces, 10% of workspaces, all. Removal in slice 8.
- Migration phases: expand (slice 1: columns, indexes, purge queue, unique-index swap), migrate (slices 2 to 7), contract (slice 8: remove the flag and the user-facing hard-delete branch).
- Deploy order, readers before writers: the columns (slice 1) exist before any code reads them; read-path filtering (slice 2) is live everywhere before any code can set `deleted_at` (slice 3), so a rollback of slice 3 leaves already-trashed projects hidden; Billing's `project.restored` handler (slice 4) is live before restore (slice 5) can emit that event.
- The purge job (slice 6) is not gated by the UI flag. Once any project is soft-deleted, the 30-day promise must hold even if the flag is turned off.
- Backward compatibility: API status codes unchanged; old mobile versions see identical behavior, so no deprecation is needed.
- One-way doors and safeguards: the purge is irreversible. Safeguard: the job ships in dry-run mode (logs what it would claim) for one week, and the first real run is limited to internal workspaces.
- Rollback rehearsal: slice 3 and slice 5 tests run with the flag on and off. Before the 10% stage, the flag is turned off once in staging with trashed projects present, confirming they stay hidden, stay unbilled, and are still purged on schedule.
- Health signals: purge lag (oldest eligible `deleted_at`), purge errors, `purge_queue` depth, outbox relay lag, restore 5xx rate, and the number of restored projects still missing a seat-resume event in Billing an hour after the restore. Turn the flag off if restore errors exceed 1% for 15 minutes or that number is above zero.

## 13. Risks and spikes
| ID | Risk or unknown | Likelihood | Impact | Mitigation or spike |
|---|---|---|---|---|
| R-1 | A read path misses the filter and leaks deleted projects (the reason commit `a1b2c3d` was reverted) | Medium | High | Slice 0 inventories every read path; slice 2 makes the live-only path the default, adds the CI check against new raw SQL, and adds a test that seeds a deleted project and asserts every inventoried path hides it |
| R-2 | Batched child deletion is too slow at large project sizes | Low | Medium | Slice 0 spike: time chunked deletes of a 1M-task project on an anonymized production-sized copy (time box: 2 hours) |
| R-3 | Billing misses or double-applies a lifecycle event, so seats are wrong after a restore | Low | High (money) | Slice 4 handler deduplicates on event id; contract test on both events; the seat-drift signal in section 12 during rollout |

## 14. Delivery slices
Commit-sized steps (T ids) are shown for slice 1 only, to keep the example short; every other slice lists its steps the same way.

### Slice 0: Spike: read-path inventory and purge timing (time box 1 day)
- Goal: answer R-1 and R-2.
- Changes: none merged; output is a list of every project read path with file:line (including foreign-key traversals), and timings for chunked deletes measured on an anonymized production-sized copy.
- Depends on: none; can run in parallel with: slice 1.
- Verification: inventory reviewed by a second engineer; the inventory command and the timings recorded in this plan.
- Rollback: n/a.
- Covers: de-risks AC-1 and AC-3.

### Slice 1: Expand the schema
- Goal: the new columns, indexes, and tables exist; no application code changes.
- Changes: migrations adding `deleted_at`, `deleted_by`, `purge_started_at`, the partial indexes, `purge_queue`, and the new partial unique index; a follow-up migration drops the old unique constraint.
- Depends on: none; can run in parallel with: slice 0.
- Verification: `make migrate-check` (applies and rolls back on a scratch database) and `make test TEST=tests/migrations`.
- Rollback: the columns and tables are unused and can stay; the down migration restores the old unique constraint if needed (with no soft-deleted rows, both indexes enforce the same rule).
- Covers: prerequisite for AC-1 to AC-5.
- Steps:
  - T1: migration adding `deleted_at`, `deleted_by` and `purge_started_at` (check: `make migrate-check`)
  - T2: partial indexes and the `purge_queue` table (check: `make migrate-check`)
  - T3: new partial unique index, then a follow-up migration that drops the old unique constraint (check: `make migrate-check` and `make test TEST=tests/migrations`)

### Slice 2: Filter every read path
- Goal: deleted projects are invisible everywhere, even though nothing can delete softly yet.
- Changes: live-only default on `Project.objects` and the repository, explicit `Project.all_objects`, the 14 direct call sites, the task queries, the digest, search filtering, and the new CI check `tests/lint/test_no_raw_project_sql.py`.
- Depends on: slice 1 deployed to all environments; slice 0 inventory.
- Verification: new `tests/projects/test_deleted_hidden.py` seeds a deleted row directly and checks every path from the inventory; run `make test TEST=tests/projects` and `make test TEST=tests/lint`.
- Rollback: revert code; no row is soft-deleted yet, so nothing becomes visible.
- Covers: AC-1.

### Slice 3: Soft delete behind the flag
- Goal: with the flag on, delete sets `deleted_at` instead of removing rows.
- Changes: projects service, delete endpoint, `project.deleted` written to the outbox in the delete transaction, search removal driven by the event.
- Depends on: slice 2 deployed to all environments.
- Verification: API tests with the flag on and off, including AC-6 status codes, and a test that the outbox row commits and rolls back with the delete; `make test TEST=tests/projects/api`.
- Rollback: flag off. Projects already trashed stay hidden (slice 2) and are purged on schedule (slice 6).
- Covers: AC-1, AC-6.

### Slice 4: Billing resumes seats on restore (Billing team)
- Goal: Billing handles `project.restored` before anything can emit it.
- Changes: new `project.restored` handler in `services/billing/handlers/projects.py` that resumes seat usage, deduplicating on event id; shared contract test for both lifecycle events.
- Depends on: none; can run in parallel with: slices 1 to 3. Must be deployed before slice 5.
- Verification: `make test TEST=services/billing/tests/test_project_events.py` and `make test TEST=tests/contracts/test_project_events.py`.
- Rollback: revert; no `project.restored` events exist until slice 5.
- Covers: AC-7.

### Slice 5: Trash view and restore
- Goal: admins can list and restore deleted projects within the window.
- Changes: trash and restore endpoints (window and claim conditions, `project.restored` to the outbox), web trash view, audit entries, reindex driven by the event.
- Depends on: slices 3 and 4 deployed. Frontend and backend halves can proceed in parallel against the agreed contract.
- Verification: authorization tests for non-admins and other workspaces (404), the name-conflict 409 test, a restore-after-day-30 test (404), and a concurrent-restore test asserting one event; run `make test TEST=tests/projects/api/test_restore.py` and `npm test -- trash-view`; manual restore on staging, checking the seat count in Billing.
- Rollback: flag off.
- Covers: AC-2, AC-4, AC-7.

### Slice 6: Purge job and erasure path (dry run first)
- Goal: permanent removal after 30 days, and immediately for erasure requests.
- Changes: claim step and batched purge on the existing job base class, `purge_queue` worker, erasure command.
- Depends on: slice 1. Independent of slices 2 to 5.
- Verification: job tests for resuming claimed projects after a crash, object-delete retry, and the restore-versus-purge race in both orders using two connections (a restore committed before the claim leaves the project and all its children in place; a restore attempted after the claim returns 404 and the purge completes); run `make test TEST=tests/jobs/test_purge.py`; one week of dry-run logs reviewed before enabling deletes.
- Rollback: disable the job schedule. Nothing is lost while it is disabled; claimed projects finish on the next run.
- Covers: AC-2 (no partial restore), AC-3, AC-5.

### Slice 7: Progressive enablement
- Goal: flag on for internal workspaces, then 10%, then all.
- Changes: flag configuration only.
- Depends on: slices 5 and 6 (dry run reviewed); the staging rollback rehearsal in section 12 passed.
- Verification: health signals in section 12 stable for 48 hours at each stage.
- Rollback: flag off.
- Covers: all ACs in production.

### Slice 8: Contract and cleanup
- Goal: remove the flag and the user-facing hard-delete branch; permanent deletion then happens only through the purge routine, which the erasure command also uses.
- Changes: flag checks and the old hard-delete code path removed.
- Depends on: slice 7 at 100% for two weeks.
- Verification: `make test`; `git grep -n project_soft_delete` returns nothing.
- Rollback: revert code.
- Covers: no new AC; keeps AC-1 to AC-7 passing.

## 15. Verification matrix
| AC | Slice | Test or check |
|---|---|---|
| AC-1 | 2, 3 | `test_deleted_hidden.py` across all inventoried read paths; CI check against new raw SQL |
| AC-2 | 5, 6 | Restore API tests (including after day 30), trash view component test, race test, staging check |
| AC-3 | 6 | Purge job tests, dry-run review |
| AC-4 | 5 | Cross-workspace and non-admin authorization tests |
| AC-5 | 6 | Erasure command test |
| AC-6 | 3 | Delete endpoint status-code tests with flag on and off |
| AC-7 | 4, 5 | Billing handler and contract tests; seat check during the staging restore |

## 16. Change log
| Date | Change | Reason |
|---|---|---|
| 2026-03-02 | First draft | |
| 2026-03-03 | Added the purge claim (`purge_started_at`) and bounded restore to the 30-day window | Review: a restore during child deletion would have returned a project with its tasks and files gone, and restore still worked on day 31 |
| 2026-03-03 | Added Billing as a consumer of `project.restored` (Q-3, AC-7, slice 4); lifecycle events moved to the outbox | Review: restored projects would never have resumed billing, and an event lost after commit had no retry |
| 2026-03-03 | Split schema expansion from read-path filtering; made the live-only path the default and added the CI check | Review: schema and behavior belong in separate slices, and a one-time inventory does not stop new leaks |
