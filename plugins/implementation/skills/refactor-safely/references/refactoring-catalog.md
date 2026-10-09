# Refactoring Catalog

These names follow common industry usage, mostly the vocabulary of Martin Fowler's *Refactoring*, so they are searchable and mean the same thing to every reviewer. Each entry has three parts:

- **Use when:** the signal that this refactoring fits.
- **How:** the minimal safe mechanics, assuming the step-by-step loop in SKILL.md (one step, then tests, then commit).
- **Watch out:** the way this particular refactoring tends to change behavior by accident. The general list of these traps is in `equivalence-traps.md`.

Most IDEs and language servers automate the starred (★) refactorings for mainstream languages. Prefer the tool whenever it exists.

## Contents

1. Smell index
2. Composing functions
3. Names and signatures
4. Moving features
5. Organizing data
6. Simplifying conditionals
7. Inheritance and composition
8. Removing code

---

## 1. Smell index

| Smell | What you see | Try first |
|---|---|---|
| Mysterious name | The name needs a comment, or misleads | Rename |
| Duplicated code | Same logic in 2+ places, or near-copies differing by a constant | Extract Function, Slide Statements then Extract, Parameterize Function, Pull Up Method |
| Long function | Scrolling; comments that label sections; many locals | Extract Function, Decompose Conditional, Split Loop, Split Phase, Replace Temp with Query; Replace Function with Command when tangled locals block extraction |
| Long parameter list | Many params, boolean flags, the same params traveling together | Introduce Parameter Object, Preserve Whole Object, Remove Flag Argument |
| Data clumps | The same few fields always appear together | Extract Class, Introduce Parameter Object |
| Primitive obsession | Strings for money, emails, IDs; ints as type codes | Replace Primitive with Object, Replace Type Code with Subclasses |
| Repeated switches | The same switch or if-chain on a type in several places | Replace Conditional with Polymorphism, Replace Conditional with Lookup Table |
| Feature envy | A function uses another object's data more than its own | Move Function (after Extract Function if only part envies) |
| Divergent change | One module changes for several unrelated reasons | Split Phase, Extract Class, Move Function |
| Shotgun surgery | One logical change edits many modules | Move Function / Move Field, Combine Functions into Class, Inline Class |
| Global or widely mutated data | Variables written from many places | Encapsulate Variable, Remove Setting Method, Separate Query from Modifier |
| Message chains | `a.getB().getC().doD()` | Hide Delegate, Extract Function then Move Function |
| Middle man | A class that mostly forwards calls | Remove Middle Man, Inline Class |
| Speculative generality | Hooks, params or abstractions with one or zero users | Inline Function / Inline Class, Collapse Hierarchy, Remove Dead Code |
| Temporary field | A field only meaningful in some states | Extract Class, Introduce Special Case |
| Large class | Many fields and methods serving several responsibilities | Extract Class, Extract Superclass / Interface |
| Data class | Fields and accessors only; behavior lives in callers | Move Function into it, Encapsulate Collection, Remove Setting Method |
| Refused bequest | A subclass ignores or overrides most of its parent | Replace Subclass with Delegate, Push Down Method / Field |
| Loop doing several jobs | One loop accumulates unrelated results | Split Loop, Replace Loop with Pipeline |
| Deep nesting | Arrow-shaped code | Replace Nested Conditional with Guard Clauses, Decompose Conditional |
| Comments explaining *what* | A comment that narrates the next block | Extract Function / Extract Variable named after the comment, Introduce Assertion |
| Dead code | Unreachable branches, unused symbols, commented-out code | Remove Dead Code |

---

## 2. Composing functions

### Extract Function ★
- **Use when:** a block needs a comment to explain it, is duplicated, or sits at a different level of abstraction from its surroundings.
- **How:** name the function for *what* it does, not how. Locals the block reads become parameters. A local the block writes and uses afterwards becomes the return value. If it writes several, extract smaller pieces, introduce a result object, or first apply Replace Function with Command so the locals become fields.
- **Watch out:** early `return`, `break` or `continue` inside the block; `this` / `self` binding; exceptions and `finally` blocks that previously wrapped the code. Also framework proxies: in proxy-based frameworks, a same-class call to an extracted method skips annotations such as transactional, cached or async.

```python
# before
def invoice_total(lines, region):
    subtotal = sum(l.qty * l.price for l in lines)
    # regional tax
    rate = 0.2 if region == "EU" else 0.07 if region == "US" else 0.0
    return subtotal + subtotal * rate

# after
def invoice_total(lines, region):
    subtotal = sum(l.qty * l.price for l in lines)
    return subtotal + subtotal * tax_rate(region)

def tax_rate(region):
    return 0.2 if region == "EU" else 0.07 if region == "US" else 0.0
```

### Inline Function ★
- **Use when:** the body is as clear as the name, the indirection is speculative, or you need to regroup badly split functions before re-extracting them.
- **How:** confirm it isn't overridden or polymorphic, and isn't reached by name (see `finding-all-usages.md`). Replace each call with the body, substituting arguments, then delete the function.
- **Watch out:** an argument with side effects that the body evaluates twice or not at all; recursion; early returns.

### Extract Variable ★
- **Use when:** a complex expression is hard to read.
- **How:** name the sub-expression and replace its occurrences.
- **Watch out:** hoisting changes *when* the expression runs. If it sat behind `&&`, `||`, `?:` or an `if`, it now runs unconditionally, which may throw, cost time or cause side effects.

### Inline Variable ★
- **Use when:** the name adds nothing over the expression.
- **Watch out:** a variable used twice now evaluates its expression twice. That is unsafe if the expression is impure, expensive or time-dependent.

### Replace Temp with Query
- **Use when:** a temporary variable blocks Extract Function, or the same derived value is computed in several methods.
- **How:** move the expression into a side-effect-free method and replace reads of the temp with calls.
- **Watch out:** repeated calls to something expensive, non-deterministic (`now()`, random, a database read) or N+1-prone. Only do this when the query is pure and cheap.

### Split Variable
- **Use when:** one variable is reassigned to mean different things (not loop counters or accumulators).
- **How:** give each assignment its own variable, made immutable where the language allows.

### Slide Statements
- **Use when:** related lines are scattered, often as preparation for Extract Function.
- **Watch out:** a statement can't move past another that reads or writes the same state, I/O, or anything that can throw.

### Split Loop
- **Use when:** one loop does two independent jobs.
- **Watch out:** it adds a pass over the data, which can't happen if the input is a single-use iterator or stream. Measure on a hot path.

### Replace Loop with Pipeline
- **Use when:** a loop filters, maps and reduces, and a collection pipeline reads more clearly.
- **Watch out:** pipelines are often lazy (generators, Java streams, LINQ), so side effects and exceptions move. Re-enumerating a lazy query can run it twice. Short-circuit behavior and iteration order can also differ.

### Split Phase
- **Use when:** code does two different things in sequence, such as parsing then computing, or fetching then formatting.
- **How:** introduce an intermediate data structure. The first phase produces it and the second consumes it.

### Replace Function with Command (Method Object)
- **Use when:** a long function's locals are so intertwined that each Extract Function would need many parameters or several return values. This is the usual first move on a long legacy function.
- **How:** create a class whose fields are the function's parameters and locals. Move the body into a single method (`execute()`, `run()` or similar) that reads and writes those fields. Make the original function construct the object and delegate to it, so callers don't change. Now Extract Function inside the class freely: the extracted methods share state through fields instead of parameter lists.
- **Watch out:** state that must be reset between calls, so create a fresh instance per call and don't reuse one across calls or threads. Once the pieces are clear, consider moving them back to plain functions; the command class is a step, not always the destination.

```python
# before: one long function whose locals every section reads and writes
def build_invoice(order, customer, today):
    ...  # 200 lines sharing subtotal, discounts, tax_lines, notes

# after: the original keeps its signature and delegates
def build_invoice(order, customer, today):
    return _InvoiceBuilder(order, customer, today).execute()

class _InvoiceBuilder:
    def __init__(self, order, customer, today):
        self.order, self.customer, self.today = order, customer, today
        self.subtotal, self.discounts, self.tax_lines, self.notes = 0, [], [], []

    def execute(self):
        ...  # the original body, with locals turned into self.* fields
```

### Substitute Algorithm
- **Use when:** a clearer algorithm gives the same results.
- **Watch out:** this carries the highest risk of any entry here. Rounding, ordering, stability, duplicate handling and edge inputs (empty, null, huge, negative, Unicode) differ between algorithms. Back it with a golden master or a parallel comparison (`large-refactors.md`).

---

## 3. Names and signatures

### Rename (variable, function, field, type, file, module) ★
- **Use when:** a name is unclear, misleading, or out of step with the domain language.
- **How:** use the tool's rename for code references. For anything that leaves the process, such as serialized fields, routes, config keys, persisted class names or metric names, follow `finding-all-usages.md` and keep the external name stable through an explicit mapping, or migrate it with expand-contract.
- **Watch out:** renaming a parameter breaks callers that pass it by name (Python, Kotlin, C#, Swift keyword arguments). Renaming a base-class method silently stops subclasses overriding it unless an `override` keyword or annotation enforces it.

### Change Function Declaration (add, remove or reorder parameters) ★
- **Use when:** a function needs different inputs, or a parameter is unused.
- **How:** for few, internal callers, change it directly with a tool. For published or widely used functions, use parallel change: add the new signature, have the old delegate to it, migrate callers, then delete the old.
- **Watch out:** reordering parameters of the same type compiles fine and silently swaps arguments. Adding an optional parameter is source-compatible but can be binary-incompatible (`equivalence-traps.md`).

### Introduce Parameter Object
- **Use when:** the same group of parameters travels together.
- **How:** create an immutable value type, add it as a parameter, move callers over, then remove the individual parameters.

```typescript
// before
function availability(start: Date, end: Date, tz: string, roomId: string) { /* ... */ }
// after
interface DateWindow { readonly start: Date; readonly end: Date; readonly tz: string }
function availability(window: DateWindow, roomId: string) { /* ... */ }
```
- **Watch out:** a mutable shared object passed to several callees creates aliasing bugs. Make it immutable.

### Preserve Whole Object
- **Use when:** callers pull several fields from one object only to pass them on.
- **Watch out:** it widens the coupling from a few values to the whole object, and can retain large objects in memory longer.

### Remove Flag Argument
- **Use when:** a boolean parameter selects between two behaviors (`render(true)`).
- **How:** create one explicitly named function per value, then migrate callers.

### Parameterize Function
- **Use when:** several functions differ only by a literal (`raiseBy5Percent`, `raiseBy10Percent`).

### Replace Parameter with Query / Replace Query with Parameter
- **Use when:** the callee could compute the value itself (the first), or you want to remove a hidden dependency on global state, time or configuration for purity and testability (the second).

### Separate Query from Modifier
- **Use when:** a function both returns a value and changes state.
- **Watch out:** callers that relied on the combined call being atomic, for example under a lock or in one transaction.

---

## 4. Moving features

### Move Function ★
- **Use when:** a function uses another module's or class's data more than its own (feature envy).
- **How:** copy it to the target and adapt it, make the old one delegate, migrate callers, then remove the delegate.
- **Watch out:** import cycles; string references to its old location (mock patch targets, DI or config entries, job names); package-scoped config such as logger levels or AOP pointcuts that no longer match the new package.

### Move Field
- **Use when:** a field is used more by another type, or always changes alongside it.
- **Watch out:** persistence mappings and serialized shape. Moving a field between types usually changes the stored or wire format, so treat it as a data migration.

### Move Statements into Function / Move Statements to Callers
- **Use when:** every caller does the same thing around a call (move it in), or callers need to vary part of what the function does (move it out).

### Extract Class
- **Use when:** a subset of fields and methods forms its own concept, or a class has more than one reason to change.
- **How:** create the new class, move fields first, then methods, testing after each move.

### Inline Class
- **Use when:** a class no longer pulls its weight, or you need to regroup responsibilities before re-extracting them.

### Hide Delegate / Remove Middle Man
- **Use when:** callers navigate chains (`order.customer().address().city()`), so add a forwarding method. Or the class is now mostly forwarding methods, so expose the delegate instead. These two are opposites; pick whichever reduces coupling for the current callers.

### Combine Functions into Class / Combine Functions into Transform
- **Use when:** several functions operate on the same data. Bundle them as methods of a class, or as a function that enriches a copy of the data with derived values.

### Split Module
- **Use when:** a file or package mixes unrelated concerns.
- **How:** move one cohesive group at a time. Keep a temporary re-export or alias at the old path while importers migrate, then remove it.
- **Watch out:** import-time side effects and initialization order; package-level visibility; public import paths that external consumers depend on.

---

## 5. Organizing data

### Encapsulate Variable / Encapsulate Field ★
- **Use when:** widely accessed mutable data needs controlled access. It is often the first step before moving or changing that data.

### Encapsulate Collection
- **Use when:** a getter returns an internal mutable collection.
- **How:** add `add` and `remove` methods, and return a read-only view or a copy.
- **Watch out:** callers that mutated the returned collection on purpose, and the cost of copying large collections.

### Replace Primitive with Object (value object)
- **Use when:** a primitive carries rules such as money with currency, email, ID, range or unit.
- **Watch out:** equality, hashing, serialization and database mapping all change. Keep the external representation identical.

### Replace Magic Literal with Named Constant
- **Use when:** an unexplained literal appears, especially when it repeats.
- **Watch out:** don't unify two equal literals that mean different things. They will need to diverge later.

### Change Reference to Value / Change Value to Reference
- **Use when:** an object should be compared by content and treated as immutable (to value), or one shared, updatable instance is needed (to reference).
- **Watch out:** identity checks, `equals` / `hashCode`, membership in sets and maps, and caching.

### Replace Derived Variable with Query
- **Use when:** a stored value can be computed from other state and risks drifting from it.
- **Watch out:** the computation cost on every read, and persisted copies that external readers rely on.

### Remove Setting Method
- **Use when:** a field should not change after construction.
- **Watch out:** frameworks that populate objects through setters or reflection (ORMs, deserializers, DI).

---

## 6. Simplifying conditionals

### Decompose Conditional ★ (via Extract Function)
- **Use when:** a complex condition or its branches are hard to read. Extract the condition and each branch into well-named functions.

### Consolidate Conditional Expression
- **Use when:** several checks lead to the same result. Combine them into one named predicate.
- **Watch out:** evaluation order and short-circuiting when the checks have side effects or can throw.

### Replace Nested Conditional with Guard Clauses
- **Use when:** special cases are buried in nesting. Return early for them so the normal path reads straight down.

```go
// before
func payout(e Employee) Money {
	var result Money
	if !e.Separated {
		if !e.Retired {
			result = normalPay(e)
		} else {
			result = retiredPay(e)
		}
	} else {
		result = separatedPay(e)
	}
	return result
}

// after
func payout(e Employee) Money {
	if e.Separated {
		return separatedPay(e)
	}
	if e.Retired {
		return retiredPay(e)
	}
	return normalPay(e)
}
```
- **Watch out:** cleanup or logging that ran at the single exit and now gets skipped. Use `defer`, `finally` or `using` if needed.

### Replace Conditional with Polymorphism
- **Use when:** the same switch on a type or kind appears in several places, or each branch is substantial.
- **How:** create a type per case, or a strategy behind an interface. Move one branch at a time into an override. Keep the original switch as the default until it's empty.
- **Watch out:** where the variant gets decided (a factory or deserialization now has to create the right subtype), and persisted type discriminators.

```java
// before: switch (bird.type) { case EUROPEAN: ...; case AFRICAN: ...; }
// after
sealed interface Bird permits European, African { double airspeed(); }
record European() implements Bird { public double airspeed() { return 35; } }
record African(int coconuts) implements Bird { public double airspeed() { return 40 - 2 * coconuts; } }
```

### Replace Conditional with Lookup Table
- **Use when:** each branch maps a key to a value or a handler with no extra logic. A map or dictionary is simpler than polymorphism here.
- **Watch out:** the old `default` branch and its behavior for unknown keys; whether matching was case-sensitive.

### Introduce Special Case (Null Object)
- **Use when:** many callers check for the same special value (null, "unknown customer") and react the same way.
- **Watch out:** callers that genuinely need to tell the special case apart.

### Introduce Assertion
- **Use when:** code silently assumes a condition holds. Make the assumption explicit.
- **Watch out:** an assertion that fails in production is a behavior change. Decide whether it's debug-only, or check that it can never fire for real data.

---

## 7. Inheritance and composition

### Pull Up Method / Pull Up Field / Pull Up Constructor Body
- **Use when:** subclasses duplicate a member. First make the duplicates identical, then move one copy up and delete the rest.

### Push Down Method / Push Down Field
- **Use when:** a superclass member is relevant to only some subclasses.

### Extract Superclass / Extract Interface
- **Use when:** several classes share behavior (superclass) or a role (interface). Prefer an interface when the classes share a contract but not an implementation.

### Collapse Hierarchy
- **Use when:** a subclass and its parent are no longer meaningfully different.

### Replace Type Code with Subclasses
- **Use when:** a type-code field drives behavior through conditionals. Often a precursor to Replace Conditional with Polymorphism.
- **Watch out:** persistence and deserialization have to map the stored code to the right subclass.

### Replace Subclass with Delegate / Replace Superclass with Delegate (composition over inheritance)
- **Use when:** inheritance is used for code reuse rather than "is-a", a class needs to vary along more than one axis, or a subclass refuses most of what it inherits.
- **Watch out:** code that type-checks against the old parent (`instanceof`, pattern matches, framework type scanning).

---

## 8. Removing code

### Remove Dead Code
- **Use when:** code is unreachable, unused or commented out. Version control remembers it.
- **How:** prove it's dead first, using the static search and the runtime checks in `finding-all-usages.md` ("Proving code is dead"). Delete it in its own commit so it's easy to revert.
- **Watch out:** reflection, plugin registries, scheduled jobs, CLI entry points, feature-flagged paths that are off today, and public API consumers that you can't see from this repo.

### Remove Unused Parameter ★
- **Use when:** a parameter is unused in every implementation.
- **Watch out:** interface implementations and callbacks whose signature is fixed by a framework; parameters passed by name.

### Inline Single-Use Abstraction
- **Use when:** an interface, factory or wrapper has exactly one implementation and no realistic second one (speculative generality).
- **Watch out:** a seam that tests rely on for substitution. Keep it if it is the only way to isolate a dependency in tests.
