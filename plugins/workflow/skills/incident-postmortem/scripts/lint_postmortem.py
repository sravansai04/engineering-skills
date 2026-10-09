#!/usr/bin/env python3
"""Lint a Markdown postmortem for structure, timeline hygiene, action items, and blame language.

Usage:
    python3 lint_postmortem.py FILE [--light] [--strict] [--json]
    python3 lint_postmortem.py --selftest

Checks:
  * required sections are present (--light requires the lightweight subset);
    a level-1 title never counts as a section, so a title like
    "Checkout impact timeline" can't stand in for the Impact or Timeline section
  * timeline rows (table rows, or timestamped bullets) carry a parseable
    timestamp, are in time order, are stated in UTC 24-hour time, and cite a
    source; a parenthesized original local time after a UTC time is allowed
  * the impact section contains at least one number
  * action items have an owner, a due date, and a tracking link, and avoid
    vague or weak wording ("be more careful", "improve monitoring"); bulleted
    action items are reported as one structural error and still get the
    wording and group-owner checks
  * blame, counterfactual, and hindsight language anywhere in the prose
  * unresolved TODO(confirm) markers

Errors are structural problems. Warnings need a human judgement (a quoted
chat message may legitimately say "I forgot"). Exit status: 0 when there are no
errors (and no warnings under --strict), 1 otherwise, 2 on usage or I/O errors.
--selftest (or its older spelling --self-test) runs the built-in regression
cases and exits 0 when all pass.
Standard library only; Python 3.8+.
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime

FULL_SECTIONS = [
    ("Summary", r"summary"),
    ("Impact", r"impact"),
    ("Timeline", r"timeline"),
    ("Contributing factors / root cause", r"contributing factors?|root causes?|causal"),
    ("What went well", r"went well"),
    ("What went poorly", r"went (?:poorly|wrong|badly)|didn'?t go well|could have gone better"),
    ("Where we got lucky", r"lucky"),
    ("Action items", r"action items?|follow[- ]?ups?|remediation"),
    ("Lessons learned", r"lessons?"),
]
LIGHT_SECTIONS = {
    "Summary",
    "Impact",
    "Timeline",
    "Contributing factors / root cause",
    "Where we got lucky",
    "Action items",
}
# How level-1 headings are told apart from the document title: a later
# level-1 heading is a section when it *starts* with a section name (after
# optional numbering and a few lead-in words); the first heading is a section
# only when it *is* a section name and nothing more.
_SECTION_NAME = (
    r"^\s*(?:\d+[.)]?\s+)?(?:(?:what|where|we|got|things|that|the)\s+){0,3}(?:"
    + "|".join(p for _, p in FULL_SECTIONS)
    + r")"
)
SECTION_LEAD = re.compile(_SECTION_NAME, re.I)
SECTION_ONLY = re.compile(_SECTION_NAME + r"\s*$", re.I)

LANGUAGE_RULES = [
    (r"\bshould(?:n'?t| not)? have\b", "counterfactual; describe what was known and done at the time"),
    (r"\bcould have (?:prevented|avoided|caught|noticed|stopped)\b", "counterfactual; name the condition that made it hard instead"),
    (r"\bfailed to\b", "judges in hindsight; state what happened and what made it hard"),
    (r"\b(?:human|operator|pilot|user) error\b", "never a final cause; name the conditions that made the error easy and costly"),
    (r"\b(?:careless(?:ness|ly)?|negligen(?:t|ce)|sloppy|lazy|incompeten(?:t|ce)|reckless(?:ly)?)\b", "character judgement; describe actions and conditions"),
    (r"\b(?:forgot|neglected|ignored|overlooked)\b", "blame-flavored verb; describe what information or prompt was missing"),
    (r"\b(?:obviously|clearly|simply|of course)\b", "hindsight minimizer; it was not obvious at the time"),
    (r"\b(?:blame[ds]?|at fault|culprit|guilty)\b", "blame framing; focus on system conditions"),
    (r"\bdidn'?t bother\b", "attributes motive; describe the conditions instead"),
    (r"(?<![\w.@])@[A-Za-z][\w.-]*", "handle of a person; prefer roles in the narrative"),
]

VAGUE_ACTION_RULES = [
    (r"\bbe (?:more )?(?:careful|vigilant|cautious)\b", "a hope, not a control; add a guardrail, check, or automation"),
    (r"\bpay (?:more )?attention\b", "a hope, not a control; add a guardrail, check, or automation"),
    (r"\bremind (?:everyone|people|the team|engineers|developers)\b", "reminders fade; pair with a systemic fix"),
    (r"\bdouble[- ]check\b", "manual re-checking is weak; automate the check"),
    (r"\b(?:more|additional) training\b|\btrain (?:the )?(?:team|engineers|everyone)\b", "training alone is a weak control; pair with a systemic fix"),
]
VAGUE_VERBS = r"^(?:improve|fix|look into|investigate|monitor|review|revisit|address|update|enhance|consider|ensure|better)\b"

GROUP_OWNER = re.compile(
    r"^(?:the )?(?:[\w-]+ )?(?:team|squad|group|org|everyone|all|engineering|eng|ops|sre|devops|platform|tbd|tbc|n/?a|none|unassigned|\?+)$",
    re.I,
)
EMPTY_CELL = re.compile(r"^(?:|-+|—|tbd|tbc|todo|n/?a|none|\?+|_+.*_+)$", re.I)

ZONES = r"PST|PDT|EST|EDT|CST|CDT|MST|MDT|HST|AKST|AKDT|IST|BST|CET|CEST|EET|EEST|WET|WEST|JST|KST|AEST|AEDT|AWST|NZST|NZDT|SGT"
TS_FULL = re.compile(
    r"^~?\s*(\d{4}-\d{2}-\d{2})[ T](\d{1,2}):(\d{2})(?::(\d{2})(?:\.\d+)?)?\s*(Z|UTC|GMT|\+00:?00)?$", re.I
)
TS_TIME_ONLY = re.compile(r"^~?\s*(\d{1,2}):(\d{2})(?::(\d{2}))?\s*(Z|UTC|GMT)?$", re.I)
NON_UTC = re.compile(
    r"[+-](?!00:?00)\d{2}:?\d{2}$|\b(?:" + ZONES + r")\b|(?:\d\s*|\b)[ap]\.?m\b\.?",
    re.I,
)
# A timestamp at the start of a bullet or numbered line. It also captures a
# 12-hour suffix, an offset, or a zone, so NON_UTC can report them specifically.
BULLET_TS = re.compile(
    r"^\s*(?:[-*+]|\d+[.)])\s+\**\s*("
    r"~?(?:\d{4}-\d{2}-\d{2}[ T])?\d{1,2}:\d{2}(?::\d{2})?"
    r"(?:\s*[aApP]\.?[mM]\b\.?)?"
    r"(?:\s*(?:Z|UTC|GMT|" + ZONES + r")\b|[+-]\d{2}:?\d{2})?"
    r")"
)
BULLET_ITEM = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(?:\[[ xX]\]\s+)?(.*\S)")
PAREN = re.compile(r"\s*\([^()]*\)")


class Report:
    def __init__(self):
        self.errors = []
        self.warnings = []

    def error(self, line, check, message):
        self.errors.append({"line": line, "check": check, "message": message})

    def warn(self, line, check, message):
        self.warnings.append({"line": line, "check": check, "message": message})


def strip_md(cell):
    cell = cell.strip()
    cell = re.sub(r"[*`]", "", cell)
    return cell.strip()


def split_row(line):
    body = line.strip()
    if body.startswith("|"):
        body = body[1:]
    if body.endswith("|") and not body.endswith("\\|"):
        body = body[:-1]
    return [c.strip() for c in re.split(r"(?<!\\)\|", body)]


def is_separator(cells):
    return all(re.fullmatch(r":?-{3,}:?", c.strip()) for c in cells if c.strip()) and any(c.strip() for c in cells)


def parse_lines(text):
    """Return (lines, prose_mask, headings). prose_mask[i] is False inside fenced code blocks."""
    lines = text.splitlines()
    mask = []
    headings = []
    in_fence = False
    fence_marker = None
    for i, line in enumerate(lines):
        stripped = line.lstrip()
        m = re.match(r"^(`{3,}|~{3,})", stripped)
        if m:
            if not in_fence:
                in_fence, fence_marker = True, m.group(1)[0]
            elif stripped.startswith(fence_marker * 3):
                in_fence = False
            mask.append(False)
            continue
        mask.append(not in_fence)
        if not in_fence:
            h = re.match(r"^(#{1,6})\s+(.*?)\s*#*\s*$", line)
            if h:
                headings.append((i, len(h.group(1)), h.group(2)))
    return lines, mask, headings


def section_heads(headings):
    """Indexes into headings of the ones that can open a section.

    A level-1 heading is usually the document title. Matching section names
    against it would let "Postmortem: checkout impact timeline" satisfy the
    Impact and Timeline checks and make the whole document their range. So the
    first heading, when it is level 1, is treated as the title unless it is a
    bare section name ("Summary", "1. Impact"). Later level-1 headings count
    as sections when the document uses level 1 for sections throughout, or
    when they start with a section name.
    """
    flat = not any(level >= 2 for _, level, _ in headings)
    keep = []
    for i, (_, level, title) in enumerate(headings):
        if level >= 2:
            keep.append(i)
        elif i == 0:
            if SECTION_ONLY.match(title):
                keep.append(i)
        elif flat or SECTION_LEAD.match(title):
            keep.append(i)
    return keep


def section_ranges(headings, total, pattern):
    """Yield (start, end) line ranges for section headings matching pattern.

    A section ends at the next heading (of any kind, title included) of the
    same or higher level.
    """
    rx = re.compile(pattern, re.I)
    for idx in section_heads(headings):
        line_no, level, title = headings[idx]
        if rx.search(title):
            end = total
            for later_line, later_level, _ in headings[idx + 1:]:
                if later_level <= level:
                    end = later_line
                    break
            yield line_no, end


def tables_in(lines, mask, start, end):
    """Return tables as lists of (line_no, cells); the first entry is the header."""
    tables, current = [], []
    for i in range(start, end):
        if mask[i] and lines[i].lstrip().startswith("|"):
            cells = split_row(lines[i])
            if is_separator(cells):
                continue
            current.append((i, cells))
        else:
            if current:
                tables.append(current)
                current = []
    if current:
        tables.append(current)
    return tables


def find_col(header, pattern):
    rx = re.compile(pattern, re.I)
    for idx, cell in enumerate(header):
        if rx.search(cell):
            return idx
    return None


def check_sections(headings, light, rep):
    titles = [headings[i][2] for i in section_heads(headings)]
    for name, pattern in FULL_SECTIONS:
        if light and name not in LIGHT_SECTIONS:
            continue
        if not any(re.search(pattern, t, re.I) for t in titles):
            rep.error(None, "sections", f"missing section: {name}")


def parse_ts(cell):
    m = TS_FULL.match(cell)
    if m:
        date, hh, mm, ss, zone = m.groups()
        return datetime.strptime(f"{date} {hh}:{mm}:{ss or '00'}", "%Y-%m-%d %H:%M:%S"), True, bool(zone)
    m = TS_TIME_ONLY.match(cell)
    if m:
        hh, mm, ss, zone = m.groups()
        if int(hh) > 23:
            return None, False, False
        return datetime(1900, 1, 1, int(hh), int(mm), int(ss or 0)), False, bool(zone)
    return None, False, False


def check_timeline(lines, mask, headings, rep):
    ranges = list(section_ranges(headings, len(lines), r"timeline"))
    if not ranges:
        return
    start, end = ranges[0]
    header_says_utc = "utc" in lines[start].lower()
    entries = []  # (line_no, raw_time, source_or_None)
    source_col_exists = False
    for table in tables_in(lines, mask, start, end):
        header = table[0][1]
        tcol = find_col(header, r"time|when|utc|date")
        if tcol is None:
            continue
        header_says_utc = header_says_utc or "utc" in header[tcol].lower()
        scol = find_col(header, r"source|evidence|link|ref")
        source_col_exists = source_col_exists or scol is not None
        for line_no, cells in table[1:]:
            raw = cells[tcol] if tcol < len(cells) else ""
            src = cells[scol] if scol is not None and scol < len(cells) else None
            entries.append((line_no, raw, src))
    from_bullets = False
    if not entries:
        for i in range(start, end):
            if mask[i]:
                m = BULLET_TS.match(lines[i])
                if m:
                    entries.append((i, m.group(1), None))
        from_bullets = bool(entries)
    if not entries:
        rep.error(start + 1, "timeline", "timeline has no timestamped rows (use a table with a Time (UTC) column)")
        return

    prev = None
    last_date = None
    date_less = False
    any_zone = False
    for line_no, raw, src in entries:
        # A parenthesized original ("14:02 UTC (09:02 CDT)") is allowed; judge the main value.
        cell = PAREN.sub("", strip_md(raw)).strip()
        if NON_UTC.search(cell):
            rep.error(line_no + 1, "timeline", f"non-UTC or 12-hour timestamp '{cell}'; convert to UTC, 24-hour")
            continue
        ts, has_date, has_zone = parse_ts(cell)
        if ts is None:
            if EMPTY_CELL.match(cell) or cell.upper().startswith("YYYY"):
                rep.warn(line_no + 1, "timeline", "row has no timestamp (template placeholder?)")
            else:
                rep.error(line_no + 1, "timeline", f"unparseable timestamp '{cell}'; use YYYY-MM-DD HH:MM[:SS]")
            continue
        any_zone = any_zone or has_zone
        if has_date:
            last_date = ts.date()
        else:
            date_less = True
            if last_date is not None:
                ts = datetime.combine(last_date, ts.time())
        if cell.startswith("~"):
            rep.warn(line_no + 1, "timeline", f"approximate time '{cell}'; confirm from a source if you can")
        if prev is not None and ts < prev:
            if has_date:
                rep.error(line_no + 1, "timeline", "row is earlier than the previous row; keep the timeline in time order")
            else:
                rep.warn(line_no + 1, "timeline", "time goes backwards; if this crosses midnight, add dates")
        prev = ts
        if src is not None and EMPTY_CELL.match(strip_md(src)):
            rep.warn(line_no + 1, "timeline", "no source for this row; link the log, message, dashboard, or deploy record")
    if date_less:
        rep.warn(start + 1, "timeline", "some rows have a time but no date; full dates avoid ambiguity across midnight and multi-day incidents")
    if not header_says_utc and not any_zone:
        rep.warn(start + 1, "timeline", "timeline never states UTC; label the column 'Time (UTC)' or suffix times with Z")
    if from_bullets:
        rep.warn(start + 1, "timeline", "timeline is a bullet list with no sources; use a table with Time (UTC), Event, and Source columns")
    elif not source_col_exists:
        rep.warn(start + 1, "timeline", "timeline table has no Source column")


def check_action_wording(ln, action, rep):
    for pattern, why in VAGUE_ACTION_RULES:
        if re.search(pattern, action, re.I):
            rep.warn(ln, "action-items", f"'{action[:60]}': {why}")
    if re.match(VAGUE_VERBS, action, re.I) and len(action.split()) < 7:
        rep.warn(ln, "action-items", f"'{action}' is too vague to verify; state the concrete end state")


def check_owner(ln, owner, rep):
    owner_core = re.sub(r"\(.*?\)", "", owner).strip()
    if EMPTY_CELL.match(owner):
        rep.error(ln, "action-items", "no owner; name one person")
    elif GROUP_OWNER.match(owner_core):
        rep.warn(ln, "action-items", f"owner '{owner}' looks like a group; name one accountable person")
    elif re.search(r",|/|&|\band\b", owner_core):
        rep.warn(ln, "action-items", f"owner '{owner}' names several people; pick one accountable owner")


def check_actions(lines, mask, headings, rep):
    ranges = list(section_ranges(headings, len(lines), r"action items?|follow[- ]?ups?|remediation"))
    if not ranges:
        return
    start, end = ranges[0]
    tables = tables_in(lines, mask, start, end)
    rows_seen = 0
    for table in tables:
        header = table[0][1]
        acol = find_col(header, r"action|item|description|task|what")
        ocol = find_col(header, r"owner|assignee|dri|who")
        dcol = find_col(header, r"due|deadline|target|date|by when")
        tcol = find_col(header, r"track|ticket|issue|link|bug|jira")
        pcol = find_col(header, r"priority|pri\b|^p$")
        fcol = find_col(header, r"address|factor|cause|cf\b")
        if acol is None:
            continue
        missing = [n for n, c in (("Owner", ocol), ("Due", dcol), ("Tracking", tcol)) if c is None]
        for n in missing:
            rep.error(table[0][0] + 1, "action-items", f"action item table has no {n} column")
        for n, c in (("Priority", pcol), ("Addresses (contributing factor)", fcol)):
            if c is None:
                rep.warn(table[0][0] + 1, "action-items", f"action item table has no {n} column")
        for line_no, cells in table[1:]:
            def get(c):
                return strip_md(cells[c]) if c is not None and c < len(cells) else ""
            action = get(acol)
            if EMPTY_CELL.match(action):
                continue
            rows_seen += 1
            ln = line_no + 1
            if ocol is not None:
                check_owner(ln, get(ocol), rep)
            if dcol is not None:
                due = get(dcol)
                if EMPTY_CELL.match(due) or due.upper().startswith("YYYY"):
                    rep.error(ln, "action-items", "no due date")
                elif not re.search(r"\d{4}-\d{2}-\d{2}", due):
                    rep.warn(ln, "action-items", f"due '{due}' is not an ISO date (YYYY-MM-DD)")
            if tcol is not None and EMPTY_CELL.match(get(tcol)):
                rep.error(ln, "action-items", "no tracking link; file the ticket in the owning team's tracker and link it")
            if fcol is not None and EMPTY_CELL.match(get(fcol)):
                rep.warn(ln, "action-items", "not linked to a contributing factor")
            check_action_wording(ln, action, rep)
    if rows_seen:
        return

    # No table rows: fall back to the bullets directly under the heading (before
    # any subsection such as "Considered and not taken"), so a bulleted draft
    # still gets the wording and owner checks.
    stop = next((h_line for h_line, _, _ in headings if start < h_line < end), end)
    bullets = []
    for i in range(start + 1, stop):
        m = BULLET_ITEM.match(lines[i]) if mask[i] else None
        if m:
            bullets.append((i + 1, strip_md(m.group(1))))
    if not bullets:
        rep.error(start + 1, "action-items", "no action items found (expected a table with Action, Owner, Due, Tracking columns)")
        return
    rep.error(start + 1, "action-items", "action items are bullets with no owner, due date, or tracking link; convert them to a table with Action, Owner, Due, and Tracking columns")
    for ln, text in bullets:
        trailing = re.search(r"\(([^()]*)\)\s*$", text)
        action = PAREN.sub("", text).strip() if trailing else text
        if trailing and GROUP_OWNER.match(trailing.group(1).strip()):
            rep.warn(ln, "action-items", f"owner '{trailing.group(1).strip()}' looks like a group; name one accountable person")
        check_action_wording(ln, action, rep)


def check_impact(lines, mask, headings, rep):
    ranges = list(section_ranges(headings, len(lines), r"impact"))
    if not ranges:
        return
    start, end = ranges[0]
    body = [re.sub(r"_[^_]*_", "", lines[i]) for i in range(start + 1, end) if mask[i]]
    if not any(re.search(r"\d", line) for line in body):
        rep.warn(start + 1, "impact", "impact section contains no numbers; quantify duration, users, error rate, budget, data")


def check_language(lines, mask, rep):
    for i, line in enumerate(lines):
        if not mask[i]:
            continue
        text = re.sub(r"`[^`]*`", "", line)
        text = re.sub(r"\]\([^)]*\)", "]", text)          # link targets
        text = re.sub(r"\S+@\S+\.\w+", "", text)           # e-mail addresses
        for pattern, why in LANGUAGE_RULES:
            m = re.search(pattern, text, re.I)
            if m:
                rep.warn(i + 1, "language", f"'{m.group(0)}': {why}")


def check_todos(lines, rep):
    for i, line in enumerate(lines):
        if re.search(r"TODO\(confirm\)", re.sub(r"`[^`]*`", "", line)):
            rep.warn(i + 1, "todo", "unresolved TODO(confirm); resolve before publishing")


def lint_text(text, light=False):
    rep = Report()
    lines, mask, headings = parse_lines(text)
    check_sections(headings, light, rep)
    check_timeline(lines, mask, headings, rep)
    check_actions(lines, mask, headings, rep)
    check_impact(lines, mask, headings, rep)
    check_language(lines, mask, rep)
    check_todos(lines, rep)
    return rep


# ---------------------------------------------------------------------------
# Self-test: regression cases for the checks above. Run with --selftest.

_ACTION_TABLE = """
| # | Action | Type | Addresses | Priority | Owner | Due | Tracking |
|---|---|---|---|---|---|---|---|
| 1 | Add a CI check that rejects retry config without backoff | prevent | CF1 | P1 | A. Lee | 2026-04-01 | T-1 |
"""

_SELF_TESTS = [
    (
        "a level-1 title naming impact and timeline does not satisfy those sections",
        "# Postmortem: High-impact timeline drift in billing\n\n## Summary\nBilling broke.\n\n"
        "## Contributing factors\nx\n\n## What went well\n- x\n\n## What went poorly\n- x\n\n"
        "## Where we got lucky\n- x\n\n## Action items\n" + _ACTION_TABLE + "\n## Lessons learned\n- x\n",
        False,
        {"errors": ["missing section: Impact", "missing section: Timeline"]},
    ),
    (
        "a level-1 title starting with 'Impact' does not satisfy the Impact section",
        "# Impact on checkout during the March node rotation\n\n## Summary\nx\n\n"
        "## Timeline\n| Time (UTC) | Event | Source |\n|---|---|---|\n| 2026-03-01 10:00 | alert | log |\n\n"
        "## Contributing factors\nx\n\n## Where we got lucky\n- x\n\n## Action items\n" + _ACTION_TABLE,
        True,
        {"errors": ["missing section: Impact"]},
    ),
    (
        "--light still requires 'Where we got lucky'",
        "# Postmortem: Near miss on a migration\n\n## Summary\nx\n\n## Impact\nNone, near miss; 0 users.\n\n"
        "## Timeline\n| Time (UTC) | Event | Source |\n|---|---|---|\n| 2026-03-01 10:00 | migration started | log |\n\n"
        "## Contributing factors\nx\n\n## Action items\n" + _ACTION_TABLE,
        True,
        {"errors": ["missing section: Where we got lucky"]},
    ),
    (
        "a bulleted draft gets 12-hour, bullet-action, vague-wording, and group-owner findings",
        "# Postmortem: Login outage\n## Summary\nx\n## Impact\nSome users could not log in.\n"
        "## Timeline\n- 3:05pm config deployed\n- 3:20pm customers complain\n"
        "## Root cause\nx\n## Action items\n- Be more careful with config changes (team)\n- Improve monitoring\n",
        True,
        {
            "errors": ["non-UTC or 12-hour timestamp '3:05pm'", "action items are bullets"],
            "warnings": ["a hope, not a control", "'Improve monitoring' is too vague", "owner 'team' looks like a group", "impact section contains no numbers"],
        },
    ),
    (
        "a UTC time with the original local time in parentheses is accepted",
        "# Postmortem: x\n## Summary\nx\n## Impact\n3 minutes.\n"
        "## Timeline\n| Time (UTC) | Event | Source |\n|---|---|---|\n"
        "| 2026-03-14 14:02 UTC (09:02 CDT) | alert | paging log |\n| 2026-03-14 14:05 | rollback | deploy log |\n"
        "## Contributing factors\nx\n## Where we got lucky\n- x\n## Action items\n" + _ACTION_TABLE,
        True,
        {"no_errors": True},
    ),
]


def self_test():
    failures = 0
    cases = list(_SELF_TESTS)
    example = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "references", "example-postmortem.md")
    if os.path.exists(example):
        with open(example, encoding="utf-8") as fh:
            cases.append(("the bundled example postmortem has no errors", fh.read(), False, {"no_errors": True}))
    for name, text, light, expect in cases:
        rep = lint_text(text, light)
        errs = [e["message"] for e in rep.errors]
        warns = [w["message"] for w in rep.warnings]
        problems = []
        if expect.get("no_errors") and errs:
            problems.append(f"expected no errors, got {errs}")
        for needle in expect.get("errors", []):
            if not any(needle in e for e in errs):
                problems.append(f"missing error containing {needle!r}; got {errs}")
        for needle in expect.get("warnings", []):
            if not any(needle in w for w in warns):
                problems.append(f"missing warning containing {needle!r}; got {warns}")
        status = "FAIL" if problems else "ok  "
        print(f"{status} {name}")
        for p in problems:
            print(f"       {p}")
        failures += bool(problems)
    print(f"{len(cases) - failures}/{len(cases)} self-tests passed")
    return 1 if failures else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Lint a Markdown postmortem.")
    ap.add_argument("file", nargs="?")
    ap.add_argument("--light", action="store_true", help="only require the lightweight-variant sections")
    ap.add_argument("--strict", action="store_true", help="treat warnings as errors")
    ap.add_argument("--json", action="store_true", help="print a JSON report")
    ap.add_argument(
        "--selftest", "--self-test", dest="self_test", action="store_true", help="run the built-in regression cases"
    )
    args = ap.parse_args(argv)

    if args.self_test:
        return self_test()
    if not args.file:
        ap.print_usage(sys.stderr)
        return 2

    try:
        with open(args.file, encoding="utf-8") as fh:
            text = fh.read()
    except OSError as exc:
        print(f"lint_postmortem: cannot read {args.file}: {exc}", file=sys.stderr)
        return 2

    rep = lint_text(text, args.light)

    failed = bool(rep.errors) or (args.strict and bool(rep.warnings))
    if args.json:
        print(json.dumps({"file": args.file, "passed": not failed, "errors": rep.errors, "warnings": rep.warnings}, indent=2))
    else:
        print(f"lint_postmortem: {args.file}")
        for kind, items in (("ERROR", rep.errors), ("WARN ", rep.warnings)):
            for item in sorted(items, key=lambda x: x["line"] or 0):
                where = f"L{item['line']}" if item["line"] else "-"
                print(f"{kind} {where:>6}  {item['check']}: {item['message']}")
        print(f"{len(rep.errors)} error(s), {len(rep.warnings)} warning(s)" + (" [strict]" if args.strict else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
