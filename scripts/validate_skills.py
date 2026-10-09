#!/usr/bin/env python3
"""Validate every skill and manifest in this plugin marketplace.

Standard library only, Python 3.8 or later. Run it in isolated mode so that
nothing on the current directory or in PYTHON* environment variables can
shadow a standard-library module:

    python3 -I scripts/validate_skills.py            # validate the repo
    python3 -I scripts/validate_skills.py --root DIR # validate another checkout
    python3 -I scripts/validate_skills.py --selftest # check the YAML subset parser

What it checks
--------------
For every plugins/<plugin>/skills/<skill>/SKILL.md:
  * the file starts with a YAML frontmatter block that parses;
  * only known frontmatter keys are used, with values of the right shape;
  * `name` equals the directory name and matches ^[a-z0-9-]{1,64}$;
  * `description` is present and at most 1024 characters, holds no XML-like
    tag such as <name> (the open skill format rejects them), and together with
    `when_to_use` stays within 1536 characters;
  * the SKILL.md body holds no unescaped $0-$9: Claude Code replaces them with
    the skill's positional arguments, so a SQL or shell example using them is
    corrupted when the skill runs with arguments (write a backslash before the
    dollar sign for a literal);
  * every relative Markdown link, every backticked references/, scripts/ or
    assets/ path and every ${CLAUDE_SKILL_DIR}/... path resolves, and none of
    them escapes the skill directory;
  * every file under references/ is mentioned from SKILL.md;
  * SKILL.md is under 500 lines;
  * evals/evals.json gives every eval a non-empty `expectations` list, and
    evals/trigger-evals.json has queries that should and should not trigger.
Relative links inside the skill's own Markdown resources are checked too.

Warnings, which do not fail the run:
  * a description longer than 500 characters (the skill listing Claude sees
    has a shared size budget);
  * an eval with fewer than three or more than six expectations;
  * a should-not-trigger query with no `should_route_to`;
  * ${CLAUDE_SKILL_DIR} in a shell block of a reference file that never says
    it is not a shell variable (Claude Code substitutes it only in SKILL.md);
  * a skill that pre-approves reading PRs or CI runs (gh pr view, gh pr diff,
    gh run) but carries no copy of the shared untrusted-input block.

For the marketplace:
  * .claude-plugin/marketplace.json and every plugin.json are valid JSON
    with the required fields;
  * every marketplace source directory exists and every directory under
    plugins/ is listed in the marketplace;
  * every other .json file in the repository parses.

Across the whole repository:
  * every block between <!-- shared:NAME vN --> and <!-- /shared:NAME vN -->
    markers is byte-identical to every other block with the same NAME and vN;
  * every label the issue forms, discussion forms or .github/dependabot.yml
    apply is created by scripts/setup_labels.sh (GitHub silently drops a
    label that does not exist);
  * an optional case-insensitive scan for denylisted terms. The terms live in
    a local file that is never committed (see denylist_paths()); without one,
    the scan is skipped. Any hit fails the run.

Exit status: 0 when every check passes, 1 when any check fails, 2 on a usage
error or an unexpected crash.
"""

import argparse
import fnmatch
import json
import os
import re
import sys
import traceback

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Terms that must never appear anywhere in this repository (file contents or
# paths), matched case-insensitively as substrings. They are read from local
# files that are never committed, so the list itself is never published:
#   * the file named by the SKILLS_DENYLIST_FILE environment variable;
#   * .denylist.local at the repository root (listed in .gitignore);
#   * ~/.config/engineering-skills/denylist.txt.
# One term per line; blank lines and lines starting with '#' are ignored.
DENYLIST_ENV = "SKILLS_DENYLIST_FILE"
DENYLIST_REPO_FILE = ".denylist.local"
DENYLIST_USER_FILE = os.path.join("~", ".config", "engineering-skills", "denylist.txt")

NAME_RE = re.compile(r"^[a-z0-9-]{1,64}$")
KEBAB_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
MAX_DESCRIPTION = 1024
RECOMMENDED_DESCRIPTION = 500  # warn above this; the listing budget is shared
MAX_DESCRIPTION_PLUS_WHEN = 1536
MAX_COMPATIBILITY = 500
MAX_SKILL_LINES = 500  # SKILL.md must stay strictly under this
MIN_EXPECTATIONS, MAX_EXPECTATIONS = 3, 6  # per behavior eval (a warning outside)

# An XML-like tag in a description: "<name>", "</b>", "<plugin>". The open
# skill format rejects them, and Claude Code shows the raw text.
XML_TAG_RE = re.compile(r"</?[A-Za-z][^<>]*>")
# $0-$9 (and $10...) that Claude Code replaces with positional skill arguments.
# A backslash in front (\$1) is Claude Code's escape for a literal dollar.
POSITIONAL_ARG_RE = re.compile(r"(?<!\\)\$[0-9]+(?![A-Za-z0-9_])")
SHELL_FENCE_INFOS = {"bash", "sh", "shell", "zsh", "console", "terminal"}
SKILL_DIR_NOTE = "not a shell variable"
# allowed-tools rules that mean the skill reads PR or CI text.
READS_PR_OR_CI_RE = re.compile(r"Bash\(\s*gh\s+(?:pr\s+(?:view|diff|checks)|run\s+(?:view|list))\b")

BOOL_WORDS = {"true", "false", "yes", "no", "on", "off", "1", "0"}

# key -> expected shape. "str", "bool", "str|list", "map", or a set of
# allowed string values.
FRONTMATTER_KEYS = {
    "name": "str",
    "description": "str",
    "when_to_use": "str",
    "argument-hint": "str",
    "arguments": "str|list",
    "disable-model-invocation": "bool",
    "user-invocable": "bool",
    "allowed-tools": "str|list",
    "disallowed-tools": "str|list",
    "model": "str",
    "effort": {"low", "medium", "high", "xhigh", "max"},
    "context": {"fork"},
    "agent": "str",
    "background": "bool",
    "hooks": "map",
    "paths": "str|list",
    "shell": {"bash", "powershell"},
    "metadata": "map",
    "license": "str",
    "compatibility": "str",
}

SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv", ".idea", ".vscode"}
RESOURCE_DIRS = ("references", "scripts", "assets")


def denylist_paths(root):
    """Return the denylist files to read, in order. Missing ones are skipped."""
    paths = []
    env = os.environ.get(DENYLIST_ENV)
    if env:
        paths.append(os.path.expanduser(env))
    paths.append(os.path.join(root, DENYLIST_REPO_FILE))
    paths.append(os.path.expanduser(DENYLIST_USER_FILE))
    return paths


def denylist_terms(report, root):
    """Read terms from every local denylist file that exists.

    Returns (terms, files_read). An unreadable file named by the environment
    variable is an error, because the caller asked for it explicitly.
    """
    terms, files = [], []
    env = os.environ.get(DENYLIST_ENV)
    for path in denylist_paths(root):
        if not os.path.isfile(path):
            if env and path == os.path.expanduser(env):
                report.error(None, "%s points at %s, which is not a readable file" % (DENYLIST_ENV, path))
            continue
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for raw in fh:
                term = raw.strip().lower()
                if term and not term.startswith("#") and term not in terms:
                    terms.append(term)
        files.append(path)
    return terms, files


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


class Report:
    def __init__(self, root):
        self.root = root
        self.errors = []
        self.warnings = []
        self.notes = []

    def _rel(self, path):
        if path is None:
            return "(repo)"
        try:
            return os.path.relpath(path, self.root)
        except ValueError:
            return path

    def error(self, path, msg, line=None):
        self.errors.append((self._rel(path), line, msg))

    def warn(self, path, msg, line=None):
        self.warnings.append((self._rel(path), line, msg))


# ---------------------------------------------------------------------------
# A deliberately small YAML subset parser for frontmatter
# ---------------------------------------------------------------------------
#
# Supported: block mappings, block sequences (including "- key: value" items),
# plain / single-quoted / double-quoted scalars (single or multi-line), literal
# and folded block scalars with chomping indicators, flow sequences of plain or
# quoted scalars on one line, and comments. Anchors, aliases, tags, flow
# mappings, multi-document streams and complex keys are rejected, which is
# fine for skill frontmatter. Scalars are returned as strings; nothing is
# type-coerced, so callers decide what "true" means.


class YamlError(Exception):
    def __init__(self, msg, line):
        Exception.__init__(self, msg)
        self.msg = msg
        self.line = line  # 1-based, relative to the start of the YAML text


KEY_RE = re.compile(r"^([A-Za-z0-9_][A-Za-z0-9_.-]*)[ \t]*:(?:[ \t]+(.*))?$")
BLOCK_HEADER_RE = re.compile(r"^([|>])([1-9]?)([+-]?)([1-9]?)[ \t]*(?:#.*)?$")


def _indent(raw):
    return len(raw) - len(raw.lstrip(" "))


def _is_skippable(raw):
    s = raw.strip()
    return s == "" or s.startswith("#")


class _YamlParser:
    def __init__(self, text):
        self.lines = text.split("\n")
        for i, raw in enumerate(self.lines):
            lead = raw[: len(raw) - len(raw.lstrip(" \t"))]
            if "\t" in lead and raw.strip():
                raise YamlError("tab character used for indentation", i + 1)

    def _next_content(self, i):
        while i < len(self.lines) and _is_skippable(self.lines[i]):
            i += 1
        return i

    def parse(self):
        i = self._next_content(0)
        if i >= len(self.lines):
            return {}
        if _indent(self.lines[i]) != 0:
            raise YamlError("top-level content must not be indented", i + 1)
        value, i = self._parse_mapping(i, 0)
        i = self._next_content(i)
        if i < len(self.lines):
            raise YamlError("unexpected content: %r" % self.lines[i].strip(), i + 1)
        if not isinstance(value, dict):
            raise YamlError("frontmatter must be a mapping of keys to values", 1)
        return value

    # -- collections --------------------------------------------------------

    def _parse_mapping(self, i, indent):
        result = {}
        while True:
            i = self._next_content(i)
            if i >= len(self.lines):
                return result, i
            raw = self.lines[i]
            ind = _indent(raw)
            if ind < indent:
                return result, i
            if ind > indent:
                raise YamlError("unexpected indentation", i + 1)
            body = raw[ind:]
            if body.startswith("- ") or body == "-":
                if indent == 0:
                    raise YamlError("a list item cannot start a top-level key", i + 1)
                return result, i
            m = KEY_RE.match(body.rstrip())
            if not m:
                raise YamlError("expected 'key: value', got %r" % body.strip(), i + 1)
            key = m.group(1)
            if key in result:
                raise YamlError("duplicate key %r" % key, i + 1)
            rest = m.group(2) or ""
            value, i = self._parse_value(rest, i, indent)
            result[key] = value

    def _parse_sequence(self, i, indent):
        result = []
        while True:
            i = self._next_content(i)
            if i >= len(self.lines):
                return result, i
            raw = self.lines[i]
            ind = _indent(raw)
            if ind < indent:
                return result, i
            if ind > indent:
                raise YamlError("unexpected indentation inside a list", i + 1)
            body = raw[ind:]
            if not (body.startswith("- ") or body.rstrip() == "-"):
                return result, i
            rest = body[1:].lstrip(" ")
            item_col = ind + (len(body) - len(rest))
            if rest.strip() == "" or rest.lstrip().startswith("#"):
                # Item value lives on the following, more indented lines.
                j = self._next_content(i + 1)
                if j < len(self.lines) and _indent(self.lines[j]) > ind:
                    value, i = self._parse_nested(j, _indent(self.lines[j]))
                else:
                    value, i = None, i + 1
            elif KEY_RE.match(rest.rstrip()) and not rest.startswith(("'", '"')):
                # "- key: value" starts a mapping aligned with "key".
                self.lines[i] = " " * item_col + rest
                value, i = self._parse_mapping(i, item_col)
            else:
                value, i = self._parse_scalar(rest, i, ind)
            result.append(value)

    def _parse_nested(self, j, indent):
        body = self.lines[j][indent:]
        if body.startswith("- ") or body.rstrip() == "-":
            return self._parse_sequence(j, indent)
        return self._parse_mapping(j, indent)

    # -- values -------------------------------------------------------------

    def _parse_value(self, rest, i, parent_indent):
        stripped = rest.strip()
        if stripped == "" or stripped.startswith("#"):
            j = self._next_content(i + 1)
            if j < len(self.lines):
                ind = _indent(self.lines[j])
                body = self.lines[j][ind:]
                if ind > parent_indent:
                    return self._parse_nested(j, ind)
                if ind == parent_indent and (body.startswith("- ") or body.rstrip() == "-"):
                    return self._parse_sequence(j, ind)
            return None, i + 1
        return self._parse_scalar(rest, i, parent_indent)

    def _parse_scalar(self, rest, i, parent_indent):
        s = rest.strip()
        lineno = i + 1
        if s[0] in "|>":
            return self._parse_block_scalar(s, i, parent_indent)
        if s[0] == '"':
            return self._parse_quoted(rest.lstrip(), i, parent_indent, '"')
        if s[0] == "'":
            return self._parse_quoted(rest.lstrip(), i, parent_indent, "'")
        if s[0] == "[":
            return self._parse_flow_sequence(s, lineno), i + 1
        if s[0] in "{&*!%@`":
            raise YamlError("unsupported or reserved YAML indicator %r at start of value" % s[0], lineno)
        if s.startswith(("- ", "? ", ": ")) or s in ("-", "?", ":"):
            raise YamlError("a value cannot start with %r" % s[:2].strip(), lineno)
        # Plain scalar, possibly continued on more-indented lines.
        parts = [self._plain_piece(s, lineno)]
        j = i + 1
        while j < len(self.lines):
            raw = self.lines[j]
            if raw.strip() == "":
                k = j
                while k < len(self.lines) and self.lines[k].strip() == "":
                    k += 1
                if k < len(self.lines) and _indent(self.lines[k]) > parent_indent:
                    parts.append("\n" * (k - j))
                    j = k
                    continue
                break
            if _indent(raw) <= parent_indent:
                break
            if raw.strip().startswith("#"):
                raise YamlError("comment lines cannot interrupt a multi-line plain value", j + 1)
            parts.append(self._plain_piece(raw.strip(), j + 1))
            j += 1
        text = ""
        for p in parts:
            if p.startswith("\n"):
                text += p
            elif text and not text.endswith("\n"):
                text += " " + p
            else:
                text += p
        return text, j

    @staticmethod
    def _plain_piece(s, lineno):
        # Strip a trailing comment (" #...").
        m = re.search(r"[ \t]#", s)
        if m:
            s = s[: m.start()]
        s = s.rstrip()
        if ": " in s or s.endswith(":"):
            raise YamlError(
                "unquoted value contains ': ' (YAML reads it as a nested mapping); quote the value", lineno
            )
        return s

    def _parse_quoted(self, text, i, parent_indent, quote):
        start_line = i + 1
        buf = []
        pos = 1  # skip the opening quote
        line = text
        pending_fold = False
        while True:
            while pos < len(line):
                ch = line[pos]
                if quote == "'" and ch == "'":
                    if pos + 1 < len(line) and line[pos + 1] == "'":
                        buf.append("'")
                        pos += 2
                        continue
                    return self._finish_quoted("".join(buf), line[pos + 1 :], i)
                if quote == '"' and ch == "\\":
                    pos += 1
                    if pos >= len(line):
                        pending_fold = "escaped"
                        break
                    esc = line[pos]
                    simple = {
                        "n": "\n", "t": "\t", "\\": "\\", '"': '"', "/": "/", "0": "\0",
                        "r": "\r", " ": " ", "a": "\a", "b": "\b", "e": "\x1b",
                        "f": "\f", "v": "\v", "N": "\x85", "_": "\xa0",
                    }
                    if esc in simple:
                        buf.append(simple[esc])
                        pos += 1
                        continue
                    if esc in "xuU":
                        width = {"x": 2, "u": 4, "U": 8}[esc]
                        digits = line[pos + 1 : pos + 1 + width]
                        if len(digits) != width or not re.match(r"^[0-9A-Fa-f]+$", digits):
                            raise YamlError("bad \\%s escape in double-quoted string" % esc, i + 1)
                        buf.append(chr(int(digits, 16)))
                        pos += 1 + width
                        continue
                    raise YamlError("unknown escape \\%s in double-quoted string" % esc, i + 1)
                if quote == '"' and ch == '"':
                    return self._finish_quoted("".join(buf), line[pos + 1 :], i)
                buf.append(ch)
                pos += 1
            # Reached end of line without the closing quote: fold into the next.
            i += 1
            if i >= len(self.lines):
                raise YamlError("unterminated %s-quoted string" % ("single" if quote == "'" else "double"), start_line)
            nxt = self.lines[i]
            if nxt.strip() == "":
                buf.append("\n")
                pending_fold = "blank"
                line, pos = "", 0
                continue
            if pending_fold == "escaped":
                pass  # an escaped line break joins with no space
            elif pending_fold == "blank":
                pass  # the blank line already produced the newline
            else:
                while buf and buf[-1] in (" ", "\t"):
                    buf.pop()
                buf.append(" ")
            pending_fold = False
            line, pos = nxt.lstrip(" \t"), 0

    def _finish_quoted(self, value, trailer, i):
        t = trailer.strip()
        if t and not t.startswith("#"):
            raise YamlError("unexpected text after closing quote: %r" % t, i + 1)
        return value, i + 1

    def _parse_flow_sequence(self, s, lineno):
        m = re.search(r"\][ \t]*(#.*)?$", s)
        if not m:
            raise YamlError("flow sequences must open and close on one line", lineno)
        inner = s[1 : m.start()].strip()
        if not inner:
            return []
        items, cur, quote = [], "", None
        for ch in inner:
            if quote:
                if ch == quote:
                    quote = None
                else:
                    cur += ch
            elif ch in "'\"":
                quote = ch
            elif ch == ",":
                items.append(cur.strip())
                cur = ""
            elif ch in "[]{}":
                raise YamlError("nested flow collections are not supported", lineno)
            else:
                cur += ch
        if quote:
            raise YamlError("unterminated quote inside flow sequence", lineno)
        if cur.strip():
            items.append(cur.strip())
        return items

    def _parse_block_scalar(self, header, i, parent_indent):
        m = BLOCK_HEADER_RE.match(header)
        if not m:
            raise YamlError("malformed block scalar header %r" % header, i + 1)
        style, ind1, chomp, ind2 = m.groups()
        explicit = ind1 or ind2
        j = i + 1
        lines = []
        content_indent = None
        if explicit:
            content_indent = (parent_indent if parent_indent >= 0 else 0) + int(explicit)
        while j < len(self.lines):
            raw = self.lines[j]
            if raw.strip() == "":
                lines.append("")
                j += 1
                continue
            ind = _indent(raw)
            if content_indent is None:
                if ind <= parent_indent:
                    break
                content_indent = ind
            if ind < content_indent:
                if ind > parent_indent:
                    raise YamlError("block scalar line is less indented than its first line", j + 1)
                break
            lines.append(raw[content_indent:])
            j += 1
        # Trailing blank lines are subject to chomping, not content.
        trailing = 0
        while lines and lines[-1] == "":
            lines.pop()
            trailing += 1
        if style == "|":
            text = "\n".join(lines)
        else:
            text = ""
            prev_more = False
            for idx, ln in enumerate(lines):
                more = ln.startswith((" ", "\t"))
                if idx == 0:
                    text = ln
                elif ln == "":
                    text += "\n"
                elif text.endswith("\n") or more or prev_more:
                    if not text.endswith("\n"):
                        text += "\n"
                    text += ln
                else:
                    text += " " + ln
                prev_more = more
            # A run of N empty lines between text lines yields N newlines;
            # the loop above already appended one per empty line.
        if lines:
            if chomp == "-":
                pass
            elif chomp == "+":
                text += "\n" * (1 + trailing)
            else:
                text += "\n"
        return text, j


def parse_yaml_subset(text):
    """Parse a YAML frontmatter body. Raises YamlError."""
    return _YamlParser(text).parse()


def split_frontmatter(text):
    """Return (yaml_text, body_text, body_start_line) or raise YamlError."""
    lines = text.split("\n")
    if not lines or lines[0].rstrip("\r") != "---":
        raise YamlError("SKILL.md must start with a '---' frontmatter line", 1)
    for idx in range(1, len(lines)):
        if lines[idx].rstrip("\r") == "---":
            yaml_text = "\n".join(l.rstrip("\r") for l in lines[1:idx])
            body = "\n".join(lines[idx + 1 :])
            return yaml_text, body, idx + 2
    raise YamlError("frontmatter is never closed with a '---' line", 1)


# ---------------------------------------------------------------------------
# Markdown helpers
# ---------------------------------------------------------------------------

FENCE_RE = re.compile(r"^[ \t]{0,3}(`{3,}|~{3,})")
INLINE_CODE_RE = re.compile(r"(`+)(.+?)\1", re.S)
MD_LINK_RE = re.compile(r"!?\[(?:[^\[\]]|\[[^\]]*\])*\]\(\s*<?([^)\s>]+)>?(?:\s+(?:\"[^\"]*\"|'[^']*'))?\s*\)")
REF_DEF_RE = re.compile(r"^[ \t]{0,3}\[[^\]]+\]:[ \t]+<?(\S+?)>?(?:[ \t]+.*)?$", re.M)
SKILL_DIR_TOKEN = "${CLAUDE_SKILL_DIR}/"
SKILL_DIR_PATH_RE = re.compile(r"\$\{CLAUDE_SKILL_DIR\}/([A-Za-z0-9_./*?\[\]-]*)")
RESOURCE_PATH_RE = re.compile(
    r"(?:(?<=\$\{CLAUDE_SKILL_DIR\}/)|(?<![A-Za-z0-9_./${}\-]))((?:references|scripts|assets)/[A-Za-z0-9_./*?\-]*)"
)
SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.\-]*:")


def strip_fenced_blocks(text):
    """Replace fenced code block contents with blank lines (keeps line numbers)."""
    out = []
    fence = None
    for line in text.split("\n"):
        m = FENCE_RE.match(line)
        if fence is None and m:
            fence = m.group(1)[0] * len(m.group(1))
            out.append("")
            continue
        if fence is not None:
            if m and m.group(1)[0] == fence[0] and len(m.group(1)) >= len(fence) and line.strip() == m.group(1):
                fence = None
            out.append("")
            continue
        out.append(line)
    return "\n".join(out)


def strip_inline_code(text):
    return INLINE_CODE_RE.sub(lambda m: " " * len(m.group(0)), text)


def inline_code_spans(text):
    """Yield (offset, content) for inline code spans outside fenced blocks."""
    for m in INLINE_CODE_RE.finditer(text):
        yield m.start(2), m.group(2)


def line_of(text, offset):
    return text.count("\n", 0, offset) + 1


def is_placeholder(path):
    return "..." in path or "<" in path or "{" in path or "$" in path


def has_glob(path):
    return any(c in path for c in "*?[")


def within(child, parent):
    child = os.path.realpath(child)
    parent = os.path.realpath(parent)
    return child == parent or child.startswith(parent + os.sep)


def list_files(base):
    found = []
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        for f in sorted(filenames):
            found.append(os.path.join(dirpath, f))
    return found


def glob_matches(skill_dir, pattern):
    hits = []
    for path in list_files(skill_dir):
        rel = os.path.relpath(path, skill_dir).replace(os.sep, "/")
        if fnmatch.fnmatchcase(rel, pattern):
            hits.append(rel)
    return hits


# ---------------------------------------------------------------------------
# Skill checks
# ---------------------------------------------------------------------------


def check_value_shape(report, path, key, value, shape, line):
    def is_str(v):
        return isinstance(v, str)

    if shape == "str":
        if not is_str(value):
            report.error(path, "frontmatter %r must be a string" % key, line)
    elif shape == "bool":
        if not is_str(value) or value.strip().lower() not in BOOL_WORDS:
            report.error(path, "frontmatter %r must be a boolean (true/false), got %r" % (key, value), line)
    elif shape == "str|list":
        ok = is_str(value) or (isinstance(value, list) and all(is_str(v) and v.strip() for v in value))
        if not ok:
            report.error(path, "frontmatter %r must be a string or a list of strings" % key, line)
    elif shape == "map":
        if not isinstance(value, dict):
            report.error(path, "frontmatter %r must be a mapping" % key, line)
    elif isinstance(shape, set):
        if not is_str(value) or value.strip() not in shape:
            report.error(
                path, "frontmatter %r must be one of %s, got %r" % (key, ", ".join(sorted(shape)), value), line
            )


def resolve_resource(report, skill_dir, skill_md, ref, line, origin):
    """Check one skill-relative path reference. Returns the normalized ref or None."""
    ref = ref.rstrip(".,;:)")
    if not ref or is_placeholder(ref):
        return None
    target = os.path.normpath(os.path.join(skill_dir, ref))
    if not within(target, skill_dir):
        report.error(skill_md, "%s %r points outside the skill directory" % (origin, ref), line)
        return None
    if has_glob(ref):
        if not glob_matches(skill_dir, ref):
            report.error(skill_md, "%s %r matches no file" % (origin, ref), line)
        return ref
    if ref.endswith("/"):
        if not os.path.isdir(target):
            report.error(skill_md, "%s %r: directory does not exist" % (origin, ref), line)
        return ref
    if not os.path.exists(target):
        report.error(skill_md, "%s %r: file does not exist" % (origin, ref), line)
    return ref


def check_markdown_links(report, md_path, text, line_offset, skill_dir):
    """Check relative Markdown links in prose (code spans and fences excluded)."""
    prose = strip_inline_code(strip_fenced_blocks(text))
    base = os.path.dirname(md_path)
    targets = [(m.group(1), m.start(1)) for m in MD_LINK_RE.finditer(prose)]
    targets += [(m.group(1), m.start(1)) for m in REF_DEF_RE.finditer(prose)]
    for target, offset in targets:
        line = line_of(prose, offset) + line_offset - 1
        if target.startswith("#") or SCHEME_RE.match(target) or target.startswith("//"):
            continue
        clean = target.split("#", 1)[0].split("?", 1)[0]
        clean = re.sub(r"%20", " ", clean)
        if not clean or is_placeholder(clean):
            continue
        if clean.startswith("/"):
            report.error(md_path, "absolute link %r; use a path relative to the file" % target, line)
            continue
        resolved = os.path.normpath(os.path.join(base, clean))
        if not within(resolved, skill_dir):
            report.error(md_path, "link %r points outside the skill directory" % target, line)
            continue
        if not os.path.exists(resolved):
            report.error(md_path, "broken link %r" % target, line)


def check_skill(report, skill_dir):
    skill_md = os.path.join(skill_dir, "SKILL.md")
    dir_name = os.path.basename(skill_dir)
    if not os.path.isfile(skill_md):
        others = [f for f in os.listdir(skill_dir) if f.lower() == "skill.md"]
        if others:
            report.error(skill_dir, "found %s; the file must be named exactly SKILL.md" % others[0])
        else:
            report.error(skill_dir, "skill directory has no SKILL.md")
        return
    with open(skill_md, "r", encoding="utf-8", errors="strict") as fh:
        text = fh.read()

    n_lines = len(text.splitlines())
    if n_lines >= MAX_SKILL_LINES:
        report.error(
            skill_md,
            "SKILL.md has %d lines; keep it under %d and move detail into references/" % (n_lines, MAX_SKILL_LINES),
        )

    # -- frontmatter ---------------------------------------------------------
    try:
        yaml_text, body, body_start = split_frontmatter(text)
    except YamlError as exc:
        report.error(skill_md, "frontmatter: %s" % exc.msg, exc.line)
        return
    try:
        fm = parse_yaml_subset(yaml_text)
    except YamlError as exc:
        # YAML line 1 is file line 2, just below the opening '---'. Keep
        # going: the body checks below do not depend on the frontmatter.
        report.error(skill_md, "frontmatter: %s" % exc.msg, exc.line + 1)
        fm = None

    if fm is not None:
        check_frontmatter(report, skill_md, dir_name, yaml_text, fm)
        check_untrusted_input(report, skill_dir, skill_md, fm)
    check_skill_body(report, skill_dir, skill_md, text, body, body_start)
    check_evals(report, skill_dir)


def check_evals(report, skill_dir):
    """evals/evals.json needs checkable expectations; trigger evals need both sides."""
    evals_dir = os.path.join(skill_dir, "evals")
    task_path = os.path.join(evals_dir, "evals.json")
    trigger_path = os.path.join(evals_dir, "trigger-evals.json")
    if not os.path.isfile(task_path):
        report.error(task_path, "skill has no evals/evals.json")
    else:
        data = load_json(report, task_path)
        cases = data.get("evals") if isinstance(data, dict) else data
        if not isinstance(cases, list) or not cases:
            report.error(task_path, "expected a non-empty 'evals' list")
        else:
            for idx, case in enumerate(cases):
                label = "evals[%d]" % idx
                if isinstance(case, dict) and "id" in case:
                    label += " (id %s)" % case["id"]
                if not isinstance(case, dict) or not isinstance(case.get("prompt"), str) or not case["prompt"].strip():
                    report.error(task_path, "%s needs a non-empty 'prompt'" % label)
                    continue
                exp = case.get("expectations")
                if not isinstance(exp, list) or not exp or not all(isinstance(e, str) and e.strip() for e in exp):
                    report.error(task_path, "%s needs a non-empty 'expectations' list of strings" % label)
                elif not MIN_EXPECTATIONS <= len(exp) <= MAX_EXPECTATIONS:
                    report.warn(
                        task_path,
                        "%s has %d expectations; aim for %d to %d checkable statements (split the case or merge checks)"
                        % (label, len(exp), MIN_EXPECTATIONS, MAX_EXPECTATIONS),
                    )
    if not os.path.isfile(trigger_path):
        report.error(trigger_path, "skill has no evals/trigger-evals.json")
        return
    data = load_json(report, trigger_path)
    if not isinstance(data, list) or not data:
        report.error(trigger_path, "expected a non-empty list of {query, should_trigger} objects")
        return
    sides = set()
    for idx, item in enumerate(data):
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("query"), str)
            or not item["query"].strip()
            or not isinstance(item.get("should_trigger"), bool)
        ):
            report.error(trigger_path, "item %d needs a string 'query' and a boolean 'should_trigger'" % idx)
            continue
        sides.add(item["should_trigger"])
        route = item.get("should_route_to")
        if item["should_trigger"] is False and (not isinstance(route, str) or not route.strip()):
            report.warn(
                trigger_path,
                "item %d should not trigger but names no 'should_route_to' (a plugin:skill, or 'none (reason)')" % idx,
            )
    if sides and sides != {True, False}:
        report.error(trigger_path, "needs queries that should trigger and queries that should not")


def check_frontmatter(report, skill_md, dir_name, yaml_text, fm):
    key_lines = {}
    for idx, raw in enumerate(yaml_text.split("\n")):
        m = KEY_RE.match(raw.rstrip())
        if m and _indent(raw) == 0:
            key_lines.setdefault(m.group(1), idx + 2)

    for key, value in fm.items():
        line = key_lines.get(key)
        if key not in FRONTMATTER_KEYS:
            report.error(skill_md, "unknown frontmatter key %r" % key, line)
            continue
        check_value_shape(report, skill_md, key, value, FRONTMATTER_KEYS[key], line)

    name = fm.get("name")
    if name is None:
        report.error(skill_md, "frontmatter is missing 'name'")
    elif isinstance(name, str):
        if not NAME_RE.match(name):
            report.error(skill_md, "name %r must match ^[a-z0-9-]{1,64}$" % name, key_lines.get("name"))
        if name != dir_name:
            report.error(
                skill_md, "name %r does not match its directory %r" % (name, dir_name), key_lines.get("name")
            )

    desc = fm.get("description")
    if desc is None or (isinstance(desc, str) and not desc.strip()):
        report.error(skill_md, "frontmatter is missing a non-empty 'description'")
    elif isinstance(desc, str):
        if len(desc) > MAX_DESCRIPTION:
            report.error(
                skill_md,
                "description is %d characters; the limit is %d" % (len(desc), MAX_DESCRIPTION),
                key_lines.get("description"),
            )
        elif len(desc) > RECOMMENDED_DESCRIPTION:
            report.warn(
                skill_md,
                "description is %d characters; keep it to about %d so the shared skill listing keeps it whole"
                % (len(desc), RECOMMENDED_DESCRIPTION),
                key_lines.get("description"),
            )
        tag = XML_TAG_RE.search(desc)
        if tag:
            report.error(
                skill_md,
                "description contains an XML-like tag %r; reword placeholders such as <name>" % tag.group(0),
                key_lines.get("description"),
            )
        when = fm.get("when_to_use")
        if isinstance(when, str) and len(desc) + len(when) > MAX_DESCRIPTION_PLUS_WHEN:
            report.error(
                skill_md,
                "description + when_to_use is %d characters; the limit is %d"
                % (len(desc) + len(when), MAX_DESCRIPTION_PLUS_WHEN),
                key_lines.get("when_to_use"),
            )
    compat = fm.get("compatibility")
    if isinstance(compat, str) and len(compat) > MAX_COMPATIBILITY:
        report.error(
            skill_md,
            "compatibility is %d characters; the limit is %d" % (len(compat), MAX_COMPATIBILITY),
            key_lines.get("compatibility"),
        )


def check_positional_args(report, skill_md, body, body_start):
    """Flag $0-$9 in SKILL.md, which Claude Code replaces with skill arguments."""
    for lineno, line in enumerate(body.split("\n"), body_start):
        m = POSITIONAL_ARG_RE.search(line)
        if m:
            report.error(
                skill_md,
                "%r is replaced by a positional skill argument when the skill runs with arguments; "
                "write \\%s for a literal, $ARGUMENTS[N] for the argument, or move the example to a reference file"
                % (m.group(0), m.group(0)),
                lineno,
            )


def check_reference_skill_dir(report, path, text):
    """Warn on ${CLAUDE_SKILL_DIR} in a reference file's shell block with no explanation."""
    if SKILL_DIR_TOKEN not in text or SKILL_DIR_NOTE in text:
        return
    fence = None
    is_shell = False
    for lineno, line in enumerate(text.split("\n"), 1):
        m = FENCE_RE.match(line)
        if m:
            if fence is None:
                fence = m.group(1)
                is_shell = line.strip()[len(fence):].strip().lower() in SHELL_FENCE_INFOS
            elif m.group(1)[0] == fence[0] and len(m.group(1)) >= len(fence) and line.strip() == m.group(1):
                fence = None
            continue
        if fence is not None and is_shell and SKILL_DIR_TOKEN in line:
            report.warn(
                path,
                "${CLAUDE_SKILL_DIR} is substituted only in SKILL.md, so this command gets an empty path; "
                "say in this file that it is %s and which path to use instead" % SKILL_DIR_NOTE,
                lineno,
            )
            return


def check_untrusted_input(report, skill_dir, skill_md, fm):
    """Warn when a skill pre-approves reading PRs or CI runs but lacks the shared block."""
    tools = fm.get("allowed-tools") if isinstance(fm, dict) else None
    if isinstance(tools, list):
        tools = ", ".join(t for t in tools if isinstance(t, str))
    if not isinstance(tools, str) or not READS_PR_OR_CI_RE.search(tools):
        return
    for path in list_files(skill_dir):
        if path.endswith(".md"):
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                if "<!-- shared:untrusted-input " in fh.read():
                    return
    report.warn(
        skill_md,
        "allowed-tools pre-approves reading PRs or CI runs, but the skill has no shared:untrusted-input block",
    )


def check_skill_body(report, skill_dir, skill_md, text, body, body_start):
    mentioned = set()  # skill-relative refs (files, dirs ending in "/", globs)
    check_positional_args(report, skill_md, body, body_start)

    check_markdown_links(report, skill_md, body, body_start, skill_dir)
    prose = strip_inline_code(strip_fenced_blocks(body))
    for m in MD_LINK_RE.finditer(prose):
        target = m.group(1).split("#", 1)[0]
        if target and not SCHEME_RE.match(target) and not target.startswith(("/", "#")):
            mentioned.add(os.path.normpath(target).replace(os.sep, "/") + ("/" if target.endswith("/") else ""))

    # Backticked references/, scripts/ and assets/ paths in the body.
    unfenced = strip_fenced_blocks(body)
    for offset, span in inline_code_spans(unfenced):
        line = line_of(unfenced, offset) + body_start - 1
        for m in RESOURCE_PATH_RE.finditer(span):
            ref = m.group(1)
            top = ref.split("/", 1)[0]
            prefixed = span[: m.start(1)].endswith(SKILL_DIR_TOKEN)
            if top != "references" and not prefixed and not os.path.isdir(os.path.join(skill_dir, top)):
                # e.g. `scripts/ci/*` naming the user's project, not this skill.
                continue
            got = resolve_resource(report, skill_dir, skill_md, ref, line, "path")
            if got:
                mentioned.add(got)

    # ${CLAUDE_SKILL_DIR}/... anywhere in the file, frontmatter included.
    for m in SKILL_DIR_PATH_RE.finditer(text):
        got = resolve_resource(report, skill_dir, skill_md, m.group(1), line_of(text, m.start()), "path")
        if got:
            mentioned.add(got)

    # -- every references/ file must be reachable from SKILL.md --------------
    ref_dir = os.path.join(skill_dir, "references")
    if os.path.isdir(ref_dir):
        for path in list_files(ref_dir):
            rel = os.path.relpath(path, skill_dir).replace(os.sep, "/")
            covered = rel in text
            if not covered:
                for ref in mentioned:
                    if ref.endswith("/") and rel.startswith(ref):
                        covered = True
                    elif has_glob(ref) and fnmatch.fnmatchcase(rel, ref):
                        covered = True
                    if covered:
                        break
            if not covered:
                report.error(skill_md, "%s is never mentioned from SKILL.md" % rel)

    # -- links inside the skill's own Markdown resources ---------------------
    for sub in RESOURCE_DIRS:
        base = os.path.join(skill_dir, sub)
        if not os.path.isdir(base):
            continue
        for path in list_files(base):
            if path.endswith(".md"):
                with open(path, "r", encoding="utf-8", errors="replace") as fh:
                    content = fh.read()
                check_markdown_links(report, path, content, 1, skill_dir)
                check_reference_skill_dir(report, path, content)


# ---------------------------------------------------------------------------
# Manifest checks
# ---------------------------------------------------------------------------


def load_json(report, path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        report.error(path, "file is missing")
    except (ValueError, UnicodeDecodeError) as exc:
        report.error(path, "invalid JSON: %s" % exc)
    return None


def check_author(report, path, author):
    if author is None:
        return
    if not isinstance(author, dict) or not isinstance(author.get("name"), str) or not author["name"].strip():
        report.error(path, "'author' must be an object with a non-empty 'name'")


def check_plugin_manifest(report, plugin_dir, entry):
    path = os.path.join(plugin_dir, ".claude-plugin", "plugin.json")
    data = load_json(report, path)
    if data is None:
        return
    if not isinstance(data, dict):
        report.error(path, "plugin.json must be a JSON object")
        return
    name = data.get("name")
    if not isinstance(name, str) or not KEBAB_RE.match(name):
        report.error(path, "'name' is required and must be kebab-case, got %r" % (name,))
    elif entry is not None and name != entry.get("name"):
        report.error(path, "name %r differs from the marketplace entry %r" % (name, entry.get("name")))
    for field in ("description", "version"):
        if field in data and (not isinstance(data[field], str) or not data[field].strip()):
            report.error(path, "%r must be a non-empty string" % field)
        elif field not in data:
            report.warn(path, "no %r field" % field)
    check_author(report, path, data.get("author"))
    if "keywords" in data and not (
        isinstance(data["keywords"], list) and all(isinstance(k, str) for k in data["keywords"])
    ):
        report.error(path, "'keywords' must be a list of strings")
    if entry is not None and "version" in entry and "version" in data and entry["version"] != data["version"]:
        report.error(
            path, "version %r differs from the marketplace entry's %r" % (data["version"], entry["version"])
        )
    skills_dir = os.path.join(plugin_dir, "skills")
    if not os.path.isdir(skills_dir) or not any(
        os.path.isdir(os.path.join(skills_dir, d)) for d in os.listdir(skills_dir)
    ):
        report.warn(plugin_dir, "plugin has no skills/<name>/ directories")


def check_marketplace(report, root):
    path = os.path.join(root, ".claude-plugin", "marketplace.json")
    data = load_json(report, path)
    plugins_root = os.path.join(root, "plugins")
    listed_dirs = set()
    if isinstance(data, dict):
        name = data.get("name")
        if not isinstance(name, str) or not KEBAB_RE.match(name):
            report.error(path, "'name' is required and must be kebab-case, got %r" % (name,))
        owner = data.get("owner")
        if not isinstance(owner, dict) or not isinstance(owner.get("name"), str) or not owner["name"].strip():
            report.error(path, "'owner' must be an object with a non-empty 'name'")
        plugins = data.get("plugins")
        if not isinstance(plugins, list) or not plugins:
            report.error(path, "'plugins' must be a non-empty list")
            plugins = []
        seen = set()
        for idx, entry in enumerate(plugins):
            where = "plugins[%d]" % idx
            if not isinstance(entry, dict):
                report.error(path, "%s must be an object" % where)
                continue
            pname = entry.get("name")
            if not isinstance(pname, str) or not KEBAB_RE.match(pname):
                report.error(path, "%s 'name' must be kebab-case, got %r" % (where, pname))
            elif pname in seen:
                report.error(path, "%s duplicates plugin name %r" % (where, pname))
            seen.add(pname)
            check_author(report, path, entry.get("author"))
            source = entry.get("source")
            if isinstance(source, str):
                if not source.startswith("./"):
                    report.error(path, "%s 'source' must be a relative path starting with './'" % where)
                    continue
                pdir = os.path.normpath(os.path.join(root, source))
                if not within(pdir, root):
                    report.error(path, "%s 'source' %r points outside the repository" % (where, source))
                    continue
                if not os.path.isdir(pdir):
                    report.error(path, "%s 'source' %r: directory does not exist" % (where, source))
                    continue
                listed_dirs.add(os.path.realpath(pdir))
                check_plugin_manifest(report, pdir, entry)
            elif isinstance(source, dict):
                report.warn(path, "%s uses a remote source; not checked locally" % where)
            else:
                report.error(path, "%s is missing 'source'" % where)
    elif data is not None:
        report.error(path, "marketplace.json must be a JSON object")

    if os.path.isdir(plugins_root):
        for d in sorted(os.listdir(plugins_root)):
            full = os.path.join(plugins_root, d)
            if os.path.isdir(full) and d not in SKIP_DIRS and os.path.realpath(full) not in listed_dirs:
                report.error(full, "plugin directory is not listed in .claude-plugin/marketplace.json")


def check_all_json(report, root):
    manifests = {
        os.path.join(root, ".claude-plugin", "marketplace.json"),
    }
    for path in list_files(root):
        if path.endswith(".json") and path not in manifests and not path.endswith(
            os.path.join(".claude-plugin", "plugin.json")
        ):
            load_json(report, path)


# ---------------------------------------------------------------------------
# Denylist scan
# ---------------------------------------------------------------------------


SHARED_OPEN_RE = re.compile(r"<!-- shared:([a-z0-9-]+) (v[0-9]+) -->")
SHARED_CLOSE_RE = re.compile(r"<!-- /shared:([a-z0-9-]+) (v[0-9]+) -->")


def check_shared_blocks(report, root):
    """Every copy of a marked shared block must be byte-identical."""
    copies = {}  # (name, version) -> list of (path, line, text)
    for path in list_files(root):
        if not path.endswith(".md"):
            continue
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            text = fh.read()
        if "shared:" not in text:
            continue
        pos = 0
        while True:
            m = SHARED_OPEN_RE.search(text, pos)
            c = SHARED_CLOSE_RE.search(text, pos)
            if c and (not m or c.start() < m.start()):
                report.error(path, "closing marker for shared:%s %s has no opening marker" % c.groups(), line_of(text, c.start()))
                pos = c.end()
                continue
            if not m:
                break
            key = m.groups()
            close = "<!-- /shared:%s %s -->" % key
            end = text.find(close, m.end())
            nxt = SHARED_OPEN_RE.search(text, m.end())
            if end < 0 or (nxt and nxt.start() < end):
                why = "is never closed" if end < 0 else "is not closed before the next block starts"
                report.error(path, "shared:%s %s %s" % (key[0], key[1], why), line_of(text, m.start()))
                pos = m.end()
                continue
            copies.setdefault(key, []).append((path, line_of(text, m.start()), text[m.end():end]))
            pos = end + len(close)
    for key, items in sorted(copies.items()):
        first_path, first_line, first_text = items[0]
        for path, line, body in items[1:]:
            if body != first_text:
                report.error(
                    path,
                    "shared:%s %s differs from the copy in %s:%d; edit every copy together (or bump the version)"
                    % (key[0], key[1], os.path.relpath(first_path, root), first_line),
                    line,
                )


LABELS_BLOCK_RE = re.compile(r"^LABELS='(.*?)'$", re.S | re.M)
FLOW_LABELS_RE = re.compile(r"^labels:[ \t]*\[(.*)\][ \t]*$", re.M)


def check_labels(report, root):
    """Labels applied by forms and Dependabot must exist in scripts/setup_labels.sh."""
    script = os.path.join(root, "scripts", "setup_labels.sh")
    if not os.path.isfile(script):
        return
    with open(script, "r", encoding="utf-8", errors="replace") as fh:
        m = LABELS_BLOCK_RE.search(fh.read())
    if not m:
        report.error(script, "no LABELS='...' block found, so the labels the forms apply cannot be checked")
        return
    known = {line.split("|", 1)[0].strip() for line in m.group(1).split("\n") if line.strip()}
    used = []  # (path, line, label)
    gh = os.path.join(root, ".github")
    for sub in ("ISSUE_TEMPLATE", "DISCUSSION_TEMPLATE"):
        folder = os.path.join(gh, sub)
        if not os.path.isdir(folder):
            continue
        for name in sorted(os.listdir(folder)):
            path = os.path.join(folder, name)
            if not name.endswith((".yml", ".yaml")) or not os.path.isfile(path):
                continue
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                text = fh.read()
            for lm in FLOW_LABELS_RE.finditer(text):
                for raw in lm.group(1).split(","):
                    label = raw.strip().strip("'\"")
                    if label:
                        used.append((path, line_of(text, lm.start()), label))
    dependabot = os.path.join(gh, "dependabot.yml")
    if os.path.isfile(dependabot):
        with open(dependabot, "r", encoding="utf-8", errors="replace") as fh:
            lines = fh.read().split("\n")
        for idx, line in enumerate(lines):
            if line.strip() != "labels:":
                continue
            indent = len(line) - len(line.lstrip(" "))
            for j in range(idx + 1, len(lines)):
                item = lines[j]
                if not item.strip() or item.strip().startswith("#"):
                    continue
                if len(item) - len(item.lstrip(" ")) <= indent or not item.strip().startswith("- "):
                    break
                label = item.strip()[2:].split(" #", 1)[0].strip().strip("'\"")
                if label:
                    used.append((dependabot, j + 1, label))
    for path, line, label in used:
        if label not in known:
            report.error(path, "label %r is not created by scripts/setup_labels.sh; GitHub drops it silently" % label, line)


def scan_denylist(report, root):
    terms, files = denylist_terms(report, root)
    if not files:
        report.notes.append(
            "denylist scan skipped: no local denylist file (%s, %s, or %s)"
            % (DENYLIST_ENV, DENYLIST_REPO_FILE, DENYLIST_USER_FILE)
        )
        return
    report.notes.append("denylist scan: %d term(s) from %d local file(s)" % (len(terms), len(files)))
    skip = {os.path.realpath(f) for f in files}
    for path in list_files(root):
        if os.path.realpath(path) in skip:
            continue
        rel = os.path.relpath(path, root)
        low_rel = rel.lower()
        for term in terms:
            if term in low_rel:
                report.error(path, "denylisted term %r in the file path" % term)
        try:
            with open(path, "rb") as fh:
                data = fh.read()
        except OSError as exc:
            report.error(path, "unreadable: %s" % exc)
            continue
        if b"\0" in data[:8192]:
            continue  # binary
        text = data.decode("utf-8", errors="replace").lower()
        if not any(t in text for t in terms):
            continue
        for lineno, line in enumerate(text.split("\n"), 1):
            for term in terms:
                if term in line:
                    report.error(path, "denylisted term %r" % term, lineno)


# ---------------------------------------------------------------------------
# Self-test for the YAML subset parser
# ---------------------------------------------------------------------------


def selftest():
    cases = [
        ("a: plain value\nb: 'it''s'\nc: \"x\\ty\"", {"a": "plain value", "b": "it's", "c": "x\ty"}),
        ("d: >-\n  folded\n  text\n\n  para\n", {"d": "folded text\npara"}),
        ("e: |\n  line1\n  line2\n", {"e": "line1\nline2\n"}),
        ("f:\n  # comment\n  - one\n  - 'two'\n", {"f": ["one", "two"]}),
        ("g:\n- one\n- two", {"g": ["one", "two"]}),
        ("h: [a, 'b c']", {"h": ["a", "b c"]}),
        ("i:\n  k1: v1\n  k2:\n    - x", {"i": {"k1": "v1", "k2": ["x"]}}),
        ("j:\n  - type: command\n    command: run\n", {"j": [{"type": "command", "command": "run"}]}),
        ("k: one\n  continued line", {"k": "one continued line"}),
        ("l: 'multi\n  line'", {"l": "multi line"}),
        ("m: value # trailing comment", {"m": "value"}),
        ("n:", {"n": None}),
    ]
    bad = [
        "a: x: y",
        "a: 1\na: 2",
        "a: 'unterminated",
        "  a: indented",
        "a: *alias",
        "a: {x: 1}",
        "\ta: tab",
    ]
    failures = 0
    for src, want in cases:
        try:
            got = parse_yaml_subset(src)
        except YamlError as exc:
            got = "YamlError(%s)" % exc.msg
        if got != want:
            failures += 1
            print("FAIL parse %r\n  want %r\n  got  %r" % (src, want, got))
    for src in bad:
        try:
            got = parse_yaml_subset(src)
            failures += 1
            print("FAIL expected an error for %r, got %r" % (src, got))
        except YamlError:
            pass
    # The pattern checks that guard skill content.
    pattern_cases = [
        (XML_TAG_RE, "Use for \"implement docs/plans/<name>.md\"", True),
        (XML_TAG_RE, "Not for a < b comparisons or a -> arrow", False),
        (POSITIONAL_ARG_RE, "WHERE id = $1 AND qty > 0", True),
        (POSITIONAL_ARG_RE, "= ANY($1::bigint[])", True),
        (POSITIONAL_ARG_RE, "write \\$1 for a literal", False),
        (POSITIONAL_ARG_RE, "$ARGUMENTS and $ARGUMENTS[0] and $name", False),
        (READS_PR_OR_CI_RE, "Bash(git diff:*), Bash(gh pr view:*)", True),
        (READS_PR_OR_CI_RE, "Bash(gh run list:*)", True),
        (READS_PR_OR_CI_RE, "Bash(gh issue view:*), Bash(gh repo view:*)", False),
    ]
    for regex, sample, want in pattern_cases:
        if bool(regex.search(sample)) != want:
            failures += 1
            print("FAIL pattern %s on %r: want %s" % (regex.pattern, sample, want))
    total = len(cases) + len(bad) + len(pattern_cases)
    print("selftest: %d/%d passed" % (total - failures, total))
    return 1 if failures else 0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def find_skill_dirs(root):
    out = []
    plugins_root = os.path.join(root, "plugins")
    if not os.path.isdir(plugins_root):
        return out
    for plugin in sorted(os.listdir(plugins_root)):
        skills_root = os.path.join(plugins_root, plugin, "skills")
        if not os.path.isdir(skills_root):
            continue
        for skill in sorted(os.listdir(skills_root)):
            full = os.path.join(skills_root, skill)
            if os.path.isdir(full) and skill not in SKIP_DIRS:
                out.append((plugin, full))
    return out


def print_report(report, n_skills, n_plugins):
    def fmt(item):
        path, line, msg = item
        return "  %s%s: %s" % (path, (":%d" % line) if line else "", msg)

    for note in report.notes:
        print("note: %s" % note)
    if report.warnings:
        print("Warnings (%d):" % len(report.warnings))
        for item in sorted(report.warnings, key=lambda x: (x[0], x[1] or 0)):
            print(fmt(item))
    if report.errors:
        print("Errors (%d):" % len(report.errors))
        for item in sorted(report.errors, key=lambda x: (x[0], x[1] or 0)):
            print(fmt(item))
        print("FAILED: %d error(s) across %d skill(s) in %d plugin(s)." % (len(report.errors), n_skills, n_plugins))
    else:
        print("OK: %d skill(s) in %d plugin(s) passed every check." % (n_skills, n_plugins))


def main(argv=None):
    parser = argparse.ArgumentParser(description="Validate skills and plugin manifests in this marketplace.")
    parser.add_argument(
        "--root",
        default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        help="repository root (default: the parent of this script's directory)",
    )
    parser.add_argument(
        "--selftest", action="store_true", help="run the self-test of the YAML subset parser and the content patterns, and exit"
    )
    args = parser.parse_args(argv)

    if args.selftest:
        return selftest()

    root = os.path.abspath(args.root)
    if not os.path.isdir(root):
        print("error: --root %s is not a directory" % root, file=sys.stderr)
        return 2

    report = Report(root)
    skills = find_skill_dirs(root)
    if not skills:
        report.error(os.path.join(root, "plugins"), "no plugins/<plugin>/skills/<skill>/ directories found")
    for plugin, skill_dir in skills:
        check_skill(report, skill_dir)
    check_marketplace(report, root)
    check_all_json(report, root)
    check_shared_blocks(report, root)
    check_labels(report, root)
    scan_denylist(report, root)

    print_report(report, len(skills), len({p for p, _ in skills}))
    return 1 if report.errors else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(2)
    except Exception:  # an unexpected crash is not a validation failure
        traceback.print_exc()
        sys.exit(2)
