# TDD in Go (`go test`)

The single-test command is in SKILL.md. This file covers idioms, a worked cycle, and tools for deterministic tests.

## Conventions that affect whether a test runs

- **Test files end in `_test.go`.** Test functions are `func TestXxx(t *testing.T)`, and the character after `Test` must not be a lowercase letter. A misnamed function silently isn't a test.
- **Prefer an external test package for behavior tests** (`package slug_test` beside `package slug`). It can only use exported identifiers, so the tests exercise the public interface, which keeps refactoring free. Use the same package only when you deliberately need internals.
- **Subtests.** `t.Run(name, ...)` subtests are selected with a slash path. Spaces in subtest names become underscores, but the `-run` pattern is not rewritten, so type the underscores yourself: `go test ./slug -run 'TestSlugify/collapses_repeated_separators' -v`.
- **Confirm your test actually ran.** Without `-v`, a passing package prints a single `ok` line with no test count, so SKILL.md's "the count rose by one" check doesn't work. Two silent passes to watch for:
  - A `-run` pattern that matches no top-level test prints `ok  <pkg>  0.00s [no tests to run]` and exits 0. Treat that as a red flag, not a pass.
  - A pattern whose subtest part matches nothing (a mistyped name, spaces instead of underscores) still runs the parent test with zero subtests, and it passes with a plain `ok`.

  During red, run with `-v` and check that `=== RUN   TestSlugify/collapses_repeated_separators` and its `--- FAIL` line appear.
- **The test cache isn't a red-step problem.** `go test` caches only passing results, keyed on the test binary, the flags, and the files and env vars the test reads. A new or edited test changes the binary, so it always runs. Use `-count=1` when a test depends on something the cache can't see, such as an external database or service.

## Worked cycle: `Slugify`

**Test list:**

- lowercases
- joins words with a hyphen
- collapses repeated separators
- trims separators at the ends
- treats punctuation as a separator
- empty input

**Cycle 1, red.** Write the first test. The function doesn't exist yet, so the first run is a compile error (`undefined: slug.Slugify`). That's "not yet" red. Add `func Slugify(s string) string { return "" }` and rerun. Now you get the right red: `Slugify("Hello") = "", want "hello"`.

**Cycle 1, green.** `return strings.ToLower(s)`.

**Cycles 2 to 5.** Each one adds a row to the table, watches that row fail, and then generalizes the code. The table grows one row per cycle:

```go
package slug_test

import (
	"testing"

	"example.com/project/slug"
)

func TestSlugify(t *testing.T) {
	tests := []struct {
		name string
		in   string
		want string
	}{
		{"lowercases words", "Hello", "hello"},
		{"joins words with a hyphen", "Hello World", "hello-world"},
		{"collapses repeated separators", "a  --  b", "a-b"},
		{"trims leading and trailing separators", "  Hi!  ", "hi"},
		{"treats punctuation as a separator", "rock&roll", "rock-roll"},
		{"empty input gives empty slug", "", ""},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if got := slug.Slugify(tt.in); got != tt.want {
				t.Errorf("Slugify(%q) = %q, want %q", tt.in, got, tt.want)
			}
		})
	}
}
```

**Refactor.** Once green, replace the chain of `strings.ReplaceAll` and `strings.Trim` calls that accumulated during the cycles with a single pass:

```go
package slug

import (
	"strings"
	"unicode"
)

func Slugify(s string) string {
	var b strings.Builder
	pendingSep := false
	for _, r := range strings.ToLower(s) {
		if unicode.IsLetter(r) || unicode.IsDigit(r) {
			if pendingSep && b.Len() > 0 {
				b.WriteByte('-')
			}
			pendingSep = false
			b.WriteRune(r)
			continue
		}
		pendingSep = true
	}
	return b.String()
}
```

The last row, empty input, passed the moment it was added. Per SKILL.md, prove it can fail before trusting it. Temporarily make `Slugify` return `"-"` when `s == ""`, watch that row go red, then revert.

## Idioms

- **Error messages.** Use `t.Errorf` to record a failure and keep going, which suits table rows. Use `t.Fatalf` when later lines would panic or mean nothing.
- **Message format.** Use `got, want` ordering, as in `Slugify(%q) = %q, want %q`. Name the input so the failure reads on its own.
- **Helpers.** Mark assertion helpers with `t.Helper()` so failures point at the caller's line.
- **Errors.** Compare with `errors.Is(err, ErrNotFound)` or `errors.As`, not string matching. Sentinel errors and error types are part of the contract. Message wording isn't.
- **Structs.** For a readable diff on mismatch, use `github.com/google/go-cmp/cmp`: `if diff := cmp.Diff(want, got); diff != "" { t.Errorf("mismatch (-want +got):\n%s", diff) }`. Use it only if the project already depends on it, or the team agrees to add it.
- **Isolation.** `t.TempDir()` gives a per-test directory. `t.Setenv` sets an env var for the test and restores it afterward. `t.Setenv` panics in a test that called `t.Parallel()`, which is a reminder that process-wide state and parallel tests don't mix.
- **Fuzzing for invariants.** Once examples pass, add a fuzz test for invariants, e.g. "a slug never contains `--` and never starts or ends with `-`." Write it as `func FuzzSlugify(f *testing.F)` and run it with `go test -fuzz=FuzzSlugify ./slug`. Saved failing inputs become permanent regression cases under `testdata/fuzz/`.

## Interfaces as seams, and fakes

Declare small interfaces where they are consumed, and fake them with plain structs:

```go
type Clock interface{ Now() time.Time }

type fixedClock struct{ t time.Time }

func (c fixedClock) Now() time.Time { return c.t }

type Notifier interface {
	Notify(ctx context.Context, userID, msg string) error
}

type fakeNotifier struct{ sent []string }

func (f *fakeNotifier) Notify(_ context.Context, userID, msg string) error {
	f.sent = append(f.sent, userID+": "+msg)
	return nil
}
```

Hand-written fakes like these are usually clearer than generated mocks. Reach for a mock generator only for wide interfaces you own, and then only to verify outgoing commands.

## Network

To test an HTTP client adapter, start a real local server:

```go
srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
	w.WriteHeader(http.StatusServiceUnavailable)
}))
defer srv.Close()

client := rates.NewClient(srv.URL)
_, err := client.Fetch(context.Background())
if !errors.Is(err, rates.ErrUnavailable) {
	t.Fatalf("Fetch() error = %v, want ErrUnavailable", err)
}
```

To test your own handlers without a socket, use `httptest.NewRequest` together with `httptest.NewRecorder`.

## Time and concurrency

- **Inject time where you can.** Pass a `Clock` or a `now func() time.Time` field. This works in every Go version and keeps the dependency visible.
- **Use `testing/synctest` (Go 1.25+, check the `go` line in `go.mod`) for code that calls `time.Now`, `time.Sleep`, timers, or tickers directly.** Inside `synctest.Test`, goroutines run in a "bubble" with a fake clock. The clock jumps forward only when every goroutine in the bubble is blocked, so a 30-minute sleep finishes instantly and deterministically. Call `synctest.Wait()` to let background goroutines in the bubble settle before asserting.

  ```go
  func TestSession_ExpiresAfterIdleTimeout(t *testing.T) {
  	synctest.Test(t, func(t *testing.T) {
  		s := session.New(30 * time.Minute)

  		time.Sleep(30*time.Minute + time.Second)
  		synctest.Wait()

  		if s.Active() {
  			t.Fatal("session still active after the idle timeout")
  		}
  	})
  }
  ```

  In Go 1.24 the package was experimental. It needed `GOEXPERIMENT=synctest` and had a different entry point, so don't use the 1.25 API on older toolchains.
- **Run concurrent code under `go test -race`.** The race detector only reports races that actually happen during the run, so pair it with tests that exercise the concurrent paths.
- **Never `time.Sleep` in a test to wait for a goroutine.** Synchronize on a channel, a `sync.WaitGroup`, or `synctest.Wait()`.

## Ordering and randomness

- **Map iteration order is randomized on purpose.** Sort keys before comparing, e.g. `slices.Sorted(maps.Keys(m))` (Go 1.23+), or compare as sets.
- **Shuffle test order.** `go test -shuffle=on ./...` runs tests in random order and prints the seed it used as a `-test.shuffle N` line. The line shows with `-v` or when the package fails. Replay the same order with `-shuffle=N`.
- **Inject randomness.** Pass a `*rand.Rand` built from a fixed seed (`math/rand/v2` has seeded sources such as `rand.NewPCG`) instead of calling package-level random functions.
