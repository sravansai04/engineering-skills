# Crashes Without a Usable Stack Trace

Read this when a process dies and leaves nothing that points at the cause: a
segfault or abort in native code, a process that is just "Killed", a container that
restarts with exit 137, a crash that happens only in the optimized release build, or
a production stack trace minified into meaningless names.

## Contents
1. Decode how the process died
2. Exit 137 or "Killed": check the OOM killer first
3. Get a backtrace from a native crash
4. Symbols: make addresses mean something
5. Crashes only in optimized (release) builds
6. Crash artifacts from managed runtimes
7. Minified JavaScript stacks
8. A trace shows where it died, not why

---

## 1. Decode how the process died

An exit status above 128 from a shell, CI job, or container usually means "killed by
signal N", where N is the status minus 128. `kill -l N` prints the signal's name.

| Status | Signal | Usual meaning |
|---|---|---|
| 134 | SIGABRT (6) | The program aborted itself: a failed `assert`, `abort()`, an uncaught C++ exception, heap corruption caught by the allocator ("double free", "corrupted size"), or a runtime giving up (Node.js running out of heap) |
| 137 | SIGKILL (9) | Killed from outside: the kernel OOM killer, a container memory limit, or a stop that escalated to KILL after a grace period. It can't be caught, so the process leaves no trace of its own |
| 139 | SIGSEGV (11) | Invalid memory access: a null or dangling pointer, an out-of-bounds write, or a stack overflow from deep recursion |
| 135 (Linux), 138 (macOS) | SIGBUS | Misaligned access, or a memory-mapped file truncated underneath the process |
| 136 | SIGFPE (8) | Integer division by zero |
| 143 | SIGTERM (15) | Asked to stop: a deploy, a scale-down, or a failed health check |

Some APIs report the signal as a negative number instead (a Python `subprocess`
return code of -11 is SIGSEGV). On Windows, an access violation shows up as exit
code 0xC0000005. The last lines logged before death and the exact time of death are
evidence too: line them up with deploys, memory graphs, and scheduled jobs.

A process that vanishes with no signal and no output was usually ended by code
(`exit()` deep in a library, an unhandled rejection policy). On Linux,
`strace -f -e trace=process,signal -p PID` shows which call exited, or which process
sent the signal.

## 2. Exit 137 or "Killed": check the OOM killer first

Before reading any code, find out who sent the KILL.

```bash
# Linux host or VM
dmesg -T | grep -iE 'out of memory|killed process'      # may need sudo
journalctl -k --since "2 hours ago" | grep -i oom
cat /sys/fs/cgroup/memory.events                         # cgroup v2, inside the container: oom_kill count

# Kubernetes: "Last State: Terminated, Reason: OOMKilled, Exit Code: 137"
kubectl describe pod POD
kubectl get pod POD -o jsonpath='{.status.containerStatuses[*].lastState.terminated.reason}'

# Docker
docker inspect --format '{{.State.OOMKilled}} {{.State.ExitCode}}' CONTAINER
```

If it was the OOM killer, the question becomes why memory went past the limit: a leak,
an unbounded batch or payload, or a limit set below the real working set. Continue
with `memory-leaks.md`. If it wasn't, look for whatever else sends KILL: a timeout
wrapper, a supervisor, a health check, or a person.

## 3. Get a backtrace from a native crash

The fastest route is often to run the reproduction under a debugger, which stops at
the crash and prints every thread's stack:

```bash
gdb -batch -ex run -ex 'thread apply all bt' --args ./prog ARGS
lldb --batch -o run -k 'bt all' -- ./prog ARGS        # -k runs only if the target crashes
```

When the crash only happens somewhere you can't attach a debugger, collect a core
dump: the process's memory at the moment it died.

```bash
ulimit -c unlimited                  # allow cores for processes started from this shell
cat /proc/sys/kernel/core_pattern    # Linux: where cores go; a "|...systemd-coredump" pipe means systemd keeps them

coredumpctl list                     # systemd-based Linux
coredumpctl info PID                 # signal, executable, and a short backtrace
coredumpctl debug PID                # open it in gdb (older versions call this "coredumpctl gdb")

gdb ./prog core                      # any core file, with the exact binary that crashed
(gdb) bt full                        # backtrace with local variables
(gdb) thread apply all bt            # every thread; one thread often corrupts what another crashes on
```

On macOS, `lldb ./prog -c /cores/core.PID` then `bt all` opens a core, but cores are
often disabled or restricted there. The system crash report usually has the crashing
thread's backtrace already: look in `~/Library/Logs/DiagnosticReports/` or in the
Console app. Inside containers, `core_pattern` belongs to the host, so a core may land
on the host or nowhere. Reproducing locally with the same image and cores enabled is
often quicker than chasing it.

## 4. Symbols: make addresses mean something

- A backtrace of `??` frames or bare hex addresses means the binary is stripped or its
  debug info is missing. `file ./prog` says "stripped" or "not stripped".
- Build with debug info at the *same* optimization level as the build that crashes
  (`-O2 -g`), plus `-fno-omit-frame-pointer` for reliable stack walking. `-g` is
  designed not to change the generated code, so the crash should survive it.
- Keep symbols for every build you ship, separately if size matters (split debug
  files, `.dSYM` bundles on macOS, PDB files on Windows), matched by build ID. Without
  them, a production crash address can't be resolved later.
- Resolve a single address with `addr2line -f -C -e ./prog ADDRESS` or
  `llvm-symbolizer`, or `atos -o PROG -l LOAD_ADDRESS ADDRESS` on macOS. For
  position-independent executables, subtract the load address first. A debugger
  reading a core does this for you.
- Rust: `RUST_BACKTRACE=1` (or `full`) prints a backtrace on panic. Go:
  `GOTRACEBACK=all` prints every goroutine on a fatal error, and `GOTRACEBACK=crash`
  also aborts so the OS can write a core.

## 5. Crashes only in optimized (release) builds

A crash that appears at `-O2` but never in a debug build almost always means undefined
behavior that the optimizer is allowed to exploit, or a data race whose timing changed.
A compiler bug is possible but rare. Usual causes: reading uninitialized memory,
out-of-bounds access, use after free, signed integer overflow, strict-aliasing
violations, a non-void function that falls off its end without returning, and relying
on unspecified evaluation order.

1. Rebuild at the failing optimization level with sanitizers:
   `-O2 -g -fno-omit-frame-pointer -fsanitize=address,undefined`. AddressSanitizer
   reports the bad access with the stacks that allocated and freed the memory.
   UBSan names the undefined operation and its line. The first report is usually the
   cause, even when it is far from where the release build crashed.
2. In separate builds (they don't combine with AddressSanitizer), run
   ThreadSanitizer (`-fsanitize=thread`) for races and, with Clang, MemorySanitizer
   (`-fsanitize=memory`) for uninitialized reads. MemorySanitizer needs every
   library instrumented to avoid false reports.
3. Turn on warnings the release flags may hide (`-Wall -Wextra`) and read every one on
   the crashing path.
4. Use diagnostic toggles as evidence, never as the fix. If `-fno-strict-aliasing` or
   `-fwrapv` makes the crash disappear, you have strong evidence of an aliasing
   violation or a signed overflow. Find that code and fix it.
5. Still suspect the compiler? Reduce the code to a small standalone file that behaves
   differently between optimization levels while the sanitizers stay clean
   (`cvise` or `creduce` automate the shrinking), then try another compiler version.

In Rust, a release-only crash nearly always points at `unsafe` code or a dependency's
native code. Run the tests under Miri (`cargo +nightly miri test`).

## 6. Crash artifacts from managed runtimes

Managed runtimes can write their own evidence when they die. Turn these on ahead of
time anywhere crashes recur.

| Runtime | How to get the evidence |
|---|---|
| Python | `python -X faulthandler` or `PYTHONFAULTHANDLER=1` prints the Python traceback of every thread on SIGSEGV, SIGFPE, SIGABRT, SIGBUS, and SIGILL. That shows which call into a native extension crashed |
| JVM | A fatal error writes `hs_err_pidNNNN.log` to the working directory (`-XX:ErrorFile=` sets the path). It names the crashing frame, native or Java. A Java `OutOfMemoryError` is an exception, not a crash: use the heap dump flags in `memory-leaks.md` |
| Node.js | `--report-on-fatalerror` writes a JSON diagnostic report (JavaScript and native stacks, heap statistics, resource usage) on fatal errors such as running out of heap. `--report-on-signal` writes one on demand |
| .NET | `DOTNET_DbgEnableMiniDump=1` writes a dump when the process crashes. Open it with `dotnet-dump analyze` |
| Go | `GOTRACEBACK`, as in section 4 |

## 7. Minified JavaScript stacks

A production stack such as `at e (main.4f9c1.js:1:20934)` can only be read through the
source map from that exact build.

- Upload source maps for every release to the error tracker, matched by release or
  build hash, and it will translate stacks automatically.
- By hand, the `source-map` npm library (`SourceMapConsumer`) maps each line and
  column through the `.map` file back to the original file, line, and function name.
  Browser DevTools apply source maps on their own when they can fetch them.
- A map from a different build gives confident, wrong answers. Check that the bundle
  hash in the stack matches the map's file name.
- For Node.js services, `node --enable-source-maps` makes runtime stack traces use the
  original source locations.

## 8. A trace shows where it died, not why

A segfault inside `free()` usually means the heap was corrupted much earlier. An abort
in an assertion means an invariant broke upstream. Take the first frame in the
project's own code, then return to Step 3 of the main workflow and form hypotheses
about how the bad state got there. Memory corruption often crashes far from the bug,
which is why a sanitizer report (section 5) is worth more than the crash site.
