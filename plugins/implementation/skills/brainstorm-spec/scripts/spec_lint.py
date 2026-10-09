#!/usr/bin/env python3
"""Mechanical self-review for a spec written with the brainstorm-spec skill.

It catches the defects a tired reviewer misses: unfilled template markers,
requirements with no acceptance check (or one that cannot be run), requirements
that serve no success criterion (scope creep), success criteria nothing
delivers or measures, blocking open questions on an "Approved" spec, an
"Approved" spec with no approver (or missing a required one), and vague words
in the binding sections.

It does NOT judge whether the design is good. That is the human pass in
references/self-review.md.

Usage:
    python3 -I spec_lint.py SPEC.md [--strict] [--no-sections] [--vague-everywhere]
    python3 -I spec_lint.py --selftest
    python3 -I spec_lint.py -h | --help

Tables may be written with or without leading/trailing pipes. Serves cells may
list ids individually ("SC1, SC2") or as ranges ("SC1-SC3", "SC1-3").
Section headings are read from H2 (from H1 only when the file has no H2), so
the document title never counts as a section.

--selftest runs the built-in fixture cases (each one a small spec that once
slipped past the linter or tripped it falsely, plus a check that the bundled
references/example-spec.md lints clean) and exits 0 when all pass.

Exit codes:
    0  no errors (warnings allowed unless --strict); selftest passed
    1  errors found (or warnings with --strict); selftest failed
    2  usage or file error

Standard library only; Python 3.8+.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import unittest
from dataclasses import dataclass, field
from typing import Dict, FrozenSet, List, Optional, Sequence, Tuple

# ---------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------

PLACEHOLDER_PATTERNS: Sequence[Tuple[str, str]] = (
    (r"\[fill:", "unfilled template marker '[fill: ...]'"),
    (r"\bTBD\b", "'TBD' left in text; move it to Open questions as a real question"),
    (r"\bTODO\b", "'TODO' left in text"),
    (r"\bFIXME\b", "'FIXME' left in text"),
    (r"\bXXX\b", "'XXX' left in text"),
    (r"\?\?\?", "'???' left in text"),
    (r"(?i)\blorem ipsum\b", "filler text left in"),
)

# Words that sound like requirements but cannot be tested as written.
# Each maps to a hint about what to say instead.
VAGUE_TERMS: Sequence[Tuple[str, str]] = (
    (r"\bfast(er)?\b|\bquick(ly)?\b|\bperformant\b|\bresponsive\b", "state a latency/throughput number and the load it holds at"),
    (r"\b(near[- ])?real[- ]time\b", "state the maximum delay in seconds"),
    (r"\beas(y|ily)\b|\bsimple\b|\bsimply\b|\bintuitive\b|\buser[- ]friendly\b", "state the task, the user, and a measurable bar (steps, time, error rate)"),
    (r"\bseamless(ly)?\b|\bsmooth(ly)?\b", "describe the observable behavior instead"),
    (r"\brobust(ly)?\b|\breliabl[ey]\b|\bresilient\b", "state the failure it survives and what the user sees"),
    (r"\bscalab(le|ility)\b", "state the volume (rows, users, requests/s) it must handle"),
    (r"\befficient(ly)?\b|\boptimal(ly)?\b", "state the resource budget"),
    (r"\bflexible\b|\bconfigurable\b", "name who changes what, and how"),
    (r"\bas (needed|appropriate|required)\b|\bwhere (possible|appropriate)\b|\bif possible\b", "decide now or make it an open question"),
    (r"\bappropriate(ly)?\b|\breasonabl[ey]\b|\bsufficient(ly)?\b|\badequate(ly)?\b", "replace with the concrete rule or number"),
    (r"\betc\.?(?=\W|$)|\band so on\b", "list the cases; 'etc.' hides scope"),
    (r"\band/or\b", "say which: both, either, or exactly one"),
    (r"\bsome\b|\bseveral\b|\bvarious\b|\bmany\b|\bfew\b", "give the number or the list"),
    (r"\bhandles?\b|\bhandled\b|\bhandling\b", "say what happens, not that it is 'handled'"),
    (r"\bsupport(s|ed)? for\b", "state the behavior that 'support' means"),
    (r"\bbest[- ]effort\b", "state what happens when the effort fails"),
)

VALID_STATUSES = ("draft", "in review", "approved")

# Section families. A heading matches a family when it contains an include
# keyword once the exclude phrases are removed, so "Non-goals" is not "Goals"
# but "Goals and non-goals" is both.
SECTION_FAMILIES: Dict[str, Tuple[Sequence[str], Sequence[str]]] = {
    "problem": (("problem", "motivation", "why"), ()),
    "success": (("success", "goal", "outcome", "metric"), ("non-goal", "non goal", "nongoal")),
    "nongoals": (("non-goal", "non goal", "nongoal", "out of scope", "not in scope"), ()),
    "constraints": (("constraint",), ()),
    "approaches": (("approach", "alternative", "options considered"), ()),
    "requirements": (("requirement",), ()),
    "questions": (("open question", "unresolved", "questions"), ()),
}

REQUIRED_FAMILIES = ("problem", "success", "nongoals", "requirements", "questions")
RECOMMENDED_FAMILIES = ("approaches",)

ID_SC = re.compile(r"\bSC\d+\b")
ID_C = re.compile(r"\bC\d+\b")
ID_TRACE = re.compile(r"\b(?:SC|C)\d+\b")
ID_RANGE = re.compile(r"\b(SC|C)(\d+)\s*[-\u2013\u2014]\s*(?:\1)?(\d+)\b")
MAX_RANGE = 50
OUTCOME_TAG = re.compile(r"\(outcome\)", re.IGNORECASE)
MEASURED_BY = re.compile(r"\bmeasured\s+(?:by|from|in|with|via)\b", re.IGNORECASE)
OBSERVABILITY_HEADING = re.compile(r"observab|monitoring|instrumentation|telemetry|metrics", re.IGNORECASE)
RUNNABLE_CHECK = re.compile(r"\b(given|when|then)\b|\d", re.IGNORECASE)
PENDING_VALUES = {"", "-", "--", "pending", "tbd", "n/a", "na", "none", "?", "nobody", "not yet"}
EMPTY_CELL = {"", "-", "--", "—", "–", "n/a", "na", "none", "tbd", "?"}
IGNORE_MARKER = "spec-lint: ignore"


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class Finding:
    line: int
    level: str  # "error" | "warn" | "note"
    message: str


@dataclass
class Line:
    number: int  # 1-based
    raw: str
    visible: str  # code fences, comments, inline code removed
    section: FrozenSet[str] = frozenset()  # family keys of the enclosing section
    heading_level: int = 0
    heading_text: str = ""
    observability: bool = False  # inside a heading about observability/metrics
    ledger: bool = False  # inside a "Working ledger" section


@dataclass
class Table:
    start: int  # 1-based line number of the header row
    header: List[str]
    section: FrozenSet[str] = frozenset()
    rows: List[Tuple[int, List[str]]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
FENCE = re.compile(r"^\s{0,3}(`{3,}|~{3,})")
INLINE_CODE = re.compile(r"(`+)(.+?)\1")
TABLE_SEPARATOR = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")


def classify_heading(text: str) -> FrozenSet[str]:
    low = text.lower()
    families = set()
    for family, (includes, excludes) in SECTION_FAMILIES.items():
        probe = low
        for phrase in excludes:
            probe = probe.replace(phrase, " ")
        if any(x in probe for x in includes):
            families.add(family)
    return frozenset(families)


def parse_lines(text: str) -> Tuple[List[Line], Dict[str, int]]:
    """Return visible lines plus the first line number of each section family.

    Sections come from H2 headings. A file with no H2 at all falls back to H1,
    so a template that uses H1 per section still works; otherwise the H1 is
    the document title and must not satisfy (or mask) a required section.
    """
    lines: List[Line] = []
    in_fence: Optional[str] = None
    in_comment = False

    for idx, raw in enumerate(text.splitlines(), start=1):
        fence = FENCE.match(raw)
        if in_fence is not None:
            if fence and fence.group(1)[0] == in_fence[0] and len(fence.group(1)) >= len(in_fence):
                in_fence = None
            lines.append(Line(idx, raw, ""))
            continue
        if fence and not in_comment:
            in_fence = fence.group(1)
            lines.append(Line(idx, raw, ""))
            continue

        visible, in_comment = strip_comments(raw, in_comment)
        visible = INLINE_CODE.sub(" ", visible)
        heading = HEADING.match(visible)
        if heading:
            lines.append(Line(idx, raw, visible, heading_level=len(heading.group(1)),
                              heading_text=heading.group(2)))
        else:
            lines.append(Line(idx, raw, visible))

    section_level = 2 if any(ln.heading_level == 2 for ln in lines) else 1
    first_seen: Dict[str, int] = {}
    section: FrozenSet[str] = frozenset()
    ledger = False
    obs_level = 0  # heading level that opened an observability block; 0 = none
    for ln in lines:
        if ln.heading_level:
            if ln.heading_level < section_level:
                section, ledger = frozenset(), False
            elif ln.heading_level == section_level:
                section = classify_heading(ln.heading_text)
                ledger = "ledger" in ln.heading_text.lower()
                for fam in section:
                    first_seen.setdefault(fam, ln.number)
            if obs_level and ln.heading_level <= obs_level:
                obs_level = 0
            if not obs_level and OBSERVABILITY_HEADING.search(ln.heading_text):
                obs_level = ln.heading_level
        ln.section = section
        ln.ledger = ledger
        ln.observability = bool(obs_level)
    return lines, first_seen


def strip_comments(raw: str, in_comment: bool) -> Tuple[str, bool]:
    out = []
    i = 0
    while i < len(raw):
        if in_comment:
            end = raw.find("-->", i)
            if end == -1:
                return "".join(out), True
            i = end + 3
            in_comment = False
        else:
            start = raw.find("<!--", i)
            if start == -1:
                out.append(raw[i:])
                break
            out.append(raw[i:start])
            i = start + 4
            in_comment = True
    return "".join(out), in_comment


def split_row(line: str) -> List[str]:
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|") and not s.endswith("\\|"):
        s = s[:-1]
    return [c.strip() for c in re.split(r"(?<!\\)\|", s)]


def has_cell_separator(text: str) -> bool:
    return re.search(r"(?<!\\)\|", text) is not None


def parse_tables(lines: List[Line]) -> List[Table]:
    """Collect pipe tables, with or without leading and trailing pipes.

    A table is a header row followed by a separator row; its body runs until
    a blank line, a heading, or a line with no cell separator.
    """
    tables: List[Table] = []
    i = 0
    while i < len(lines) - 1:
        cur, nxt = lines[i], lines[i + 1]
        if (not cur.heading_level and has_cell_separator(cur.visible)
                and TABLE_SEPARATOR.match(nxt.visible)
                and len(split_row(nxt.visible)) == len(split_row(cur.visible))):
            table = Table(cur.number, [h.lower() for h in split_row(cur.visible)], cur.section)
            j = i + 2
            while j < len(lines):
                body = lines[j]
                if body.heading_level or not body.visible.strip() or not has_cell_separator(body.visible):
                    break
                table.rows.append((body.number, split_row(body.visible)))
                j += 1
            tables.append(table)
            i = j
        else:
            i += 1
    return tables


def column(header: List[str], *needles: str) -> Optional[int]:
    for idx, name in enumerate(header):
        if any(n in name for n in needles):
            return idx
    return None


def id_column(header: List[str]) -> Optional[int]:
    for idx, name in enumerate(header):
        if re.fullmatch(r"\W*(id|#|ref|req(uirement)? id)\W*", name):
            return idx
    return 0 if header else None


def cell(row: List[str], idx: Optional[int]) -> str:
    if idx is None or idx >= len(row):
        return ""
    return row[idx].strip()


def is_empty(value: str) -> bool:
    return value.strip().strip("*_").lower() in EMPTY_CELL or "[fill:" in value


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

def check_placeholders(lines: List[Line]) -> List[Finding]:
    found = []
    for ln in lines:
        for pattern, message in PLACEHOLDER_PATTERNS:
            if re.search(pattern, ln.visible):
                found.append(Finding(ln.number, "error", message))
    return found


def check_vague(lines: List[Line], everywhere: bool) -> List[Finding]:
    found = []
    binding = {"success", "requirements", "constraints"}
    for ln in lines:
        if ln.heading_level or IGNORE_MARKER in ln.raw:
            continue
        if not everywhere and not (ln.section & binding):
            continue
        hits = []
        for pattern, hint in VAGUE_TERMS:
            m = re.search(pattern, ln.visible, flags=re.IGNORECASE)
            if m:
                hits.append(f"'{m.group(0)}' ({hint})")
        if hits:
            found.append(Finding(ln.number, "warn", "vague wording: " + "; ".join(hits)))
    return found


def check_sections(first_seen: Dict[str, int]) -> List[Finding]:
    found = []
    for fam in REQUIRED_FAMILIES:
        if fam not in first_seen:
            found.append(Finding(1, "error", f"missing required section: {fam_label(fam)}"))
    for fam in RECOMMENDED_FAMILIES:
        if fam not in first_seen:
            found.append(Finding(1, "warn", f"no '{fam_label(fam)}' section; record the options you rejected"))
    return found


def fam_label(fam: str) -> str:
    return {
        "problem": "Problem",
        "success": "Success criteria",
        "nongoals": "Non-goals",
        "constraints": "Constraints",
        "approaches": "Approaches considered",
        "requirements": "Requirements",
        "questions": "Open questions",
    }[fam]


def find_status(lines: List[Line]) -> Tuple[Optional[str], int]:
    pattern = re.compile(r"\bstatus\W*?[:|]\W*([A-Za-z][A-Za-z ]*)", re.IGNORECASE)
    for ln in lines[:40]:
        m = pattern.search(ln.visible)
        if m:
            return m.group(1).strip().lower(), ln.number
    return None, 1


def check_status(status: Optional[str], line: int) -> List[Finding]:
    if status is None:
        return [Finding(1, "warn", "no 'Status:' field near the top (Draft | In review | Approved)")]
    if status not in VALID_STATUSES:
        return [Finding(line, "warn", f"unrecognised status '{status}'; use Draft, In review, or Approved")]
    return []


def section_count(lines: List[Line], tables: List[Table], family: str) -> int:
    """Count items (table rows, H3 headings, or top-level list items) in a section."""
    rows = sum(len(t.rows) for t in tables if family in t.section)
    table_lines = {n for t in tables for n, _ in t.rows} | {t.start for t in tables}
    h3 = items = 0
    for ln in lines:
        if family not in ln.section or ln.number in table_lines:
            continue
        if ln.heading_level == 3:
            h3 += 1
        elif re.match(r"^([-*+]|\d+[.)])\s+\S", ln.visible):
            items += 1
    return max(rows, h3, items)


def expand_ranges(text: str) -> str:
    """Rewrite 'SC1-SC3' / 'SC1-3' / 'C2\u2013C4' as explicit id lists."""
    def repl(m: "re.Match[str]") -> str:
        prefix, lo, hi = m.group(1), int(m.group(2)), int(m.group(3))
        if hi < lo or hi - lo > MAX_RANGE:
            return m.group(0)
        return ", ".join(f"{prefix}{n}" for n in range(lo, hi + 1))
    return ID_RANGE.sub(repl, text)


def success_blocks(lines: List[Line]) -> Dict[str, Tuple[int, str]]:
    """Map each SC id to (line, text) where it is defined in the success section.

    The text runs from the defining line through its wrapped continuation
    lines, so a 'measured by' clause on the next line still counts.
    """
    blocks: Dict[str, Tuple[int, str]] = {}
    current: Optional[str] = None
    for ln in lines:
        v = ln.visible
        if "success" not in ln.section or ln.heading_level or not v.strip():
            current = None
            continue
        ids = ID_SC.findall(v)
        new_item = (re.match(r"^\s*([-*+]|\d+[.)]|\|)\s", v) is not None
                    or re.match(r"^\s*[*_]*\s*SC\d+", v) is not None)
        if new_item:
            current = ids[0] if ids else None
        elif current is not None:
            line_no, text = blocks[current]
            blocks[current] = (line_no, text + " " + v)
        for sc in ids:
            blocks.setdefault(sc, (ln.number, v))
        if current is None and ids:
            current = ids[0]
    return blocks


def check_traceability(lines: List[Line], tables: List[Table], first_seen: Dict[str, int]) -> List[Finding]:
    found: List[Finding] = []

    sc_blocks = success_blocks(lines)
    defined_sc: Dict[str, int] = {sc: line for sc, (line, _) in sc_blocks.items()}
    defined_c: Dict[str, int] = {}
    observed: set = set()
    for ln in lines:
        if "constraints" in ln.section:
            for m in ID_C.finditer(ln.visible):
                defined_c.setdefault(m.group(0), ln.number)
        if ln.observability:
            observed.update(ID_SC.findall(ln.visible))

    req_tables = [t for t in tables if column(t.header, "acceptance") is not None]
    if not req_tables:
        if "requirements" in first_seen:
            found.append(Finding(first_seen["requirements"], "warn",
                                 "requirements are not in a table with 'ID', 'Acceptance check' and 'Serves' "
                                 "columns; acceptance and traceability checks skipped"))
        return found

    if "success" in first_seen and not defined_sc:
        found.append(Finding(first_seen["success"], "warn",
                             "success criteria carry no SC1, SC2, ... ids; traceability check skipped"))

    referenced: Dict[str, int] = {}
    seen_ids: Dict[str, int] = {}
    for table in req_tables:
        id_col = id_column(table.header)
        acc_col = column(table.header, "acceptance")
        srv_col = column(table.header, "serves", "traces", "satisfies")
        if srv_col is None:
            found.append(Finding(table.start, "warn",
                                 "requirements table has no 'Serves' column; cannot tell which success "
                                 "criterion each requirement exists for"))
        for line_no, row in table.rows:
            rid = cell(row, id_col) or f"row at line {line_no}"
            if rid in seen_ids:
                found.append(Finding(line_no, "error", f"duplicate requirement id {rid} (first at line {seen_ids[rid]})"))
            seen_ids.setdefault(rid, line_no)

            check = cell(row, acc_col)
            if is_empty(check):
                found.append(Finding(line_no, "error", f"{rid} has no acceptance check; write a yes/no test for it"))
            elif not RUNNABLE_CHECK.search(check) and IGNORE_MARKER not in lines[line_no - 1].raw:
                found.append(Finding(line_no, "warn",
                                     f"acceptance check for {rid} is not a runnable given/when/then with a "
                                     f"threshold or a yes/no result"))

            if srv_col is None:
                continue
            serves = expand_ranges(cell(row, srv_col))
            ids = ID_TRACE.findall(serves)
            if not ids:
                found.append(Finding(line_no, "error",
                                     f"{rid} serves no success criterion or constraint; cut it (YAGNI) or "
                                     f"name the SC/C id it exists for"))
            for ref in ids:
                referenced.setdefault(ref, line_no)
                is_sc = ref.startswith("SC")
                known = defined_sc if is_sc else defined_c
                # An undefined SC id is only reportable once SC ids exist at all
                # (the missing-ids case is already a warning above). Constraint
                # ids are always checked: citing C3 with no constraints list is
                # a dangling reference.
                if ref not in known and (known or not is_sc):
                    found.append(Finding(line_no, "error", f"{rid} references {ref}, which is not defined"))

    outcome_only = 0
    for sc, (line_no, text) in sc_blocks.items():
        if sc in referenced:
            continue
        if OUTCOME_TAG.search(text):
            missing = []
            if not MEASURED_BY.search(text):
                missing.append("a 'measured by <source>' clause")
            if sc not in observed:
                missing.append("a mention in the Observability design section saying how it is collected")
            if missing:
                found.append(Finding(line_no, "error",
                                     f"outcome criterion {sc} is served by no requirement and lacks "
                                     + " and ".join(missing)))
            else:
                outcome_only += 1
            continue
        found.append(Finding(line_no, "error",
                             f"{sc} is not served by any requirement; add one, drop the criterion, or tag it "
                             f"(outcome) with a 'measured by' clause if it can only be read after release"))
    if sc_blocks and outcome_only == len(sc_blocks):
        found.append(Finding(first_seen.get("success", 1), "warn",
                             "every success criterion is an unserved (outcome); at least one should be a "
                             "capability a requirement delivers and a test can check before release"))
    return found


BLOCKING_WORD = re.compile(r"\bblock(?:s|ing|er)?\b", re.IGNORECASE)
NEGATED_BEFORE = re.compile(r"(?:\bnon[- ]?|\bnot\s+|n't\s+|\bno\s+)$", re.IGNORECASE)
NEGATED_AFTER = re.compile(r"^\W*(?:approval)?\W*(?:no|false|n)\b", re.IGNORECASE)


def mentions_blocking(text: str) -> bool:
    """True when free text marks a question as blocking ('blocking', 'blocks
    approval: yes'), false for 'non-blocking', 'not blocking', 'blocks: no'."""
    for m in BLOCKING_WORD.finditer(text):
        if NEGATED_BEFORE.search(text[:m.start()]):
            continue
        if NEGATED_AFTER.match(text[m.end():]):
            continue
        return True
    return False


def check_open_questions(lines: List[Line], tables: List[Table], status: Optional[str]) -> List[Finding]:
    found: List[Finding] = []
    blocking = 0
    recognised = False
    for table in tables:
        q_col = column(table.header, "question")
        b_col = column(table.header, "block")
        if q_col is None or b_col is None:
            continue
        recognised = True
        o_col = column(table.header, "owner")
        for line_no, row in table.rows:
            question = cell(row, q_col)
            if not question or is_empty(question):
                continue
            if cell(row, b_col).lower().startswith("y"):
                blocking += 1
                if status == "approved":
                    found.append(Finding(line_no, "error",
                                         "blocking open question on an Approved spec; resolve it or "
                                         "downgrade it to non-blocking with a reason"))
            if o_col is not None and is_empty(cell(row, o_col)):
                found.append(Finding(line_no, "warn", "open question has no owner"))

    if not recognised:
        # Questions written as bullets or prose: the blocking flag cannot be
        # read reliably, so scan the wording and say that it was a guess.
        content = [ln for ln in lines
                   if "questions" in ln.section and not ln.heading_level
                   and ln.visible.strip()
                   and not TABLE_SEPARATOR.match(ln.visible)
                   and not is_empty(re.sub(r"^\s*(?:[-*+]|\d+[.)])\s*", "", ln.visible).strip(" .|"))]
        if content:
            found.append(Finding(content[0].number, "warn",
                                 "open questions are not in a table with Question / Owner / Blocks approval "
                                 "columns; blocking status could not be verified"))
            for ln in content:
                if mentions_blocking(ln.visible):
                    blocking += 1
                    if status == "approved":
                        found.append(Finding(ln.number, "error",
                                             "this open question reads as blocking, on an Approved spec; "
                                             "resolve it or mark it non-blocking with a reason"))

    if blocking and status != "approved":
        found.append(Finding(1, "note", f"{blocking} blocking open question(s) must be resolved before approval"))
    return found


def find_header_field(lines: List[Line], label: str) -> Tuple[Optional[str], int]:
    """Value of a 'Label: value' or '| Label | value |' line near the top."""
    pattern = re.compile(r"\b" + label + r"\b[^:|]*[:|](.*)", re.IGNORECASE)
    for ln in lines[:40]:
        m = pattern.search(ln.visible)
        if m:
            value = m.group(1).strip().strip("*_| ").strip()
            return value, ln.number
    return None, 1


def required_signers(value: str) -> List[str]:
    """Names listed in 'Sign-off needed from', without role notes in parentheses."""
    bare = re.sub(r"\([^)]*\)", " ", value)
    names = []
    for part in re.split(r"[;,]", bare):
        name = part.strip(" .*_").lower()
        if not name or name in PENDING_VALUES or "requester" in name or "[fill:" in name:
            continue
        if len(name.split()) <= 3:
            names.append(name)
    return names


def check_approval(lines: List[Line], status: Optional[str]) -> List[Finding]:
    found: List[Finding] = []
    approver, line = find_header_field(lines, r"approved\s+by")
    if status == "approved":
        if approver is None:
            found.append(Finding(1, "error",
                                 "Approved spec has no 'Approved by / on' field; record who approved it and when"))
        elif approver.lower().strip(" .") in PENDING_VALUES or "[fill:" in approver:
            found.append(Finding(line, "error",
                                 f"Approved spec has no approver/date ('{approver or 'blank'}'); only a person's "
                                 f"explicit approval sets Approved"))
        else:
            if not re.search(r"\d", approver):
                found.append(Finding(line, "warn", "'Approved by / on' names no date"))
            signoff, signoff_line = find_header_field(lines, r"sign-?off")
            for name in required_signers(signoff or ""):
                if name not in approver.lower():
                    found.append(Finding(signoff_line, "error",
                                         f"sign-off needed from '{name}', who is not in 'Approved by / on'; keep "
                                         f"Status at In review until they approve"))
    if status in ("in review", "approved"):
        for ln in lines:
            if ln.heading_level and ln.ledger:
                found.append(Finding(ln.number, "warn",
                                     "working ledger is still in the spec; fold its rows into sections 2-5 and "
                                     "delete it before review"))
                break
    return found


def check_counts(lines: List[Line], tables: List[Table], first_seen: Dict[str, int]) -> List[Finding]:
    found = []
    if "approaches" in first_seen and section_count(lines, tables, "approaches") < 2:
        found.append(Finding(first_seen["approaches"], "warn",
                             "fewer than two approaches recorded; a single option is not a decision"))
    if "nongoals" in first_seen and section_count(lines, tables, "nongoals") < 1:
        found.append(Finding(first_seen["nongoals"], "warn",
                             "Non-goals section is empty; name at least one thing this deliberately does not do"))
    return found


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def lint(text: str, *, sections: bool = True, vague_everywhere: bool = False) -> List[Finding]:
    lines, first_seen = parse_lines(text)
    tables = parse_tables(lines)
    status, status_line = find_status(lines)

    findings: List[Finding] = []
    findings += check_placeholders(lines)
    if sections:
        findings += check_sections(first_seen)
    findings += check_status(status, status_line)
    findings += check_approval(lines, status)
    findings += check_traceability(lines, tables, first_seen)
    findings += check_open_questions(lines, tables, status)
    findings += check_counts(lines, tables, first_seen)
    findings += check_vague(lines, vague_everywhere)
    order = {"error": 0, "warn": 1, "note": 2}
    return sorted(findings, key=lambda f: (f.line, order[f.level]))


# ---------------------------------------------------------------------------
# Self-test (--selftest): fixture cases, one defect per fixture, so a failure
# names its cause. Keep them small. Add one whenever a spec slips past the
# linter or trips it falsely.
# ---------------------------------------------------------------------------

_EXAMPLE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "references", "example-spec.md")


def _errors(findings: List[Finding]) -> List[str]:
    return [f.message for f in findings if f.level == "error"]


def _warns(findings: List[Finding]) -> List[str]:
    return [f.message for f in findings if f.level == "warn"]


# A minimal, clean Spark-size spec. Tests below derive broken variants from it.
_CLEAN = """\
# Schedule Posts Ahead

- **Status:** In review
- **Approved by / on:** pending

## 1. Problem

Creators post at bad times because they must be online to post.

## 3. Success criteria

- **SC1:** A post scheduled up to 30 days ahead publishes within 60 s of its
  scheduled time.

## 4. Non-goals

- Recurring posts (reason: no request yet).

## 6. Approaches considered

| Approach | How it works | Cost | Main risk | Reversible? | Meets |
|---|---|---|---|---|---|
| A. Job per post | Enqueue a delayed job | S | Queue backlog | Yes | SC1 |
| B. Minute sweep | Cron publishes due posts | S | 60 s drift | Yes | SC1 |

**Chosen:** A. **Rejected:** B, drift eats the 60 s budget.

## 8. Requirements

| ID | Requirement | Acceptance check | Serves | Priority |
|---|---|---|---|---|
| R1 | A due post publishes on time | Given a post due at T, when T passes, then it is live by T+60 s | SC1 | Must |

## 10. Open questions

| ID | Question | Owner | Blocks approval |
|---|---|---|---|
| Q1 | Allow editing a scheduled post? | dana | no |
"""


class _TestCleanBaseline(unittest.TestCase):
    def test_clean_spark_spec_passes(self):
        self.assertEqual(_errors(lint(_CLEAN)), [])
        self.assertEqual(_warns(lint(_CLEAN)), [])

    def test_bundled_example_passes(self):
        if not os.path.isfile(_EXAMPLE):
            self.skipTest("references/example-spec.md not found next to this script")
        with open(_EXAMPLE, encoding="utf-8") as fh:
            findings = lint(fh.read())
        self.assertEqual(_errors(findings), [])
        self.assertEqual(_warns(findings), [])


class _TestHeadings(unittest.TestCase):
    def test_h1_title_does_not_satisfy_a_section(self):
        text = _CLEAN.replace("# Schedule Posts Ahead", "# Goals Dashboard for Sales Reps")
        text = text.replace("## 3. Success criteria", "## 3. Targets")
        self.assertIn("missing required section: Success criteria", _errors(lint(text)))

    def test_h1_sections_still_work_when_no_h2_exists(self):
        text = _CLEAN.replace("\n## ", "\n# ").replace("# Schedule Posts Ahead\n", "")
        self.assertEqual(_errors(lint(text)), [])


class _TestTables(unittest.TestCase):
    def test_pipe_less_tables_are_read(self):
        text = _CLEAN.replace("- **Status:** In review", "- **Status:** Approved")
        text = text.replace("- **Approved by / on:** pending", "- **Approved by / on:** dana, 2026-03-14")
        text = text.replace(
            "| ID | Question | Owner | Blocks approval |\n|---|---|---|---|\n"
            "| Q1 | Allow editing a scheduled post? | dana | no |",
            "ID | Question | Owner | Blocks approval\n---|---|---|---\n"
            "Q1 | Allow editing a scheduled post? | dana | yes")
        text = text.replace(
            "| ID | Requirement | Acceptance check | Serves | Priority |\n|---|---|---|---|---|\n| R1 |",
            "ID | Requirement | Acceptance check | Serves | Priority\n---|---|---|---|---\nR1 |")
        errs = _errors(lint(text))
        self.assertTrue(any("blocking open question on an Approved spec" in e for e in errs), errs)
        self.assertFalse(any("SC1 is not served" in e for e in errs), errs)

    def test_ranges_in_serves_are_expanded(self):
        text = _CLEAN.replace(
            "- **SC1:** A post scheduled up to 30 days ahead publishes within 60 s of its\n  scheduled time.",
            "- **SC1:** Publishes within 60 s.\n- **SC2:** Edits apply within 60 s.\n- **SC3:** Deletes apply within 60 s.")
        text = text.replace("then it is live by T+60 s | SC1 |", "then it is live by T+60 s | SC1–SC3 |")
        self.assertEqual(_errors(lint(text)), [])
        text2 = text.replace("SC1–SC3", "SC1-3")
        self.assertEqual(_errors(lint(text2)), [])


class _TestOpenQuestions(unittest.TestCase):
    def approved(self, questions: str) -> str:
        text = _CLEAN.replace("- **Status:** In review", "- **Status:** Approved")
        text = text.replace("- **Approved by / on:** pending", "- **Approved by / on:** dana, 2026-03-14")
        head, _ = text.split("## 10. Open questions")
        return head + "## 10. Open questions\n\n" + questions + "\n"

    def test_bullet_blocking_question_on_approved_spec_is_an_error(self):
        findings = lint(self.approved("- Q1 (blocking, owner: dana): which storage backend?"))
        self.assertTrue(any("reads as blocking" in e for e in _errors(findings)))
        self.assertTrue(any("could not be verified" in w for w in _warns(findings)))

    def test_bullet_non_blocking_question_is_not_an_error(self):
        for phrase in ("non-blocking", "not blocking", "blocks approval: no", "nonblocking"):
            findings = lint(self.approved(f"- Q1 ({phrase}, owner: dana): which storage backend?"))
            self.assertEqual(_errors(findings), [], phrase)

    def test_none_needs_no_table(self):
        findings = lint(self.approved("None."))
        self.assertEqual(_errors(findings), [])
        self.assertEqual(_warns(findings), [])


class _TestApproval(unittest.TestCase):
    def test_approved_with_pending_approver_is_an_error(self):
        text = _CLEAN.replace("- **Status:** In review", "- **Status:** Approved")
        self.assertTrue(any("no approver/date" in e for e in _errors(lint(text))))

    def test_approved_without_approver_field_is_an_error(self):
        text = _CLEAN.replace("- **Status:** In review", "- **Status:** Approved")
        text = text.replace("- **Approved by / on:** pending\n", "")
        self.assertTrue(any("no 'Approved by / on' field" in e for e in _errors(lint(text))))

    def test_missing_required_signer_is_an_error(self):
        text = _CLEAN.replace("- **Status:** In review", "- **Status:** Approved")
        text = text.replace("- **Approved by / on:** pending",
                            "- **Sign-off needed from:** dana (requester); ravi (database owner, for C1)\n"
                            "- **Approved by / on:** dana, 2026-03-14")
        self.assertTrue(any("sign-off needed from 'ravi'" in e for e in _errors(lint(text))))
        text = text.replace("dana, 2026-03-14", "dana, 2026-03-14; ravi, 2026-03-16")
        self.assertEqual(_errors(lint(text)), [])

    def test_requester_only_signoff_needs_no_extra_name(self):
        text = _CLEAN.replace("- **Status:** In review", "- **Status:** Approved")
        text = text.replace("- **Approved by / on:** pending",
                            "- **Sign-off needed from:** requester only\n- **Approved by / on:** dana, 2026-03-14")
        self.assertEqual(_errors(lint(text)), [])

    def test_working_ledger_left_in_review__warns(self):
        text = _CLEAN + "\n## Working ledger (delete before In review)\n\n| Item | Value | Provenance |\n|---|---|---|\n| Users | creators | stated |\n"
        self.assertTrue(any("working ledger" in w for w in _warns(lint(text))))


class _TestAcceptanceAndOutcomes(unittest.TestCase):
    def test_vague_acceptance_check__warns(self):
        text = _CLEAN.replace("Given a post due at T, when T passes, then it is live by T+60 s", "works")
        self.assertTrue(any("not a runnable given/when/then" in w for w in _warns(lint(text))))

    def test_outcome_sc_with_measurement_needs_no_requirement(self):
        text = _CLEAN.replace(
            "  scheduled time.",
            "  scheduled time.\n- **SC2 (outcome):** posts outside peak hours fall from 40% to under 15%,\n"
            "  measured by the analytics posting-time report, read 30 days after release.")
        text = text.replace("## 8. Requirements",
                            "## 7. Design\n\n### 7.7 Observability\n\nSC2 is read from the posting-time "
                            "report; the baseline is captured before release.\n\n## 8. Requirements")
        self.assertEqual(_errors(lint(text)), [])

    def test_outcome_sc_without_observability_mention_is_an_error(self):
        text = _CLEAN.replace(
            "  scheduled time.",
            "  scheduled time.\n- **SC2 (outcome):** off-peak posts fall from 40% to under 15%, measured by the "
            "posting-time report.")
        self.assertTrue(any("outcome criterion SC2" in e for e in _errors(lint(text))))

    def test_untagged_unserved_sc_is_still_an_error(self):
        text = _CLEAN.replace("  scheduled time.", "  scheduled time.\n- **SC2:** Creators like it.")
        self.assertTrue(any("SC2 is not served" in e for e in _errors(lint(text))))


_SELFTEST_CASES = (
    _TestCleanBaseline, _TestHeadings, _TestTables, _TestOpenQuestions, _TestApproval, _TestAcceptanceAndOutcomes,
)


def selftest() -> int:
    loader = unittest.TestLoader()
    suite = unittest.TestSuite(loader.loadTestsFromTestCase(case) for case in _SELFTEST_CASES)
    result = unittest.TextTestRunner(stream=sys.stderr, verbosity=1).run(suite)
    if result.wasSuccessful():
        print(f"selftest: {result.testsRun} checks passed ({len(result.skipped)} skipped)")
        return 0
    print(f"selftest: {len(result.failures) + len(result.errors)} of {result.testsRun} checks failed")
    return 1


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------

def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="spec_lint.py",
        description="Lint a spec written with the brainstorm-spec skill.",
        epilog="Exit status: 0 no errors (or selftest passed), 1 errors (or warnings with --strict, "
               "or a failed selftest), 2 usage or file error.",
    )
    parser.add_argument("spec", nargs="?", help="path to the spec markdown file")
    parser.add_argument("--strict", action="store_true", help="treat warnings as errors")
    parser.add_argument("--no-sections", action="store_true",
                        help="skip required-section checks (use when following a repo's own template)")
    parser.add_argument("--vague-everywhere", action="store_true",
                        help="flag vague wording in every section, not only success criteria, constraints, requirements")
    parser.add_argument("--selftest", action="store_true", help="run the built-in fixture cases and exit")
    args = parser.parse_args(argv)

    if args.selftest:
        return selftest()
    if not args.spec:
        parser.error("a spec file is required (or pass --selftest)")

    try:
        with open(args.spec, encoding="utf-8") as fh:
            text = fh.read()
    except OSError as exc:
        print(f"spec_lint: cannot read {args.spec}: {exc}", file=sys.stderr)
        return 2

    findings = lint(text, sections=not args.no_sections, vague_everywhere=args.vague_everywhere)
    for f in findings:
        print(f"{args.spec}:{f.line}: {f.level}: {f.message}")

    errors = sum(f.level == "error" for f in findings)
    warns = sum(f.level == "warn" for f in findings)
    notes = sum(f.level == "note" for f in findings)
    print(f"spec_lint: {errors} error(s), {warns} warning(s), {notes} note(s)")

    if errors or (args.strict and warns):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
