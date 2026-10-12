# Maintainer guide

How this repository is released, labelled, triaged and configured. The maintainer is [@sravansai04](https://github.com/sravansai04); anyone given write access later follows the same process.

## Releases

### How versions work

Claude Code delivers a plugin update only when the plugin's `version` changes. Users who added the marketplace track the default branch, so a merged version bump reaches them the next time they update, whether or not a release has been tagged. Two consequences follow:

- **A pull request that changes what a plugin ships bumps that plugin's version**, in `plugins/<plugin>/.claude-plugin/plugin.json` and in the plugin's entry in `.claude-plugin/marketplace.json`, to the same value. That is item 7 of the review bar in CONTRIBUTING.md. The repository validator fails when the two disagree. Changes that ship nothing to users (the README, `docs/`, CI, the validator) bump nothing.
- **A tagged release puts every plugin on one version.** The release workflow (`.github/workflows/release.yml`) refuses a `vX.Y.Z` tag unless every `plugin.json` and every marketplace entry carries `X.Y.Z` and `CHANGELOG.md` has a section for it, and then publishes that section as the GitHub release notes. Between releases a plugin's version can run ahead of the others; the release brings the rest up to it.

Pick each bump with Semantic Versioning, judged from a user's point of view:

| Change | Bump |
|---|---|
| Wording, a description tuned for better triggering, a corrected command or fact, new evals, a script fix | Patch |
| A new skill, a new reference file or capability, a new supported stack | Minor |
| A skill renamed or removed, a plugin renamed or split, or a change that breaks `/<plugin>:<skill>` or a documented output format people script against | Major |

The release version is at least the highest version any plugin reached since the last tag, and its level is the largest bump in the release: one major change makes the release major.

### Cutting a release

1. **Check main is releasable.** CI is green on the latest commit, and locally, with your denylist in place (CI cannot run the denylist scan, because its output is public):

   ```bash
   python3 -I scripts/validate_skills.py
   claude plugin validate . --strict
   for p in plugins/*/; do claude plugin validate "$p" --strict; done
   ```

2. **Work out the version.** See what changed since the last tag:

   ```bash
   git log --oneline "$(git describe --tags --abbrev=0)"..HEAD
   git diff "$(git describe --tags --abbrev=0)"..HEAD -- '*/plugin.json' .claude-plugin/marketplace.json
   ```

3. **Open a release pull request** (main is protected, so releases go through review like everything else) that:
   - sets `version` in every `plugin.json` and every marketplace entry to `X.Y.Z`;
   - moves the entries under `## [Unreleased]` into a new `## [X.Y.Z] - YYYY-MM-DD` section, with the date you will tag, grouped by plugin, and leaves an empty `## [Unreleased]` above it;
   - updates the link references at the bottom of `CHANGELOG.md`: `[Unreleased]` compares `vX.Y.Z...HEAD`, and a new `[X.Y.Z]` line points at the release tag.

   Before merging, check each plugin's versions agree (`claude plugin tag` refuses a dirty working tree, so commit first; `--dry-run` creates nothing):

   ```bash
   for p in plugins/*/; do claude plugin tag "$p" --dry-run; done
   ```

4. **Tag the merged commit** with an annotated tag and push it:

   ```bash
   git switch main && git pull --ff-only
   git tag -a vX.Y.Z -m "vX.Y.Z"
   git push origin vX.Y.Z
   ```

   The release workflow validates the tree, checks every version against the tag, refuses a release tag that is not on the default branch, and publishes the GitHub release from the changelog section. If the workflow fails, fix the cause in a pull request, then move the tag to the fixed commit (`git tag -d vX.Y.Z && git push origin :refs/tags/vX.Y.Z`, and tag again); don't publish the release by hand, or the notes and the checks drift apart. Only tag `vX.Y.Z`: per-plugin tags (what `claude plugin tag` would create without `--dry-run`) are not used here.

5. **Confirm it reached users.** On a machine with the marketplace installed, run `claude plugin marketplace update engineering-skills`, then `claude plugin update <plugin>@engineering-skills`, and check the new version in `claude plugin list`.

6. **Announce it** in the **Announcements** discussion category with a link to the release.

**Release candidates.** Marketplace users track the default branch, so a version merged there reaches every user as a normal update, whatever the tag says. Cut a release candidate from a short-lived branch that is never merged: branch from `main`, set every version to `X.Y.Z-rc.N`, add a `## [X.Y.Z-rc.N] - YYYY-MM-DD` section to `CHANGELOG.md`, commit, and tag that commit `vX.Y.Z-rc.N`. The workflow publishes it as a pre-release (the default-branch check skips pre-release tags), and testers load it from a checkout of the tag (`git switch --detach vX.Y.Z-rc.N`, then `claude --plugin-dir ./plugins`), or, on a machine that doesn't already have the marketplace, add it pinned to the tag (`claude plugin marketplace add sravansai04/engineering-skills#vX.Y.Z-rc.N`). Delete the branch once `vX.Y.Z` ships from `main`.

A hotfix follows the same steps with a patch version. There are no maintenance branches: only the latest release is supported (see SECURITY.md).

### Changelog entries

Every pull request that ships something to users adds a line under `## [Unreleased]`, in the Keep a Changelog groups (`Added`, `Changed`, `Deprecated`, `Removed`, `Fixed`, `Security`), naming the plugin and skill: "`review-suite`: `pr-review` no longer flags generated files as missing tests." Write for users, not for reviewers: what changed for them, not how.

## Labels

| Label | Use for |
|---|---|
| `type:bug` | A skill, script or document is wrong: bad advice, a command or flag that doesn't exist, a broken link, a script failure |
| `type:skill-improvement` | Improving an existing skill: its guidance, its triggers, or its coverage (the Skill improvement form applies it) |
| `type:skill-request` | Proposing or building a new skill (the Skill request form applies it) |
| `type:evals` | New or better trigger or behavior evals |
| `type:docs` | Documentation outside the skills: README, `docs/`, community files |
| `type:ci` | The validator, CI workflows, repository scripts (Dependabot applies it to its own pull requests) |
| `type:security` | Public hardening work. Vulnerabilities themselves are reported privately (SECURITY.md), never in a labelled issue |
| `plugin:implementation`, `plugin:review-suite`, `plugin:data-api`, `plugin:workflow`, `plugin:frontend`, `plugin:skill-dev` | The plugin an issue or pull request touches; several can apply |
| `status:needs-triage` | New and not yet looked at (the issue forms apply it) |
| `status:needs-info` | Waiting on the reporter |
| `status:accepted` | Confirmed and wanted; anyone may pick it up |
| `status:in-progress` | Someone is working on it; link the pull request |
| `status:blocked` | Waiting on something outside this issue (an upstream fix, a decision, another pull request) |
| `good first issue` | Small, self-contained, with pointers to the files involved and a clear definition of done |
| `help wanted` | Accepted, and the maintainer would welcome someone else taking it |
| `dependencies` | A dependency update; Dependabot applies it to its own pull requests |

`good first issue` and `help wanted` keep GitHub's exact names, because GitHub's contributor pages and search filters look for them.

**Creating them.** Run `scripts/setup_labels.sh` from a checkout, with `gh` signed in as someone with write access to the repository: once when the repository is set up, and again whenever this table changes. The script and this table must list the same labels, so change both in the same pull request; the repository validator fails if an issue form or `.github/dependabot.yml` applies a label the script does not create, because GitHub silently drops a label that doesn't exist. If GitHub's default labels that the `type:*` labels replace are still there afterwards (`bug`, `enhancement`, `documentation`), delete them by hand, for example `gh label delete enhancement --yes`. The script creates `dependencies` itself, so Dependabot's label exists even on a repository that never had GitHub's defaults.

**Rules of thumb.** Every open issue has one `type:*` and one `status:*`, plus a `plugin:*` when it concerns a plugin. Treat an issue with no `status:*` label as untriaged.

## Triage

This is a one-person project, so the targets are best effort and published so contributors know what to expect:

| What | First response | Then |
|---|---|---|
| Security report (private) | 5 business days | Assessment within 10 business days; see SECURITY.md |
| Conduct report (private) | 5 days | Handled under CODE_OF_CONDUCT.md |
| New issue | 7 days | Labelled, or a question back to the reporter |
| Pull request | 7 days | A review, or a note saying when one will come |
| Discussion question | Best effort | Community answers welcome |

Work through new items about once a week:

1. **Issues.** Reproduce or check the claim first. If information is missing, ask for it and add `status:needs-info`; close the issue after 14 days without a reply, saying it will be reopened when the details arrive. Close duplicates with a link to the original. A question filed as an issue moves to Discussions (**Convert to discussion** on the issue page). Otherwise apply the labels, and add `status:accepted` (plus `good first issue` or `help wanted` where they fit) once the change is wanted.
2. **Pull requests.** Hold them to the review bar in CONTRIBUTING.md: CI green, the before and after evidence in the description, the version bump and changelog line when something ships to users, and no overlap with a sibling skill. A pull request that adds a skill should link the Discussion or issue where it was agreed.
3. **Code from contributors.** Read eval cases, fixture scripts and skill scripts from a pull request before running anything from it on your machine, including `claude plugin eval`, which executes the plugin and its cases as you. The trust rule the review skills follow applies to maintainers too. CI runs fork pull requests with a read-only token and no secrets; keep it that way.
4. **Merging.** Squash-merge, with the pull request title as the commit subject. Don't merge your own pull request until CI is green, even where the ruleset allows you to.

## Go-public checklist

Work through this before switching the repository to public, and keep it for reference afterwards.

### Before changing visibility

- [ ] The repository validator passes **with the denylist in place**, so no employer, customer or internal name appears in any file or path.
- [ ] No private names or secrets in history either. A clean working tree doesn't clean history, and file contents are only one of three places a name can hide. Search all three for the denylist terms; any hit means rewriting history before the repository is public, not after:

  ```bash
  terms() { grep -v -e '^#' -e '^$' ~/.config/engineering-skills/denylist.txt; }
  git grep -i -F -f <(terms) $(git rev-list --all)                                       # file contents
  git log --all --format='%an%n%ae%n%cn%n%ce%n%B' | grep -i -n -F -f <(terms)              # messages and identities
  git log --all --name-only --format= | sort -u | grep -i -F -f <(terms)                   # file paths
  ```

  If you have it, also run a secret scanner over the history (`gitleaks git .`).
- [ ] Commit author and committer emails will become public. Check them with `git log --all --format='%an <%ae> / %cn <%ce>' | sort -u`, and set `user.email` to the private no-reply address GitHub provides (Settings, Emails) before the first public commit. Set it in the repository's own config (`git config user.email ...`), and for other clones of it, with an `includeIf "gitdir:..."` section in your global git config, so a fresh clone on another machine doesn't fall back to a work address. In GitHub's Settings, Emails, also turn on **Keep my email addresses private** (web merges then use the no-reply address) and **Block command line pushes that expose my email**. Run the check again before every release tag.
- [x] The README describes the repository as public: anonymous install with `claude plugin marketplace add sravansai04/engineering-skills`, with private-fork credentials only in a collapsed note.
- [ ] `.claude-plugin/marketplace.json` lists all six plugins, each with a `plugin.json`, and the versions agree.
- [ ] `LICENSE`, `CODE_OF_CONDUCT.md`, `CONTRIBUTING.md`, `SECURITY.md`, `SUPPORT.md` and the issue and pull request templates are on the default branch.

### Repository settings

- [ ] **Visibility.** Settings, General, Danger Zone: **Change repository visibility** to Public.
- [ ] **About box.** On the repository's home page, the gear next to **About**: a one-line description and topics. Topics are lowercase with hyphens, at most 20; for example `claude-code`, `claude-code-plugin`, `claude-code-skills`, `agent-skills`, `ai-coding`, `code-review`, `developer-tools`.
- [ ] **Social preview.** Settings, General, **Social preview**: upload an image of 1280 by 640 pixels (at least 640 by 320, under 1 MB). Make it yourself; no third-party logos.
- [ ] **Features.** Settings, General, Features: Issues on, **Discussions** on, Wikis off (the documentation lives in the repository, where it is reviewed).
- [ ] **Discussion categories.** In Discussions, edit the categories: keep **Announcements** (announcement format: only maintainers start threads), **Q&A** (question and answer format, so replies can be marked as answers), **Ideas** (new skills and bigger changes) and **Show and tell** (what people built with the skills); remove **Polls** and **General** unless you plan to use them. Pin a welcome post that links to SUPPORT.md, CONTRIBUTING.md and docs/roadmap.md.
- [ ] **Pull request merge options.** Settings, General, Pull Requests: allow squash merging only, default the squash commit message to the pull request title, turn on **Always suggest updating pull request branches** and **Automatically delete head branches**.
- [ ] **Ruleset on main.** Settings, Rules, **Rulesets**, **New ruleset**, **New branch ruleset**. Name it after the branch, set **Enforcement status** to Active, and under target branches add the default branch. Turn on:
  - **Restrict deletions** and **Block force pushes**;
  - **Require linear history** (squash merging already produces it);
  - **Require a pull request before merging**, with 1 required approval, **Dismiss stale pull request approvals when new commits are pushed**, **Require approval of the most recent reviewable push**, and **Require conversation resolution before merging**;
  - **Require status checks to pass**, with **Require branches to be up to date before merging**, adding every job from `.github/workflows/validate.yml` (at the time of writing: Repository validator, both Script self-tests jobs, claude plugin validate --strict, Agent Skills spec (skills-ref), and actionlint). Add them after CI has run once on a pull request, so their exact names appear in the picker.

  Then, under **Bypass list**, add the **Repository admin** role with the mode **For pull requests only**. GitHub doesn't let you approve your own pull request, so without this a sole maintainer could never merge; with it, you still have to open a pull request and you can't push to main directly.
- [ ] **Private vulnerability reporting.** Settings, Advanced Security (Code security on older layouts): **Private vulnerability reporting**, Enable. SECURITY.md and CODE_OF_CONDUCT.md both depend on it.
- [ ] **Dependabot.** On the same page: **Dependency graph** on, **Dependabot alerts** on, and **Dependabot security updates off**. Every npm, pip, Go and Maven manifest in this repository is an eval fixture, and several pin old versions on purpose (docs-lookup's evals test exactly that), so a security-update pull request would "fix" a fixture and break its eval. Dismiss an alert on a file under `plugins/*/skills/*/evals/files/` with the reason **Vulnerable code is not actually used** or **Used in tests**. The only real dependencies are the workflow actions, which `.github/dependabot.yml` keeps current through version updates; keep that file scoped to the `github-actions` ecosystem.
- [ ] **Secret scanning.** On the same page: **Secret scanning** (Secret Protection) on, and **Push protection** on, so a commit containing a recognized token is rejected at push time. GitHub enables some of this by default on public repositories; confirm each switch rather than assuming.
- [ ] **Code scanning.** Optionally, CodeQL **default setup** on the same page. It covers the Python and JavaScript helper scripts and the workflow files.
- [ ] **Actions.** Settings, Actions, General: **Workflow permissions** set to read repository contents only, and **Allow GitHub Actions to create and approve pull requests** off. For fork pull request workflows, require approval at least for first-time contributors.
- [ ] **Labels.** Run `scripts/setup_labels.sh` (see Labels above).
- [ ] **Community profile.** Insights, **Community standards**: every item should be checked. "Repository admins accept content reports" applies only to organization-owned repositories, so it stays unchecked here; reports go through the channels in CODE_OF_CONDUCT.md instead.

### After going public

- [ ] From a machine with no GitHub credentials, add the marketplace and install each plugin, following the README, to prove that anonymous install works.
- [ ] Open a test pull request from a fork (or ask a friend to) and check that every required check runs and reports, and that the pull request template is filled in.
- [ ] Tag the first release (see Releases), and announce it in Discussions.
