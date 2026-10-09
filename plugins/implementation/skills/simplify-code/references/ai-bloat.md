# Recognizing and removing generated-code bloat

Code produced by an assistant (or by a hurried human) tends to bloat in
predictable ways. The cause is structural, not carelessness: the generator
writes each function as if it had to survive on its own. It does not know
the invariants established elsewhere (types, validation at the edge, the
codebase's error strategy, helpers that already exist), so it re-establishes
them locally, and it hedges against failure modes that cannot occur. The
result is code that looks robust line by line and is redundant as a whole.

Simplifying it means reattaching the code to the context it was written
without: the types, the callers, the existing helpers, and the project's
conventions for errors and logging.

## Fingerprints

A quick scan for these finds most of it. One or two are normal; a cluster
means the whole diff deserves a bloat pass.

- Nearly every function wrapped in try/catch, each with a log line.
- Comments on most lines, or "Step 1 / Step 2" narration.
- Docstrings that repeat the signature ("@param id the id").
- Arguments validated for conditions their types already rule out.
- Fallback defaults on values that cannot be missing.
- A new `utils`, `helpers`, or `common` file whose functions shadow existing
  ones.
- Interfaces, factories, registries, or base classes with exactly one
  implementation.
- Parameters and options that no caller passes, often labeled "for
  flexibility" or "for future use".
- Casts or ignore-pragmas that silence the type checker instead of fixing a
  type.
- Log messages announcing success after each step, with decorative prefixes.
- Data copied, re-sorted, re-parsed, or re-fetched when it is already in the
  right shape and in hand. Not a candidate when a lock acquisition, an
  `await` or `yield`, a transaction boundary, or an I/O call sits between the
  first read and the repeat (the re-read after `SELECT ... FOR UPDATE` or
  after taking a lock is the point), or when the copy keeps callers or other
  threads and tasks from seeing or mutating shared state (returning a copy of
  an internal list, copying an argument before storing it, snapshotting a
  collection before iterating while it may change). Those are tier 2 at
  least, and the tests will not tell you if you got it wrong.
- Compatibility aliases or deprecated wrappers for names that never shipped.
- Placeholder comments like "TODO: add proper error handling".
- Generic names (`data`, `result`, `info`, `temp`, `processItems`,
  `handleData`) next to code that uses precise domain names.

## The boundary rule

Validation, broad error handling, and fallbacks belong at trust and failure
boundaries: where input arrives (HTTP handlers, CLI parsing, message
consumers, file and environment reads, deserialization, FFI) and where a
process must survive a failure (request handlers, job loops, UI event
handlers, top-level entry points). Inside those boundaries, code should
trust its types and the invariants the boundary established.

Most generated bloat is boundary code copied inward. So first identify the
boundaries that touch the scope. Then every defensive construct inside them
is a candidate, and every one at them is presumed legitimate until shown
otherwise.

## Align with the project's error strategy

Find out how the codebase handles errors before touching any catch block:

- Exceptions propagate to a central handler (common in web frameworks):
  local catch-and-log blocks are usually noise.
- Errors are returned and wrapped with context (Go's
  `fmt.Errorf("...: %w", err)`, Rust's `?` with context): handle each error
  once; logging and returning it is double handling.
- Result or Either types: a thrown exception or a swallowed error is the
  inconsistency, not the missing try/catch.

Generated code often mixes strategies within one diff. Converge on the one
the neighbors use. Where that changes what callers observe (a function that
used to return a default now raises), it is tier 2 and goes in the report.

## Patterns, with keep and remove rules

| Pattern | Remove when | Keep when | Typical tier |
|---|---|---|---|
| try/catch that logs and continues or returns a default | The caller cannot do anything useful with the default; the error should reach a real handler | It is at a process boundary, or a documented best-effort operation (cache warm-up, telemetry send) | 2 |
| catch that rethrows unchanged | It is the only handler on its `try`, or every handler on that `try` rethrows unchanged (in C#, `throw ex;` also resets the stack trace, so removing it improves the trace) | A later sibling handler catches a supertype: `except ValueError: raise` before `except Exception: return None` keeps `ValueError` from being swallowed. The clause is load-bearing; keep it, or restructure only as tier 2. JavaScript has one catch clause per `try`, which is why ESLint's `no-useless-catch` is always safe there | 1 |
| Log and rethrow at every layer | Another layer logs the same error | It is the one layer that handles the error | 2 |
| Entry/exit and "success" logs | Nothing consumes them and tracing already covers timing | An alert, dashboard, audit, or support runbook reads them | 2 |
| Re-validation of validated input | A boundary or the type system already guarantees it, and the type is enforced at runtime or every path to it is checked (no `any`, untyped caller, or parsed data) | It is the boundary, or a public library entry point; or a lock, `await`, or transaction sits between the first check and this one (double-checked locking, re-checking shared state after an `await`) | 1, or 2 across a lock or `await` |
| Impossible-state checks (`if (items.length < 0)`) | The state cannot be constructed | The check documents and enforces an invariant other code relies on (then prefer an assertion in the project's style); or other threads or tasks can change the state between construction and the check | 0-1, or 2 for shared state |
| Casts and type-ignore pragmas | The value already has the target type, or fixing the source type is local | The cast is a narrowing the compiler cannot prove and the code establishes it right before | 1 |
| Fallback defaults (`?? x`, `or {}`, `getOrDefault`) | Absence is impossible, or absence should fail loudly (missing required config) | Absence is a legitimate, documented case | 1-2 |
| Options and parameters nobody passes | No caller sets them and they are not public | They are public API, read from config, or used by tests as a seam | 1, or 3 if public |
| Single-implementation interface or factory | No test double, no plugin boundary, no enforced module boundary | Any of those exist | 1 |
| New helper duplicating an existing one | The existing helper matches on the edge cases you checked | They differ and the difference is intended (document it at the helper) | 1-2 |
| Compatibility alias for a never-released name | The old name was never in a release or used outside the scope | It shipped; then it is a deprecation decision, tier 3 | 1 |
| Narrating comments and echo docstrings | They restate the code | They explain why, cite a constraint, or generate public docs | 0 |
| Unused imports | Imports are compile-time only: Java, C#, Rust `use`, TypeScript with default import elision (Go refuses to compile an unused named import, so the only ones left are blank `_` imports, which exist for their side effects) | The import runs code that matters: Python, Ruby `require`, plain JavaScript, or TypeScript under `verbatimModuleSyntax` or `preserveValueImports`, where the module registers models, signals, tasks, or plugins, or patches something; or the file re-exports it (`__init__.py`, `__all__`, an index barrel). Keep it, marked with the project's idiom for a side-effect import | 0 for compile-time imports, 1 elsewhere |
| `async` function with no `await` | It is private, and either the body cannot throw or every caller writes `await f()` directly (no stored promise, no `.then`/`.catch`, no `Promise.all`, no call started before the `try` that awaits it) | It is exported; a caller uses `.then`/`.catch`, collects the promise, or checks for one; or the body can throw, since without `async` the throw escapes synchronously instead of rejecting | 1, or 3 if exported |
| `return await` | The project's lint configuration requires dropping it (for example typescript-eslint `return-await` set to `in-try-catch`) and it is outside any `try`/`catch`/`finally` and any block holding `using` or `await using` declarations | Everywhere else. Inside those blocks it is load-bearing, and elsewhere it keeps the function in async stack traces; ESLint deprecated `no-return-await` for that reason. Without a project rule, removing it is taste: skip it | 1 |
| Redundant conditionals (`if c: return True else: return False`, `x == true`) | `c` is already a boolean | `c` is truthy but not boolean and callers depend on getting a real bool; then use `bool(c)` | 0-1 |

## Tests in a generated diff

Generated tests often assert on mocks of the code under test, repeat the
same setup in every case, or test trivial accessors. Within this skill, tests
are in scope for three things only: removing tests of code you deleted as
dead, collapsing duplicated setup into the fixture style the suite already
uses, and updating a test that pins the bloat itself (such as "returns []
when the database throws") when the bloat's removal is an authorized tier 2
change. That update gets its own batch, and the old and new assertion are
quoted under Behavior changes. Do not otherwise delete assertions or reduce
coverage in the name of simplification; if a test is genuinely worthless,
list it under "Noticed outside scope" for a deliberate decision.

## A worked pass

Before (TypeScript, new in the diff):

```ts
// Utility function to get the active users from the list of users
export async function getActiveUsers(users: User[] | undefined, options: { includeAdmins?: boolean } = {}): Promise<User[]> {
  try {
    // Check if users exist
    if (!users || !Array.isArray(users)) {
      console.log("No users provided, returning empty array");
      return [];
    }
    const includeAdmins = options.includeAdmins ?? true;
    // Filter the users
    const result = users.filter((user: User) => {
      if (user.active === true) {
        if (!includeAdmins && user.role === "admin") {
          return false;
        }
        return true;
      }
      return false;
    });
    console.log(`Found ${result.length} active users`);
    return result as User[];
  } catch (error) {
    console.error("Error getting active users:", error);
    return [];
  }
}
```

Facts checked: both callers pass a non-undefined `User[]` and never pass
`options`; `user.active` is typed `boolean`; nothing awaits anything inside;
`filter` cannot throw here; no alert reads these console lines; the function
is exported only from its own new file, and both callers are in the diff.

After:

```ts
export function getActiveUsers(users: User[]): User[] {
  return users.filter((user) => user.active);
}
```

Report lines this produces: dead option removed (tier 1, no caller passes
it); `undefined` handling and `Array.isArray` check removed (tier 1, typed
callers); try/catch removed (tier 1 here, because `filter` with a pure
predicate cannot throw, so no observable change); console logs removed
(tier 2 in general, tier 1 here because nothing consumed them); `async`
dropped (tier 1: both callers are in the diff and were updated to stop
awaiting; it would be tier 3 if anything outside the diff imported it).
