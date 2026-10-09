# WCAG 2.2 Level A + AA checklist, grouped by review area

Use this when you need the full criterion list: to make sure a review covered everything, to
pick the right success criterion (SC) for a finding, or to mark what still needs a human. It
lists all 55 Level A and AA criteria in WCAG 2.2 (31 A + 24 AA), checked against the W3C
Recommendation at https://www.w3.org/TR/WCAG22/. The paraphrases are summaries; when a finding
turns on exact wording (an exception, a threshold), open the criterion's "Understanding" page
(`https://www.w3.org/WAI/WCAG22/Understanding/<slug>`) and quote it.

**axe column** = which axe-core rules map to the SC (from the rules' own `wcag###` tags, checked
against axe-core 4.13 and 4.14). "none" means no rule runs and the criterion is entirely manual.
"off by default" and "experimental" rules run only when the scan asks for them (see
`automated-testing.md` §1). Even where a rule runs, it checks presence/validity, not quality:
`image-alt` proves an `alt` exists, not that it is right.

## Contents
1. Structure and semantics
2. Names, labels, and instructions
3. Keyboard and focus
4. Visual presentation (contrast, color, resize, reflow, spacing)
5. Forms and errors
6. Images, media, and time-based content
7. Dynamic content and status
8. Pointer, touch, and motion input
9. Timing, movement, and flashing
10. Consistency and help
11. Authentication
12. Removed and beyond-AA criteria you will be asked about

The citation cheat sheet below comes first.

---

## Citation cheat sheet (most common findings)

Start here for the usual suspects; the numbered sections below have every criterion.

| Problem | Cite |
|---|---|
| Missing, wrong, or noisy alt text; unhidden decorative SVG | 1.1.1 Non-text Content (A) |
| Control with no name, wrong role, or state not exposed (expanded/selected/pressed) | 4.1.2 Name, Role, Value (A) |
| Visible label text missing from the accessible name | 2.5.3 Label in Name (A) |
| Headings, lists, tables, or label associations missing from the markup | 1.3.1 Info and Relationships (A) |
| Reading order differs from visual meaning (CSS reordering) | 1.3.2 Meaningful Sequence (A) |
| No visible label or instructions for an input | 3.3.2 Labels or Instructions (A) |
| Error not identified in text / no correction suggested | 3.3.1 (A) / 3.3.3 (AA) |
| Personal-data field without `autocomplete` | 1.3.5 Identify Input Purpose (AA) |
| Not reachable or operable by keyboard | 2.1.1 Keyboard (A) |
| Focus can't leave a component | 2.1.2 No Keyboard Trap (A) |
| Illogical focus order; focus lost after an action | 2.4.3 Focus Order (A) |
| No visible focus indicator | 2.4.7 Focus Visible (AA) |
| Focused element fully hidden by sticky or overlay content | 2.4.11 Focus Not Obscured (Minimum) (AA) |
| Text contrast / UI-component, focus-ring, or icon contrast | 1.4.3 (AA) / 1.4.11 (AA) |
| Meaning conveyed by color alone | 1.4.1 Use of Color (A) |
| Status message not announced | 4.1.3 Status Messages (AA) |
| No skip link or landmarks to bypass repeated blocks | 2.4.1 Bypass Blocks (A) |
| Missing or non-updating page title | 2.4.2 Page Titled (A) |
| Missing or incorrect `lang` (page / passage) | 3.1.1 (A) / 3.1.2 (AA) |
| Two-way scroll at 320 px / clipping at 200% / text-spacing breakage | 1.4.10 / 1.4.4 / 1.4.12 (AA) |
| Target smaller than 24×24 without spacing | 2.5.8 Target Size (Minimum) (AA) |
| Drag-only interaction | 2.5.7 Dragging Movements (AA) |
| Hover or focus popup that can't be dismissed, hovered, or kept open | 1.4.13 Content on Hover or Focus (AA) |
| Auto-moving content longer than 5 s without pause | 2.2.2 Pause, Stop, Hide (A) |
| Context changes on focus / on input | 3.2.1 (A) / 3.2.2 (A) |
| No captions / no audio description | 1.2.2 (A) / 1.2.5 (AA) |
| Login needs memorizing or transcribing; paste blocked | 3.3.8 Accessible Authentication (Minimum) (AA) |
| Re-asking for information given earlier in the same flow | 3.3.7 Redundant Entry (A) |
| Ignores `prefers-reduced-motion` | 2.3.3 (AAA): advisory at AA |

---

## 1. Structure and semantics

| SC | Lvl | What must be true | How to test | axe |
|---|---|---|---|---|
| 1.3.1 Info and Relationships | A | Structure a sighted user infers from layout (headings, lists, tables, groups, label↔field, required markers) is in the markup or the text | Inspect the accessibility tree; headings list in a screen reader; check `th`/`scope`, `fieldset`/`legend`, `ul/ol` | partial: list, listitem, dlitem, definition-list, th-has-data-cells, td-headers-attr, aria-required-children/parent |
| 1.3.2 Meaningful Sequence | A | DOM/reading order yields the right meaning when CSS (grid/flex `order`, absolute positioning) is ignored | Read the page linearly with a screen reader, or disable CSS; compare with visual order | none |
| 2.4.1 Bypass Blocks | A | A way to skip repeated blocks: skip link, or landmarks + headings | Tab once from page load; check landmarks exist (`header`, `nav`, `main`, `footer`) | partial: bypass |
| 2.4.2 Page Titled | A | `<title>` describes the page; SPA route changes update it | Check the tab title on every route, including after client-side navigation | partial: document-title (presence only) |
| 2.4.6 Headings and Labels | AA | Headings and labels that exist describe their topic/purpose | Read the headings list out of context: can you tell what each section is? | none |
| 3.1.1 Language of Page | A | `<html lang>` is set and correct | View source; check SPA shells set it too | partial: html-has-lang, html-lang-valid, html-xml-lang-mismatch |
| 3.1.2 Language of Parts | AA | Passages in another language carry their own `lang` | Find quotes, language pickers ("Deutsch", "日本語"), legal text in other languages | partial: valid-lang |

Heading-level skips (h2 → h4) and "one `h1` per page" are **best practices**, not 1.3.1 failures,
unless the skipped level misrepresents the structure. Report them as best practice.

## 2. Names, labels, and instructions

| SC | Lvl | What must be true | How to test | axe |
|---|---|---|---|---|
| 4.1.2 Name, Role, Value | A | Every control exposes a name, a correct role, and its current state/value (expanded, selected, checked, pressed), and state changes are exposed | Accessibility tree per control; operate it and confirm the state updates | partial: button-name, link-name, label, select-name, aria-* validity, nested-interactive, frame-title, … |
| 2.5.3 Label in Name | A | When a control has visible text, its accessible name contains that text (ideally starts with it) | Compare visible label with computed name; voice-control users say what they see | label-content-name-mismatch (experimental through 4.13, so it runs only if requested; on by default from 4.14) |
| 2.4.4 Link Purpose (In Context) | A | Link purpose is clear from its text, or from text plus its sentence/list item/table cell/heading context | Links list in a screen reader; "click here" ×10 with no programmatic context fails | partial: link-name, area-alt |
| 3.3.2 Labels or Instructions | A | Inputs have labels or instructions (format, required) when needed | Every field has a persistent visible label; formats stated up front | partial: form-field-multiple-labels |
| 1.3.3 Sensory Characteristics | A | Instructions don't depend only on shape, color, size, position, or sound ("click the green button on the right") | Read instructional copy | none |

## 3. Keyboard and focus

| SC | Lvl | What must be true | How to test | axe |
|---|---|---|---|---|
| 2.1.1 Keyboard | A | Everything doable with a pointer is doable with a keyboard (no timing-dependent keystrokes) | Keyboard pass: reach AND operate every control, including drag/drop alternatives, hover menus, custom widgets | partial: scrollable-region-focusable, frame-focusable-content, server-side-image-map |
| 2.1.2 No Keyboard Trap | A | Focus can always leave a component with the keyboard (and non-standard exits are explained) | Tab into every widget, embed, editor, modal; get out again | none |
| 2.1.4 Character Key Shortcuts | A | Single-character shortcuts can be turned off, remapped, or only work when the component has focus | Look for global `keydown` handlers on letters/"?"/"/"; speech-input users trigger them by accident | none |
| 2.4.3 Focus Order | A | Focus order preserves meaning and operability | Compare Tab order with visual order; look for `tabindex > 0`, portals that land focus at the end of the DOM | none |
| 2.4.7 Focus Visible | AA | A visible focus indicator for keyboard users | Tab through; look for `outline: none` without replacement | none |
| 2.4.11 Focus Not Obscured (Minimum) | AA | A focused component is not *entirely* hidden by author content (sticky headers/footers, cookie banners, chat widgets) | Tab with sticky UI present, also with Shift+Tab; fix with `scroll-padding` | none |
| 3.2.1 On Focus | A | Receiving focus doesn't change context (no navigation, submission, or new window on focus) | Tab through; watch for auto-opening popups/new pages | none |

## 4. Visual presentation

| SC | Lvl | What must be true | How to test | axe |
|---|---|---|---|---|
| 1.4.1 Use of Color | A | Color is never the only way to convey information, state, or an action (errors, required, links in text, chart series, status) | Grayscale emulation; links in body text need a non-color cue (underline) or 3:1 against surrounding text plus a cue on hover/focus | partial: link-in-text-block |
| 1.4.3 Contrast (Minimum) | AA | Text ≥ 4.5:1; large text (≥ 18pt / 24 px, or ≥ 14pt / ~18.67 px bold) ≥ 3:1. Exempt: disabled controls, pure decoration, invisible text, incidental text in photos, logos | `scripts/contrast.mjs`; check hover/focus/visited/placeholder/error states and text over images | partial: color-contrast (images/gradients/overlaps go to "needs review") |
| 1.4.11 Non-text Contrast | AA | 3:1 against adjacent colors for what identifies a control and its state (input borders, checkbox outlines, focus indicators, toggle state, icon-only buttons) and for meaningful graphic parts (chart lines, icons that carry meaning) | Measure boundary vs background with `scripts/contrast.mjs --target 3` | none |
| 1.4.4 Resize Text | AA | Text resizes to 200% without loss of content/function | Browser zoom 200%; check clipping, overlap, truncated buttons; viewport meta must not block zoom | partial: meta-viewport |
| 1.4.5 Images of Text | AA | Real text instead of pictures of text (logos and essential cases excepted) | Look for text baked into images, banners, buttons | none |
| 1.4.10 Reflow | AA | At 320 CSS px wide (= 1280 px at 400% zoom) content works with vertical scrolling only; data tables, maps, diagrams, toolbars that need 2-D layout are excepted | Set viewport to 320×(any) or zoom 400%; look for horizontal scroll, hidden content, overlapping fixed bars | none |
| 1.4.12 Text Spacing | AA | No loss of content when users set line-height 1.5, paragraph spacing 2×, letter-spacing 0.12em, word-spacing 0.16em | Inject the override CSS in `manual-testing.md` and look for clipped text in fixed-height boxes | partial: avoid-inline-spacing |
| 1.4.13 Content on Hover or Focus | AA | Tooltips/popovers that appear on hover or focus are dismissible (Esc) without moving focus/pointer, hoverable (pointer can move onto them), and persistent until dismissed | Hover, then move the pointer onto the tooltip; press Esc; focus-trigger them too | none |
| 1.3.4 Orientation | AA | Not locked to portrait or landscape unless essential | Rotate a device or emulate both orientations | experimental only: css-orientation-lock |

## 5. Forms and errors

| SC | Lvl | What must be true | How to test | axe |
|---|---|---|---|---|
| 1.3.5 Identify Input Purpose | AA | Fields collecting the user's *own* data carry the right `autocomplete` token (from the WCAG "Input Purposes" list: `name`, `given-name`, `email`, `tel`, `street-address`, `postal-code`, `bday`, `username`, `current-password`, `new-password`, `cc-number`, …) | Inspect every personal-data field | partial: autocomplete-valid (validity, not presence) |
| 3.3.1 Error Identification | A | Detected errors identify the field and describe the problem in text | Submit invalid/empty; the message must be text, tied to the field (`aria-describedby`, `aria-invalid`) and announced | none |
| 3.3.3 Error Suggestion | AA | When a fix is known, suggest it ("Use the format DD/MM/YYYY", "Did you mean gmail.com?") unless that would undermine security | Read each error message | none |
| 3.3.4 Error Prevention (Legal, Financial, Data) | AA | Legal/financial commitments, data changes/deletions, and test submissions are reversible, checked, or confirmed | Find commit-type actions; is there review/confirm/undo? | none |
| 3.3.7 Redundant Entry | A | Information already given in the same process is auto-filled or selectable, not retyped (except security re-entry or when it is no longer valid) | Walk multi-step flows: shipping→billing, account→profile | none |
| 3.2.2 On Input | A | Changing a field's value doesn't change context unexpectedly (select that navigates on change, auto-submit) unless the user was told first | Change each select/radio; watch for navigation/submission | none |

## 6. Images, media, and time-based content

| SC | Lvl | What must be true | How to test | axe |
|---|---|---|---|---|
| 1.1.1 Non-text Content | A | Informative images have equivalent text; functional images (in links/buttons) describe the action; decorative ones are hidden (`alt=""`, CSS background, `aria-hidden` on inline SVG); controls have names | Review every `img`, `svg`, icon font, `canvas`, `input type=image`, CAPTCHA | partial: image-alt, svg-img-alt, role-img-alt, input-image-alt, object-alt |
| 1.2.1 Audio-only and Video-only (Prerecorded) | A | Transcript for audio-only; transcript or audio track for silent video | Check each media item | none (`audio-caption` is deprecated and does not run) |
| 1.2.2 Captions (Prerecorded) | A | Synchronized captions for recorded video with audio | Play with captions on; check accuracy and speaker IDs | flag only: video-caption |
| 1.2.3 Audio Description or Media Alternative (Prerecorded) | A | Audio description or a full text alternative for recorded video | Is visual-only information described? | none |
| 1.2.4 Captions (Live) | AA | Captions for live audio in synchronized media | Check the streaming setup | none |
| 1.2.5 Audio Description (Prerecorded) | AA | Audio description for recorded video (a text alternative alone no longer suffices at AA) | Same as 1.2.3, stricter | none |
| 1.4.2 Audio Control | A | Audio that autoplays for more than 3 s can be paused/stopped or volume-controlled separately | Load pages with media | partial: no-autoplay-audio |

## 7. Dynamic content and status

| SC | Lvl | What must be true | How to test | axe |
|---|---|---|---|---|
| 4.1.3 Status Messages | AA | Status updates that don't take focus (saved, 3 results, uploading, error count, added to cart) are exposed via `role="status"`/`aria-live`/`role="alert"` | Trigger each with a screen reader running; it must be spoken without moving focus | none |
| 4.1.2 Name, Role, Value | A | (state half) `aria-expanded`, `aria-selected`, `aria-pressed`, `aria-checked`, `aria-current` update as the UI changes | Toggle every disclosure/tab/toggle and inspect | partial |

## 8. Pointer, touch, and motion input

| SC | Lvl | What must be true | How to test | axe |
|---|---|---|---|---|
| 2.5.1 Pointer Gestures | A | Multipoint or path-based gestures (pinch, two-finger swipe, drawn shapes) have a single-pointer alternative | Find gesture handlers; is there a button alternative? | none |
| 2.5.2 Pointer Cancellation | A | Actions fire on the up-event (or can be aborted/undone); nothing commits on `mousedown`/`pointerdown` unless that is essential (a piano key) | Press, drag off, release: nothing should happen | none |
| 2.5.4 Motion Actuation | A | Shake/tilt features have a UI alternative and can be disabled | Find `devicemotion`/`deviceorientation` use | none |
| 2.5.7 Dragging Movements | AA | Anything done by dragging can also be done with single clicks/taps (e.g., move up/down buttons, "move to…" menu) | Sortable lists, sliders, kanban, map pans, file drop zones (a file-picker button satisfies the drop zone) | none |
| 2.5.8 Target Size (Minimum) | AA | Pointer targets are ≥ 24×24 CSS px, or an undersized target's 24 px-diameter circle (centered on it) doesn't overlap another target or its circle; exceptions: an equivalent control elsewhere on the page meets it, inline links in text, browser-default controls, essential/legally fixed presentation | axe `target-size`, then eyeball dense toolbars, pagination, close icons, table action icons | partial: target-size (off by default: runs only with the `wcag22aa` tag or when enabled by id) |

## 9. Timing, movement, and flashing

| SC | Lvl | What must be true | How to test | axe |
|---|---|---|---|---|
| 2.2.1 Timing Adjustable | A | Time limits can be turned off, adjusted (≥ 10×), or extended with a warning and ≥ 20 s to respond (real-time and essential limits, and limits over 20 h, excepted) | Session-timeout warnings, OTP timers, quizzes, carousels with timed steps | partial: meta-refresh |
| 2.2.2 Pause, Stop, Hide | A | Moving/blinking/scrolling content that starts automatically, lasts > 5 s, and sits beside other content can be paused/stopped/hidden; auto-updating content can be controlled | Carousels, marquees, tickers, looping hero videos, live feeds | partial: blink, marquee |
| 2.3.1 Three Flashes or Below Threshold | A | Nothing flashes more than 3 times per second (above the general/red flash thresholds) | Review animations, video, error flashing | none |

`prefers-reduced-motion` support maps to **2.3.3 Animation from Interactions, which is AAA**.
At AA, report missing reduced-motion support as a best practice (or as 2.2.2 when the motion
autoplays for more than 5 s with no pause control).

## 10. Consistency and help

| SC | Lvl | What must be true | How to test | axe |
|---|---|---|---|---|
| 2.4.5 Multiple Ways | AA | More than one way to find a page in a set (nav + search, sitemap, related links), except pages that are steps in a process | Check site-level navigation | none |
| 3.2.3 Consistent Navigation | AA | Repeated navigation appears in the same relative order across pages | Compare nav on several pages | none |
| 3.2.4 Consistent Identification | AA | Same function, same label/icon across pages ("Search" vs "Find" for the same thing fails) | Compare repeated controls | none |
| 3.2.6 Consistent Help | A | Help mechanisms that repeat across pages (contact details, chat, help link, FAQ link) stay in the same relative position | Check help placement across templates | none |

## 11. Authentication

| SC | Lvl | What must be true | How to test | axe |
|---|---|---|---|---|
| 3.3.8 Accessible Authentication (Minimum) | AA | No step requires a cognitive function test (memorizing, transcribing, solving a puzzle) unless an alternative exists, a mechanism helps (password managers can fill, paste is allowed), or the test is object recognition / identifying the user's own content | Login, MFA, and recovery: is paste allowed? does `autocomplete` let managers fill? is there a non-puzzle CAPTCHA alternative? | none |

Blocking paste into password or one-time-code fields is the most common 3.3.8 failure. Splitting
an OTP into six inputs that break paste is another. (`autocomplete="one-time-code"` is valid HTML
that helps here, though it is not one of the 1.3.5 input purposes.)

## 12. Removed and beyond-AA criteria you will be asked about

- **4.1.1 Parsing** is *obsolete and removed* in WCAG 2.2, and W3C's 2023 errata to WCAG 2.0
  and 2.1 add that it "should be considered as always satisfied" for any content using HTML or
  XML. Never file a 4.1.1 failure, even under a 2.0 or 2.1 contract. A markup defect is a
  finding only through the criterion it actually breaks: a duplicate `id` that makes an
  `aria-labelledby`/`for` reference resolve to the wrong element is 4.1.2 or 1.3.1 (axe's
  `duplicate-id-aria`). If an older audit script or contract test method still lists 4.1.1,
  mark it satisfied and cite the errata.
- **AAA criteria** are advisory unless the contract requires them. Common ones: 1.4.6 Contrast
  (Enhanced, 7:1 / 4.5:1), 2.4.12 Focus Not Obscured (Enhanced, no part hidden), 2.4.13 Focus
  Appearance (indicator size and 3:1 change), 2.5.5 Target Size (Enhanced, 44×44), 2.3.3
  Animation from Interactions, 2.2.6 Timeouts. Label them "AAA (advisory)" and never let them
  outrank an AA failure.
- **Mixing up 2.5.5 and 2.5.8** is the most frequent citation error: 44×44 is AAA (2.5.5);
  the AA requirement is 24×24 with a spacing exception (2.5.8).
