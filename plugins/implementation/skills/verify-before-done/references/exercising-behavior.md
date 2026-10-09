# Exercising a change end to end

Read this in Step 4 when you are unsure how to drive a change through its real entry point, or when you want the edge-case catalog. The aim is to observe the behavior a user or caller will get, not what a unit test asserts about an internal function.

## Contents

1. Before you start: final code, safe targets
2. Long-running processes: start, wait, stop
3. HTTP APIs
4. Command-line tools
5. User interfaces
6. Libraries and SDKs
7. Jobs, workers, and event handlers
8. Schema and data changes
9. Configuration and feature flags
10. Bug fixes
11. Edge-case catalog
12. Cleaning up

## 1. Before you start: final code, safe targets

**Exercise the code you just wrote, not an older copy of it.** Watching stale code behave and reporting the new behavior as verified is one of the most common false claims. Typical stale copies:

| Stale copy | Refresh it |
|---|---|
| Compiled output (`dist/`, `build/`, a binary in `target/` or `bin/`) | rebuild after the last edit (`npm run build`, `cargo build`, `go build`, `mvn package`) |
| A dev server or worker without hot reload | restart it |
| A container image | `docker compose up --build` (plain `up` reuses the old image), or rebuild the image |
| An installed package or CLI that shadows the source | use an editable install (`pip install -e .`, `uv pip install -e .`, `npm link`) or reinstall |
| Browser cache or a service worker | hard-reload with the cache disabled in devtools; unregister the service worker if the app has one |

Where you can, prove it: a version string, the commit hash in a build-info endpoint, a startup log line that includes your new option, or a deliberately unique log message you then see.

**Point side effects at safe targets.** Local `.env` files often hold live third-party keys or a shared database URL, so exercising a payment, email, SMS, webhook, or bulk-write path "locally" can charge a card, mail a customer, or change shared data. Before you trigger one, read the effective configuration: `DATABASE_URL` and other connection strings, API base URLs, the mail or SMS transport, and key prefixes that distinguish live from test credentials (many providers use `live` versus `test` in the key). Switch to a local service, a mail catcher, the provider's test mode, or a stub. If you cannot confirm the target is not production, do not trigger the side effect; list it under "Not verified" with the steps to run it safely.

## 2. Long-running processes: start, wait, stop

Start servers in the background with output going to a log you can read, wait until they are ready rather than sleeping a fixed time, and stop them when you are done.

```bash
npm run dev > /tmp/verify-server.log 2>&1 &   # use the project's own start command
SERVER_PID=$!
curl -sS --retry 30 --retry-delay 1 --retry-connrefused -o /dev/null http://localhost:3000/ \
  || { echo "server never became ready"; tail -n 50 /tmp/verify-server.log; }
# ... exercise it ...
kill "$SERVER_PID"
```

Find the port and the start command in the project's scripts, its README, or the framework's defaults. If a dev server spawns child processes, killing the parent may leave the children running; check with `lsof -i :3000` (macOS and most Linux) and stop what you started.

Read the server log after exercising it. A 200 response with a stack trace in the log is not a pass.

## 3. HTTP APIs

For each new or changed endpoint, send at least: one valid request, one invalid request, and one unauthenticated or unauthorized request (if the endpoint is protected).

```bash
# Valid request: print headers and body
curl -sS -i -X POST http://localhost:3000/api/widgets \
  -H 'Content-Type: application/json' \
  -d '{"name": "example", "size": 3}'

# Invalid body: expect a 4xx with a useful message, never a 500
curl -sS -i -X POST http://localhost:3000/api/widgets \
  -H 'Content-Type: application/json' -d '{"size": "not-a-number"}'

# No credentials: expect 401 (or 403), never the data
curl -sS -o /dev/null -w '%{http_code}\n' http://localhost:3000/api/widgets/123
```

Check: status code, response shape against the documented contract (field names, types, nulls), headers you rely on (content type, caching, pagination links), and that the side effect really happened (read the record back with a GET, or query the database). Also try a resource that does not exist (expect 404) and, if the endpoint takes a list or a page size, an empty list and the maximum size. For API design questions use `data-api:api-design`.

## 4. Command-line tools

```bash
./bin/tool list --json > /tmp/out.json; echo "exit=$?"
python3 -m json.tool /tmp/out.json > /dev/null && echo "valid JSON"
./bin/tool list --json --limit -1; echo "exit=$?"     # bad input: expect a clear error and non-zero exit
./bin/tool --help | grep -- '--json'                  # the new flag is documented
```

Check: exit code (0 on success, non-zero on failure), that data goes to stdout and diagnostics to stderr (a stray debug print on stdout breaks every consumer that parses it), that `--help` describes the new behavior, behavior with no TTY (pipe the output somewhere), and behavior when run twice (idempotent where it should be). If the tool is installed as an entry point, reinstall it or use an editable install first (section 1), then run the installed command, not just the module, to prove the entry point is wired.

## 5. User interfaces

Use a browser, not just a build. If your environment provides a browser automation tool, drive the page with it; otherwise ask the user to look, and mark the UI as not verified until they do.

Walk through:

- The page loads with no new errors in the browser console and no failed network requests.
- The changed interaction works end to end: input, submit, the result is displayed, and it persists after a reload if it should.
- Loading, empty, and error states render sensibly (simulate an error by sending invalid input or stopping the backend).
- A narrow viewport (around 375 px wide) does not overflow or hide controls.
- Keyboard only: you can reach and operate the new controls with Tab, Enter, Space, and Escape, and focus is visible.
- Back, forward, and refresh do not lose state or resubmit unexpectedly.

Load the page with the cache disabled after your last build (section 1). If the project already depends on Playwright, its CLI can capture a screenshot for the report: `npx --no -- playwright screenshot --full-page http://localhost:3000/settings /tmp/settings.png` (browsers come from `npx --no -- playwright install`, which downloads them; ask first if network use is restricted). A screenshot shows rendering only; it does not prove the interaction works.

## 6. Libraries and SDKs

Write a throwaway consumer that imports the library the way a user would, from its public entry point, not from an internal file path. That catches missing exports and packaging mistakes that in-repo unit tests cannot see.

```bash
# JavaScript/TypeScript: what would actually be published?
npm pack --dry-run          # lists the files that would go into the tarball
# Python: build the distributions and confirm the new module is inside
python -m build && python -m zipfile -l dist/*.whl
```

Check: the new symbol is importable from the public entry point, types resolve for a TypeScript or typed-Python consumer, the change is backward compatible (or the version and changelog say otherwise), and errors raised to the caller are documented and catchable.

## 7. Jobs, workers, and event handlers

Trigger the job directly using the project's own command or test harness, rather than waiting for a schedule, after checking that its side effects go to safe targets (section 1). Then:

- Confirm the side effect: the row, the file, the message, the email in a local mail catcher.
- Run it twice. Retries and redeliveries happen in production, so a second run must not duplicate the effect.
- Make one input fail and confirm the failure is recorded (logged, retried, or dead-lettered) and does not block the rest of the batch.
- Confirm the job is registered with the scheduler or queue consumer that will actually run it in production (see `wiring-and-companions.md`).

## 8. Schema and data changes

- Apply the migration to a fresh database, then run the test suite against it.
- If the framework supports rollback, roll back and reapply to prove both directions work.
- Apply it to a database with realistic existing data when you can: a new non-null column, a uniqueness constraint, or a type change can fail on rows that an empty test database never has.
- Read back data through the application, not just with SQL, to prove the models and the schema agree.

Deeper review of locking, backfills, and deploy ordering belongs to `data-api:db-migration-safety`; query plans and indexes belong to `data-api:query-review`.

## 9. Configuration and feature flags

- Start the application with the new configuration and confirm it is read (log it at startup, or exercise the behavior it controls).
- Remove the new key and start again: expect a safe default or a clear error naming the missing key, not a crash deep in a request.
- For a feature flag, exercise both states. Off must behave exactly as before the change; on must reach the new code.

## 10. Bug fixes

- Rerun the original reproduction steps from the report and observe the corrected behavior.
- Confirm the regression test fails without the fix, following the hand-edit procedure in SKILL.md Step 3, and check it fails for the right reason (the assertion about the bug, not an import error).
- Look for siblings: the same mistake in neighboring code paths (`git grep` for the pattern you fixed).
- If you never found the root cause, say so; `implementation:debug-root-cause` exists for that.

## 11. Edge-case catalog

Pick the ones that apply to the input and the operation. You will not need all of them.

| Area | Cases |
|---|---|
| Presence | missing field, null, empty string, empty list, whitespace only |
| Boundaries | 0, 1, -1, maximum allowed, maximum plus one, off-by-one at page or batch edges |
| Size | very long string, very large file or list, deeply nested data |
| Text | unicode, emoji, right-to-left text, combining characters, leading and trailing spaces, mixed case |
| Numbers and money | rounding, negative values, very large values, locale decimal separators, currency precision |
| Time | time zones, daylight-saving transitions, leap day, end of month, end of year, clock skew |
| Identity and access | unauthenticated, wrong role, another user's resource, expired session or token |
| Duplicates and repetition | the same request twice, double-click submit, retry after timeout |
| Concurrency | two writers at once, read during write, out-of-order events |
| Dependencies | downstream service down, slow, or returning malformed data; disk full; network timeout |
| Partial failure | failure halfway through a multi-step write: no half-written state left behind |

## 12. Cleaning up

Stop every process you started, delete temporary files and test data you created outside the test harness, and reset any configuration or flag you changed for the experiment. List anything you could not clean up in the report.
