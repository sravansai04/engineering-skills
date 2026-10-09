# Memory Leaks and Unbounded Growth

Read this when memory keeps growing, a process gets OOM-killed after hours or days,
or resource counts (threads, goroutines, file handles, connections) climb over time.

## Contents
1. Confirm it is a leak
2. Managed heap or native memory?
3. The snapshot-diff method
4. Tools by stack
5. Common causes
6. Fix and prove

---

## 1. Confirm it is a leak

A leak is retained memory that keeps growing under a steady, repeating workload. Several
things look like leaks but are not:

- **Warm-up to a plateau:** caches, connection pools, and JIT code fill up, then stop
  growing.
- **Lazy garbage collection:** many runtimes grow the heap toward its configured
  maximum before collecting hard. High usage alone is not a leak.
- **Allocator retention:** after a spike, freed memory may not return to the OS, so
  resident memory stays high but stops growing.
- **Bounded caches** that are simply larger than expected.
- **Fragmentation:** resident memory above live data, usually stable over time.

Test it:

1. Drive a steady, repeatable workload: the same request or operation in a loop.
2. Sample two numbers over time: live heap after a garbage collection (if the runtime
   allows forcing or observing one) and resident memory (RSS).
3. Plot them. A leak grows roughly in proportion to the number of operations and never
   plateaus. Growth per operation (bytes per request) is the most useful number. It
   tells you how big the leaked object is and helps match it to a type in a heap
   snapshot.

Run many iterations so the leak dominates noise. A 2 KB-per-request leak is
invisible in 100 requests and obvious in 100,000.

## 2. Managed heap or native memory?

- If live heap grows: the leak is in managed objects. Use the snapshot-diff method
  (section 3).
- If live heap is flat but RSS grows: suspect native memory, such as native
  extensions, off-heap or direct buffers, memory-mapped files, thread stacks (thread
  count growing), or the allocator itself. Use native tools (section 4).
- If a resource count grows (threads, goroutines, file descriptors, sockets, DB
  connections), treat it as a leak of that resource. Find who creates it and which
  code path fails to release it. `lsof -p PID | wc -l` and the runtime's thread or
  goroutine dump are quick checks.

## 3. The snapshot-diff method

1. Warm up, then take heap snapshot A, after a GC if possible.
2. Run N more iterations of the workload.
3. Take snapshot B, again after a GC.
4. Compare B against A. Look for object types whose count grew in proportion to N.
   Ignore types that grew by a fixed amount.
5. For one leaked instance, follow its **retainer path**: the chain of references that
   keeps it alive, back to a GC root. The bug is in whoever holds that reference,
   usually a long-lived collection, registry, or closure. The allocation site only
   shows who created the object.

Taking a third snapshot after another N iterations, and confirming the same types
grew by the same amount again, separates real leaks from one-off growth.

## 4. Tools by stack

**JavaScript (Node.js and browsers)**
- Chrome DevTools Memory panel: take heap snapshots, then use the Comparison view, and
  the Retainers pane for one object. For Node, start with `node --inspect` and attach
  DevTools.
- Node can write snapshots without a debugger: `node --heapsnapshot-signal=SIGUSR2 app.js`
  then `kill -USR2 PID`, or call `v8.writeHeapSnapshot()` from code.
  `--heapsnapshot-near-heap-limit=N` captures snapshots automatically as the heap
  approaches its limit.
- In browsers, check for detached DOM nodes and listeners on removed elements.

**Python**
- `tracemalloc`: `tracemalloc.start(25)`, take a snapshot, run the workload, take
  another, then `snapshot2.compare_to(snapshot1, "lineno")` lists the growth by source
  line. You can also start it with `python -X tracemalloc=25`.
- `objgraph.show_growth()` lists object types whose counts grew.
  `objgraph.show_backrefs(obj)` draws who refers to an object.
- Native memory, including C extensions: `memray run script.py`, then
  `memray flamegraph` on the output file.

**JVM**
- Class histogram, twice, then compare: `jcmd PID GC.class_histogram`.
- Heap dump: `jcmd PID GC.heap_dump /tmp/heap.hprof`. On OOM, set
  `-XX:+HeapDumpOnOutOfMemoryError -XX:HeapDumpPath=/some/dir` ahead of time.
- Analyze dumps with Eclipse MAT (dominator tree, paths to GC roots) or a similar
  heap analyzer.
- Native memory: start with `-XX:NativeMemoryTracking=summary`, then
  `jcmd PID VM.native_memory summary`.

**Go**
- With `net/http/pprof` enabled, fetch `/debug/pprof/heap` twice and compare:
  `go tool pprof -base heap1.pb.gz heap2.pb.gz` (in-use space is the default view).
- Goroutine leaks: watch the count at `/debug/pprof/goroutine?debug=1`, which groups
  goroutines by stack, so the leaking stack shows up with a large, growing count. In
  tests, `go.uber.org/goleak` fails on leaked goroutines.

**C, C++, Rust**
- LeakSanitizer (included with `-fsanitize=address` on supported Linux targets)
  reports leaks at exit.
- `valgrind --leak-check=full ./prog` gives precise but slow reports. `heaptrack`
  profiles allocations with low overhead on Linux.
- macOS: `leaks PID`, or the Allocations and Leaks instruments in Instruments.
- Rust leaks are usually logical, not unsafe: reference-count cycles (`Rc`/`Arc` that
  need a `Weak`), collections that only grow, or intentional `Box::leak` and
  `mem::forget`.

**.NET**
- `dotnet-counters monitor -p PID` to watch GC heap size and gen-2 growth live.
- `dotnet-gcdump collect -p PID` twice and compare, or `dotnet-dump collect` for a
  full dump.

## 5. Common causes

- Caches or memoization keyed by unbounded input (IDs, URLs, user input) with no size
  limit or expiry.
- Event listeners, observers, subscriptions, or callbacks registered and never
  removed, especially on long-lived objects such as a global event bus, the DOM, or a
  singleton.
- Timers and intervals never cleared. Each one keeps its closure and everything that
  closure captures alive.
- Closures capturing a large object when only one field was needed.
- Static or global collections that only ever grow (registries, "seen" sets, debug
  buffers).
- Request-scoped data stored on long-lived singletons, or thread-local storage in
  pooled threads that is never cleared.
- Unclosed resources (files, sockets, DB cursors, streams, HTTP response bodies),
  often on the error path only.
- Tasks or goroutines blocked forever on a channel, lock, or future nobody will
  complete.
- Metrics or logging context with unbounded label cardinality.
- Hot reload or plugin systems that keep old class loaders or modules reachable.

## 6. Fix and prove

- Fix the retention, not the symptom. Bound the cache (size limit, LRU, TTL),
  unregister in the paired lifecycle hook (close, dispose, unsubscribe in a
  `finally`, `defer`, `using`, or `with` block), or use weak references where the
  semantics are truly "don't keep this alive".
- Restarting the process on a schedule, or raising the memory limit, is a mitigation.
  Label it as one and keep the bug open.
- Prove it with the same steady workload from section 1: memory now plateaus, and the
  snapshot diff no longer shows the type growing.
- Add a regression test where practical. Run the operation N times and assert that the
  relevant count (listeners, cache entries, goroutines, open handles) returns to its
  baseline. Counts are deterministic. Raw byte counts usually are not.
