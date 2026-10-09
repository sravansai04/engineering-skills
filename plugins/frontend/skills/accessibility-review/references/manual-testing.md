# Manual testing protocols

Read this before the keyboard pass, the screen-reader smoke test, or the zoom/contrast/motion
checks. These are the checks no scanner can make; they are where most real blockers are found.

## Contents
1. Keyboard pass
2. Screen-reader smoke test (VoiceOver, NVDA) and the accessibility-tree fallback
3. Zoom, reflow, and text spacing
4. Contrast and color
5. Motion, flashing, and auto-updating content
6. Forced colors (high-contrast modes)
7. Target size
8. Evidence to capture

---

## 1. Keyboard pass

**Setup.** Put the mouse away. On macOS, turn on *System Settings → Keyboard → Keyboard
navigation*; in Safari also enable *Settings → Advanced → "Press Tab to highlight each item on a
webpage"*, or Tab will skip links and you will report bugs that are not there. Chrome and
Firefox on other platforms tab to everything by default.

Start with leads from the scripted walk (run it from the project root so Playwright resolves),
then do it by hand:

`${CLAUDE_SKILL_DIR}` in these commands is not a shell variable: replace it with this skill's directory, the path SKILL.md shows for `scripts/`, and keep the quotes.

```bash
node "${CLAUDE_SKILL_DIR}/scripts/keyboard-walk.mjs" http://localhost:3000/checkout --screenshot focus-order.png
# the same page with its dialog open (a --setup module drives the page into that state)
node "${CLAUDE_SKILL_DIR}/scripts/keyboard-walk.mjs" http://localhost:3000/checkout --setup open-address-dialog.mjs
```

**Protocol** (repeat per page and per important state):

1. **First Tab.** From a fresh load the first stop should be the skip link (if the page has
   repeated navigation), and it must become *visible* when focused. Activate it: the next Tab
   continues inside the main content.
2. **Forward pass.** Tab through everything. At each stop ask: can I *see* where focus is
   (2.4.7)? Is it at least partly visible, not under a sticky header, cookie bar, or chat bubble
   (2.4.11)? Is it something interactive (a focusable `div` with no role is a bug)? Does the
   order match the reading order (2.4.3)? Did anything open, navigate, or submit just because
   it received focus (3.2.1)?
3. **Backward pass.** Shift+Tab through at least one dense region. Sticky headers obscure
   focus mostly when moving backwards.
4. **Operate every control** with the keys its role implies:

   | Control | Keys that must work |
   |---|---|
   | Link | Enter |
   | Button | Enter and Space |
   | Checkbox / switch | Space |
   | Radio group | Arrow keys move and select; Tab enters/leaves the group |
   | Native select | Arrows; Alt+Down (Windows) opens the list |
   | Tabs, menus, listboxes, trees, grids | Arrows move, Home/End jump, Enter/Space activate, focus stays inside the widget (roving tabindex) |
   | Slider | Arrows; Page Up/Down; Home/End |
   | Any popover, menu, dialog, tooltip | Escape closes it |

   A custom widget that only responds to clicks fails 2.1.1. If it uses arrow-key patterns,
   compare against the WAI-ARIA Authoring Practices pattern for that widget.
5. **Overlays.** For every dialog, drawer, menu, date picker, and popover:
   focus moves into it when it opens; for a *modal*, Tab and Shift+Tab stay inside and the
   page behind cannot be reached; Escape closes it; on close, focus returns to the control that
   opened it (or a logical successor if that control is gone). Focus landing on `<body>` after
   close is a failure users experience as "I got thrown to the top of the page".
6. **Content that changes.** Delete a row, dismiss a toast, remove a filter chip, load more
   results. Focus should land somewhere sensible (the next row, the list heading, the "load
   more" position), never on `<body>`.
7. **Route changes (SPAs).** After activating an in-app link, the title changes and focus moves
   to the new content (or to the top of the page) instead of staying on a link that no longer
   exists. Check what your framework does by default before adding your own handling.
8. **Forms.** Submit with errors. Focus should move to an error summary or the first invalid
   field; every error must be reachable and read in text.
9. **Hover-only UI.** Anything revealed on hover (row actions, mega-menus, tooltips) must also be
   reachable by focus, and a tooltip must be dismissible with Escape (1.4.13).
10. **Shortcuts.** Single-character shortcuts ("/", "?", "j", "k") must be switch-off-able,
    remappable, or active only when their component has focus (2.1.4).

**Symptom → cause → criterion**

| Symptom | Usual cause | SC |
|---|---|---|
| A control can't be reached | `div`/`span` with a click handler; `tabindex="-1"` on a real control; hover-only reveal | 2.1.1 |
| Reached but Enter/Space do nothing | Click handler only on a non-button; key handler missing Space | 2.1.1 |
| Can't Tab out of an embed/editor/widget | Script swallowing Tab; missing Escape route | 2.1.2 |
| No visible focus | `outline: none` without a replacement; ring same color as background | 2.4.7 (and 1.4.11 for a ring under 3:1) |
| Focus hidden under a bar | Sticky/fixed UI without `scroll-padding` | 2.4.11 |
| Order jumps around | `tabindex` > 0; CSS `order`/grid placement diverging from DOM; portals | 2.4.3 |
| Focus lost to the top after an action | Focused element removed/re-rendered; no focus restore | 2.4.3 |
| Page navigates when a select changes | `onchange` navigation without a submit button or warning | 3.2.2 |

## 2. Screen-reader smoke test

Pick the pairings your users actually run; at minimum one desktop pairing:

- **VoiceOver + Safari** (macOS, iOS). VoiceOver is built for Safari; mismatches with other
  browsers are not necessarily your bug.
- **NVDA + Firefox or Chrome** (Windows; free).
- **TalkBack + Chrome** (Android) for mobile-heavy products. JAWS + Chrome is common in
  enterprise and government audiences.

### VoiceOver (macOS) essentials

| Action | Keys |
|---|---|
| Turn on/off | Cmd+F5, or hold Cmd and press Touch ID three times (three presses without Cmd open the Accessibility Shortcuts panel instead) |
| VO modifier ("VO") | Control+Option (or Caps Lock, if enabled) |
| Rotor: headings, links, landmarks, form controls lists | VO+U, then Left/Right to change list |
| Next / previous item | VO+Right / VO+Left |
| Next heading / link / form control / table | VO+Cmd+H / VO+Cmd+L / VO+Cmd+J / VO+Cmd+T (add Shift to go back) |
| Read from here | VO+A; Control stops speech |
| Activate | VO+Space (or Enter on links) |
| Enter / leave a group or table | VO+Shift+Down / VO+Shift+Up |

The on-screen caption panel shows what VoiceOver spoke: screenshot it as evidence.

### NVDA (Windows) essentials

| Action | Keys |
|---|---|
| NVDA modifier | Insert (or Caps Lock, if chosen at install) |
| Read from here | NVDA+Down Arrow; Control stops speech |
| Elements list (headings, links, landmarks) | NVDA+F7 |
| Next heading / heading level n | H / 1–6 |
| Next landmark / link / form field / button / table / list | D / K / F / B / T / L (Shift goes back) |
| Move by table cell | Ctrl+Alt+Arrow keys |
| Toggle browse ↔ focus mode | NVDA+Space (focus mode starts automatically in most fields) |
| Quit | NVDA+Q |

*Tools → Speech Viewer* shows NVDA's spoken text: copy it into findings as evidence.

### The 15-minute script

1. **Load.** Is the page title announced and meaningful?
2. **Outline.** Open the headings list. Is there one descriptive `h1`? Does the outline make
   sense without seeing the page? Open the landmarks list: main, navigation (each named if
   there are several), banner, content info.
3. **Read.** Read the main content linearly. Does it come out in a sensible order? Are
   informative images described, decorative ones silent, icons not read as "image" or a file
   name?
4. **Controls.** Tab through. Each control should announce *name, role, state*: "Filters,
   collapsed, button", "Remember me, checkbox, not checked". "Button" alone, or "clickable",
   is a failure.
5. **Operate.** Expand, select, toggle. Is the *new* state announced?
6. **Forms.** Are labels, required state, and hints read on focus? Submit invalid input: is
   each error announced and connected to its field?
7. **Status.** Trigger a save, a filter that changes the result count, an add-to-cart, a toast.
   It must be spoken *without* moving focus (4.1.3).
8. **Dialog.** On open, is the dialog announced with its name? With the virtual cursor
   (VO+arrows, NVDA arrows in browse mode) can you wander into the page behind a modal? You
   should not.
9. **Tables.** Moving between cells, are the column/row headers read?

Record the screen reader, browser, OS, and versions. Behavior that works in one pairing is
not proof for another; when pairings disagree, check the accessibility tree to see whether the
markup or the screen reader is at fault.

### When no screen reader is available (e.g., a headless agent)

Inspect the **accessibility tree** instead. It is what screen readers consume, so it catches
missing names, wrong roles, and stale states, but it does not show live-region announcements,
verbosity, or browse/focus-mode behavior.

- Chrome DevTools: Elements → Accessibility pane (computed name, role, states), with the
  full-page accessibility tree toggle. Firefox: Accessibility Inspector.
- Playwright: `await locator.ariaSnapshot()` or `await expect(locator).toMatchAriaSnapshot(...)`.
- A browser-automation MCP server, if one is connected (for example, Playwright MCP's
  `browser_snapshot` returns the accessibility tree, optionally with element boxes).

Report the screen-reader pass as **not performed** and list it under "Needs human
verification". Never describe tree inspection as screen-reader testing.

## 3. Zoom, reflow, and text spacing

- **Reflow (1.4.10).** Set the viewport to 320 CSS px wide (DevTools device toolbar, or
  `await page.setViewportSize({ width: 320, height: 640 })`), or zoom a 1280 px-wide window
  to 400%. Fail signals: horizontal scrolling to read text, content clipped or overlapping,
  controls pushed off-screen, a sticky header plus footer leaving no room for content, dialogs
  that can't scroll. Data tables, maps, and diagrams may scroll in two directions; the rest of
  the page may not.
- **Resize text (1.4.4).** Browser zoom to 200%. Firefox's *View → Zoom → Zoom Text Only*
  isolates text scaling. Look for truncated labels and text escaping fixed-height containers.
  A viewport meta with `user-scalable=no` or `maximum-scale=1` blocks pinch-zoom on mobile.
- **Text spacing (1.4.12).** Inject this override (DevTools snippet, a bookmarklet, or
  `page.addStyleTag({ content })`) and look for clipped or overlapping text:

  ```css
  * {
    line-height: 1.5 !important;
    letter-spacing: 0.12em !important;
    word-spacing: 0.16em !important;
  }
  p { margin-bottom: 2em !important; }
  ```
- **Orientation (1.3.4).** Emulate portrait and landscape; neither may be blocked.

## 4. Contrast and color

Scanners measure plain text on solid backgrounds well and skip the rest. Measure by hand:
text over images or gradients (test the worst region), translucent overlays, hover/focus/
visited/error states, placeholder text (it is not exempt), "disabled-looking" controls that are
actually enabled, and all non-text indicators: input borders, checkbox/radio outlines, toggle
states, focus rings, meaningful icons, chart lines and segments (1.4.11, 3:1).

`${CLAUDE_SKILL_DIR}` in these commands is not a shell variable: replace it with this skill's directory, the path SKILL.md shows for `scripts/`, and keep the quotes.

```bash
node "${CLAUDE_SKILL_DIR}/scripts/contrast.mjs" '#6b7280' '#ffffff'                 # text, 4.5:1 target
node "${CLAUDE_SKILL_DIR}/scripts/contrast.mjs" '#d1d5db' '#ffffff' --target 3      # input border (1.4.11)
node "${CLAUDE_SKILL_DIR}/scripts/contrast.mjs" 'rgba(0,0,0,0.5)' '#f8fafc'         # translucent text
node "${CLAUDE_SKILL_DIR}/scripts/contrast.mjs" 'oklch(55.1% 0.027 264.364)' white  # modern CSS colors
```

Read colors from DevTools computed styles, not the design file. For color reliance (1.4.1),
use Chrome DevTools *Rendering → Emulate vision deficiencies* (achromatopsia/grayscale and the
common deficiencies) and check that errors, required fields, statuses, links in body text, and
chart series remain distinguishable.

## 5. Motion, flashing, and auto-updating content

- Emulate reduced motion: DevTools *Rendering → Emulate CSS media feature
  prefers-reduced-motion*, `await page.emulateMedia({ reducedMotion: 'reduce' })`, or the OS
  setting. Large parallax, zooms, and slide transitions should stop or soften. (Advisory at AA;
  see the checklist.)
- Anything that moves, blinks, scrolls, or auto-updates on its own for more than 5 seconds
  next to other content (carousels, tickers, background video, live feeds) needs a visible,
  keyboard-operable pause/stop/hide control (2.2.2).
- Nothing may flash more than three times per second (2.3.1). Check error shakes, video, and
  attention-grabbing animations.

## 6. Forced colors (high-contrast modes)

Not a WCAG criterion by itself, but users of Windows contrast themes lose anything drawn with
`box-shadow` or background images. Emulate with DevTools *Rendering → forced-colors: active* or
`page.emulateMedia({ forcedColors: 'active' })`. Look for focus rings built with `box-shadow`
(add `outline: 2px solid transparent` so forced colors can paint it), icon-only buttons whose
icon vanishes, and custom checkboxes that disappear. If a control or information disappears,
report it with the criterion that the disappearance breaks for those users; otherwise as best
practice.

## 7. Target size

When it runs, axe's `target-size` rule evaluates 2.5.8 including the spacing exception. It is
off by default and runs only when the scan requests the `wcag22aa` tag (the bundled
`axe-scan.mjs` does) or enables the rule by id, so check the tags before you rely on a clean
result. For a quick manual lead list, paste this into the DevTools console (it ignores the
exceptions, so confirm each):

```js
[...document.querySelectorAll(
  'a[href], button, input:not([type="hidden"]), select, textarea, summary, ' +
  '[role="button"], [role="link"], [role="checkbox"], [role="radio"], [role="switch"], ' +
  '[role="tab"], [role="menuitem"], [tabindex]:not([tabindex="-1"])'
)]
  .map((el) => ({ el, r: el.getBoundingClientRect() }))
  .filter(({ r }) => r.width > 0 && r.height > 0 && (r.width < 24 || r.height < 24))
  .forEach(({ el, r }) => console.log(`${Math.round(r.width)}x${Math.round(r.height)}`, el));
```

Inline links inside sentences are exempt; icon buttons in dense toolbars, pagination numbers,
close "x" icons, and table row actions are the usual failures.

## 8. Evidence to capture

For each finding, keep enough that someone else can reproduce it in two minutes: the URL and
state (e.g., "checkout, address dialog open, validation errors shown"), viewport, browser,
the exact keys pressed, a screenshot with focus visible, the screen-reader output (caption
panel or Speech Viewer text), and tool output with versions and settings (the axe-core version
and tags that `axe-scan.mjs` prints on its first line, the rule id).
