#!/usr/bin/env python3
"""Measure how often a skill auto-triggers for a set of prompts.

Runs each prompt through a fresh, non-interactive Claude Code session
(`claude -p ... --output-format stream-json --verbose`) with the plugins under
test loaded via `--plugin-dir`, watches the event stream for the first `Skill`
tool call, and reports a per-prompt trigger rate against the expectation in
the cases file.

Every session runs with `--permission-mode dontAsk` (anything that would need
approval is refused), with Write, Edit, NotebookEdit and Bash removed, and
with `--strict-mcp-config` (your MCP servers stay off). Each run stops as soon
as a skill is chosen, so a run costs about one model turn.

Each session also writes a debug log, which the checker reads for Claude
Code's "Skill listing over budget" warning: when the listing of installed
skills is over budget, the descriptions of the least-used skills are dropped,
and a newly added skill is usually first to lose its description. The summary
says whether that happened, so a miss is not blamed on wording by mistake.

Cases file (JSON array). The canonical committed form is

    [{"query": "...", "should_trigger": true},
     {"query": "...", "should_trigger": false,
      "should_route_to": "workflow:pr-description"}]

The {"id", "prompt", "expect": "trigger"|"no-trigger"} form is accepted too.
`should_route_to` names the skill a near miss belongs to; a value starting
with "none" means no skill should be needed. A named sibling that is loaded
must fire in at least --min-hit-rate of the valid runs, or the case fails.

Scoring is conservative. A case needs at least two thirds of its requested
runs to finish (otherwise ERROR). Errored runs are counted both ways (as
fires and as misses); if the verdict depends on how they resolve, the case is
ERROR (inconclusive), never PASS.

Usage:

    python3 -I trigger_check.py \\
        --plugin-dir plugins/skill-dev --plugin-dir plugins/workflow \\
        --skill skill-dev:create-skill \\
        --cases evals/trigger-evals.json --runs 3

    python3 -I trigger_check.py --selftest   # no model calls, no cost

--selftest checks the scoring rules (errored runs, bare-name matches, routes,
listing-budget detection, exit codes, shell-safe --dry-run) by driving this
script against a fake `claude` executable written to a temp directory. Run it
after changing this file.

Exit codes: 0 every case passed and no run errored (or the self-test passed);
1 at least one case failed (or a self-test case failed); 2 setup problem (CLI
missing, bad cases file, skill not loaded); 3 no case failed but at least one
run errored (rerun before trusting it).

Standard library only. Requires the `claude` CLI on PATH (or --claude-bin),
except for --selftest and --dry-run.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

DISALLOWED_TOOLS = "Write,Edit,NotebookEdit,Bash"
BUDGET_RE = re.compile(r"Skill listing over budget: (\d+) skills, (\d+) chars > (\d+) budget")


@dataclass
class RunResult:
    fired: str | None = None          # skill id of the first Skill call, if any
    loaded_skills: list[str] = field(default_factory=list)
    saw_init: bool = False
    error: str | None = None
    over_budget: tuple[int, int, int] | None = None  # (skills, chars, budget)
    cost: float | None = None         # total_cost_usd, only when the run reached its result event


def build_command(args: argparse.Namespace, prompt: str, debug_file: str) -> list[str]:
    cmd = [
        args.claude_bin, "-p", prompt,
        "--output-format", "stream-json",
        "--verbose",
        "--max-turns", str(args.max_turns),
        "--no-session-persistence",
        "--permission-mode", "dontAsk",
        "--disallowedTools", DISALLOWED_TOOLS,
        "--debug-file", debug_file,
    ]
    if not args.with_user_mcp:
        cmd.append("--strict-mcp-config")
    for plugin_dir in args.plugin_dir:
        cmd += ["--plugin-dir", plugin_dir]
    if args.model:
        cmd += ["--model", args.model]
    return cmd


def build_env(args: argparse.Namespace) -> dict[str, str]:
    # Start each session as if from a plain shell, not as a child of the caller's session.
    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
    if args.listing_budget:
        env["SLASH_COMMAND_TOOL_CHAR_BUDGET"] = str(args.listing_budget)
    return env


def canonical(skill_id: str | None, loaded: list[str]) -> str | None:
    """Map a fired or expected id onto the loaded skill it means, if unambiguous.

    The model may invoke a plugin skill as "plugin:name" or as a bare "name".
    A bare name counts only when exactly one loaded skill has it; otherwise a
    personal or built-in skill of the same name could pass for the target.
    """
    if not skill_id:
        return None
    if skill_id in loaded:
        return skill_id
    bare = skill_id.split(":", 1)[-1]
    owners = [s for s in loaded if s.split(":", 1)[-1] == bare]
    if ":" not in skill_id and len(owners) == 1:
        return owners[0]
    return skill_id


def run_once(args: argparse.Namespace, prompt: str, cwd: str) -> RunResult:
    result = RunResult()
    log_dir = tempfile.mkdtemp(prefix="trigger-check-log-")
    debug_file = os.path.join(log_dir, "debug.log")
    stderr_file = tempfile.TemporaryFile(mode="w+")  # a file, not a pipe: no deadlock
    try:
        try:
            proc = subprocess.Popen(
                build_command(args, prompt, debug_file),
                cwd=cwd, env=build_env(args), text=True,
                stdin=subprocess.DEVNULL,  # otherwise -p waits a few seconds for piped input
                stdout=subprocess.PIPE, stderr=stderr_file,
            )
        except OSError as exc:
            result.error = f"could not start claude: {exc}"
            return result

        decided = False  # saw a Skill call or the final result event
        timer = threading.Timer(args.timeout, proc.kill)
        timer.start()
        try:
            assert proc.stdout is not None
            for line in proc.stdout:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                kind = event.get("type")
                if kind == "system" and event.get("subtype") == "init":
                    result.saw_init = True
                    result.loaded_skills = [str(s) for s in (event.get("skills") or [])]
                    if args.skill not in result.loaded_skills:
                        break  # setup problem; reported by the caller
                elif kind == "assistant":
                    for block in event.get("message", {}).get("content", []):
                        if block.get("type") == "tool_use" and block.get("name") == "Skill":
                            result.fired = str(block.get("input", {}).get("skill", ""))
                            break
                    if result.fired is not None:
                        decided = True
                        break  # the routing decision is made; stop spending tokens
                elif kind == "result":
                    decided = True
                    if isinstance(event.get("total_cost_usd"), (int, float)):
                        result.cost = float(event["total_cost_usd"])
                    break
        finally:
            timer.cancel()
            if proc.poll() is None:
                proc.kill()
            proc.wait()

        if not result.saw_init:
            stderr_file.seek(0)
            result.error = "no init event (timeout or CLI error). " + stderr_file.read()[-400:].strip()
        elif args.skill in result.loaded_skills and not decided:
            result.error = f"no routing decision within {args.timeout}s (timeout or crash)"
        try:
            with open(debug_file, encoding="utf-8", errors="replace") as handle:
                for log_line in handle:
                    match = BUDGET_RE.search(log_line)
                    if match:
                        result.over_budget = tuple(int(g) for g in match.groups())  # type: ignore[assignment]
                        break
        except OSError:
            pass
        return result
    finally:
        stderr_file.close()
        shutil.rmtree(log_dir, ignore_errors=True)


def load_cases(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as handle:
        cases = json.load(handle)
    if not isinstance(cases, list) or not cases:
        raise ValueError("cases file must be a non-empty JSON array")
    seen = set()
    for index, case in enumerate(cases):
        if not isinstance(case, dict):
            raise ValueError(f"case #{index} must be an object")
        if "prompt" not in case and "query" in case:
            case["prompt"] = case["query"]
        if "expect" not in case and isinstance(case.get("should_trigger"), bool):
            case["expect"] = "trigger" if case["should_trigger"] else "no-trigger"
        if not str(case.get("prompt", "")).strip():
            raise ValueError(f"case #{index} needs a non-empty 'prompt' or 'query'")
        if case.get("expect") not in ("trigger", "no-trigger"):
            raise ValueError(f"case #{index} needs 'expect' (trigger|no-trigger) or 'should_trigger' (true|false)")
        case.setdefault("id", f"case-{index + 1}")
        if case["id"] in seen:
            raise ValueError(f"duplicate case id {case['id']!r}")
        seen.add(case["id"])
    return cases


def score(case: dict, runs: list[RunResult], args: argparse.Namespace) -> dict:
    requested = args.runs
    valid = [r for r in runs if r.error is None]
    errored = requested - len(valid)
    hits = sum(1 for r in valid if canonical(r.fired, r.loaded_skills) == args.skill)
    others = Counter(
        canonical(r.fired, r.loaded_skills) for r in valid
        if r.fired and canonical(r.fired, r.loaded_skills) != args.skill
    )
    if case["expect"] == "trigger":
        best = (hits + errored) / requested >= args.min_hit_rate   # errored runs as fires
        worst = hits / requested >= args.min_hit_rate              # errored runs as misses
    else:
        best = hits / requested <= args.max_false_rate
        worst = (hits + errored) / requested <= args.max_false_rate
    if len(valid) < math.ceil(requested * 2 / 3):
        verdict = "ERROR"
    elif best and worst:
        verdict = "PASS"
    elif not best and not worst:
        verdict = "FAIL"
    else:
        verdict = "ERROR"

    route_text, route_ok = "-", True
    target = str(case.get("should_route_to") or "").strip()
    if case["expect"] == "no-trigger" and target and valid:
        if target.lower().startswith("none"):
            quiet = sum(1 for r in valid if not r.fired)
            route_text = f"none {quiet}/{len(valid)}"
        else:
            wanted = target.split()[0]
            loaded = valid[0].loaded_skills
            sibling = canonical(wanted, loaded)
            if sibling not in loaded:
                route_text = "n/a"  # sibling not loaded in this run
            else:
                routed = sum(1 for r in valid if canonical(r.fired, r.loaded_skills) == sibling)
                route_ok = routed / len(valid) >= args.min_hit_rate
                route_text = f"{routed}/{len(valid)}" + ("" if route_ok else " low")
    if verdict == "PASS" and not route_ok:
        verdict = "FAIL"

    return {
        "id": case["id"], "expect": case["expect"], "prompt": case["prompt"],
        "should_route_to": case.get("should_route_to"),
        "hits": hits, "runs": requested, "valid_runs": len(valid), "errored_runs": errored,
        "rate": round(hits / requested, 3), "verdict": verdict, "route": route_text,
        "other_skills": dict(others),
        "errors": [r.error for r in runs if r.error],
    }


def claude_version(binary: str) -> str:
    try:
        out = subprocess.run([binary, "--version"], capture_output=True, text=True, timeout=30,
                             stdin=subprocess.DEVNULL)
        return out.stdout.strip() or out.stderr.strip()
    except (OSError, subprocess.SubprocessError):
        return "unknown"


# --- self-test ----------------------------------------------------------------

# A stand-in for the `claude` CLI. It pops one scripted outcome per run from a
# queue file keyed by the prompt: "fire:<skill id>", "none" or "error", with an
# optional "+budget" suffix that writes the listing-over-budget debug line.
# Runs are sequential in the self-test (--jobs 1), so the queue needs no lock.
FAKE_CLAUDE = r'''
import json, os, sys
argv = sys.argv[1:]
if argv == ["--version"]:
    print("9.9.9 (fake)")
    sys.exit(0)
prompt = argv[argv.index("-p") + 1]
debug = argv[argv.index("--debug-file") + 1]
if "--permission-mode" not in argv or argv[argv.index("--permission-mode") + 1] != "dontAsk":
    sys.stderr.write("fake claude: expected --permission-mode dontAsk\n")
    sys.exit(1)
queue = os.environ["FAKE_QUEUE"]
with open(queue) as handle:
    plan = json.load(handle)
outcome = plan[prompt].pop(0)
with open(queue, "w") as handle:
    json.dump(plan, handle)
if outcome.endswith("+budget"):
    outcome = outcome[:-len("+budget")]
    with open(debug, "w") as log:
        log.write("[WARN] Skill listing over budget: 30 skills, 24000 chars > 8000 budget - descriptions will be truncated\n")
if outcome == "error":
    sys.stderr.write("simulated failure\n")
    sys.exit(1)
skills = os.environ["FAKE_SKILLS"].split(",")
print(json.dumps({"type": "system", "subtype": "init", "skills": skills}))
if outcome.startswith("fire:"):
    block = {"type": "tool_use", "name": "Skill", "input": {"skill": outcome[len("fire:"):]}}
    print(json.dumps({"type": "assistant", "message": {"content": [block]}}))
print(json.dumps({"type": "result", "total_cost_usd": 0.01}))
'''


def selftest() -> int:
    failures: list[str] = []
    total = 0

    def expect(label: str, condition: bool) -> None:
        nonlocal total
        total += 1
        if not condition:
            failures.append(label)

    # Unit checks on the pieces the scoring depends on.
    expect("a bare name maps to its only loaded owner",
           canonical("create-skill", ["skill-dev:create-skill"]) == "skill-dev:create-skill")
    expect("a bare name shared by two loaded skills stays ambiguous",
           canonical("create-skill", ["skill-dev:create-skill", "create-skill"]) == "create-skill")
    match = BUDGET_RE.search("Skill listing over budget: 25 skills, 16921 chars > 8000 budget")
    expect("the listing-budget line parses", bool(match) and match.groups() == ("25", "16921", "8000"))

    with tempfile.TemporaryDirectory(prefix="trigger-check-selftest-") as tmp:
        script = os.path.abspath(__file__)
        fake_py = os.path.join(tmp, "fake_claude.py")
        with open(fake_py, "w", encoding="utf-8") as handle:
            handle.write(FAKE_CLAUDE)
        fake = os.path.join(tmp, "claude")
        with open(fake, "w", encoding="utf-8") as handle:
            handle.write("#!/bin/sh\nexec %s -I %s \"$@\"\n" % (shlex.quote(sys.executable), shlex.quote(fake_py)))
        os.chmod(fake, 0o755)
        counter = [0]

        def run_checker(plan: dict, cases: list, runs: int = 3,
                        skills: str = "skill-dev:create-skill,workflow:pr-description") -> tuple:
            counter[0] += 1
            work = os.path.join(tmp, "run-%d" % counter[0])
            os.makedirs(work)
            queue = os.path.join(work, "queue.json")
            cases_path = os.path.join(work, "cases.json")
            out = os.path.join(work, "out.json")
            with open(queue, "w", encoding="utf-8") as handle:
                json.dump(plan, handle)
            with open(cases_path, "w", encoding="utf-8") as handle:
                json.dump(cases, handle)
            env = dict(os.environ, FAKE_QUEUE=queue, FAKE_SKILLS=skills)
            proc = subprocess.run(
                [sys.executable, "-I", script, "--plugin-dir", work, "--skill", "skill-dev:create-skill",
                 "--cases", cases_path, "--runs", str(runs), "--jobs", "1", "--claude-bin", fake,
                 "--cwd", work, "--json-out", out],
                capture_output=True, text=True, env=env, stdin=subprocess.DEVNULL, timeout=120)
            result = None
            if os.path.exists(out):
                with open(out, encoding="utf-8") as handle:
                    result = json.load(handle)
            return proc, result

        def verdicts(result) -> dict:
            return {c["id"]: c["verdict"] for c in (result or {}).get("cases", [])}

        proc, result = run_checker(
            {"p1": ["fire:skill-dev:create-skill"] * 3, "n1": ["none"] * 3, "p2": ["none"] * 3},
            [{"id": "p1", "prompt": "p1", "expect": "trigger"},
             {"id": "n1", "prompt": "n1", "expect": "no-trigger"},
             {"id": "p2", "prompt": "p2", "expect": "trigger"}])
        expect("clean runs pass and a missed trigger fails",
               verdicts(result) == {"p1": "PASS", "n1": "PASS", "p2": "FAIL"})
        expect("a failed case exits 1", proc.returncode == 1)

        proc, result = run_checker(
            {"p": ["fire:skill-dev:create-skill", "error", "error"], "n": ["none", "error", "none"]},
            [{"id": "p", "prompt": "p", "expect": "trigger"},
             {"id": "n", "prompt": "n", "expect": "no-trigger"}])
        expect("errored runs that could flip the verdict make it ERROR, never PASS",
               verdicts(result) == {"p": "ERROR", "n": "ERROR"})
        expect("inconclusive cases exit 3", proc.returncode == 3)

        proc, result = run_checker(
            {"p": ["fire:skill-dev:create-skill", "fire:create-skill", "error"]},
            [{"id": "p", "prompt": "p", "expect": "trigger"}])
        expect("one error that cannot flip the verdict still passes", verdicts(result) == {"p": "PASS"})
        expect("a pass with an errored run exits 3", proc.returncode == 3)

        proc, result = run_checker(
            {"p": ["fire:create-skill"] * 3}, [{"id": "p", "prompt": "p", "expect": "trigger"}],
            skills="skill-dev:create-skill,create-skill")
        expect("a bare name counts only when unique", verdicts(result) == {"p": "FAIL"})

        proc, result = run_checker(
            {"a": ["fire:workflow:pr-description"] * 3, "b": ["none"] * 3, "c": ["none"] * 3},
            [{"query": "a", "should_trigger": False, "should_route_to": "workflow:pr-description"},
             {"query": "b", "should_trigger": False, "should_route_to": "workflow:pr-description"},
             {"query": "c", "should_trigger": False, "should_route_to": "data-api:not-loaded"}])
        expect("a near miss must reach its loaded sibling",
               verdicts(result) == {"case-1": "PASS", "case-2": "FAIL", "case-3": "PASS"})
        expect("a sibling that is not loaded shows n/a",
               bool(result) and result["cases"][2]["route"] == "n/a")

        proc, result = run_checker(
            {"p": ["fire:skill-dev:create-skill+budget"] * 3}, [{"id": "p", "prompt": "p", "expect": "trigger"}])
        expect("an over-budget listing is reported", "OVER BUDGET" in proc.stdout)
        expect("the over-budget figures reach the JSON",
               bool(result) and result.get("over_budget") == [30, 24000, 8000])

        proc, _ = run_checker({"p": ["none"] * 3}, [{"id": "p", "prompt": "p", "expect": "trigger"}],
                              skills="create-skill")
        expect("a skill missing from the session is a setup error (exit 2)", proc.returncode == 2)
        expect("the setup error names a same-name skill that did load", "same name did load" in proc.stderr)

        cases_path = os.path.join(tmp, "dry.json")
        with open(cases_path, "w", encoding="utf-8") as handle:
            json.dump([{"prompt": "it's $HOME `x`", "expect": "trigger"}], handle)
        out = subprocess.run([sys.executable, "-I", script, "--plugin-dir", tmp, "--skill", "a:b",
                              "--cases", cases_path, "--dry-run"],
                             capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=60)
        expect("--dry-run quotes the prompt for the shell", "'it'\"'\"'s $HOME `x`'" in out.stdout)
        expect("--dry-run prints the session count", "planned sessions: 3" in out.stdout)

    for label in failures:
        print(f"FAIL {label}")
    print(f"selftest: {total - len(failures)}/{total} passed")
    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--plugin-dir", action="append",
                        help="plugin directory to load; repeat to load siblings as competitors (required)")
    parser.add_argument("--skill",
                        help="namespaced skill id to watch for, e.g. skill-dev:create-skill (required)")
    parser.add_argument("--cases", help="JSON array of test cases (required)")
    parser.add_argument("--selftest", action="store_true",
                        help="check the scoring rules against a fake claude CLI and exit (no model calls)")
    parser.add_argument("--runs", type=int, default=3, help="runs per prompt (default 3)")
    parser.add_argument("--jobs", type=int, default=4, help="parallel sessions (default 4)")
    parser.add_argument("--max-turns", type=int, default=3,
                        help="turn cap per run; leaves room for a look-around before routing")
    parser.add_argument("--timeout", type=int, default=180, help="seconds per run")
    parser.add_argument("--min-hit-rate", type=float, default=0.66,
                        help="should-trigger and should_route_to pass at or above this rate (default 0.66)")
    parser.add_argument("--max-false-rate", type=float, default=0.2,
                        help="should-not-trigger passes at or below this rate (default 0.2)")
    parser.add_argument("--model", help="model alias or id; match what contributors use")
    parser.add_argument("--cwd", help="directory to run sessions in (default: fresh empty temp dir); "
                        "use a small fixture project for skills whose trigger depends on the project")
    parser.add_argument("--listing-budget", type=int,
                        help="force the skill-listing budget (chars) via SLASH_COMMAND_TOOL_CHAR_BUDGET; "
                        "a large value shows every description, to separate wording from listing space")
    parser.add_argument("--with-user-mcp", action="store_true",
                        help="keep your configured MCP servers (default: --strict-mcp-config drops them)")
    parser.add_argument("--compare", metavar="BEFORE_JSON",
                        help="an earlier --json-out file; list cases whose verdict changed")
    parser.add_argument("--claude-bin", default="claude")
    parser.add_argument("--json-out", help="write the full results here as JSON")
    parser.add_argument("--dry-run", action="store_true",
                        help="print the command for the first case and the session count, then exit")
    args = parser.parse_args()

    if args.selftest:
        return selftest()
    if not (args.plugin_dir and args.skill and args.cases):
        parser.error("--plugin-dir, --skill and --cases are required (or pass --selftest)")
    if args.runs < 1:
        print("setup error: --runs must be at least 1", file=sys.stderr)
        return 2
    try:
        cases = load_cases(args.cases)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"setup error: {exc}", file=sys.stderr)
        return 2
    args.plugin_dir = [os.path.abspath(p) for p in args.plugin_dir]
    for plugin_dir in args.plugin_dir:
        if not os.path.isdir(plugin_dir):
            print(f"setup error: not a directory: {plugin_dir}", file=sys.stderr)
            return 2

    sessions = len(cases) * args.runs
    if args.dry_run:
        print(shlex.join(build_command(args, cases[0]["prompt"], "<per-run debug log>")))
        extra = f" SLASH_COMMAND_TOOL_CHAR_BUDGET={args.listing_budget}" if args.listing_budget else ""
        print(f"planned sessions: {sessions} ({len(cases)} cases x {args.runs} runs){extra}")
        return 0
    if shutil.which(args.claude_bin) is None:
        print(f"setup error: '{args.claude_bin}' not found on PATH", file=sys.stderr)
        return 2

    version = claude_version(args.claude_bin)
    cwd = args.cwd or tempfile.mkdtemp(prefix="trigger-check-")
    jobs = [(case, n) for case in cases for n in range(args.runs)]
    with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        outcomes = list(pool.map(lambda job: run_once(args, job[0]["prompt"], cwd), jobs))

    started = [o for o in outcomes if o.saw_init]
    missing = [o for o in started if args.skill not in o.loaded_skills]
    if missing:
        loaded = missing[0].loaded_skills
        bare = args.skill.split(":", 1)[-1]
        print(f"setup error: '{args.skill}' was not in the session's skill list.", file=sys.stderr)
        same_name = [s for s in loaded if s.split(":", 1)[-1] == bare]
        if same_name:
            print(f"a skill with the same name did load: {', '.join(same_name)} "
                  "(a personal or built-in skill, or a different plugin name?)", file=sys.stderr)
        print("loaded skills: " + ", ".join(loaded), file=sys.stderr)
        print("check the frontmatter, the directory name, the plugin name and the --plugin-dir path.",
              file=sys.stderr)
        return 2

    by_case: dict[str, list[RunResult]] = {case["id"]: [] for case in cases}
    for (case, _), outcome in zip(jobs, outcomes):
        by_case[case["id"]].append(outcome)

    report = [score(case, by_case[case["id"]], args) for case in cases]
    print(f"{'id':<12} {'expect':<11} {'hits':>5} {'err':>3}  {'verdict':<7} {'route':<10} other skills that fired")
    for row in report:
        others = ", ".join(f"{name} x{count}" for name, count in Counter(row["other_skills"]).most_common()) or "-"
        print(f"{row['id']:<12} {row['expect']:<11} {row['hits']:>2}/{row['runs']:<2} {row['errored_runs']:>3}  "
              f"{row['verdict']:<7} {row['route']:<10} {others}")
        for error in row["errors"]:
            print(f"{'':<12} run error: {error}")

    failures = sum(1 for row in report if row["verdict"] == "FAIL")
    inconclusive = sum(1 for row in report if row["verdict"] == "ERROR")
    run_errors = sum(row["errored_runs"] for row in report)
    print(f"\n{sum(r['verdict'] == 'PASS' for r in report)}/{len(report)} cases passed, "
          f"{failures} failed, {inconclusive} inconclusive, {run_errors} run errors "
          f"(runs per case: {args.runs}; sessions ran in {cwd}; {version})")

    budget_hits = [o.over_budget for o in outcomes if o.over_budget]
    forced = f" (budget forced to {args.listing_budget} chars)" if args.listing_budget else ""
    if budget_hits:
        skills, chars, budget = budget_hits[0]
        print(f"Listing{forced}: OVER BUDGET in {len(budget_hits)}/{len(started)} sessions ({skills} skills, "
              f"{chars} chars > {budget}). Claude Code dropped the descriptions of the least-used skills, "
              f"which can include {args.skill}. Before rewording, rerun failing should-trigger cases with "
              "--listing-budget 200000: if they pass then, the problem is listing space, not wording.")
    else:
        print(f"Listing{forced}: no over-budget warning in the debug logs.")

    priced = [o.cost for o in outcomes if o.cost is not None]
    if priced:
        print(f"Cost: ${sum(priced):.2f} across {len(priced)} sessions that ran to the end "
              f"(about ${sum(priced) / len(priced):.3f} each); {len(outcomes) - len(priced)} sessions "
              "stopped at a Skill call and report no cost, but cost about the same.")

    if args.compare:
        try:
            with open(args.compare, encoding="utf-8") as handle:
                before = {c["id"]: c["verdict"] for c in json.load(handle).get("cases", [])}
        except (OSError, ValueError, KeyError, AttributeError) as exc:
            print(f"compare: could not read {args.compare}: {exc}", file=sys.stderr)
        else:
            changed = [(r["id"], before[r["id"]], r["verdict"]) for r in report
                       if r["id"] in before and before[r["id"]] != r["verdict"]]
            if changed:
                print(f"Changed vs {args.compare}:")
                for case_id, old, new in changed:
                    tag = "REGRESSION" if old == "PASS" else ("fixed" if new == "PASS" else "changed")
                    print(f"  {case_id}: {old} -> {new} ({tag})")
            else:
                print(f"Changed vs {args.compare}: none")

    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as handle:
            json.dump({
                "skill": args.skill, "plugin_dirs": args.plugin_dir, "model": args.model,
                "cli_version": version, "runs": args.runs, "listing_budget": args.listing_budget,
                "over_budget_sessions": len(budget_hits),
                "over_budget": list(budget_hits[0]) if budget_hits else None,
                "cost_usd_priced_sessions": round(sum(priced), 4) if priced else None,
                "cases": report,
            }, handle, indent=2)

    if failures:
        return 1
    if inconclusive or run_errors:
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
