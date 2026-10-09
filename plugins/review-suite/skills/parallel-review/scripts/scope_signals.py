#!/usr/bin/env python3
"""Summarize a review target and suggest reviewer personas.

Reads a list of changed (or in-scope) files and prints the target size, the
language mix, the path-based risk signals it found, and the personas those
signals suggest. The output is advisory: path names are a heuristic, so read
the code before trusting a signal or dismissing a missing one.

Accepted input, one entry per line (auto-detected):
  * plain paths            git diff --name-only BASE_SHA HEAD_SHA
                           gh pr diff 123 --name-only
                           git ls-files -- src/billing/
  * numstat lines          git diff --numstat BASE_SHA HEAD_SHA
    ("added<TAB>deleted<TAB>path"; binary files show "-")

Paths that git quoted (non-ASCII names, with the default core.quotePath) are
unquoted. Binary files and common asset types are counted but not treated as
reviewable source.

Usage:
  git diff --numstat BASE_SHA HEAD_SHA | python3 scope_signals.py -
  python3 scope_signals.py files.txt
  python3 scope_signals.py --json - < files.txt
  python3 scope_signals.py --selftest

Standard library only; Python 3.8+.
"""

import argparse
import json
import re
import sys
from collections import Counter, OrderedDict

# Each signal: regexes matched (case-insensitively) against the full path,
# the personas it suggests, and a one-line reason shown in the output.
# (?-i:...) switches case sensitivity back on for one group, which matters for
# naming conventions such as FooTest.java versus Latest.java.
SIGNALS = OrderedDict(
    [
        (
            "tests",
            {
                "patterns": [
                    r"(^|/)(tests?|specs?|__tests__|e2e|integration[-_]tests?)(/)",
                    r"(^|/)test_[^/]*\.py$",
                    r"_test\.(go|py|rb|exs?)$",
                    r"\.(test|spec)\.[cm]?[jt]sx?$",
                    r"_spec\.rb$",
                    r"(?-i:Tests?|Spec|(?<=[a-z0-9])IT)\.(java|kt|kts|cs|swift|php|scala|groovy)$",
                ],
                "personas": ["test-quality"],
                "reason": "test code changed",
            },
        ),
        (
            "docs",
            {
                "patterns": [r"\.(md|mdx|rst|adoc)$", r"(^|/)docs?/"],
                "personas": [],
                "reason": "documentation only",
            },
        ),
        (
            "ui",
            {
                "patterns": [
                    r"\.(tsx|jsx|vue|svelte|astro|html?|css|scss|sass|less)$",
                    r"\.(erb|twig|hbs|handlebars|njk|liquid|cshtml|razor|xib|storyboard)$",
                    r"(^|/)(components|views|templates|pages|screens|layouts|frontend|ui)/",
                ],
                "personas": ["ux-accessibility", "security"],
                "reason": "user-facing UI or templates (accessibility, output encoding)",
            },
        ),
        (
            "data",
            {
                "patterns": [
                    r"\.(sql|prisma|cql)$",
                    r"(^|/)(migrations?|migrate|alembic|flyway|liquibase|changelog|schema|db|database)(/)",
                    r"(^|/)(models?|entities|repositor(y|ies)|dao|persistence)(/)",
                    r"(^|/)schema\.(rb|graphql|prisma|sql)$",
                ],
                "personas": ["data-database", "performance"],
                "reason": "schema, migrations, models, or queries",
            },
        ),
        (
            "api",
            {
                "patterns": [
                    r"(openapi|swagger)[^/]*\.(ya?ml|json)$",
                    r"\.(proto|graphqls?|gql|avsc|thrift)$",
                    r"(^|/)(api|apis|routes?|controllers?|handlers?|endpoints?|resolvers?|rpc|contracts?|sdk|webhooks?)(/)",
                    r"(^|/)(events?|messages?|schemas?)(/)",
                ],
                "personas": ["api-compat", "security"],
                "reason": "endpoints, contracts, or message schemas consumed by others",
            },
        ),
        (
            "security-sensitive",
            {
                "patterns": [
                    # auth, authz, authorize, authorization, oauth; not author or authority.
                    r"(auth(?!or(?!i[sz]))|login|logout|session|token|jwt|oidc|saml|sso)",
                    r"(password|passwd|credential|secret|crypto|cipher|encrypt|signature|signing)",
                    r"(permission|acl|rbac|access[-_]?control|polic(y|ies)|entitlement|guards?(/|\.|$))",
                    r"(csrf|cors|sanitiz|upload)",
                ],
                "personas": ["security"],
                "reason": "authentication, authorization, crypto, or input-handling paths",
            },
        ),
        (
            "money",
            {
                "patterns": [
                    r"(payments?|pay(out|roll)s?|billing|invoic|ledger|refund|checkout|wallet)",
                    r"(charg(e|es|ing)|pric(e|es|ing)|currenc|money|(?<!syn)tax(?!on))",
                ],
                "personas": [
                    "correctness",
                    "security",
                    "data-database",
                    "reliability-operability",
                ],
                "reason": "money movement or pricing (rounding, double-charge, idempotency)",
            },
        ),
        (
            "dependencies",
            {
                "patterns": [
                    r"(^|/)(package(-lock)?\.json|yarn\.lock|pnpm-lock\.yaml|bun\.lockb?)$",
                    r"(^|/)(requirements[^/]*\.txt|pipfile(\.lock)?|poetry\.lock|pyproject\.toml|uv\.lock)$",
                    r"(^|/)(go\.(mod|sum)|cargo\.(toml|lock)|gemfile(\.lock)?|composer\.(json|lock))$",
                    r"(^|/)(pom\.xml|build\.gradle(\.kts)?|gradle\.lockfile|packages\.lock\.json)$",
                    r"(^|/)(package\.swift|package\.resolved|mix\.(exs|lock))$",
                    r"\.csproj$",
                ],
                "personas": ["security", "reliability-operability"],
                "reason": "dependency manifests or lockfiles (supply chain, upgrade risk)",
            },
        ),
        (
            "infra-config",
            {
                "patterns": [
                    r"(^|/)dockerfile[^/]*$",
                    r"(^|/)(docker-)?compose[^/]*\.ya?ml$",
                    r"\.(tf|tfvars|hcl)$",
                    r"(^|/)(helm|charts|k8s|kubernetes|deploy|deployment|infra|terraform|ansible)/",
                    r"(^|/)\.github/workflows/",
                    r"(^|/)(\.gitlab-ci\.yml|jenkinsfile|azure-pipelines\.yml)$",
                    r"(^|/)\.circleci/",
                    r"(^|/)\.env[^/]*$",
                    r"\.(ya?ml|toml|ini|conf|properties)$",
                ],
                "personas": ["reliability-operability", "security"],
                "reason": "build, deploy, CI, or runtime configuration",
            },
        ),
        (
            "async-jobs",
            {
                "patterns": [
                    r"(^|/)(jobs?|workers?|queues?|consumers?|producers?|subscribers?|listeners?)(/)",
                    r"(^|/)(schedulers?|cron|tasks?|batch|pipelines?|streams?)(/)",
                ],
                "personas": ["reliability-operability", "performance"],
                "reason": "background jobs, queues, or scheduled work",
            },
        ),
        (
            "caching",
            {
                "patterns": [r"(cache|caching|memoiz|memois)"],
                "personas": ["performance", "correctness"],
                "reason": "caching (staleness, invalidation, memory growth)",
            },
        ),
    ]
)

# Signals that make a small change risky enough to deserve more than one pass.
HIGH_RISK_SIGNALS = ("security-sensitive", "money", "data", "api", "dependencies")

PERSONA_ORDER = [
    "correctness",
    "security",
    "performance",
    "data-database",
    "architecture",
    "test-quality",
    "api-compat",
    "reliability-operability",
    "ux-accessibility",
]

# Counted in the totals but never treated as reviewable source.
ASSET_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".avif", ".ico", ".bmp", ".tiff",
    ".woff", ".woff2", ".ttf", ".otf", ".eot",
    ".mp3", ".mp4", ".wav", ".webm", ".mov",
    ".pdf", ".zip", ".gz", ".tgz", ".jar", ".bin",
}

# Thresholds used only for the advisory notes; tune per team if needed.
SMALL_FILES = 8
SMALL_LINES = 300
ARCH_FILES = 15
ARCH_TOP_DIRS = 3
SLICE_FILES = 60
SLICE_LINES = 3000

NUMSTAT_RE = re.compile(r"^(\d+|-)\t(\d+|-)\t(.+)$")
BRACE_RENAME_RE = re.compile(r"\{([^{}]*) => ([^{}]*)\}")
QUOTED_RE = re.compile(r'"((?:[^"\\]|\\.)*)"')
SIMPLE_ESCAPES = {"a": 7, "b": 8, "t": 9, "n": 10, "v": 11, "f": 12, "r": 13, '"': 34, "\\": 92}


def unquote_c_style(text):
    """Decode git's C-style quoting, e.g. "src/caf\\303\\251.py" -> src/café.py."""
    out = bytearray()
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "\\" and i + 1 < len(text):
            nxt = text[i + 1]
            octal = text[i + 1:i + 4]
            if len(octal) == 3 and all(c in "01234567" for c in octal):
                out.append(int(octal, 8))
                i += 4
                continue
            if nxt in SIMPLE_ESCAPES:
                out.append(SIMPLE_ESCAPES[nxt])
                i += 2
                continue
        out.extend(ch.encode("utf-8"))
        i += 1
    return out.decode("utf-8", "replace")


def unquote_path(path):
    """Unquote every quoted segment; renames quote old and new separately."""
    if '"' not in path:
        return path
    return QUOTED_RE.sub(lambda m: unquote_c_style(m.group(1)), path)


def resolve_rename(path):
    """Turn numstat rename notation into the new path.

    'src/{old => new}/f.py' -> 'src/new/f.py'; 'a.py => b.py' -> 'b.py'.
    """
    if "{" in path and " => " in path:
        path = BRACE_RENAME_RE.sub(lambda m: m.group(2), path)
        return path.replace("//", "/")
    if " => " in path:
        return path.split(" => ", 1)[1]
    return path


def parse(lines):
    entries = []  # (path, added or None, deleted or None, is_binary)
    for raw in lines:
        line = raw.rstrip("\n").rstrip("\r")
        if not line.strip():
            continue
        m = NUMSTAT_RE.match(line)
        if m:
            added = None if m.group(1) == "-" else int(m.group(1))
            deleted = None if m.group(2) == "-" else int(m.group(2))
            path = resolve_rename(unquote_path(m.group(3)))
            entries.append((path, added, deleted, added is None and deleted is None))
        else:
            entries.append((unquote_path(line.strip()), None, None, False))
    return entries


def extension(path):
    name = path.rsplit("/", 1)[-1]
    if "." not in name.lstrip("."):
        return "(none)"
    return "." + name.rsplit(".", 1)[-1].lower()


def top_dir(path):
    parts = path.split("/")
    return "/".join(parts[:2]) if len(parts) > 2 else parts[0] if len(parts) > 1 else "."


def classify(paths):
    compiled = {
        name: [re.compile(p, re.IGNORECASE) for p in spec["patterns"]]
        for name, spec in SIGNALS.items()
    }
    hits = OrderedDict((name, []) for name in SIGNALS)
    for path in paths:
        for name, regexes in compiled.items():
            if any(r.search(path) for r in regexes):
                hits[name].append(path)
    return hits


def summarize(entries):
    paths = [p for p, _, _, _ in entries]
    assets = {
        p for p, _, _, is_binary in entries
        if is_binary or extension(p) in ASSET_EXTENSIONS
    }
    hits = classify([p for p in paths if p not in assets])
    test_set = set(hits["tests"])
    # A path is "doc" only when no other signal claims it, so files such as
    # requirements.txt or docs/openapi.yaml still count as reviewable source.
    other = set()
    for name, files in hits.items():
        if name not in ("docs", "tests"):
            other.update(files)
    doc_set = set(hits["docs"]) - test_set - other
    source = [
        p for p in paths if p not in test_set and p not in doc_set and p not in assets
    ]

    has_numstat = any(a is not None or d is not None for _, a, d, _ in entries)
    added = sum(a or 0 for _, a, _, _ in entries)
    deleted = sum(d or 0 for _, _, d, _ in entries)
    changed_lines = added + deleted if has_numstat else None

    personas = OrderedDict()

    def suggest(persona, reason):
        personas.setdefault(persona, [])
        if reason not in personas[persona]:
            personas[persona].append(reason)

    if source:
        suggest("correctness", "source changed")
        suggest("test-quality", "source changed")
    for name, spec in SIGNALS.items():
        if hits[name] and name != "docs":
            for persona in spec["personas"]:
                suggest(persona, name)
    top_dirs = sorted({top_dir(p) for p in source})
    if len(source) >= ARCH_FILES or (
        len(top_dirs) >= ARCH_TOP_DIRS and len(source) >= ARCH_FILES // 2
    ):
        suggest(
            "architecture",
            "%d source files across %d areas" % (len(source), len(top_dirs)),
        )

    risky = [name for name in HIGH_RISK_SIGNALS if hits[name]]
    notes = []
    if paths and not source:
        notes.append(
            "Only docs, tests, or assets changed: a single pr-review pass is usually enough."
        )
    elif len(paths) <= SMALL_FILES and changed_lines is not None and changed_lines <= SMALL_LINES:
        if risky:
            notes.append(
                "Small but high-risk (%d file(s), %d lines; signals: %s): run a trimmed "
                "review, correctness plus the matching lanes, rather than a single pass."
                % (len(paths), changed_lines, ", ".join(risky))
            )
        else:
            notes.append(
                "Small change (%d file(s), %d lines) with no high-risk path signal: prefer "
                "one pr-review pass, after reading the code to confirm it is low-risk."
                % (len(paths), changed_lines)
            )
    if source and not test_set:
        notes.append(
            "No test files in the target: check whether this behavior is tested "
            "elsewhere; if not, it is a test gap."
        )
    if len(paths) > SLICE_FILES or (changed_lines or 0) > SLICE_LINES:
        notes.append(
            "Large target: slice the file list by subsystem and brief personas per slice."
        )
    if not has_numstat:
        notes.append("No line counts (plain path list); size notes are based on file count only.")

    ordered = OrderedDict(
        (p, personas[p]) for p in PERSONA_ORDER if p in personas
    )
    return {
        "files": len(paths),
        "source_files": len(source),
        "test_files": len(test_set),
        "doc_files": len(doc_set),
        "binary_or_asset_files": len(assets),
        "lines_added": added if has_numstat else None,
        "lines_deleted": deleted if has_numstat else None,
        "top_level_areas": top_dirs,
        "extensions": Counter(extension(p) for p in paths).most_common(),
        "signals": OrderedDict(
            (
                name,
                {
                    "count": len(files),
                    "reason": SIGNALS[name]["reason"],
                    "examples": files[:3],
                },
            )
            for name, files in hits.items()
            if files
        ),
        "suggested_personas": ordered,
        "notes": notes,
    }


def render_text(summary):
    out = []
    size = "%d file%s (%d source, %d test, %d doc, %d binary/asset)" % (
        summary["files"],
        "" if summary["files"] == 1 else "s",
        summary["source_files"],
        summary["test_files"],
        summary["doc_files"],
        summary["binary_or_asset_files"],
    )
    if summary["lines_added"] is not None:
        size += ", +%d/-%d lines" % (summary["lines_added"], summary["lines_deleted"])
    out.append("Target size: " + size)
    out.append(
        "Top-level areas: " + (", ".join(summary["top_level_areas"]) or "(none)")
    )
    out.append(
        "Extensions: "
        + ", ".join("%s %d" % (ext, n) for ext, n in summary["extensions"][:10])
    )
    out.append("")
    out.append("Signals:")
    if not summary["signals"]:
        out.append("  (none matched)")
    for name, info in summary["signals"].items():
        out.append("  %-19s %3d  %s" % (name, info["count"], info["reason"]))
        out.append("  %-19s      e.g. %s" % ("", ", ".join(info["examples"])))
    out.append("")
    out.append("Suggested personas, with the signals behind each (advisory):")
    if not summary["suggested_personas"]:
        out.append("  (none)")
    for persona, reasons in summary["suggested_personas"].items():
        out.append("  %-24s %s" % (persona, "; ".join(reasons)))
    if summary["notes"]:
        out.append("")
        out.append("Notes:")
        for note in summary["notes"]:
            out.append("  - " + note)
    return "\n".join(out)


def selftest():
    """Check the heuristics that are easiest to break when editing the regexes."""
    failures = []

    def expect(label, condition):
        if not condition:
            failures.append(label)

    def signals_for(path):
        return {name for name, files in classify([path]).items() if files}

    for path in ("src/authorization/policy.py", "src/middleware/Authorizer.java",
                 "lib/authorize.ts", "src/oauth/callback.go", "app/authz/rules.rb"):
        expect("security signal for " + path, "security-sensitive" in signals_for(path))
    for path in ("src/authors/list.py", "docs/authority.txt"):
        expect("no security signal for " + path, "security-sensitive" not in signals_for(path))
    for path in ("src/payments/charge.py", "src/ledger/entries.go", "app/pricing.ts"):
        expect("money signal for " + path, "money" in signals_for(path))
    for path in ("src/parser/syntax.py", "src/taxonomy/tree.py"):
        expect("no money signal for " + path, "money" not in signals_for(path))
    for path in ("src/Latest.kt", "src/Contest.java", "src/CREDIT.java"):
        expect("not a test: " + path, "tests" not in signals_for(path))
    for path in ("src/FooTest.kt", "src/FooTests.cs", "src/FooIT.java", "src/FooSpec.scala"):
        expect("is a test: " + path, "tests" in signals_for(path))

    entries = parse([
        '1\t0\t"src/caf\\303\\251.py"\n',
        '0\t0\t"src/a\\303\\251.py" => "src/b\\303\\250.py"\n',
        "-\t-\tassets/logo.png\n",
    ])
    expect("unquotes a quoted path", entries[0][0] == "src/café.py")
    expect("unquotes a quoted rename", entries[1][0] == "src/bè.py")
    expect("marks numstat binaries", entries[2][3] is True)
    summary = summarize(entries)
    expect("binary is not source", summary["source_files"] == 2)

    risky = summarize(parse(["40\t7\tsrc/auth_token.py\n", "5\t0\tdb/migrations/001.sql\n"]))
    expect("small high-risk change gets the trimmed-review note",
           any(n.startswith("Small but high-risk") for n in risky["notes"]))
    plain = summarize(parse(["10\t2\tsrc/utils/strings.py\n"]))
    expect("small low-risk change gets the single-pass note",
           any(n.startswith("Small change") for n in plain["notes"]))
    scattered = summarize(parse(["lib/a.py\n", "src/x/b.py\n", "src/y/c.py\n"]))
    expect("three one-file areas do not suggest architecture",
           "architecture" not in scattered["suggested_personas"])

    if failures:
        for label in failures:
            print("FAIL: " + label, file=sys.stderr)
        return 1
    print("selftest: all checks passed")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "input",
        nargs="?",
        help="file with one path or numstat line per line, or - for stdin",
    )
    parser.add_argument("--json", action="store_true", help="emit JSON")
    parser.add_argument(
        "--selftest", action="store_true", help="run the built-in heuristic checks and exit"
    )
    args = parser.parse_args(argv)

    if args.selftest:
        return selftest()
    if args.input is None:
        parser.error("an input file or - is required (or pass --selftest)")

    if args.input == "-":
        lines = sys.stdin.readlines()
    else:
        with open(args.input, encoding="utf-8") as handle:
            lines = handle.readlines()

    entries = parse(lines)
    if not entries:
        print("No paths on input; nothing to scope.", file=sys.stderr)
        return 1
    summary = summarize(entries)
    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print(render_text(summary))
    return 0


if __name__ == "__main__":
    sys.exit(main())
