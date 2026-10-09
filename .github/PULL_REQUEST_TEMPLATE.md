## Summary

<!-- What changes and why. Link the issue it closes, if any: "Closes #123". -->

## Type of change

- [ ] New skill
- [ ] Skill improvement (guidance, triggers, scripts, evals)
- [ ] Bug fix
- [ ] Documentation
- [ ] CI or repository tooling
- [ ] Other:

## Skills touched

<!-- As plugin:skill, one per line, e.g. review-suite:pr-review. Write "none" for repository-only changes. -->

## Before and after

<!-- For a skill change: one eval prompt, what Claude did without the change, and what it does with it.
     Use the Evidence format from docs/testing-skills.md, section 6 (Put the evidence in the pull request);
     for a small wording fix the three lines below are enough. Redact anything private. -->

**Prompt:**

**Before:**

**After:**

## Checklist

- [ ] `python3 -I scripts/validate_skills.py` passes.
- [ ] `claude plugin validate . --strict` passes, and so does `claude plugin validate plugins/<plugin> --strict` for every plugin I touched.
- [ ] Every command, flag, threshold and claim I added was checked by running it or against current documentation, not recalled.
- [ ] Trigger evals are updated on both sides: new phrasings are `should_trigger: true` here, and near misses that belong to a sibling skill are `false` here and `true` in that skill.
- [ ] `evals/evals.json` cases have checkable `expectations`, and the before and after above comes from one of them.
- [ ] The skill follows the conventions in CONTRIBUTING.md: the body skeleton, a description ending in a "Not for X (sibling)" list, `plugin:skill` references, the exact Related-skills fallback sentence, shared blocks unchanged or updated in every copy, and any bundled script supports `-h`/`--help` and `--selftest`.
- [ ] No secrets, credentials, real hostnames, or employer, customer or other proprietary content. Fixtures are obviously fake.
- [ ] `allowed-tools` stays read-only, and nothing destructive or outward-facing happens without the user's confirmation.
- [ ] The text is my own words, not copied from another skill collection or vendor docs.
- [ ] If users will notice the change: `version` is bumped in the plugin's `plugin.json` and in its `.claude-plugin/marketplace.json` entry, and the two match.
- [ ] `CHANGELOG.md` has an entry for the change.
