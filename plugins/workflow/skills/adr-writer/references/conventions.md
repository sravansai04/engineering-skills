# ADR Conventions, Tooling, and Numbering

Read this when step 2 turns up ADR tooling, an unusual layout, a monorepo, or date-prefixed files, or when two branches may have claimed the same number.

## Contents

1. Recognising the convention in use
2. adr-tools
3. log4brains
4. MADR folders and versions
5. Numbering and collisions
6. Monorepos and multiple ADR folders
7. Index maintenance
8. Status formats and spelling
9. Referencing ADRs from code and PRs
10. Retroactive ADRs

## 1. Recognising the convention in use

| Signal in the repo | Convention | Default folder | Filename pattern |
|---|---|---|---|
| `.adr-dir` file at the root (it contains the folder path) | adr-tools | `doc/adr` | `0007-use-x.md` (4-digit, zero-padded) |
| `.log4brains.yml` with `project.adrFolder` | log4brains (MADR 2-based template with `- Status:` / `- Deciders:` / `- Tags:` bullets) | whatever `adrFolder` says, often `docs/adr` | no required scheme; examples use `20240115-use-x.md` |
| YAML front matter with `decision-makers:`, quoted `status:` | MADR 4 | `docs/decisions` | `0007-use-x.md` |
| YAML front matter with `deciders:` | MADR 3 | `docs/decisions` | `0007-use-x.md` |
| `* Status:` / `* Deciders:` bullets, "Positive Consequences" / "Negative Consequences" headings, optional `Technical Story:` line | MADR 2 | `docs/adr` | `0007-use-x.md` |
| `## Status` heading, then Context / Decision / Consequences | Nygard or adr-tools | `doc/adr`, `doc/arch` | `0007-...` or `adr-007.md` |

Whatever is already in the repo outranks this table. If several conventions coexist, follow the most recent ADRs and mention the inconsistency in your report. Don't migrate old files unless the user asks you to.

## 2. adr-tools

adr-tools is a shell-script CLI (`npryce/adr-tools`; last tagged release 3.0.0, 2018, and still common). Only run it if it's already installed (`command -v adr`). Don't install it unasked.

| Command | Effect |
|---|---|
| `adr init doc/architecture/decisions` | Creates the folder, writes `.adr-dir`, and adds ADR 1, "Record architecture decisions" |
| `adr new Use PostgreSQL for the billing ledger` | Creates the next-numbered file. The title words are joined, so quotes are optional. |
| `adr new -s 12 Use PostgreSQL for the billing ledger` | Supersedes ADR 12: adds links both ways and replaces ADR 12's "Accepted" status |
| `adr new -l "5:Amends:Amended by" New title` | Links to ADR 5 with a forward and a reverse description |
| `adr link 12 Amends 10 "Amended by"` | Links two existing ADRs |
| `adr list` | Lists ADR files in order |
| `adr generate toc` | Prints a Markdown table of contents to stdout. `-p PREFIX` prefixes the links. |

Things to watch for:

- `adr new` opens `$VISUAL`, or `$EDITOR` if `VISUAL` is unset, and waits. In an automated session, prefix the command with `VISUAL=true` so it returns right away and prints the new file path.
- New ADRs get status **Accepted** whatever their real state. Change it to Proposed when the decision is still under review.
- The tool writes "Superceded" / "Supercedes". Keep whatever spelling the existing files use, so a grep finds all of them.
- If `templates/template.md` exists inside the ADR folder, it's used instead of the built-in Nygard template. The `ADR_TEMPLATE` environment variable overrides both.
- Without `.adr-dir`, the tool assumes `doc/adr`. Check that you're running it from the repo root.

## 3. log4brains

log4brains is a Node.js CLI and static site generator. Use it only when `.log4brains.yml` exists, and run it the way the project already does (for example through an npm script or `npx`).

- `log4brains adr new --quiet "Title"` creates an ADR from the template without prompting. `-p NAME` targets a package-specific folder, and `--from FILE` seeds the ADR from a file.
- `log4brains adr list` lists ADRs. `-s accepted,proposed` filters by status, and `-r` prints raw output.
- The ADR folder holds `template.md` and `index.md`. Edit `template.md` only if the user asks you to change the team's template.
- Statuses include `draft` alongside proposed, rejected, accepted, deprecated, and superseded.
- Filenames are date-prefixed and unnumbered, so refer to ADRs by filename (`20240115-use-x`) rather than by number. Point supersession links at the filename too.

## 4. MADR folders and versions

- MADR 2 puts metadata in `* Status:` / `* Deciders:` / `* Date:` bullets, has an optional `Technical Story:` line, and splits "Positive Consequences" from "Negative Consequences".
- MADR 3 (2022) moved the recommended folder from `docs/adr` to `docs/decisions`, moved the metadata into YAML front matter (`status`, `date`, `deciders`, plus new `consulted` and `informed`), dropped the Technical Story line in favor of the problem statement, and merged the consequences into one list of "Good, because / Bad, because / Neutral, because" items. Its `status` may still contain a Markdown link.
- MADR 4 (2024) renamed `deciders` to `decision-makers`, quotes the `status` value and allows only the identifier there (`status: "superseded by ADR-0123"`, no link), renamed "Validation" to "Confirmation" and moved it under Decision Outcome, and added minimal and bare template variants.
- In MADR 2 through 4, `date` means when the record was last updated.
- Large projects may split decisions into subfolders (`docs/decisions/backend/`). Follow whatever split already exists.

## 5. Numbering and collisions

- Next number = highest existing number + 1. Numbers are permanent identifiers. Gaps are harmless; reuse is not.
- Match the existing zero-padding width (`007` vs `0007`), the separator, and any prefix (`adr-007`, `ADR-0007`).
- Parallel branches can claim the same number. Before merging, compare against the default branch and against open PRs:

  ```bash
  ADR_DIR=docs/adr
  BASE=$(git symbolic-ref --short refs/remotes/origin/HEAD 2>/dev/null || echo origin/main)
  git fetch --quiet origin
  # Highest number on the default branch
  git ls-tree --name-only "$BASE" "$ADR_DIR/" | sed 's#.*/##' \
    | sed -nE 's/^[^0-9]*([0-9]+).*/\1/p' | sort -n | tail -1
  # ADR files touched by open PRs (requires the GitHub CLI)
  gh pr list --state open --limit 100 --json number,files \
    --jq '.[] | .number as $n | .files[].path | select(test("(^|/)(adrs?|decisions|architecture[-_]decisions?)/")) | "#\($n) \(.)"'
  ```

- If there's a collision, renumber the ADR that hasn't merged yet. Rename the file with `git mv`, then update its title line, the index entry, and every link to it. Renumbering a Proposed ADR is fine. Never renumber an Accepted one.
- If collisions keep happening, suggest the team switch to date-prefixed names (log4brains-style) or assign numbers at merge time. Raise it as a suggestion and don't make the change yourself, because it changes team process.

## 6. Monorepos and multiple ADR folders

- Cross-cutting decisions go in the root ADR folder. Decisions that only affect one package or service go in that package's folder, if the repo already has per-package folders.
- If a decision affects several packages but not the whole system, put it at the root and list the affected packages in its scope statement.
- Link between folders with relative paths. Don't duplicate an ADR in two places.

## 7. Index maintenance

Common index forms (update whichever exists, in its existing format):

- A table or list in the ADR folder's `README.md` or `index.md`, showing number, title, status, and date
- A docs-site nav or sidebar file (`mkdocs.yml` `nav:`, a Docusaurus sidebar, and so on)
- A generated table of contents (`adr generate toc`), or the site log4brains builds on its own

When an ADR is superseded, update the old entry's status in the index too, if the index shows status.

## 8. Status formats and spelling

- Match the existing case and wording exactly ("Accepted" vs "accepted", "Superseded by" vs "superseded by"). Status values get grepped and parsed.
- Put the status where the repo puts it: YAML front matter, a `## Status` section, or a `* Status:` / `- Status:` bullet. Quote it in YAML if the existing files do (MADR 4).
- Date convention: MADR's `date` is when the record was last updated, so a status change moves it. Some teams keep the decision date instead. Follow what the existing files do, and keep the original decision date visible either way (SKILL.md step 8, "Dates").

## 9. Referencing ADRs from code and PRs

Discoverability is the weakest part of most ADR practices. Where it helps, suggest the following (they're optional, and depend on the team's taste):

- A short code comment at the point where the decision shows up, such as `# See docs/adr/0019-adopt-transactional-outbox.md`, so the next engineer finds the reasoning before "fixing" it.
- A link to the ADR in the description of the PR that implements it.
- Under the ADR's Confirmation section, an automated check (a dependency rule, an architecture test, a lint rule) that names the ADR in its failure message.

## 10. Retroactive ADRs

Documenting a decision made long ago is worth doing when the reasoning is still recoverable. Make that honest:

- State in the context that the ADR was recorded retroactively, the date it was written, and roughly when the decision was made.
- Separate what was known then from what has been learned since. Put the latter under consequences ("observed since adoption").
- Set the status to Accepted only if the decision is still in force. If it's been reversed, write it as Superseded or Deprecated, and link to the replacement if there is one.
