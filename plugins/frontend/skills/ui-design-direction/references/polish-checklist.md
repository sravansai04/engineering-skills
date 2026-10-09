# UI polish checklist

Read this in step 6 (verify against the direction), after the UI renders. Each item is phrased so
it can be answered yes or no from evidence. The tag says how to get that evidence:

- **[auto]** a script or command answers it (`scripts/scan-hardcoded.mjs`, `scripts/token-contrast.mjs`).
  A clean scan answers only for what the scanner can see; values built at runtime (template strings,
  props, chart options in variables) still need a read of the diff.
- **[shot]** visible in the screenshot matrix
- **[hand]** needs interaction: keyboard, pointer, zoom, or a changed setting

Report every failed item in the final report, either fixed or waived with a reason. "Looks fine"
is not evidence; name what you looked at.

Contents: A Tokens · B Typography · C Spacing and alignment · D Color and contrast ·
E Interactive states · F Data states · G Responsive and input · H Motion · I Themes ·
J Icons and imagery · K Content · L Visual stability · M Distinctiveness · Screenshot matrix ·
Waivers

---

## A. Tokens and consistency
- [ ] [auto] No new hard-coded colors, lengths, shadows, durations, z-indexes, or font stacks in
      component code: `scan-hardcoded.mjs --changed` reports 0 new hits, or each remaining one is
      justified with `token-exempt:`. Native files it lists as not scanned were grepped instead.
- [ ] [hand] The diff has no visual values assembled at runtime (`${n}px`, inline numbers passed to
      chart, canvas, or animation libraries).
- [ ] [auto] Components reference semantic tokens, not primitives (search for `palette-` or the
      project's primitive prefix inside component files).
- [ ] [hand] Any token you added has a role-based name and lives in the token source, not in a
      component file.
- [ ] [shot] Sibling elements share radius, border width, and control height; nothing is "almost"
      the same (a 6px radius next to an 8px one).

## B. Typography
- [ ] [shot] Every text style on screen maps to a named type step; no one-off sizes.
- [ ] [shot] Hierarchy reads in a quick glance: one clear title, then section headings, then body.
- [ ] [shot] Paragraphs stay within roughly 45 to 75 characters per line at wide viewports.
- [ ] [shot] No orphaned single word on headline last lines where avoidable.
- [ ] [shot] Numbers in tables and changing values use tabular figures and align.
- [ ] [hand] Text zoomed to 200% (browser zoom) stays readable without clipping or overlap.
- [ ] [hand] With increased text spacing (line height 1.5, paragraph spacing 2x, letter spacing
      0.12em, word spacing 0.16em), nothing clips or overlaps (WCAG 1.4.12).

## C. Spacing and alignment
- [ ] [auto] Spacing values come from the scale.
- [ ] [shot] Related items sit closer together than unrelated ones (labels hug their fields;
      groups are separated more than items within a group).
- [ ] [shot] Edges align to a shared grid; no element is a few pixels off its neighbors.
- [ ] [shot] Padding inside containers is balanced (not tight on one side and loose on another),
      and optical alignment is corrected where needed (icons next to text, play triangles).

## D. Color and contrast
- [ ] [auto] Every text/background pair that occurs meets 4.5:1 (3:1 for large text) in every theme,
      checked by `token-contrast.mjs --pairs` with pairs that name tokens (or literals refreshed from
      the token source before this run).
- [ ] [auto] Control boundaries, meaningful icons, and focus indicators meet 3:1 against adjacent
      colors.
- [ ] [auto] Chart marks meet 3:1 against the plot background in every theme (`chart-*` pairs in the
      pairs file, `kind: ui`).
- [ ] [hand] The chart library is themed once from the `chart-*` tokens; no single chart's options
      carry a color.
- [ ] [shot] Under simulated protanopia, deuteranopia, and achromatopsia, every chart series is still
      distinguishable, and each chart is readable without color (direct labels, shapes, patterns).
- [ ] [shot] Accent color marks interactive or important things only; status colors appear only
      for status.
- [ ] [shot] No state or meaning relies on color alone (errors have text and an icon, selected
      items have a check or weight change, links in body text are underlined or otherwise distinct).
- [ ] [shot] Text over images or gradients stays legible at the worst point of the image (use a
      scrim token and check that composite).

## E. Interactive states (each interactive component)
- [ ] [hand] Hover styles exist and are limited to devices that hover (`@media (hover: hover)`;
      Tailwind v4's `hover:` variant already does this), so touch users do not get stuck hover
      states.
- [ ] [hand] Keyboard focus is always visible, uses `:focus-visible`, has 3:1 contrast against
      what surrounds it, and is not hidden behind sticky headers or footers (WCAG 2.4.11).
- [ ] [hand] Pressed/active, selected/checked, and current-page states are distinct from hover.
- [ ] [hand] Disabled looks disabled but still legible; if users need to know why it is disabled,
      the reason is shown nearby (or the control stays enabled and explains on submit).
- [ ] [hand] Loading/pending: the control shows progress, keeps its width (no layout jump), and
      prevents double submission.
- [ ] [hand] Validation errors appear next to the field, say what to do, and are announced; the
      field's error styling is not color-only.
- [ ] [hand] Read-only differs from disabled where both exist.

## F. Data and view states
- [ ] [shot] Empty: first-use empty (explains and offers the first action), no-results (says what
      was searched and how to widen it), and cleared/all-done states are distinct.
- [ ] [shot] Loading: skeletons match the final layout, or progress is shown for actions; nothing
      flashes for fast responses.
- [ ] [shot] Error: says what failed in plain language and offers a retry or next step; partial
      failure does not blank the whole view.
- [ ] [shot] Overflow: the longest realistic name, a huge number, many tags, and a long unbroken
      string (URL, email) wrap or truncate gracefully, with the full value available.
- [ ] [shot] Volume: one item, typical, and maximum realistic counts all look intentional.

## G. Responsive and input
- [ ] [shot] At 320px wide nothing scrolls horizontally except deliberate containers (data tables,
      carousels), and nothing is cut off.
- [ ] [shot] At each breakpoint the layout changes because the content needed it, not merely
      because a breakpoint exists; no awkward in-between widths (check a width between breakpoints).
- [ ] [shot] Wide screens: content has a maximum width; nothing stretches into unreadable lines.
- [ ] [hand] Pointer targets are at least 24x24 CSS px (or adequately spaced); primary touch
      targets near 44x44.
- [ ] [hand] Everything reachable with a pointer is reachable and operable with a keyboard, in a
      sensible order.
- [ ] [shot] Mobile: fixed bars respect safe areas; full-height layouts do not jump when browser
      chrome hides (dvh/svh).

## H. Motion
- [ ] [auto] Durations and easing come from tokens.
- [ ] [hand] Each animation has a purpose (feedback, continuity, attention); remove the rest.
- [ ] [hand] With reduced motion enabled, movement becomes a fade or an instant change, and nothing
      essential is lost.
- [ ] [hand] Only `transform` and `opacity` are animated in frequently repeated interactions.

## I. Themes
- [ ] [shot] Dark theme is a deliberate mapping: elevation reads, accents are not glaring, images
      and illustrations do not glow against the canvas.
- [ ] [hand] No flash of the wrong theme on load or navigation; native controls and scrollbars
      match (`color-scheme`).
- [ ] [hand] In forced-colors mode (Windows high contrast or browser emulation), focus indicators,
      control borders, and selected states remain visible.

## J. Icons and imagery
- [ ] [shot] One icon set, consistent stroke and size per context; icons align with text baselines.
- [ ] [auto] No emoji used as icons or bullets.
- [ ] [hand] Icon-only buttons have accessible names; decorative icons are hidden from assistive
      technology.
- [ ] [shot] Images share one treatment (ratio, radius, overlay) and have reserved space.

## K. Content
- [ ] [shot] Real or realistic content, never lorem ipsum or "Item 1, Item 2" in the reviewed UI.
- [ ] [shot] Each action label is a verb plus an object ("Send invoice", "Archive project"), and its
      success message reuses that verb in the past tense ("Invoice sent", "Project archived").
- [ ] [shot] One primary action per view or section; secondary actions look secondary.
- [ ] [shot] Labels and titles follow the project's capitalization convention consistently.
- [ ] [shot] No marketing filler in product UI ("seamless", "powerful", "unlock").

## L. Visual stability and performance you can see
- [ ] [hand] Fonts load without visible layout shift (metric-matched fallbacks or `optional`).
- [ ] [hand] Images and embeds have dimensions or aspect ratios; late content does not push the
      page around.
- [ ] [hand] Large decorative effects (blur, big shadows, filters) do not make scrolling stutter on
      a mid-range device.

## M. Distinctiveness (author and consolidate modes)
- [ ] [shot] The signature decision from the direction is visible in the screenshots.
- [ ] [shot] Swap test still passes: the screen would feel wrong for a competitor.
- [ ] [shot] Squint test: blur your eyes (or downscale the screenshot heavily); the most important
      thing on the screen is still the most prominent shape.
- [ ] [shot] Device count: count the separation devices (whitespace, hairline, tonal step, shadow)
      and decorative layers (gradients, illustrations, glows, background patterns) on the screen.
      If there are more than the direction allows, remove until the count matches and attach the
      before and after screenshots.

---

## Screenshot matrix

Capture at least: widths 320, 768, and 1280 (add 1440 or 1920 for dashboards and marketing pages)
x light and dark x the key states (default, focus-visible on the primary control, error, empty,
loading). 320 is the width at which WCAG 1.4.10 requires content to reflow without horizontal
scrolling, so it is the narrowest width that has a pass/fail meaning; it replaces the 375 default of
the browser-testing smoke script for this purpose.

**Primary path: the browser-testing smoke script** (`frontend:browser-testing`; `<browser-testing-dir>`
is that skill's directory, the sibling of this skill's folder when both come from the `frontend`
plugin, as the screenshot item of SKILL.md step 6 shows; run it from the project, where Playwright is
installed). If the script is not there, use the Playwright CLI fallback below. One run per
theme; it also reports horizontal overflow, console errors, and failed requests:

```bash
node <browser-testing-dir>/scripts/page-smoke.mjs http://localhost:3000/invoices \
  --widths 320,768,1280 --color-scheme light --wait-for-text "Invoices" --full-page --out shots/light
node <browser-testing-dir>/scripts/page-smoke.mjs http://localhost:3000/invoices \
  --widths 320,768,1280 --color-scheme dark --wait-for-text "Invoices" --full-page --out shots/dark
```

Wait for content that only exists once the view is ready (`--wait-for-text`), so the shot is not the
loading skeleton or the pre-font-swap frame. Capture loading states on purpose, never by accident.
States that need interaction (focus, error, empty) are captured by driving the page with the browser
tool, as described in that skill.

**Themes chosen by an attribute or a stored preference.** `--color-scheme` only emulates
`prefers-color-scheme`. If the app reads the theme from localStorage or a cookie, give the browser
that state before navigation with a storage-state file (`--storage-state` for page-smoke,
`--load-storage` for the Playwright CLI):

```json
{ "cookies": [],
  "origins": [ { "origin": "http://localhost:3000",
                 "localStorage": [ { "name": "theme", "value": "dark" } ] } ] }
```

Use the app's real key and value (search the theme toggle for `localStorage.setItem` or the cookie
name); for a cookie, add `{ "name": "theme", "value": "dark", "domain": "localhost", "path": "/",
"expires": -1, "httpOnly": false, "secure": false, "sameSite": "Lax" }` to `cookies`. If the app
supports a query parameter (`?theme=dark`), use that instead. In your own Playwright code,
`await context.addInitScript(() => { localStorage.setItem('theme', 'dark'); })` before `page.goto`
does the same; setting `document.documentElement.dataset.theme` there works only if the app does
not overwrite it while hydrating.

**Fallback: the Playwright CLI** (installs a browser on first use with
`npx playwright install chromium`):

```bash
mkdir -p shots
for w in 320 768 1280; do
  for scheme in light dark; do
    npx playwright screenshot --viewport-size "$w,900" --color-scheme "$scheme" --full-page \
      --wait-for-selector '[data-ready], main table' \
      http://localhost:3000/invoices "shots/invoices-$w-$scheme.png"
  done
done
```

Replace the selector with one that appears only when the content is ready (fallback:
`--wait-for-timeout 1500`), and add `--load-storage theme-dark.json` for attribute-based themes.

Look at every image you capture. A screenshot nobody inspected verifies nothing. If no browser can
be run in the environment, say so in the report and list what still needs a visual check. Do not
describe how the UI looks unless you have seen it.

## Waivers

A failed item may be waived only with a reason a reviewer can evaluate:

```
WAIVED [D. Color] focus ring vs accent button 1.13:1 - the ring is drawn at var(--focus-ring-offset)
from the button, so it sits on the canvas (4.79:1) and the accent-adjacent pair never occurs on screen.
```
