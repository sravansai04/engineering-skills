# Fix patterns

Read this when you move from reporting to fixing. Each pattern gives the preferred fix (almost
always native HTML), the minimum a custom implementation must do if native is impossible, and
how to verify. Examples are plain HTML unless a framework changes the answer; framework notes
are at the end.

## Contents
1. Accessible names (and when to use ARIA at all)
2. Buttons vs links; custom controls
3. Images, icons, and SVG
4. Forms: labels, required, hints, errors, autocomplete
5. Dialogs and drawers
6. Disclosures, navigation menus, tabs, comboboxes
7. Live regions and status messages
8. Route changes in single-page apps
9. Skip links, focus styles, sticky UI
10. Contrast and color
11. Target size, dragging, and pointer actions
12. Motion
13. Reflow and zoom
14. Tables
15. Language
16. Media
17. Tooltips and hover content
18. Authentication
19. Framework notes (React, Vue, Angular, Svelte, web components)

---

## 1. Accessible names (and when to use ARIA at all)

ARIA changes what assistive technology *announces*; it never adds behavior, focusability, or
keyboard support. So: use a native element when one exists; use ARIA only to express something
HTML cannot; never use ARIA to contradict the element's native role; never hide a focusable
element with `aria-hidden`. A wrong `role` or stale `aria-expanded` is worse than none because
it actively misleads.

Choose a name source in this order:

1. **Visible text content** of the control: `<button>Save draft</button>`.
2. **`<label>`** for form fields (`for`/`id`, or wrapping).
3. **`aria-labelledby`** pointing at visible text elsewhere (a dialog's heading, a table
   caption, a row's name + the button: `aria-labelledby="row-12-name delete-label"`).
4. **Visually hidden text** inside the control, when there is no visible text (icon buttons).
   It survives page translation tools better than attributes.
5. **`aria-label`**, last. Never on non-interactive `div`/`span` (most roles without
   interactivity ignore or prohibit it), and never with text that differs from the visible
   label (2.5.3: voice-control users say what they see, so "Submit" visible with
   `aria-label="Send application"` breaks "click Submit").

`title` is not a dependable name: it is hover-only and inconsistently announced.

The standard visually-hidden utility (keeps text in the accessibility tree, removes it from
view):

```css
.visually-hidden {
  position: absolute !important;
  width: 1px;
  height: 1px;
  margin: -1px;
  padding: 0;
  overflow: hidden;
  clip: rect(0 0 0 0);
  white-space: nowrap;
  border: 0;
}
```

Do not use `display: none` or `visibility: hidden` for "screen-reader-only" text: both remove it
from the accessibility tree too.

## 2. Buttons vs links; custom controls

- A **link** goes somewhere (has a URL; opens in a new tab with middle-click). A **button**
  does something on this page (submit, toggle, open a dialog). Mixing them breaks user
  expectations and keyboard behavior (links don't activate on Space; buttons don't open in new
  tabs).
- `<a href="#">` / `<a href="javascript:…">` used as a button → make it `<button type="button">`.
- A clickable `div`/`span` → `<button type="button">` (reset its styles with CSS) or a real
  link. This single change gives focusability, Enter/Space activation, the button role, and
  disabled handling.

```html
<!-- Before: unreachable by keyboard, announced as nothing -->
<div class="icon-btn" onclick="closePanel()"><svg>…</svg></div>

<!-- After -->
<button type="button" class="icon-btn" onclick="closePanel()">
  <svg aria-hidden="true">…</svg>
  <span class="visually-hidden">Close panel</span>
</button>
```

If you truly cannot use a native element, the custom control needs *all* of: a `role`,
`tabindex="0"`, an accessible name, Enter **and** Space activation (Space activates on key-up
and must not scroll the page), state attributes (`aria-pressed`, `aria-checked`,
`aria-expanded`) kept in sync, and a disabled state (`aria-disabled="true"` plus ignoring
activation). That list is why native is the fix.

Toggle buttons: `<button type="button" aria-pressed="false">Bold</button>`; keep the label
constant and flip `aria-pressed`. Don't change both the label and the state, or it reads as
"Unmute, pressed".

## 3. Images, icons, and SVG

Decide alt text by the image's *job*, not its content:

| Image's job | Alt text |
|---|---|
| Conveys information not in nearby text | That information, briefly ("Revenue rose 12% from Q1 to Q2") |
| Only content of a link or button | Where it goes / what it does ("Home", "Search"), not what it depicts ("magnifying glass") |
| Repeats adjacent text (product photo next to its name, avatar next to the user name) | `alt=""` |
| Decorative / mood / spacer | `alt=""`, or a CSS background |
| Complex (chart, diagram, map) | Short alt naming it and its takeaway, plus the full data/description in visible text, a table, or a linked description |
| Text inside an image | The same text (and prefer real text, 1.4.5) |

Never: missing `alt` (screen readers read the file name), "image of…", file names, or the same
alt on every image in a grid.

Inline SVG:

```html
<!-- Decorative, or labeled by its parent control -->
<svg aria-hidden="true" focusable="false">…</svg>

<!-- Informative on its own -->
<svg role="img" aria-labelledby="chart-title">
  <title id="chart-title">Signups per week, rising from 40 to 95</title>
  …
</svg>
```

Icon fonts: put `aria-hidden="true"` on the glyph element and give the control a name.

## 4. Forms: labels, required, hints, errors, autocomplete

```html
<form novalidate>
  <div id="error-summary"></div>  <!-- empty until a submit fails; see "Error summary" below -->

  <label for="email">Email address (required)</label>
  <input id="email" name="email" type="email" autocomplete="email" required
         aria-describedby="email-hint">
  <p id="email-hint">We send the receipt here.</p>

  <fieldset>
    <legend>Delivery speed</legend>
    <label><input type="radio" name="speed" value="std"> Standard (3–5 days)</label>
    <label><input type="radio" name="speed" value="exp"> Express (next day)</label>
  </fieldset>
</form>
```

On a failed submit:

```html
<input id="email" … aria-invalid="true" aria-describedby="email-hint email-error">
<p id="email-error">Enter an email address in the format name@example.com</p>
```

**Error summary: choose one way to make it heard, never both.**

- *Move focus (recommended for submit-time summaries).* Render the summary on a failed submit
  and focus its heading. Focus makes the screen reader read it, so it needs no live role:

  ```html
  <div id="error-summary">
    <h2 tabindex="-1">There are 2 problems with your details</h2>
    <ul>
      <li><a href="#email">Enter an email address in the format name@example.com</a></li>
      <li><a href="#postcode">Enter a postcode</a></li>
    </ul>
  </div>
  ```
  ```js
  document.querySelector('#error-summary h2').focus();
  ```
- *Announce without moving focus* (inline status such as "2 fields need attention" while the
  user stays put). Keep an empty `role="alert"` container in the DOM from page load and fill
  it. Do not hide it with `hidden` or `display: none`, which removes it from the accessibility
  tree, so filling it is not announced.

Never put `role="alert"` on an element you also move focus to: depending on the screen reader
and browser it is read twice, or the alert is cut off by the focus announcement.

- **Label every field visibly and persistently.** A placeholder is a hint, not a label: it
  disappears on input and usually fails contrast.
- **Required:** the `required` attribute (or `aria-required="true"` on custom fields) for
  assistive tech, plus a visible text cue. If you use an asterisk, explain it once at the top
  and keep the explanation in text; color alone fails 1.4.1.
- **Errors (3.3.1, 3.3.3):** text that names the field and says how to fix it; programmatically
  tied to the field (`aria-describedby` and `aria-invalid="true"`); visible next to the field;
  a summary for long forms that links to each field (above); on submit, move focus to the
  summary heading or to the first invalid field. Keep the user's input. Remove `aria-invalid`
  when fixed.
- **Don't validate on every keystroke with announcements.** Validate on blur or submit; announce
  once.
- **Disabled submit buttons** that never explain why are a usability trap: prefer an enabled
  button that reports what is missing.
- **Groups:** radio and checkbox sets, date parts, and address blocks use
  `<fieldset>`/`<legend>`.
- **Autocomplete (1.3.5):** tokens for fields about the user (`name`, `given-name`,
  `family-name`, `email`, `tel`, `street-address`, `address-line1`, `postal-code`, `country`,
  `bday`, `username`, `current-password`, `new-password`, `cc-number`, `cc-exp`, …). Fields
  about *someone else* (a gift recipient) don't require them.
- **High-stakes submissions (3.3.4):** add a review step, a confirmation, or an undo for
  payments, legal agreements, and destructive data changes.

## 5. Dialogs and drawers

Prefer the native element:

```html
<button type="button" id="edit-btn">Edit address</button>

<dialog id="edit-dialog" aria-labelledby="edit-title">
  <h2 id="edit-title">Edit address</h2>
  <form method="dialog">
    …
    <button type="submit" value="save">Save</button>
    <button type="submit" value="cancel" formnovalidate>Cancel</button>
  </form>
</dialog>

<script>
  const dialog = document.getElementById('edit-dialog');
  document.getElementById('edit-btn').addEventListener('click', () => dialog.showModal());
</script>
```

`showModal()` makes the rest of the page inert (unreachable by Tab and by the virtual cursor),
closes on Escape, moves focus into the dialog, and browsers return focus to the previously
focused element when it closes. Two gaps remain, so keep a small fallback: Safari does not focus
buttons on mouse click, so a dialog opened by click there has nothing to return to; and a trigger
that re-rendered or disappeared while the dialog was open can't receive focus. Record the opener
yourself and restore it in a `close` listener if focus ended up on `<body>`:

```js
let opener = null;
openButton.addEventListener('click', () => { opener = openButton; dialog.showModal(); });
dialog.addEventListener('close', () => {
  if (document.activeElement === document.body && opener?.isConnected) opener.focus();
});
```

Use `autofocus` on the element that should
receive focus first when the first focusable control is not the right start (for example, put
it on the heading's container in a long read-only dialog, or on a safe "Cancel" in a destructive
confirmation).

A custom modal must do all of: `role="dialog"` (or `alertdialog` for urgent confirmations),
`aria-modal="true"`, a name (`aria-labelledby` → its heading), move focus in on open, keep Tab
inside (or set `inert` on the rest of the page, which also hides it from the virtual cursor),
close on Escape, restore focus to the trigger (save `document.activeElement` before opening),
and stop the background from scrolling. Drawers and full-screen mobile menus follow the same
rules when they cover the page.

Non-modal popovers (menus, date pickers): focus moves in when opened by keyboard, Escape closes
and returns focus to the trigger, and Tabbing away closes or continues logically. The HTML
`popover` attribute provides light dismiss and Escape for free; still check what state your
target browsers expose on the invoking button.

## 6. Disclosures, navigation menus, tabs, comboboxes

**Disclosure / accordion** (show-hide section):

```html
<button type="button" aria-expanded="false" aria-controls="ship-panel">Shipping costs</button>
<div id="ship-panel" hidden>…</div>
```

Toggle both `hidden` and `aria-expanded` together. `<details><summary>` is a native
alternative with built-in state.

**Site navigation:** a `<nav aria-label="Main">` with a list of links; submenus are disclosure
buttons (above). Do **not** use `role="menu"`/`menuitem` for site navigation: those roles tell
screen readers to expect an application menu with arrow-key navigation and switch NVDA/JAWS out
of browse mode, so users can't read it the way they read the rest of the page. Mark the current
page with `aria-current="page"`.

**Tabs** only when it really is one view with switchable panels (not page navigation):
`role="tablist"` containing `role="tab"` buttons with `aria-selected` and `aria-controls`, each
`role="tabpanel"` labelled by its tab; one tab in the Tab order at a time (roving `tabindex`),
Left/Right arrows move between tabs, Home/End jump. If the "tabs" change the URL, they are
navigation links; use links with `aria-current`.

**Combobox / autocomplete / custom select:** this is the widget most often built wrong. Prefer
a native `<select>` for picking from a fixed list. For search-as-you-type, use a well-tested
library that follows the WAI-ARIA Authoring Practices combobox pattern and verify it with a
screen reader; hand-rolling one requires managing `aria-expanded`, `aria-controls`,
`aria-activedescendant`, option roles, and announcements of result counts.

## 7. Live regions and status messages

```html
<!-- Present in the DOM from page load, empty -->
<div id="status" role="status"></div>
<div id="errors" role="alert"></div>
```

```js
const statusRegion = document.getElementById('status');
let pendingAnnouncement;
function announce(message) {
  statusRegion.textContent = '';             // clear first, so a repeated "3 results" is a change
  clearTimeout(pendingAnnouncement);
  pendingAnnouncement = setTimeout(() => { statusRegion.textContent = message; }, 100);
}
announce('3 results');
```

- The region must **already exist** (and be in the accessibility tree) before its content
  changes. Inserting a live region together with its message is often not announced.
- Set the new text after a short delay (about 100 ms), as widely used announcer utilities do,
  not in `requestAnimationFrame`. A rAF callback runs before the browser's next rendering
  update, so the cleared state and the new text can reach the accessibility tree as one change,
  and a repeated message is then not re-announced.
- Only a screen reader can confirm an announcement. Inspecting the accessibility tree shows that
  the region and its text exist, not that anything was spoken.
- `role="status"` (polite) for confirmations, counts, and progress; `role="alert"` (assertive)
  only for errors or time-critical warnings. Assertive interrupts whatever the user is hearing.
- Keep announcements short and specific. Don't make large areas live.
- Toasts: announce through a live region, keep them on screen long enough to read (or until
  dismissed), and never make a toast the only place an action (like "Undo") exists unless it
  stays reachable.
- Loading: set `aria-busy="true"` on the updating region while it loads, and announce
  completion ("Results loaded").

## 8. Route changes in single-page apps

After a client-side navigation, users need two things: to *hear* that the page changed and to
have *focus* at the start of the new content.

- Update `document.title` on every route.
- Move focus to the new page's `h1` (give it `tabindex="-1"`) or to `<main>`, but not on the
  very first load, and not for in-page state changes such as filters or sort order (keep focus
  where it is and announce the result count instead).
- Know your framework's default before adding your own: Next.js ships a route announcer but does
  not move focus; SvelteKit announces the new page and resets focus to `<body>` after navigation;
  Nuxt provides a `<NuxtRouteAnnouncer>` component you add yourself. Adding a second announcer
  causes double announcements.

```jsx
// React Router: focus the new page heading after navigation (not on first render)
function useFocusHeadingOnNavigate() {
  const { pathname } = useLocation();
  const isFirstRender = useRef(true);
  useEffect(() => {
    if (isFirstRender.current) { isFirstRender.current = false; return; }
    document.querySelector('main h1')?.focus();
  }, [pathname]);
}
// <h1 tabIndex={-1}>Order history</h1>
```

## 9. Skip links, focus styles, sticky UI

```html
<a class="skip-link" href="#main">Skip to main content</a>
…
<main id="main" tabindex="-1">…</main>
```

```css
.skip-link { position: absolute; left: 0.5rem; top: -100vh; }
.skip-link:focus { top: 0.5rem; }            /* must become visible when focused */

:focus-visible {
  outline: 3px solid var(--focus-ring-color); /* ≥ 3:1 against the surrounding background */
  outline-offset: 2px;
}

/* A box-shadow ring disappears in forced-colors mode; a transparent outline makes it reappear */
.button:focus-visible {
  box-shadow: 0 0 0 3px var(--focus-ring-color);
  outline: 2px solid transparent;
}

/* Keep focused elements clear of sticky header/footer/cookie bar (2.4.11) */
html { scroll-padding-top: var(--sticky-header-height); scroll-padding-bottom: var(--sticky-footer-height); }
```

Never remove outlines globally (`*:focus { outline: none }`). If designers object to rings on
mouse click, style `:focus-visible` (keyboard) and leave `:focus` alone; browsers already show
the ring mainly for keyboard focus. Check the ring against *every* background it can appear on.
For cookie banners and chat widgets that cover the bottom of the screen, also make them
dismissible and avoid covering focusable content on load.

## 10. Contrast and color

- Fix contrast in the **design tokens or theme variables**, not one component at a time; a
  failing token usually fails in dozens of places.
- Check every state: default, hover, focus, active, visited, selected, error, and dark mode.
- Text on images: put the text on a solid or sufficiently opaque scrim, and measure the worst
  part of the image.
- Never encode meaning in color alone: pair error red with an icon and text, mark required
  fields in text, underline links in body text, use patterns or direct labels on charts, add
  a text status next to colored status dots.
- `scripts/contrast.mjs` prints the nearest passing color that keeps the hue, for both the
  foreground and the background.

## 11. Target size, dragging, and pointer actions

```css
.icon-button {
  min-width: 24px;   /* WCAG 2.2 AA minimum (2.5.8); 44px is the AAA / platform-comfortable size */
  min-height: 24px;
}

/* Grow the hit area without changing the visual size */
.icon-button { position: relative; }
.icon-button::after { content: ""; position: absolute; inset: -6px; }
```

When targets must stay small, space them so a 24 px circle centered on each does not overlap
its neighbors. For drag interactions (2.5.7) add a single-pointer path: "Move up"/"Move down"
buttons, a "Move to…" menu, click-to-place, or a file-picker button next to a drop zone. Trigger
actions on click/`pointerup`, not `pointerdown` (2.5.2), so users can slide off to cancel.

## 12. Motion

Make motion opt-in, so users who asked for less get none by default:

```css
@media (prefers-reduced-motion: no-preference) {
  .hero { animation: drift 12s ease-in-out infinite alternate; }
  html { scroll-behavior: smooth; }
}
```

```js
const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
if (!reduceMotion) carousel.autoplay();
```

Carousels and background videos that move for more than 5 s need a visible pause control
(2.2.2), regardless of the user's motion setting.

## 13. Reflow and zoom

- Remove `maximum-scale=1` / `user-scalable=no` from the viewport meta.
- Size containers with `max-width`, flexible units, and wrapping (`flex-wrap`, grid
  `minmax()`); avoid fixed pixel widths and heights on text containers.
- Let long strings wrap (`overflow-wrap: anywhere` for URLs, IDs).
- Wide data tables may scroll horizontally; make the scroll container reachable and named:

```html
<div role="region" aria-labelledby="orders-caption" tabindex="0" class="table-scroll">
  <table>
    <caption id="orders-caption">Orders, last 30 days</caption>
    …
  </table>
</div>
```

```css
.table-scroll { overflow-x: auto; }
```

- At narrow widths, collapse sticky headers/footers so they don't consume the viewport.

## 14. Tables

```html
<table>
  <caption>Plan comparison</caption>
  <thead>
    <tr><th scope="col">Feature</th><th scope="col">Basic</th><th scope="col">Pro</th></tr>
  </thead>
  <tbody>
    <tr><th scope="row">Storage</th><td>10 GB</td><td>1 TB</td></tr>
  </tbody>
</table>
```

Use tables for data, not layout. Sortable columns: put a `<button>` inside the `th` and set
`aria-sort="ascending|descending"` on the sorted `th` only. Interactive spreadsheet-like grids
need the `grid` pattern (arrow-key cell navigation); a plain table with buttons in cells does
not.

## 15. Language

`<html lang="en">` on every document (including the SPA shell); `lang` on passages in another
language (`<blockquote lang="fr">`); language-switcher entries in their own language with
`lang` and `hreflang` (`<a href="/de/" lang="de" hreflang="de">Deutsch</a>`). Update `lang` if
the app switches language client-side.

## 16. Media

```html
<video controls preload="metadata">
  <source src="/media/onboarding.mp4" type="video/mp4">
  <track kind="captions" src="/media/onboarding.en.vtt" srclang="en" label="English" default>
</video>
<a href="/media/onboarding-transcript.html">Read the transcript</a>
```

Captions for recorded speech (1.2.2), audio description or an equivalent narration of visual
information (1.2.3/1.2.5), a transcript for audio-only content (1.2.1), no autoplaying sound
(1.4.2), and custom player controls that are real buttons with names and states.

## 17. Tooltips and hover content

Show tooltips on focus as well as hover; dismiss with Escape without moving focus; let the
pointer move onto the tooltip without it vanishing; keep it until the user moves away (1.4.13).
Connect tooltip text with `aria-describedby` on the trigger. Never put information needed to
complete a task only in a tooltip, and never put interactive content in a tooltip (use a
popover/dialog).

## 18. Authentication

Allow paste in password and code fields; set `autocomplete="username"`,
`"current-password"`, `"new-password"`, and `"one-time-code"` so password managers and OS
autofill work; don't split one-time codes into fields that break paste; offer an alternative to
puzzle CAPTCHAs (and to transcribing distorted text). Passkeys, magic links, and OAuth sign-in
all satisfy 3.3.8 because they need no cognitive test.

## 19. Framework notes

- **React:** `htmlFor`, `tabIndex`, `aria-*` attributes stay hyphenated in JSX; generate
  label/description ids with `useId()`; move focus in `useEffect`/refs *after* the element
  renders; portals render at the end of `<body>`, so dialogs/menus must manage focus explicitly.
  Lint with `eslint-plugin-jsx-a11y`. Test with Testing Library's `getByRole(…, { name })`.
- **Vue:** bind ids with `:id`/`:for`; focus after `await nextTick()`; lint with
  `eslint-plugin-vuejs-accessibility`.
- **Angular:** the CDK `A11yModule` provides `cdkTrapFocus`, `FocusMonitor`, and the
  `LiveAnnouncer` service; CDK/Material dialogs handle focus trap and restore. Lint templates
  with angular-eslint's `templateAccessibility` config.
- **Svelte / SvelteKit:** the compiler emits `a11y_*` warnings; treat them as errors in CI.
  SvelteKit already announces route changes and resets focus.
- **Web components:** ID references (`for`, `aria-labelledby`, `aria-describedby`) cannot cross a
  shadow root. Keep a label and its control in the same tree, slot light-DOM labels in, or use
  `ElementInternals` / element-reference ARIA properties where your target browsers support them.
- **Component libraries:** fix accessibility bugs in the shared component (Button, IconButton,
  Modal, FormField, Tooltip) and you fix every page that uses it. When a third-party component is
  inaccessible, wrap it, configure it (many expose `aria-label`/`labelId` props), or replace it,
  and report it upstream.
