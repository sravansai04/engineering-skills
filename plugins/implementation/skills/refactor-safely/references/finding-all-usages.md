# Finding All Usages

Read this before you rename, move, change the signature of, or delete anything that isn't obviously local to one file. A refactor rarely breaks the call sites the compiler can see; it breaks the ones it can't.

## Contents

1. Search order
2. Semantic tools from the command line
3. Search commands
4. Hidden-reference checklist (all stacks)
5. Per-language dynamic access
6. In-flight and persisted data at deploy time
7. Proving code is dead
8. Recording what you found

---

## 1. Search order

1. **Semantic references.** Use the language server or IDE: find references, call hierarchy (incoming calls), implementations, and subtypes. These understand scope, overloads and shadowing, so they're the most precise source. Run them for every overload and every implementation of an interface method. Without an IDE, drive the same engines from the command line (section 2).
2. **Text search in this repo** for every spelling of the name (section 3). This catches strings, config, templates and docs.
3. **The hidden-reference checklist** (section 4), plus the section for each language the repo uses (section 5).
4. **Outside the repo.** Other repositories, published packages, external clients, stored data, and in-flight messages (section 6).
5. **Classify the reach** as private, internal or published, and choose a strategy: change it in place, or use expand-contract (`large-refactors.md`).

## 2. Semantic tools from the command line

An agent working in a terminal has no IDE, but most language servers and refactoring engines can be driven from a shell or a short script. Use them before falling back to text search and hand edits.

| Stack | Find references, implementations, callers | Rename or restructure |
|---|---|---|
| Go | `gopls references file.go:LINE:COL`, `gopls implementation file.go:LINE:COL`, `gopls call_hierarchy file.go:LINE:COL` | `gopls rename -d file.go:LINE:COL NewName` to preview the diff, `-w` to write it |
| TypeScript / JavaScript | A short ts-morph script: load the `tsconfig.json` into a `Project`, find the declaration, call `findReferencesAsNodes()` on it | In the same script call `.rename("newName")` on the declaration, then `project.save()`; confirm with `tsc --noEmit` |
| Python | jedi: `jedi.Script(path=...).get_references(line, column)` | rope: `Rename(project, resource, offset).get_changes("new_name")` then `project.do(changes)`; or jedi's `Script.rename(line, column, new_name=...)`. Run the type checker afterwards |
| Java | OpenRewrite search recipes such as `FindMethods` and `FindTypes` | OpenRewrite `ChangeMethodName`, `ChangeType`, `ChangePackage`: run `mvn rewrite:dryRun` (or Gradle `rewriteDryRun`), review the patch, then `rewrite:run` / `rewriteRun` |
| Rust | `rust-analyzer search '<pattern>'` | `rust-analyzer ssr 'old_fn($a) ==>> new_fn($a)'` (writes files in place, so commit first), then `cargo check` |
| Anything else | `ast-grep run -p '<pattern>'` (syntax-aware, not type-aware) | `ast-grep run -p '<pattern>' -r '<rewrite>'` to preview, add `-U` to apply |

Mind each tool's position format. gopls takes a 1-based line and a 1-based byte column, which is what `rg -n --column` prints. jedi lines are 1-based but its columns start at 0. rope takes a character offset into the file.

**Review every tool-produced diff.** In statically typed code a semantic rename is close to exact. In dynamically typed code (Python, JavaScript, Ruby) it is inference: it can miss references made through `getattr`, bracket access or duck typing, and it can over-match an unrelated attribute that happens to share the name. Many engines also offer to rename inside strings and comments, which catches documentation but also unrelated words. Leave that off unless you check each hit, and always follow a tool rename with the text search in section 3 and a run of the type checker and tests.

## 3. Search commands

Identifiers drift in spelling as they cross layers: `invoiceTotal` in code, `invoice_total` in the database and JSON, `InvoiceTotal` in another language, `INVOICE_TOTAL` in env vars, `invoice-total` in URLs, CSS and CLI flags. Search all of them.

```bash
# Every common casing at once (camel, snake, kebab, Pascal, upper); -i ignores case.
rg -n -i 'invoice[_-]?total'

# ripgrep skips hidden files and anything matched by .gitignore by default.
# --hidden brings back dotfiles only (CI config, .env.example, editor and tool configs):
rg -n --hidden -g '!.git' -g '!node_modules' -g '!vendor' -i 'invoice[_-]?total'

# -uu (= --no-ignore --hidden) also searches gitignored paths: generated clients, local
# env files, build-time config. Exclude bulky dependency and build dirs explicitly.
rg -n -uu -g '!.git' -g '!node_modules' -g '!vendor' -g '!dist' -g '!build' -i 'invoice[_-]?total'

# Whole-word match, to avoid hits like 'invoiceTotals' when you care about exact uses.
rg -n -w 'invoiceTotal'

# Fixed-string match for dotted or bracketed paths (a regex dot matches any character).
rg -n -F 'billing.invoice.total'

# Tracked files only, dotfiles included, and other refs such as an unmerged release branch.
git grep -n -i -E 'invoice[_-]?total'
git grep -n -w 'invoiceTotal' origin/release-2.4

# History: commits that added or removed the string (-S), or changed lines matching a regex (-G).
git log -S 'invoiceTotal' --oneline
git log -G 'invoice[_-]?total' --oneline -- config/
```

Also search for the **containing module or class path**, not only the leaf name. String references often use the fully qualified form (`billing.invoices.InvoiceService`, `App\Billing\InvoiceService`, `com.acme.billing.InvoiceService`).

For **other repositories**, use your organization's code search: GitHub code search on the web, a self-hosted Sourcegraph or OpenGrok, or the CLI:

```bash
gh search code 'invoiceTotal' --owner YOUR_ORG --limit 100
```

`gh search code` goes through GitHub's legacy code-search API. Results can differ from the web UI and regex is not supported, so treat them as a lower bound. When the stakes are high, clone the known consumers and search them locally. For a published package, check its registry's dependents listing or your internal dependency graph as well.

## 4. Hidden-reference checklist (all stacks)

Tick through each category and note what you searched.

| Category | Examples of what breaks |
|---|---|
| Reflection and dynamic dispatch | Lookup by name string, `method_missing` / `__getattr__` / `__call`, dynamic imports |
| DI and plugin wiring | Bean or service names, assembly or package scanning by naming convention, plugin registries, `META-INF/services`-style files, entry points |
| Routing | Route names, controller#action strings, URL helpers keyed by function name, OpenAPI `operationId` |
| Config and environment | YAML, JSON, TOML or XML keys bound to field names; env var names; CLI flags; feature-flag keys in a flag service |
| Templates | Server-side templates and front-end templates that read properties by name; the template checker may be off |
| Serialization and wire formats | JSON, XML and YAML field names derived from code names; GraphQL fields; protobuf/Avro names in JSON mappings; event schemas on topics |
| Persistence | Columns or tables derived from class and field names; stored enum names or ordinals; class names in type-discriminator columns; stored procedures and views |
| Queues, caches, sessions | Job or task names derived from module paths; pickled or serialized objects holding class names; cache keys built from names |
| Tests | Mocks and patches targeted by string path; snapshot files keyed by test name; UI selectors (`data-testid`, CSS classes); fixtures |
| Observability | Logger names (often the package path, which log-level config targets); metric and span names that dashboards and alerts query; log text matched by alerts |
| Infrastructure and build | Dockerfiles, deployment manifests, CI jobs referencing paths, binaries or test files; infrastructure-as-code resource addresses (renaming one can mean destroy and recreate unless you use the tool's move mechanism, e.g. Terraform `moved` blocks) |
| Generated code | Clients and stubs generated from a schema or IDL. Rename at the source and regenerate; never hand-edit the output |
| Front end and external | Analytics event names, i18n keys, `localStorage` / cookie keys, deep links, public URLs, webhooks registered by third parties |
| Docs and runbooks | READMEs, API docs, on-call runbooks, ADRs that name the symbol |

## 5. Per-language dynamic access

Each list covers references that compile and type-check after a rename but fail at runtime, or quietly change behavior.

**Python**
- `getattr`, `setattr`, `hasattr`, `importlib.import_module("pkg.mod")`, `__import__`, `__all__`.
- `unittest.mock.patch("pkg.mod.name")` targets are strings. After a move, patch where the name is *looked up*, not where it's defined.
- Entry points in `pyproject.toml` (`[project.scripts]`, `[project.entry-points.*]`) use `"pkg.module:func"` strings.
- `pickle` stores module path and qualified name, so moving or renaming a class breaks unpickling of stored data.
- Task queues often derive the task name from module and function (Celery's default), so queued messages carrying the old name fail after deploy.
- Web frameworks: Flask endpoint names default to the view function's name (`url_for("view_name")`); Django URL names, app labels and template variable names.
- Dataclasses, pydantic models, attrs classes and NamedTuples: field names are the serialized keys. For dataclasses (including `pydantic.dataclasses`), attrs and NamedTuple, field order also defines the positional constructor; a pydantic `BaseModel` takes keyword arguments only.

**JavaScript / TypeScript**
- Bracket access `obj[name]`, dynamic `import()` with computed paths, `require(variable)`.
- `package.json` `main`, `exports` and `bin` paths; barrel `index` re-exports that external importers rely on.
- String event names (`emit("x")`), action-type strings, message-channel names.
- `JSON.stringify` uses property names, so renaming a field changes payloads, stored `localStorage` values and API bodies.
- Template expressions in component frameworks may not be type-checked unless the framework's template type-checking is on.
- Test selectors and CSS class names referenced from end-to-end tests and stylesheets.

**JVM (Java, Kotlin)**
- `Class.forName`, `getMethod` / `getDeclaredField`, annotation processors.
- Spring and similar: bean names, `@Qualifier("name")`, `@Value("${key}")`, and configuration-properties binding, where renaming a field changes the property key it binds to.
- JPA and Hibernate: column names implied by field names when there's no explicit mapping; JPQL/HQL query strings that use entity field names; `@Enumerated` defaults to `ORDINAL`, so reordering enum constants silently changes the meaning of stored rows.
- Jackson and other serializers: field and getter names become JSON keys unless annotated.
- `META-INF/services/*` files list fully qualified class names; so does Java serialization.
- Logging config names loggers by package, and AOP pointcuts often match by package pattern. Moving a class to another package can silently change its log level or drop advice such as transactions or security.
- Kotlin data classes: only primary-constructor properties take part in `equals`, `hashCode`, `copy` and `componentN`.

**.NET (C#, F#)**
- `Type.GetType("Ns.Type, Assembly")`, `Activator.CreateInstance`, reflection over members.
- DI registration by assembly scanning and naming conventions; options binding (`GetSection("Name")`) maps config keys to property names.
- `System.Text.Json` / Newtonsoft property names; EF Core conventions that derive columns and keys from property names.
- Razor views and tag helpers. `nameof(...)` is rename-safe; string literals are not.

**Go**
- Struct tags: a field with a `json:"name"` tag keeps its wire name when renamed, but an untagged exported field's JSON key is its Go name. Changing a field from exported to unexported means `encoding/json` stops marshaling it.
- Interfaces are satisfied implicitly. Renaming a method can make a type stop satisfying an interface, and that only surfaces at a runtime type assertion (`v, ok := x.(Iface)` quietly returns false) or a dynamic registration.
- `text/template` and `html/template` resolve `.FieldName` at execution time.
- `reflect`, `//go:linkname`, `//go:embed` paths, build tags.

**Ruby (Rails)**
- `send` / `public_send`, `method_missing`, `respond_to?`, `"ClassName".constantize`.
- Single-table-inheritance `type` columns and polymorphic `*_type` columns store class names in rows.
- Background-job class names sit in the queue backend.
- Route strings (`to: "controller#action"`), partial paths (`render "users/form"`), and i18n keys derived from model and attribute names.

**PHP**
- `$obj->$method()`, `new $className`, `call_user_func`, `__call` / `__get`.
- Container config (YAML, XML, PHP arrays) referencing class or service names as strings; ORM mapping attributes.
- `serialize()` output stores class names, and so do session and cache stores.

**Rust**
- Serde: field and variant names are the wire format unless `#[serde(rename = "...")]` pins them.
- `#[no_mangle]` and `extern` symbols, and macros that generate identifiers.
- Cargo feature names; tracing span and field names that observability queries use.

## 6. In-flight and persisted data at deploy time

Even when every code reference is updated, data created by the *old* code is still out there:

- **Rolling deploys** run old and new versions side by side, so both names must work during the overlap.
- **Queued jobs and messages** created before the deploy still name the old class, function or schema.
- **Caches, sessions and serialized blobs** hold old class names or field names.
- **Mobile apps and other clients** on old versions keep calling old endpoints and sending old field names for months.
- **Long-running workflows, schedules and webhooks** that external parties registered against old URLs.

For any of these, keep an alias or mapping for the old name (accept both, emit the new one), let the old data drain or migrate it, and only then remove the alias. That's expand-contract; see `large-refactors.md`.

## 7. Proving code is dead

Static tools find *candidates*. Expect false positives on anything reached dynamically.

| Stack | Candidate finders |
|---|---|
| JS / TS | `knip` (unused files, exports, dependencies); `tsc` with `noUnusedLocals` / `noUnusedParameters` |
| Python | `vulture`; ruff's unused-import and unused-variable rules |
| Go | `staticcheck` (U1000 unused); `deadcode` from `golang.org/x/tools/cmd/deadcode` |
| Rust | The compiler's `dead_code` warnings |
| JVM / .NET | IDE "unused declaration" inspections; .NET IDE analyzers for unused private members |

Before deleting anything with nontrivial blast radius:

1. Run the semantic and text searches from sections 2 to 5 for each candidate.
2. Check runtime evidence: access logs for routes, metrics for jobs, flag-evaluation counts for flagged paths.
3. When it's still uncertain, **instrument before deleting**. Add a log line or counter (a "tombstone") on the path and ship it. Wait for a window that covers the code's natural cycle: a month-end, quarter-end or year-end job only runs at those times. Delete once nothing fires.
4. Delete in its own commit, so a revert restores exactly that code.

## 8. Recording what you found

Put this in the refactor report:

- The semantic reference count, the tool that produced it, and the number of sites changed.
- The text patterns searched, and where (this repo, other branches, org code search).
- Every dynamic, string or persisted reference found, and how each was handled (updated, aliased, mapped, or migrated).
- The reach classification, and the deprecation path if the symbol is published.
- Anything you couldn't check (for example, "no access to the partner repos"), stated as a remaining risk.
