#!/usr/bin/env python3
"""Static checks for a skill directory, with no third-party dependencies.

Use it next to (never instead of) the repository's own validator and
`claude plugin validate`. It catches the mistakes that make a skill fail to
load, fail to route, leak private context, or work in only one agent, before
any paid test runs. Skills follow the open Agent Skills standard
(agentskills.io), so the same folder loads in Claude Code and in other agents.

Checks, per skill directory:

  errors    frontmatter that will not parse; with --portable, a top-level
            frontmatter field outside the Agent Skills standard (name,
            description, license, compatibility, metadata, allowed-tools),
            such as argument-hint or when_to_use; a missing or invalid `name` (lowercase letters,
            digits and single hyphens, 1-64 chars, equal to the directory
            name, no "anthropic" or "claude"); a missing or over-long
            `description` (1-1024 chars); a `compatibility` over 500 chars;
            XML-like tags in name or description; the dollar-sign ARGUMENTS
            placeholder in SKILL.md or references/ (only Claude Code
            substitutes it); the skill-dir variable used in the SKILL.md body,
            references/ or scripts/ while SKILL.md lacks the sentence that
            explains it to other agents; a markdown link in SKILL.md that
            points at a missing file; a file under references/ that SKILL.md
            never mentions; a hit for any --deny pattern
  warnings  without --portable, a frontmatter field outside the standard
            (Claude Code-only keys such as disable-model-invocation or paths
            are fine in a skill that only ever runs in Claude Code); description
            over --max-desc chars (the shared listing budget); description +
            when_to_use over 1,536 chars; SKILL.md at 500+ lines;
            YAML that only lenient parsers accept; the skill-dir variable used
            before its explanation sentence, or the sentence repeated;
            skill-dir variables inside shell blocks of reference files
            (only SKILL.md gets them substituted); unescaped $0-$9 in SKILL.md
            (replaced by arguments); bundled scripts SKILL.md never mentions;
            eval files that do not follow the canonical names; behavior evals
            without a list of 3-6 checkable `expectations`; stray hidden or
            cache directories; private-looking strings (home paths, internal
            hostnames, private IPs, key or token shapes)

With --listing ROOT it also totals the description text of every
ROOT/plugins/*/skills/*/SKILL.md, because Claude Code drops descriptions
(least-used skills first) once the combined listing exceeds its budget.

Usage:
    python3 -I check_skill.py plugins/<plugin>/skills/<name> [more skill dirs]
    python3 -I check_skill.py <skill-dir> --deny 'acme|internal-tool-name'
    python3 -I check_skill.py <skill-dir> --portable   # for a skill meant for any agent
    python3 -I check_skill.py --listing .
    python3 -I check_skill.py --selftest

Exit codes: 0 no errors (or the self-test passed), 1 at least one error (or
a self-test case failed), 2 usage problem.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
XML_TAG_RE = re.compile(r"</?[A-Za-z][^<>]*>")
KEY_RE = re.compile(r"^([A-Za-z0-9_][A-Za-z0-9_-]*):(\s.*|)$")
MD_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
TICK_PATH_RE = re.compile(r"`((?:references|scripts|assets)/[^`\s]+)`")
SKILL_VAR_RE = re.compile(r"\$\{CLAUDE_(?:SKILL_DIR|PLUGIN_ROOT|PLUGIN_DATA|PROJECT_DIR)\}")
POSITIONAL_RE = re.compile(r"(?<!\\)\$[0-9]")
# The all-caps arguments placeholder, written so this file never contains it.
ARGS_PLACEHOLDER_RE = re.compile(r"[$]ARGUMENTS")
SHELL_FENCES = {"bash", "sh", "shell", "zsh", "console", "terminal"}

# The top-level frontmatter fields of the open Agent Skills standard
# (agentskills.io). Claude Code reads more (argument-hint, when_to_use,
# disable-model-invocation, paths, ...), but other agents ignore or reject
# them, so a portable skill uses only these.
SPEC_KEYS = ("name", "description", "license", "compatibility", "metadata", "allowed-tools")
# Documented Claude Code skill frontmatter outside the standard. Valid in a skill
# that only ever runs in Claude Code (disable-model-invocation is a real safety
# control there), so these warn unless --portable asks for the standard alone.
CLAUDE_CODE_KEYS = {
    "when_to_use", "argument-hint", "arguments", "disable-model-invocation",
    "user-invocable", "disallowed-tools", "model", "effort", "context", "agent",
    "background", "hooks", "paths", "shell",
}
MAX_COMPATIBILITY = 500

# The sentence that explains the skill-dir variable to agents that do not
# substitute it. Built in pieces so this file never contains the variable.
SKILL_DIR_TOKEN = "${" + "CLAUDE_SKILL_DIR}"
SKILL_DIR_SENTENCE = ("`" + SKILL_DIR_TOKEN + "` stands for this skill's folder, the directory that contains "
                      "this SKILL.md. Claude Code fills it in; in other tools, use that folder's path.")
SKILL_DIR_SENTENCE_RE = re.compile(
    r"`?" + re.escape(SKILL_DIR_TOKEN) + r"`?\s+"
    + r"\s+".join(re.escape(word) for word in SKILL_DIR_SENTENCE.split()[1:]))

# Patterns are written so that this file does not match itself.
PRIVATE_PATTERNS = [
    ("absolute home path", re.compile(r"/Users/[A-Za-z][\w.-]*/|/home/[a-z][\w.-]*/|[A-Za-z]:\\{1,2}Users\\{1,2}[A-Za-z][\w.-]*")),
    ("home-relative path", re.compile(r"(?<![\w.])~/(?!\.)[\w-][\w.-]*(?:/[\w.-]+)*")),
    ("internal hostname", re.compile(r"\b[a-z0-9-]+(?:\.[a-z0-9-]+)*\.(?:internal|corp|intranet|lan)\b|https?://[a-z0-9.-]+\.local\b", re.I)),
    ("private IP address", re.compile(r"\b(?:10\.\d{1,3}\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3}|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})\b")),
    ("private key block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("token-shaped string", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9_-]{20,}|AKIA[0-9A-Z]{16}|xox[abprs]-[A-Za-z0-9-]{10,})")),
    ("credential assignment", re.compile(r"(?i)\b(?:api[_-]?key|secret|token|password)\b\s*[:=]\s*['\"]?[A-Za-z0-9_\-/+]{16,}")),
]
# Example usernames that are clearly placeholders, not someone's real home.
PLACEHOLDER_HOME_RE = re.compile(r"(?:/Users/|/home/|Users\\{1,2})(?:me|you|user|username|dev|developer|alice|bob|example|runner|name|jane|john)\b", re.I)
SKIP_DIRS = {".git", "__pycache__", "node_modules", "results"}


class Report:
    def __init__(self, root: str) -> None:
        self.root = root
        self.items: list[tuple[str, str, str]] = []

    def add(self, level: str, where: str, message: str) -> None:
        self.items.append((level, where, message))

    def count(self, level: str) -> int:
        return sum(1 for item in self.items if item[0] == level)


# --- frontmatter --------------------------------------------------------------

def split_frontmatter(text: str) -> tuple[list[str] | None, int]:
    """Return (frontmatter lines, index of the closing line) or (None, 0)."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None, 0
    for index in range(1, len(lines)):
        if lines[index].strip() in ("---", "..."):
            return lines[1:index], index
    return None, 0


def unquote_double(raw: str) -> tuple[str | None, str]:
    """Parse a double-quoted scalar at the start of raw; return (value, rest)."""
    out, i = [], 1
    escapes = {"n": "\n", "t": "\t", '"': '"', "\\": "\\", "/": "/", " ": " "}
    while i < len(raw):
        ch = raw[i]
        if ch == "\\" and i + 1 < len(raw):
            out.append(escapes.get(raw[i + 1], "\\" + raw[i + 1]))
            i += 2
            continue
        if ch == '"':
            return "".join(out), raw[i + 1:]
        out.append(ch)
        i += 1
    return None, ""


def unquote_single(raw: str) -> tuple[str | None, str]:
    out, i = [], 1
    while i < len(raw):
        if raw[i] == "'":
            if raw[i + 1:i + 2] == "'":
                out.append("'")
                i += 2
                continue
            return "".join(out), raw[i + 1:]
        out.append(raw[i])
        i += 1
    return None, ""


def parse_frontmatter(lines: list[str], report: Report) -> dict[str, object]:
    """Parse the flat key: value subset that skill frontmatter uses."""
    data: dict[str, object] = {}
    i = 0
    while i < len(lines):
        line, lineno = lines[i], i + 2  # +2: the opening '---' is line 1
        if not line.strip() or line.lstrip().startswith("#"):
            i += 1
            continue
        if line[0] in " \t":
            report.add("ERROR", f"SKILL.md:{lineno}", "indented line where a new 'key: value' was expected")
            i += 1
            continue
        match = KEY_RE.match(line)
        if not match:
            report.add("ERROR", f"SKILL.md:{lineno}", f"not a 'key: value' line: {line[:60]!r}")
            i += 1
            continue
        key, rest = match.group(1), match.group(2).strip()
        cont: list[str] = []
        j = i + 1
        while j < len(lines) and (lines[j][:1] in (" ", "\t") or not lines[j].strip()):
            if lines[j][:1] == "\t":
                report.add("ERROR", f"SKILL.md:{j + 2}", "tab used for indentation (YAML forbids tabs)")
            cont.append(lines[j])
            j += 1
        while cont and not cont[-1].strip():
            cont.pop()
        if key in data:
            report.add("ERROR", f"SKILL.md:{lineno}", f"duplicate key '{key}'")
        data[key] = parse_value(key, rest, cont, lineno, report)
        i = j
    return data


def parse_value(key: str, rest: str, cont: list[str], lineno: int, report: Report) -> object:
    where = f"SKILL.md:{lineno}"
    if rest == "" and cont:
        items = [c.strip() for c in cont if c.strip()]
        if all(item.startswith("- ") or item == "-" for item in items):
            return [item[1:].strip() for item in items]
        return "\n".join(cont)  # nested mapping (hooks, metadata): keep raw
    if rest[:1] in ("|", ">"):
        body = [c.strip() for c in cont]
        if rest[0] == "|":
            return "\n".join(body)
        paragraphs, current = [], []
        for part in body:
            if part:
                current.append(part)
            else:
                paragraphs.append(" ".join(current))
                current = []
        paragraphs.append(" ".join(current))
        return "\n".join(p for p in paragraphs if p)
    joined = " ".join([rest] + [c.strip() for c in cont if c.strip()])
    if rest[:1] == '"':
        value, tail = unquote_double(joined)
    elif rest[:1] == "'":
        value, tail = unquote_single(joined)
    else:
        value, tail = None, ""
    if rest[:1] in ('"', "'"):
        if value is None:
            report.add("ERROR", where, f"'{key}': quoted value is never closed")
            return ""
        if tail.strip() and not tail.strip().startswith("#"):
            report.add("ERROR", where, f"'{key}': text after the closing quote: {tail.strip()[:40]!r}")
        return value
    if rest[:1] in ("[", "{"):
        if joined.count(rest[0]) != joined.count("]" if rest[0] == "[" else "}"):
            report.add("ERROR", where, f"'{key}': unbalanced flow collection")
        return joined
    if rest[:1] in ("*", "&", "!", "%", "@", "`"):
        report.add("ERROR", where, f"'{key}': a plain value cannot start with {rest[0]!r}; quote it")
    if re.search(r":\s", joined):
        report.add("WARN", where, f"'{key}': unquoted value contains ': '; strict YAML parsers reject it, so quote the value")
    if " #" in joined:
        report.add("WARN", where, f"'{key}': ' #' starts a YAML comment; everything after it is dropped")
        joined = joined.split(" #", 1)[0].rstrip()
    return joined


# --- per-skill checks ---------------------------------------------------------

def read_text(path: str) -> str | None:
    try:
        if os.path.getsize(path) > 1_000_000:
            return None
        with open(path, encoding="utf-8") as handle:
            return handle.read()
    except (OSError, UnicodeDecodeError):
        return None


def iter_files(root: str):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and not d.startswith("."))
        for name in sorted(filenames):
            yield os.path.join(dirpath, name)


def check_frontmatter(skill_dir: str, text: str, report: Report, portable: bool = False) -> dict[str, object]:
    fm_lines, _ = split_frontmatter(text)
    if fm_lines is None:
        report.add("ERROR", "SKILL.md:1", "no frontmatter: the file must start with '---' and close it with '---'")
        return {}
    data = parse_frontmatter(fm_lines, report)
    dir_name = os.path.basename(os.path.abspath(skill_dir))

    level = "ERROR" if portable else "WARN"
    scope = ("" if portable else
             "; fine in a skill that only runs in Claude Code, and an error with --portable")
    for key in data:
        if key in SPEC_KEYS:
            continue
        if key == "argument-hint":
            report.add(level, "SKILL.md", "'argument-hint' is a Claude Code autocomplete hint, not an Agent Skills field; "
                       f"other agents ignore it and skills-ref rejects it, so say in the body what the skill's arguments are{scope}")
        elif key in CLAUDE_CODE_KEYS:
            report.add(level, "SKILL.md", f"'{key}' is Claude Code-only, not an Agent Skills frontmatter field "
                       f"(allowed: {', '.join(SPEC_KEYS)}); other agents ignore it and skills-ref rejects it, "
                       f"so a portable skill carries its intent in the body{scope}")
        else:
            report.add(level, "SKILL.md", f"'{key}' is not an Agent Skills frontmatter field "
                       f"(allowed: {', '.join(SPEC_KEYS)}) nor a documented Claude Code key; check the spelling{scope}")

    name = data.get("name")
    if not isinstance(name, str) or not name:
        report.add("ERROR", "SKILL.md", "missing 'name'")
    else:
        if not NAME_RE.match(name):
            report.add("ERROR", "SKILL.md", f"name {name!r}: use lowercase letters, digits and single hyphens, no leading or trailing hyphen")
        if len(name) > 64:
            report.add("ERROR", "SKILL.md", f"name is {len(name)} chars (limit 64)")
        if name != dir_name:
            report.add("ERROR", "SKILL.md", f"name {name!r} differs from the directory name {dir_name!r}")
        for word in ("anthropic", "claude"):
            if word in name:
                report.add("ERROR", "SKILL.md", f"name contains the reserved word {word!r}; the Claude API rejects it on upload")
        if XML_TAG_RE.search(name):
            report.add("ERROR", "SKILL.md", "name contains an XML-like tag")

    desc = data.get("description")
    if not isinstance(desc, str) or not desc.strip():
        report.add("ERROR", "SKILL.md", "missing or empty 'description'")
        desc = ""
    else:
        if len(desc) > 1024:
            report.add("ERROR", "SKILL.md", f"description is {len(desc)} chars (limit 1024)")
        tag = XML_TAG_RE.search(desc)
        if tag:
            report.add("ERROR", "SKILL.md", f"description contains an XML-like tag {tag.group(0)!r}; placeholders such as <plugin> count, so reword them")
    compat = data.get("compatibility")
    if isinstance(compat, str) and len(compat) > MAX_COMPATIBILITY:
        report.add("ERROR", "SKILL.md", f"compatibility is {len(compat)} chars (limit {MAX_COMPATIBILITY})")
    when = data.get("when_to_use")
    combined = len(desc) + (len(when) if isinstance(when, str) else 0)
    if combined > 1536:
        report.add("WARN", "SKILL.md", f"description + when_to_use is {combined} chars; Claude Code cuts the listing entry at 1,536")
    return data


def mentioned_paths(text: str) -> set[str]:
    found = set()
    for target in MD_LINK_RE.findall(text):
        if "://" in target or target.startswith(("#", "mailto:")):
            continue
        found.add(os.path.normpath(target.split("#", 1)[0]))
    for target in TICK_PATH_RE.findall(text):
        found.add(os.path.normpath(target.rstrip(".,;:)")))
    return found


def strip_code(text: str) -> str:
    """Blank out fenced code blocks and inline code spans, which are examples, not links."""
    out, fence = [], None
    for line in text.split("\n"):
        mark = re.match(r"^\s*(`{3,}|~{3,})", line)
        if fence is None and mark:
            fence = mark.group(1)
            out.append("")
            continue
        if fence is not None:
            if mark and mark.group(1)[0] == fence[0] and len(mark.group(1)) >= len(fence) and not line.strip()[len(mark.group(1)):]:
                fence = None
            out.append("")
            continue
        out.append(re.sub(r"(`+)(.+?)\1", lambda m: " " * len(m.group(0)), line))
    return "\n".join(out)


def check_links(skill_dir: str, text: str, report: Report) -> None:
    for target in MD_LINK_RE.findall(strip_code(text)):
        if "://" in target or target.startswith(("#", "mailto:")) or "<" in target:
            continue
        path = target.split("#", 1)[0]
        if path and not os.path.exists(os.path.join(skill_dir, path)):
            report.add("ERROR", "SKILL.md", f"link target does not exist: {path}")
    for target in TICK_PATH_RE.findall(text):
        path = target.rstrip(".,;:)")
        if "<" in path or "*" in path or os.path.exists(os.path.join(skill_dir, path)):
            continue
        level = "ERROR" if path.startswith("references/") else "WARN"
        note = "" if level == "ERROR" else " (ignore if it names a repository-level path)"
        report.add(level, "SKILL.md", f"mentioned path does not exist in the skill: {path}{note}")

    mentioned = mentioned_paths(text)
    for sub, level in (("references", "ERROR"), ("scripts", "WARN")):
        base = os.path.join(skill_dir, sub)
        if not os.path.isdir(base):
            continue
        for path in iter_files(base):
            rel = os.path.relpath(path, skill_dir)
            if sub == "scripts" and (os.path.basename(rel).startswith("test_") or rel.endswith((".json", ".pyc"))):
                continue
            if sub == "references" and rel.count(os.sep) > 1:
                report.add("WARN", rel, "nested reference file; keep references one level deep so readers can find every rule from SKILL.md")
            if os.path.normpath(rel) not in mentioned and rel.replace(os.sep, "/") not in text:
                report.add(level, rel, "never mentioned in SKILL.md; link it with a note on when to read or run it")


def check_markdown_bodies(skill_dir: str, skill_text: str, report: Report) -> None:
    lines = skill_text.splitlines()
    _, close = split_frontmatter(skill_text)
    for index, line in enumerate(lines[close + 1:], start=close + 2):
        if POSITIONAL_RE.search(line):
            report.add("WARN", f"SKILL.md:{index}", "unescaped $0-$9 is replaced by a skill argument; move shell snippets with positional parameters to scripts/ or write \\$1")
    if len(lines) >= 500:
        report.add("WARN", "SKILL.md", f"{len(lines)} lines; keep SKILL.md under 500 and move depth to references/")

    for path in iter_files(skill_dir):
        rel = os.path.relpath(path, skill_dir)
        if not rel.endswith(".md") or rel == "SKILL.md":
            continue
        text = read_text(path)
        if text is None:
            continue
        open_fence: tuple[str, int, bool] | None = None  # (char, length, is_shell)
        for number, line in enumerate(text.splitlines(), start=1):
            fence = re.match(r"^\s*(`{3,}|~{3,})\s*([\w-]*)\s*$", line)
            if fence:
                marker, info = fence.group(1), fence.group(2).lower()
                if open_fence is None:
                    open_fence = (marker[0], len(marker), info in SHELL_FENCES)
                elif marker[0] == open_fence[0] and len(marker) >= open_fence[1] and not info:
                    open_fence = None
                continue
            if open_fence and open_fence[2] and SKILL_VAR_RE.search(line) and "not a shell variable" not in text:
                report.add("WARN", f"{rel}:{number}", "skill-dir variables are substituted only in SKILL.md (and allowed-tools); in a reference file this command expands to an empty path. Use a placeholder and let SKILL.md supply the resolved path")
        head = "\n".join(text.splitlines()[:40])
        if rel.startswith("references") and text.count("\n") > 300 and not re.search(r"(?im)^#*\s*(?:\*\*)?(?:contents|table of contents)\b", head):
            report.add("WARN", rel, "over 300 lines with no 'Contents' list near the top")


def check_portability(skill_dir: str, skill_text: str, report: Report) -> None:
    """Flag text that only Claude Code understands: the arguments placeholder,
    and the skill-dir variable with no sentence explaining it to other agents."""
    def files_under(sub: str) -> list[tuple[str, str]]:
        base = os.path.join(skill_dir, sub)
        found = []
        if os.path.isdir(base):
            for path in iter_files(base):
                text = read_text(path)
                if text is not None:
                    found.append((os.path.relpath(path, skill_dir), text))
        return found

    references, scripts = files_under("references"), files_under("scripts")
    for rel, text in [("SKILL.md", skill_text)] + references:
        for number, line in enumerate(text.splitlines(), start=1):
            if ARGS_PLACEHOLDER_RE.search(line):
                report.add("ERROR", f"{rel}:{number}", "the dollar-sign ARGUMENTS placeholder is substituted only by Claude Code "
                           "(other agents show it as literal text); refer to \"the skill's arguments\" instead, since Claude Code "
                           "appends them after ARGUMENTS: when SKILL.md has no placeholder")

    lines = skill_text.splitlines()
    _, close = split_frontmatter(skill_text)
    body_start = close + 2 if close else 1  # file line number of the first body line
    body = "\n".join(lines[close + 1:] if close else lines)
    users = (["SKILL.md"] if SKILL_DIR_TOKEN in body else []) + \
        [rel for rel, text in references + scripts if SKILL_DIR_TOKEN in text]
    if not users:
        return
    sentences = list(SKILL_DIR_SENTENCE_RE.finditer(body))
    if not sentences:
        shown = ", ".join(users[:3]) + (" ..." if len(users) > 3 else "")
        report.add("ERROR", "SKILL.md", f"the skill-dir variable is used ({shown}) but SKILL.md never explains it to agents "
                   f"that do not substitute it; add this sentence once, just before its first use in the body: {SKILL_DIR_SENTENCE}")
        return
    if len(sentences) > 1:
        report.add("WARN", "SKILL.md", f"the skill-dir explanation sentence appears {len(sentences)} times; keep one, before the first use")
    first = sentences[0]
    index = body.find(SKILL_DIR_TOKEN)
    while index != -1 and first.start() <= index < first.end():
        index = body.find(SKILL_DIR_TOKEN, index + 1)
    if index != -1 and index < first.start():
        report.add("WARN", f"SKILL.md:{body_start + body.count(chr(10), 0, index)}",
                   "the skill-dir variable is used before the sentence that explains it; move the sentence to just before this first use")


def check_evals(skill_dir: str, report: Report) -> None:
    evals = os.path.join(skill_dir, "evals")
    if not os.path.isdir(evals):
        report.add("WARN", "evals/", "no committed test cases; add evals/trigger-evals.json and evals/evals.json so the next editor can rerun them")
        return
    names = set(os.listdir(evals))
    for name in sorted(names):
        if name.startswith("trigger") and name.endswith(".json") and name != "trigger-evals.json":
            report.add("WARN", f"evals/{name}", "canonical name is evals/trigger-evals.json ([{query, should_trigger, should_route_to?}])")
    if "trigger-evals.json" not in names and not any(n.startswith("trigger") for n in names):
        report.add("WARN", "evals/", "no trigger cases (evals/trigger-evals.json)")
    behavior = os.path.join(evals, "evals.json")
    if os.path.isfile(behavior):
        try:
            with open(behavior, encoding="utf-8") as handle:
                payload = json.load(handle)
        except (OSError, ValueError) as exc:
            report.add("ERROR", "evals/evals.json", f"not valid JSON: {exc}")
            return
        cases = payload.get("evals", []) if isinstance(payload, dict) else payload
        if not isinstance(cases, list) or not cases:
            report.add("WARN", "evals/evals.json", "no cases; add at least three realistic task prompts under 'evals'")
            cases = []
        elif len(cases) < 3:
            report.add("WARN", "evals/evals.json", f"{len(cases)} case(s); aim for at least three realistic task prompts")
        for index, case in enumerate(cases):
            if not isinstance(case, dict):
                continue
            label = f"evals[{index}]" + (f" (id {case['id']})" if "id" in case else "")
            checks = case.get("expectations")
            if not isinstance(checks, list) or not checks:
                if isinstance(case.get("assertions"), list) and case["assertions"]:
                    report.add("WARN", "evals/evals.json", f"{label} lists its checks under 'assertions'; this marketplace's validator reads 'expectations' (follow your own repo's validator if it differs)")
                else:
                    report.add("WARN", "evals/evals.json", f"{label} has no 'expectations' list of checkable statements")
            elif not 3 <= len(checks) <= 6:
                report.add("WARN", "evals/evals.json", f"{label} has {len(checks)} expectations; aim for 3-6 checkable statements")
    trig = os.path.join(evals, "trigger-evals.json")
    if os.path.isfile(trig):
        try:
            with open(trig, encoding="utf-8") as handle:
                cases = json.load(handle)
        except (OSError, ValueError) as exc:
            report.add("ERROR", "evals/trigger-evals.json", f"not valid JSON: {exc}")
            return
        if isinstance(cases, list):
            positives = sum(1 for c in cases if isinstance(c, dict) and c.get("should_trigger") is True)
            negatives = sum(1 for c in cases if isinstance(c, dict) and c.get("should_trigger") is False)
            unrouted = sum(1 for c in cases if isinstance(c, dict) and c.get("should_trigger") is False
                           and not str(c.get("should_route_to") or "").strip())
            if unrouted:
                report.add("WARN", "evals/trigger-evals.json", f"{unrouted} should-not case(s) name no should_route_to; give each a plugin:skill or 'none (reason)'")
            if positives < 3 or negatives < 3:
                report.add("WARN", "evals/trigger-evals.json", f"{positives} should-trigger and {negatives} should-not cases; aim for at least 3 of each")


def check_hygiene(skill_dir: str, deny: list[re.Pattern[str]], report: Report) -> None:
    for dirpath, dirnames, _ in os.walk(skill_dir):
        for name in dirnames:
            if name.startswith(".") or name in ("__pycache__", "node_modules"):
                rel = os.path.relpath(os.path.join(dirpath, name), skill_dir)
                report.add("WARN", rel + "/", "stray hidden or cache directory; scratch work belongs outside the skill")
        dirnames[:] = [d for d in dirnames if not d.startswith(".") and d not in SKIP_DIRS]
    for path in iter_files(skill_dir):
        rel = os.path.relpath(path, skill_dir)
        text = read_text(path)
        if text is None:
            continue
        found: dict[str, list[tuple[int, str]]] = {}
        for number, line in enumerate(text.splitlines(), start=1):
            for label, pattern in PRIVATE_PATTERNS:
                for hit in pattern.finditer(line):
                    value = hit.group(0)
                    if label == "absolute home path" and PLACEHOLDER_HOME_RE.search(value):
                        continue
                    found.setdefault(label, []).append((number, value))
            for pattern in deny:
                hit = pattern.search(line)
                if hit:
                    report.add("ERROR", f"{rel}:{number}", f"denylisted term {hit.group(0)!r}")
        for label, hits in found.items():
            values = sorted({value[:40] for _, value in hits})
            shown = ", ".join(repr(v) for v in values[:4]) + (" ..." if len(values) > 4 else "")
            first = hits[0][0]
            report.add("WARN", f"{rel}:{first}", f"{label} x{len(hits)}: {shown} (review each; this repo is public)")


def plugin_version_note(skill_dir: str, report: Report) -> None:
    plugin_root = os.path.dirname(os.path.dirname(os.path.abspath(skill_dir)))
    manifest = os.path.join(plugin_root, ".claude-plugin", "plugin.json")
    if os.path.basename(os.path.dirname(os.path.abspath(skill_dir))) != "skills":
        return
    if not os.path.isfile(manifest):
        report.add("INFO", "plugin", f"no {os.path.relpath(manifest)}; report it instead of inventing a version")
        return
    try:
        with open(manifest, encoding="utf-8") as handle:
            version = json.load(handle).get("version")
    except (OSError, ValueError, AttributeError) as exc:
        report.add("WARN", "plugin", f"plugin.json unreadable: {exc}")
        return
    if version:
        report.add("INFO", "plugin", f"plugin version {version}")
    else:
        report.add("INFO", "plugin", "plugin.json has no 'version'; report it instead of inventing one")


def check_skill(skill_dir: str, deny: list[re.Pattern[str]], max_desc: int, portable: bool = False) -> Report:
    report = Report(skill_dir)
    skill_md = os.path.join(skill_dir, "SKILL.md")
    text = read_text(skill_md) if os.path.isfile(skill_md) else None
    if text is None:
        report.add("ERROR", "SKILL.md", "missing or unreadable SKILL.md")
        return report
    data = check_frontmatter(skill_dir, text, report, portable)
    desc = data.get("description")
    if isinstance(desc, str) and max_desc < len(desc) <= 1024:
        report.add("WARN", "SKILL.md", f"description is {len(desc)} chars; above {max_desc} it eats the listing budget every installed skill shares")
    check_links(skill_dir, text, report)
    check_markdown_bodies(skill_dir, text, report)
    check_portability(skill_dir, text, report)
    check_evals(skill_dir, report)
    check_hygiene(skill_dir, deny, report)
    plugin_version_note(skill_dir, report)
    lines = text.count("\n") + 1
    report.add("INFO", "SKILL.md", f"description {len(desc) if isinstance(desc, str) else 0} chars; {lines} lines")
    return report


# --- listing total ------------------------------------------------------------

def listing_total(root: str) -> int:
    rows = []
    base = os.path.join(root, "plugins")
    if not os.path.isdir(base):
        print(f"no plugins/ directory under {root}", file=sys.stderr)
        return 2
    for plugin in sorted(os.listdir(base)):
        skills = os.path.join(base, plugin, "skills")
        if not os.path.isdir(skills):
            continue
        for skill in sorted(os.listdir(skills)):
            path = os.path.join(skills, skill, "SKILL.md")
            text = read_text(path) if os.path.isfile(path) else None
            if text is None:
                continue
            fm_lines, _ = split_frontmatter(text)
            data = parse_frontmatter(fm_lines, Report(path)) if fm_lines else {}
            desc = data.get("description") if isinstance(data.get("description"), str) else ""
            when = data.get("when_to_use") if isinstance(data.get("when_to_use"), str) else ""
            rows.append((min(len(desc) + len(when), 1536), f"{plugin}:{skill}"))
    total = sum(chars for chars, _ in rows)
    print(f"{'chars':>6}  skill")
    for chars, skill in sorted(rows, reverse=True):
        print(f"{chars:>6}  {skill}")
    print(f"\n{len(rows)} skills, {total} chars of description text (names and formatting add more).")
    print("Claude Code sizes the listing at about 1% of the model's context window; recent CLIs logged")
    print("about 8,000 chars on a 200K-context model and 30,000 on a 1M-context model. Over budget, it")
    print("drops descriptions starting with the least-used skills, so a newly installed skill goes first.")
    print("Run a session with --debug-file and look for 'Skill listing over budget' to see your figure.")
    return 0


# --- self-test ----------------------------------------------------------------

def selftest() -> int:
    """Build throwaway skills in a temp dir and check what each rule reports."""
    import tempfile

    failures: list[str] = []
    total = 0

    def expect(label: str, condition: bool) -> None:
        nonlocal total
        total += 1
        if not condition:
            failures.append(label)

    with tempfile.TemporaryDirectory(prefix="check-skill-selftest-") as tmp:
        counter = [0]

        def make_skill(frontmatter: str, body: str = "# T\n", name: str = "demo-skill",
                       files: dict[str, str] | None = None) -> str:
            counter[0] += 1
            skill = os.path.join(tmp, str(counter[0]), "plugins", "p", "skills", name)
            os.makedirs(skill)
            with open(os.path.join(skill, "SKILL.md"), "w", encoding="utf-8") as handle:
                handle.write("---\n" + frontmatter + "---\n" + body)
            for rel, content in (files or {}).items():
                path = os.path.join(skill, rel)
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "w", encoding="utf-8") as handle:
                    handle.write(content)
            return skill

        def messages(skill: str, level: str, deny: tuple[str, ...] = (), portable: bool = False) -> list[str]:
            report = check_skill(skill, [re.compile(d, re.I) for d in deny], 500, portable)
            return [m for lvl, _, m in report.items if lvl == level]

        def has(skill: str, level: str, needle: str, deny: tuple[str, ...] = (), portable: bool = False) -> bool:
            return any(needle in m for m in messages(skill, level, deny, portable))

        clean = make_skill('name: demo-skill\ndescription: "Does a thing. Use when X. Not for Y."\n')
        expect("a clean skill has no errors", messages(clean, "ERROR") == [])

        expect("name must equal the directory",
               has(make_skill("name: other\ndescription: d\n"), "ERROR", "differs from the directory"))
        expect("name must be lowercase with single hyphens",
               has(make_skill("name: Bad--Name\ndescription: d\n", name="Bad--Name"), "ERROR", "single hyphens"))
        expect("name must not contain a reserved word",
               has(make_skill("name: claude-helper\ndescription: d\n", name="claude-helper"), "ERROR",
                   "reserved word 'claude'"))

        expect("description over 1024 chars is an error",
               has(make_skill("name: demo-skill\ndescription: " + "x" * 1100 + "\n"), "ERROR", "limit 1024"))
        expect("an XML-like placeholder in the description is an error",
               has(make_skill("name: demo-skill\ndescription: Edits plugins/<plugin>/x files\n"), "ERROR",
                   "XML-like tag"))
        expect("a long description warns about the listing budget",
               has(make_skill("name: demo-skill\ndescription: " + "y" * 600 + "\n"), "WARN",
                   "eats the listing budget"))

        expect("an unclosed quote is an error",
               has(make_skill('name: demo-skill\ndescription: "unclosed\n'), "ERROR", "never closed"))
        expect("an unquoted ': ' warns",
               has(make_skill("name: demo-skill\ndescription: Use when: things break\n"), "WARN", "contains ': '"))
        expect("a duplicate key is an error",
               has(make_skill("name: demo-skill\nname: demo-skill\ndescription: d\n"), "ERROR", "duplicate key"))

        data = parse_frontmatter(
            ["name: a", "description: >", "  first line", "  second line", "compatibility: '[x]'"], Report("x"))
        expect("a folded description joins its lines", data.get("description") == "first line second line")
        expect("a single-quoted value is unquoted", data.get("compatibility") == "[x]")

        spec_only = make_skill('name: demo-skill\ndescription: "Does a thing."\nlicense: MIT\n'
                               'compatibility: Needs Python 3.8 or later.\nmetadata:\n  author: example\n'
                               'allowed-tools: Bash(git diff:*), Read\n')
        expect("every Agent Skills field is accepted, even with --portable",
               messages(spec_only, "ERROR", portable=True) == []
               and not has(spec_only, "WARN", "frontmatter field", portable=True))
        hinted = make_skill("name: demo-skill\ndescription: d\nargument-hint: \"[target]\"\n")
        expect("argument-hint warns by default",
               has(hinted, "WARN", "'argument-hint' is a Claude Code autocomplete hint")
               and not has(hinted, "ERROR", "argument-hint"))
        expect("argument-hint is an error with --portable",
               has(hinted, "ERROR", "'argument-hint' is a Claude Code autocomplete hint", portable=True))
        for key, value in (("when_to_use", "Use when X."), ("disable-model-invocation", "true"), ("paths", "\"*.sql\"")):
            keyed = make_skill(f"name: demo-skill\ndescription: d\n{key}: {value}\n")
            expect(f"the Claude Code-only field {key} warns by default",
                   has(keyed, "WARN", f"'{key}' is Claude Code-only") and messages(keyed, "ERROR") == [])
            expect(f"the Claude Code-only field {key} is an error with --portable",
                   has(keyed, "ERROR", f"'{key}' is Claude Code-only", portable=True))
        typo = make_skill("name: demo-skill\ndescription: d\nlicence: MIT\n")
        expect("an unknown field warns by default and is an error with --portable",
               has(typo, "WARN", "check the spelling") and has(typo, "ERROR", "check the spelling", portable=True))
        expect("a compatibility over 500 chars is an error",
               has(make_skill("name: demo-skill\ndescription: d\ncompatibility: " + "z" * 501 + "\n"), "ERROR",
                   "compatibility is 501 chars"))

        args = "$" + "ARGUMENTS"  # built at runtime so this file never contains the placeholder
        expect("the arguments placeholder in SKILL.md is an error",
               has(make_skill("name: demo-skill\ndescription: d\n", body=f"Target: {args}.\n"), "ERROR",
                   "ARGUMENTS placeholder"))
        expect("the arguments placeholder in a reference is an error",
               has(make_skill("name: demo-skill\ndescription: d\n", body="[r](references/r.md)\n",
                              files={"references/r.md": f"Use {args}[0] here.\n"}), "ERROR", "ARGUMENTS placeholder"))
        expect("portable argument wording is not an error",
               not has(make_skill("name: demo-skill\ndescription: d\n",
                                  body="Target: the skill's arguments (they appear after ARGUMENTS: in Claude Code).\n"),
                       "ERROR", "ARGUMENTS placeholder"))

        linked = make_skill("name: demo-skill\ndescription: d\n",
                            body="See [guide](references/guide.md) and [gone](references/gone.md).\n",
                            files={"references/guide.md": "# g\n", "references/orphan.md": "# o\n"})
        expect("a link to a missing reference is an error", has(linked, "ERROR", "references/gone.md"))
        expect("an unmentioned reference is an error", has(linked, "ERROR", "never mentioned"))

        var = "${" + "CLAUDE_SKILL_DIR}"
        shell_ref = make_skill(
            "name: demo-skill\ndescription: d\n", body="[r](references/r.md)\n",
            files={"references/r.md": f"Prose mention of {var} is fine.\n\n```bash\npython3 {var}/scripts/x.py\n```\n"})
        expect("a skill-dir variable in a reference's shell block warns exactly once",
               len([m for m in messages(shell_ref, "WARN") if "substituted only in SKILL.md" in m]) == 1)
        noted_ref = make_skill(
            "name: demo-skill\ndescription: d\n", body="[r](references/r.md)\n",
            files={"references/r.md": f"{var} below is not a shell variable: use this skill's folder.\n\n```bash\npython3 {var}/scripts/x.py\n```\n"})
        expect("a reference that explains the skill-dir variable does not warn",
               not any("substituted only in SKILL.md" in m for m in messages(noted_ref, "WARN")))
        expect("a skill-dir variable in a reference needs the sentence in SKILL.md",
               has(noted_ref, "ERROR", "never explains it"))

        sentence = SKILL_DIR_SENTENCE
        wrapped = sentence.replace(" the directory", "\nthe directory")
        unexplained = make_skill("name: demo-skill\ndescription: d\n", body=f"Run `python3 {var}/scripts/x.py`.\n")
        expect("a skill-dir variable in the body without the sentence is an error",
               has(unexplained, "ERROR", "never explains it"))
        explained = make_skill("name: demo-skill\ndescription: d\n",
                               body=f"{wrapped}\n\nRun `python3 {var}/scripts/x.py`.\n")
        expect("the sentence, even wrapped across lines, satisfies the check",
               not has(explained, "ERROR", "never explains it") and not has(explained, "WARN", "skill-dir"))
        late = make_skill("name: demo-skill\ndescription: d\n",
                          body=f"Run `python3 {var}/scripts/x.py`.\n\n{sentence}\n")
        expect("a sentence after the first use warns", has(late, "WARN", "used before the sentence"))
        twice = make_skill("name: demo-skill\ndescription: d\n", body=f"{sentence}\n\n{sentence}\n")
        expect("a repeated sentence warns", has(twice, "WARN", "appears 2 times"))
        tools_only = make_skill(f"name: demo-skill\ndescription: d\nallowed-tools: Bash(python3 {var}/scripts/x.py:*)\n")
        expect("a skill-dir variable only in allowed-tools needs no sentence", not has(tools_only, "ERROR", "never explains it"))
        in_script = make_skill("name: demo-skill\ndescription: d\n", body="Run `scripts/x.sh`.\n",
                               files={"scripts/x.sh": f"#!/bin/sh\n# usage: sh {var}/scripts/x.sh\n"})
        expect("a skill-dir variable in a script needs the sentence in SKILL.md", has(in_script, "ERROR", "never explains it"))
        code_link = make_skill("name: demo-skill\ndescription: d\n",
                               body="Link it as `Supersedes [ADR-NNNN](NNNN-old.md)`.\n\n```md\n[x](missing.md)\n```\n")
        expect("example links inside code are not checked", not has(code_link, "ERROR", "link target does not exist"))

        home = "/Us" + "ers/jdoe/work"  # built at runtime so this file does not match itself
        private = make_skill("name: demo-skill\ndescription: d\n",
                             body=f"Copied from {home}/acme-tool and /home/dev/example.\n")
        expect("a real-looking home path warns once and a placeholder home does not",
               has(private, "WARN", "absolute home path x1"))
        expect("a --deny term is an error", has(private, "ERROR", "denylisted", deny=("acme",)))

        good_case = {"id": 1, "prompt": "p", "expectations": ["a", "b", "c"]}
        evals_ok = make_skill("name: demo-skill\ndescription: d\n", files={
            "evals/evals.json": json.dumps({"evals": [good_case, dict(good_case, id=2), dict(good_case, id=3)]}),
            "evals/trigger-evals.json": "[]"})
        expect("well-formed behavior evals raise no eval warning",
               not any("evals.json" in w or "expectations" in w for w in messages(evals_ok, "WARN")))
        evals_bad = make_skill("name: demo-skill\ndescription: d\n", files={
            "evals/evals.json": json.dumps({"evals": [{"id": 1, "prompt": "p"},
                                                      {"id": 2, "prompt": "p", "assertions": ["a", "b", "c"]},
                                                      {"id": 3, "prompt": "p", "expectations": ["a"]}]}),
            "evals/trigger-cases.json": "[]",
            "evals/trigger-evals.json": json.dumps([{"query": "q", "should_trigger": False}])})
        expect("a case with no checks warns", has(evals_bad, "WARN", "has no 'expectations' list"))
        expect("a case using 'assertions' warns", has(evals_bad, "WARN", "under 'assertions'"))
        expect("a case with one expectation warns", has(evals_bad, "WARN", "aim for 3-6"))
        expect("a non-canonical trigger file name warns", has(evals_bad, "WARN", "canonical name is evals/trigger-evals.json"))
        expect("a should-not case without should_route_to warns", has(evals_bad, "WARN", "name no should_route_to"))

    for label in failures:
        print(f"FAIL {label}")
    print(f"selftest: {total - len(failures)}/{total} passed")
    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("skill_dirs", nargs="*", help="skill directories (each holds a SKILL.md)")
    parser.add_argument("--deny", action="append", default=[],
                        help="regex for an employer, product or internal name that must not appear (case-insensitive; repeatable)")
    parser.add_argument("--max-desc", type=int, default=500,
                        help="warn when a description is longer than this (default 500)")
    parser.add_argument("--listing", metavar="ROOT", help="total the descriptions of ROOT/plugins/*/skills/*")
    parser.add_argument("--portable", action="store_true",
                        help="fail on frontmatter fields outside the Agent Skills standard (use for a skill meant for any "
                             "agent, such as every skill in a shared marketplace); without it they only warn")
    parser.add_argument("--quiet", action="store_true", help="hide INFO lines")
    parser.add_argument("--selftest", action="store_true", help="run the built-in checks of these rules and exit")
    args = parser.parse_args()

    if args.selftest:
        return selftest()
    if not args.skill_dirs and not args.listing:
        parser.print_usage(sys.stderr)
        return 2
    try:
        deny = [re.compile(p, re.I) for p in args.deny]
    except re.error as exc:
        print(f"bad --deny pattern: {exc}", file=sys.stderr)
        return 2

    errors = 0
    for skill_dir in args.skill_dirs:
        if not os.path.isdir(skill_dir):
            print(f"not a directory: {skill_dir}", file=sys.stderr)
            return 2
        report = check_skill(skill_dir, deny, args.max_desc, args.portable)
        print(f"check_skill: {skill_dir}")
        order = {"ERROR": 0, "WARN": 1, "INFO": 2}
        for level, where, message in sorted(report.items, key=lambda item: order[item[0]]):
            if level == "INFO" and args.quiet:
                continue
            print(f"  {level:<5}  {where}: {message}")
        print(f"  summary: {report.count('ERROR')} errors, {report.count('WARN')} warnings\n")
        errors += report.count("ERROR")

    if args.listing:
        status = listing_total(args.listing)
        if status:
            return status
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
