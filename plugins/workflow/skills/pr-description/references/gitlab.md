# GitLab and Other Hosts

Read this only when the remote is not GitHub. Write the description content exactly as SKILL.md describes. Only the mechanics change.

## GitLab merge requests

**Terms.** A pull request is a *merge request* (MR). MRs are referenced as `!123`, issues as `#123`, and issues in another project as `group/project#123`.

**Templates.**
- MR description templates live in `.gitlab/merge_request_templates/*.md`. Find them with `git ls-files '.gitlab/merge_request_templates/*'`.
- A template named `Default.md` (case-insensitive) is applied automatically. A project can also set a default in its merge request settings, which the files don't show. If recent MRs share a structure that no file explains, follow the recent MRs.
- Follow the same rules as for GitHub templates: keep the headings, answer every section, and tick only checkboxes that are true.

**Closing patterns.**
- By default these keywords close referenced issues: Close, Closes, Closed, Closing, Fix, Fixes, Fixed, Fixing, Resolve, Resolves, Resolved, Resolving, Implement, Implements, Implemented and Implementing.
- Issues close only when the MR merges into the project's default branch.
- Administrators can change the pattern. If recent MRs use a different convention, follow it.

**Commands.** Flags differ between `glab` versions, so run `glab mr create --help` before relying on any of them.

```bash
git ls-files '.gitlab/merge_request_templates/*'
glab mr view --output json                 # an MR already open for this branch?

git push -u origin "HEAD:refs/heads/<branch>"   # only after the branch guard in SKILL.md step 1
glab mr create --target-branch main --title "Prevent duplicate invoices on billing retry" \
  --description-file - --yes <<'MR_BODY'
## Summary
...
MR_BODY

glab mr update 123 --description-file - <<'MR_BODY'
...full updated description...
MR_BODY
```

- `--draft` marks the MR as a draft.
- `--template NAME` pre-fills the description from a template in `.gitlab/merge_request_templates/`.
- `--yes` skips the confirmation prompt, which matters in non-interactive runs.
- If your installed `glab` has no `--description-file`, write the body to a file and pass `--description "$(cat body.md)"` instead.
- Replacing the description overwrites it entirely, just as on GitHub. Read the current one first with `glab mr view 123` and keep content you didn't write.

## Other hosts

- **Bitbucket, Azure DevOps and others.** The description content is the same. Create the PR through the host's web UI or its official CLI. Check the host's own syntax for linking work items rather than assuming GitHub's closing keywords work there.
- **Gerrit and other commit-message-as-description workflows.** The reviewed text is the commit message itself, so use the `workflow:commit-message` skill. The structure here (why, testing, risk) still applies, but compressed into the commit body.
