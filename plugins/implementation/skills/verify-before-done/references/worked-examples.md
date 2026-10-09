# Worked examples of the final verification write-up

Read this before writing your first verification write-up, or when unsure which status applies. Each example fills in the template from SKILL.md. The projects, commands, and numbers are illustrative.

## Contents

1. Done: a CLI flag in a Node project
2. Done, with gaps: a UI change with no browser available
3. Not done: a bug fix with a failing integration test
4. Phrasing: claims that need rewording

## 1. Done

```markdown
## Verification report

**Status:** Done
**Change:** Added a `--json` flag to `tool list` that prints machine-readable output.
**Base:** origin/main, fetched today (merge-base a1b2c3d, 0 commits behind)
**Verified state:** HEAD e4f5a6b plus uncommitted changes to 5 files; all checks below ran after the final edit
**Environment:** Node 20.11 locally (CI matrix 18 and 20; the change uses no version-specific APIs)

### Acceptance criteria
- [x] `tool list --json` prints a JSON array of items: ran it against the fixture project; output parses with `python3 -m json.tool`
- [x] Existing text output is unchanged: `tool list` output diffed against main's output for the same fixture, identical
- [x] Invalid combinations are rejected: `tool list --json --format table` exits 2 with "--json cannot be combined with --format"

### Checks run (Final gate, after the last edit)
| Check | Command | Result |
|---|---|---|
| Format | `npm run format:check` | pass |
| Lint | `npm run lint` | pass, 0 warnings |
| Types | `npm run typecheck` | pass |
| Build | `npm run build` | pass |
| Unit tests | `npm test` | 214 passed, 0 failed, 0 skipped (includes 6 new tests in `list.test.ts`) |
| E2E (CLI) | `npm run test:e2e` | 18 passed, 0 failed |

### Behavior exercised
- Fresh build: `npm run build` after the last edit; `node dist/cli.js list --help` lists `--json`, so the runs below used the new code
- Happy path: `node dist/cli.js list --json` on the fixture project; 3 items, correct fields
- Edge cases: empty project prints `[]` and exits 0; names with emoji and quotes are escaped correctly
- Failure path: unreadable config file prints the path and reason on stderr, exits 1, stdout empty
- New tests fail without the change: commented out the serializer call by hand, `list.test.ts` failed 4 of 6, restored it by hand and reran green

### Diff self-review
- Files changed: 5, all intended (`src/commands/list.ts`, `src/format/json.ts`, 2 test files, `README.md`)
- Removed before finishing: a `console.log` in `json.ts`; `scan-diff.sh` now flags nothing
- Secrets, generated files, lockfiles: none
- Wiring: the flag is declared in the command's option table and appears in `tool list --help`

### Not verified
- n/a

### Notes and follow-ups
- README usage section updated; CHANGELOG entry added under Unreleased
```

## 2. Done, with gaps

```markdown
## Verification report

**Status:** Done, with gaps
**Change:** The settings page now shows a confirmation dialog before deleting an API key.
**Base:** origin/main, fetched today (merge-base 9f8e7d6, 0 commits behind)
**Verified state:** clean tree; commit 1a2b3c4 contains exactly what was tested
**Environment:** Node 20.11, pnpm 9 (matches `packageManager`); no browser available

### Acceptance criteria
- [x] Clicking Delete opens a dialog instead of deleting immediately: component test `ApiKeyRow.test.tsx` "asks before deleting"
- [x] Cancel leaves the key in place; Confirm deletes it: component tests, and the DELETE request confirmed with curl against the dev server
- [ ] The dialog is usable by keyboard and looks right on a phone-sized screen: not verified (no browser available in this environment)

### Checks run (Final gate, after the last edit)
| Check | Command | Result |
|---|---|---|
| Lint | `pnpm lint` | pass |
| Types | `pnpm typecheck` | pass |
| Unit and component tests | `pnpm test` | 388 passed, 0 failed, 2 skipped (both also skipped on main) |
| Build | `pnpm build` | pass |
| E2E | `pnpm test:e2e` | not run: needs Playwright browsers, which are not installed here |

### Behavior exercised
- API path: `curl -X DELETE` with a valid session returned 204; the key was absent from a follow-up GET
- UI: not exercised in a real browser (see Not verified)

### Diff self-review
- Files changed: 4, all intended
- `scan-diff.sh`: one hit, a new `// eslint-disable-next-line react-hooks/exhaustive-deps` in `ApiKeyRow.tsx`; kept, with a comment explaining why the effect must run only on mount
- Wiring: the dialog is rendered from `ApiKeyRow`, which the settings page route uses

### Not verified
- Keyboard focus trap, Escape to close, and layout at 375 px wide. To verify: `pnpm dev`, open `/settings/api-keys`, tab to Delete, press Enter, check focus moves into the dialog and Escape closes it; repeat with a narrow window.
- E2E suite: `pnpm exec playwright install && pnpm test:e2e`

### Notes and follow-ups
- The two skipped tests are skipped at the merge-base 9f8e7d6 as well (checked in a worktree of that commit)
```

## 3. Not done

```markdown
## Verification report

**Status:** Not done (one integration test fails)
**Change:** Fixed pagination so page 2 no longer repeats the last item of page 1.
**Base:** origin/main, fetched today (merge-base 5c4b3a2, 3 commits behind; none touch pagination)
**Verified state:** HEAD 7d8e9f0, clean tree
**Environment:** Python 3.12 locally (CI matrix 3.11 and 3.12); Postgres 16 via `docker compose up -d db`

### Acceptance criteria
- [x] Page boundaries do not overlap: new unit test `test_pages_do_not_overlap` fails on main, passes with the fix
- [ ] Cursor pagination in the public API still works: `tests/integration/test_api_pagination.py::test_cursor_roundtrip` fails

### Checks run (Final gate, after the last edit)
| Check | Command | Result |
|---|---|---|
| Lint | `uv run ruff check .` | pass |
| Format | `uv run ruff format --check .` | pass |
| Types | `uv run mypy src` | pass |
| Unit tests | `uv run pytest tests/unit` | 512 passed, 0 failed |
| Integration tests | `uv run pytest tests/integration` (Postgres started with `docker compose up -d db`) | 87 passed, 1 failed |

### Behavior exercised
- Reproduction from the bug report: `GET /items?page=2&per_page=20` no longer repeats item 20
- Failure: the cursor round-trip test now returns one item too few on the last page

### Diff self-review
- Files changed: 2 (`src/app/pagination.py`, `tests/unit/test_pagination.py`); nothing flagged

### Not verified
- n/a (the failure above is the blocker)

### Notes and follow-ups
- The failure is caused by this change: the same test passes at the merge-base 5c4b3a2 (checked in a worktree of that commit). The offset fix also changed the cursor's boundary arithmetic. Next step: give the cursor path its own boundary calculation, then rerun the full suite.
```

## 4. Phrasing: claims that need rewording

| Instead of | Write |
|---|---|
| "All tests pass." (after running one file) | "The 12 tests in `test_orders.py` pass; the full suite was not run because ..." |
| "This should work." | "Not verified: ... To verify, run ..." |
| "Fixed the bug." | "The reproduction from the issue now returns the correct total; regression test `test_total_with_discount` fails without the fix and passes with it." |
| "The failure is unrelated." | "The same test fails at the merge-base a1b2c3d (checked in a worktree of that commit), so it predates this change." |
| "UI looks good." (no browser used) | "The build and component tests pass; the page was not viewed in a browser." |
| "Verified the endpoint." (server started before the last edit) | "Restarted the server after the final edit and confirmed the new route in the startup log; `curl` then returned 200." |
| "CI will catch anything else." (after pushing) | "Pushed; CI is still running (`gh pr checks 123`). Local checks pass; status is Done, with gaps until CI finishes." |
| "Cleaned up the code." | "Removed two debug logs and an unused import; no behavior change." |
| "Tests are green." (with a test left out) | "`test_export_large` times out locally, so the suite ran with it deselected (`pytest -k 'not test_export_large'`): 511 passed. No skip was committed; that test is listed under Not verified." |
