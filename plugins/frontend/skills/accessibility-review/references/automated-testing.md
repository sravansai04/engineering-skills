# Automated testing: scanners, linters, regression tests, and CI

Read this when choosing or running automated checks, interpreting their output, or adding
accessibility regression tests and CI gates.

## Contents
1. What automation can and cannot tell you
2. The scripts bundled with this skill
3. axe-core in browser tests (Playwright, Cypress)
4. Component and unit level (jest-axe, vitest-axe, Testing Library, Storybook)
5. Command-line scanners (axe CLI, pa11y, Lighthouse)
6. Linters
7. CI strategy
8. Triage: false positives, "needs review", third-party content

---

## 1. What automation can and cannot tell you

axe-core is the engine behind most tools (Lighthouse, the axe CLI and browser extension,
`@axe-core/playwright`, `cypress-axe`, `jest-axe`, Storybook's addon). In axe-core 4.13, rules
that actually run touch 20 of the 55 WCAG 2.2 A/AA success criteria (22 if you also request
the experimental rules); 4.14 turned `label-content-name-mismatch` (2.5.3) on by default, making
21. For almost all of those the rule checks only *part* of the criterion: that an `alt` exists,
not that it is right; that a button has a name, not that the name makes sense. Nothing automated
checks focus order, focus visibility, keyboard traps, focus management after dialogs or route
changes, whether status messages are announced, reflow at 320 px, non-text contrast, or whether
headings and labels are meaningful.

Counts like these move with every axe release, so recount for the version the project has
installed instead of quoting a number. Run this where `axe-core` resolves; it prints the version,
a count, and the criteria. The list includes 2.1.3, an AAA criterion that shares a rule with
2.1.1, so subtract one (4.13 prints 21, meaning 20 A/AA criteria):

```bash
node -e 'const a=require("axe-core"),s=new Set();for(const r of a.getRules()){const t=r.tags;if(t.includes("deprecated")||t.includes("experimental")||!t.some(x=>/^wcag2(1|2)?aa?$/.test(x)))continue;for(const x of t){const m=x.match(/^wcag(\d)(\d)(\d+)$/);if(m)s.add(m.slice(1).join("."))}}console.log(a.version,s.size,[...s].sort().join(" "))'
```

**Rules that are off unless you ask for them.** `target-size` (2.5.8) ships disabled and runs
only when the run requests the `wcag22aa` tag or enables the rule by id. A bare `axe.run()`,
`new AxeBuilder({ page }).analyze()` without tags, jest-axe, vitest-axe, Storybook's addon-a11y,
pa11y's axe runner, and any harness whose tags stop at `wcag21aa` never check 2.5.8, and say
nothing about it. Experimental rules (for example `css-orientation-lock` for 1.3.4, and
`label-content-name-mismatch` for 2.5.3 up to 4.13) run only when you add the `experimental`
tag or enable them by id. Deprecated rules (`audio-caption`, `duplicate-id`, `duplicate-id-active`)
never run by default.

Consequences for how you report:

- A clean scan means "no *detectable* violations in the scanned states, with these tags, in this
  axe version". Never report it as "accessible" or "WCAG compliant", and record the version and
  tags in the report.
- An axe *violation* is usually real (axe is tuned to avoid false positives), but confirm the
  user impact before assigning severity.
- Axe's *incomplete* ("needs review") results are work items for a human, not passes.
- Lighthouse's accessibility score is a weighted subset of axe rules; a 100 says nothing about
  the criteria above.

## 2. The scripts bundled with this skill

`contrast.mjs` has no dependencies. `axe-scan.mjs` and `keyboard-walk.mjs` need Node 20+
(Playwright's minimum) and `playwright`; keyboard-walk needs Playwright 1.49 or later because it
reads roles and names with `locator.ariaSnapshot()` (it exits with an error on older versions
rather than skip those checks), and axe-scan also needs `@axe-core/playwright`. They load these
from the **current working directory** (run them from the project root) or from next to the
script. If the project lacks them, ask before adding them, because the install edits its
manifest and lockfile:
`npm i -D playwright @axe-core/playwright && npx playwright install chromium`. The alternative
is to install them into a scratch directory and run the scripts from there, passing `--setup`
files as absolute paths. All three scripts accept `-h`/`--help`, and `--selftest` checks the
logic that runs outside the browser (argument parsing, tag-to-criterion mapping, the PNG pixel
diff, the color math) with no dependencies.

| Script | Purpose | Exit codes |
|---|---|---|
| `scripts/axe-scan.mjs` | axe across URLs × viewports (default 1280×800 and 320×640) × states (`--setup`/`--click`), grouped by rule with SC numbers and level, de-duplicated across viewports and states, plus the "needs review" list and the axe-core version | 0 clean, 1 violations at/above `--fail-on`, 2 error (including any run that hit an HTTP error, a redirect, or a failed setup) |
| `scripts/keyboard-walk.mjs` | Presses Tab through a page (optionally in a `--setup` state) and records each stop's role, name, and selector; flags missing indicator, obscured/invisible focus, unnamed or role-less stops, positive tabindex, traps, focus getting stuck, unreached controls (one per radio group; scoped to an open modal), and pointer-only elements; optional numbered focus-order screenshot | 0 no leads, 1 leads, 2 error (including an HTTP error, a redirect, or a failed setup) |
| `scripts/contrast.mjs` | WCAG contrast for hex/rgb/hsl/oklch colors with alpha compositing; PASS/FAIL for 1.4.3, 1.4.11, 1.4.6; nearest passing colors | 0 meets `--target`, 1 below, 2 error |

`${CLAUDE_SKILL_DIR}` in these commands is not a shell variable: replace it with this skill's directory, the path SKILL.md shows for `scripts/`, and keep the quotes.

```bash
node "${CLAUDE_SKILL_DIR}/scripts/axe-scan.mjs" http://localhost:3000/ http://localhost:3000/signup \
  --storage-state .auth/user.json --wait-for main --json a11y-axe.json
node "${CLAUDE_SKILL_DIR}/scripts/keyboard-walk.mjs" http://localhost:3000/signup --screenshot signup-focus.png
node "${CLAUDE_SKILL_DIR}/scripts/contrast.mjs" '#64748b' '#f1f5f9'
```

**States.** Both scripts test the page as a URL loads it unless you drive it somewhere else
first. A `--setup <file.mjs>` module exports one function that receives the Playwright page
after load (and after `--wait-for`) and must leave it in the state to test, waiting for that
state before it returns:

```js
// open-address-dialog.mjs
export default async (page) => {
  await page.getByRole('button', { name: 'Edit address' }).click();
  await page.getByRole('dialog', { name: 'Edit address' }).waitFor();
};
```

axe-scan accepts several `--setup` files and scans each as its own state next to the initial load
(`--no-initial` skips the load itself); scope a state's scan with `--include 'dialog[open]'`.
keyboard-walk takes one `--setup`. Both accept repeatable `--click <css>` as a shorthand for a
state reached by clicks. A setup that fails is an error for that run, never a clean result.

**Wrong-page guard.** Both scripts stop with exit code 2 on an HTTP status of 400 or more, or
when the page they land on (before or after `--wait-for`) is not the URL they were given, which
is what an expired `--storage-state` sending you to a login screen looks like. Pass
`--allow-redirect` only when the redirect is intended.

Other options: `axe-scan.mjs --best-practice` adds axe's best-practice rules (reported
separately and never with an SC), `--include`/`--exclude` scope by CSS selector, `--color-scheme
dark` scans the dark theme, `--fail-on serious` relaxes the exit code for legacy apps.
`keyboard-walk.mjs --max 400` for long pages, `--viewport 390x844` for mobile layouts, `--headed`
to watch. Both accept `--storage-state` (a Playwright storage-state file) for logged-in pages.

The walk's flags are leads. `evals/files/` contains a checkout page with planted defects and a
keyboard-trap page, and `evals/files/EXPECTED.md` lists exactly what each script must report on
them (and what it must not, such as the non-checked radios of a group); rerun them after editing
either script. Heuristics can still misfire on real pages: a focus style applied to a distant
element, an animation unrelated to focus, or `pointer-events: none` overlays can all mislead the
walk. Confirm each flag by looking.

## 3. axe-core in browser tests

Scanning only the initial page load misses most bugs; drive the UI into each important state
(menu open, dialog open, validation errors, empty and loaded lists) and scan again, scoped to
the part that changed.

**Playwright** (`npm i -D @playwright/test @axe-core/playwright`):

```ts
import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

const WCAG_AA = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'];

test('profile page and its edit dialog have no detectable WCAG A/AA violations', async ({ page }) => {
  await page.goto('/profile');
  expect((await new AxeBuilder({ page }).withTags(WCAG_AA).analyze()).violations).toEqual([]);

  await page.getByRole('button', { name: 'Edit address' }).click();
  const dialog = page.getByRole('dialog', { name: 'Edit address' });
  await expect(dialog).toBeVisible();
  const inDialog = await new AxeBuilder({ page }).withTags(WCAG_AA).include('dialog[open]').analyze();
  expect(inDialog.violations).toEqual([]);
});

test('edit dialog: focus moves in, Escape closes, focus returns to the trigger', async ({ page }) => {
  await page.goto('/profile');
  const trigger = page.getByRole('button', { name: 'Edit address' });
  await trigger.focus();
  await page.keyboard.press('Enter');
  const dialog = page.getByRole('dialog', { name: 'Edit address' });
  await expect(dialog).toBeVisible();
  await expect(dialog.locator(':focus')).toHaveCount(1);
  await page.keyboard.press('Escape');
  await expect(dialog).toBeHidden();
  await expect(trigger).toBeFocused();
});

test('icon buttons expose names and errors are tied to fields', async ({ page }) => {
  await page.goto('/signup');
  await expect(page.getByRole('button', { name: 'Show password' })).toBeVisible();
  await page.getByRole('button', { name: 'Create account' }).click();
  await expect(page.getByLabel('Email address')).toHaveAccessibleDescription(/enter an email/i);
});
```

Keep `wcag22aa` in any tag list you write; without it `target-size` (2.5.8) does not run.

Useful locator assertions (Playwright ≥ 1.44 unless noted): `toHaveAccessibleName`,
`toHaveAccessibleDescription`, `toHaveRole`, `toBeFocused`, `toHaveAccessibleErrorMessage`
(1.50, for `aria-errormessage`), and `toMatchAriaSnapshot` (1.49) for locking down the
accessibility tree of a component. Querying with `getByRole(…, { name })` is itself an
accessibility test: it fails when the name or role is wrong.

Emulate user settings per test with `page.emulateMedia({ reducedMotion: 'reduce' })`,
`{ colorScheme: 'dark' }`, `{ forcedColors: 'active' }`, or `{ contrast: 'more' }` (1.51+), and
reflow with `page.setViewportSize({ width: 320, height: 640 })`.

**Cypress** (`npm i -D cypress-axe axe-core`, then `import 'cypress-axe'` in the support file):

```js
it('settings page has no detectable WCAG A/AA violations', () => {
  cy.visit('/settings');
  cy.injectAxe(); // after cy.visit
  cy.checkA11y(null, {
    runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'] },
  });
});
```

`checkA11y` also accepts `includedImpacts` (e.g. `['critical', 'serious']`) to phase in a gate
on a legacy app.

## 4. Component and unit level

**jest-axe** (`npm i -D jest-axe`; jsdom environment):

```js
import { render } from '@testing-library/react';
import { axe, toHaveNoViolations } from 'jest-axe';
expect.extend(toHaveNoViolations);

it('SignupForm has no detectable violations', async () => {
  const { container } = render(<SignupForm />);
  expect(await axe(container)).toHaveNoViolations();
});
```

**vitest-axe** (`npm i -D vitest-axe`): `import { axe } from 'vitest-axe'` and
`import 'vitest-axe/extend-expect'` (or `expect.extend(matchers)` from `vitest-axe/matchers`).
It does not work with the happy-dom environment; use jsdom.

jsdom has no layout or rendering: color contrast is turned off in jest-axe, and target size,
reflow, focus visibility, and anything visual cannot be tested there (jest-axe and vitest-axe
also run axe's defaults, so `target-size` is off anyway). Keep those in browser tests.

**Testing Library** queries double as checks: `screen.getByRole('button', { name: /close/i })`,
`getByLabelText('Email address')`, and with `@testing-library/user-event`, `await user.tab()`
followed by `expect(element).toHaveFocus()` (jest-dom) to assert focus order and management.

**Storybook:** `@storybook/addon-a11y` runs axe on each story in the UI; recent versions can also
fail story tests on violations. Check the configuration for your Storybook version. It passes
axe's default options, so 2.5.8 is unchecked unless you set `parameters.a11y.options.runOnly`
to tags that include `wcag22aa`. Stories of each state (error, disabled, open) are where
component-level coverage comes from.

## 5. Command-line scanners

```bash
# axe CLI. Needs a ChromeDriver matching your Chrome (npx browser-driver-manager install chrome)
npx @axe-core/cli http://localhost:3000 --tags wcag2a,wcag2aa,wcag21a,wcag21aa,wcag22aa --exit

# pa11y. Default runner is HTML_CodeSniffer, a second opinion from a different engine
npx pa11y --standard WCAG2AA http://localhost:3000
npx pa11y --runner axe --reporter json http://localhost:3000 > pa11y.json

# Lighthouse accessibility category only (a subset of axe rules; the score is not conformance)
npx lighthouse http://localhost:3000 --only-categories=accessibility \
  --output=json --output-path=./lighthouse-a11y.json --chrome-flags="--headless"
```

`pa11y-ci` runs pa11y across a list of URLs from a config file for CI. Know its limits before
trusting it for a 2.2 review:

- **`--runner axe`** turns `--standard WCAG2AA` into the tags `wcag2a, wcag21a, wcag2aa,
  wcag21aa` plus `best-practice`. It never requests `wcag22aa`, so 2.5.8 is never checked, and
  best-practice results are mixed in with the WCAG errors. Sort them before reporting, and cover
  2.5.8 with `axe-scan.mjs` or a Playwright test.
- **HTML_CodeSniffer** (the default runner) was last released in 2020, before WCAG 2.2, and has
  no checks for the criteria 2.2 added.
- **Lighthouse** runs axe with the `wcag2a`/`wcag2aa` tags plus a hand-picked list. It does
  enable `target-size`, but it turns off several WCAG rules (for example `nested-interactive`,
  `scrollable-region-focusable`, `role-img-alt`), so a 100 can coexist with failures axe-scan
  finds.

## 6. Linters

Linters catch source-level mistakes before anything renders: missing `alt`, click handlers on
non-interactive elements, invalid ARIA, positive `tabindex`, labels without controls.

| Stack | Tool | Flat-config usage |
|---|---|---|
| React / JSX | `eslint-plugin-jsx-a11y` | `jsxA11y.flatConfigs.recommended` (or `.strict`) |
| Vue | `eslint-plugin-vuejs-accessibility` | `...pluginVueA11y.configs['flat/recommended']` |
| Angular templates | `angular-eslint` | `...angular.configs.templateAccessibility` in the `**/*.html` block |
| Svelte | the Svelte compiler / `svelte-check` | built-in `a11y_*` warnings; fail CI on them |

Treat lint suppressions for these rules like security suppressions: each needs a reason.

## 7. CI strategy

- **Gate the flows that matter** (sign-in, sign-up, checkout, the product's primary task) in
  every important state, at two widths (desktop and 320 px) and in each theme you ship.
- **Ratchet legacy debt.** Baseline existing violations by rule + selector and fail only on new
  ones; burn the baseline down. Never disable a rule globally to get green; exclude a specific
  selector with a ticket reference.
- **Stabilize scans.** Wait for a ready selector instead of a timeout; emulate reduced motion so
  mid-animation colors don't create contrast noise; scan after fonts load.
- **Keep keyboard behavior in tests.** Add one focus-management test per dialog, menu, and
  route-change pattern (see the Playwright example); these are the regressions scanners never
  catch.
- **Publish the "needs review" list** as an artifact so humans actually see it.

## 8. Triage

- **color-contrast "needs review"**: text over images, gradients, pseudo-element backgrounds,
  or overlapping elements. Measure manually with `scripts/contrast.mjs` at the worst point.
- **target-size**: inline links in sentences are exempt; so are browser-default controls the
  author didn't restyle. Check the spacing exception before reporting.
- **region / landmark / heading rules** are best practices in axe (no SC). Report them as best
  practice, or tie them to 1.3.1/2.4.1 only when you can show the user impact.
- **`duplicate-id-aria`** (tagged 4.1.2) fires when an id referenced by `aria-labelledby`,
  `aria-describedby`, `for` or similar is duplicated, so the reference can resolve to the wrong
  element. That is a real relationship failure: confirm which element wins and report it under
  4.1.2 (or 1.3.1). The older `duplicate-id` and `duplicate-id-active` rules belong to the
  obsolete 4.1.1, are deprecated, and do not run by default; a duplicate id that breaks nothing
  is not a finding.
- **Hidden content**: a violation inside a closed menu or a `display: none` template may not be
  reachable; reproduce it in the state where users meet it.
- **Third-party widgets** (chat, consent banners, embedded players, maps): they are part of your
  page's conformance. Report them, contact the vendor, and if you must exclude them from CI,
  keep them in the report.
