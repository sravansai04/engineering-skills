# Visual foundations: the decisions behind each token group

Read this when you are authoring or consolidating a direction (not when you are conforming to an
existing system; there, the system has already made these calls). Each section gives the decision
to make, sensible starting numbers, and the reasoning, so you can depart from the numbers on purpose.

Contents
1. Context dial
2. Typography
3. Spacing and sizing
4. Color (including data visualization)
5. Shape: radius, borders, separation
6. Elevation and layering
7. Motion
8. Layout, grid, breakpoints
9. Iconography and imagery

---

## 1. Context dial

Set these four dials before anything else. They resolve most later arguments ("should this be
bigger?", "can we add a gradient?") by pointing back to the job of the surface.

| Surface | Density | Expressiveness | Color budget | Motion budget |
|---|---|---|---|---|
| Data-heavy tool used all day (admin, ops console, IDE-like) | High: compact controls, 14px body acceptable, tight rows | Low: type and layout do the work | Neutrals plus one accent; color reserved for status and selection | Feedback only (press, expand, toast) |
| Consumer app / transactional flow (checkout, booking, settings) | Medium | Medium: one recognizable move | Neutrals, accent, a supporting hue | Feedback plus continuity between steps |
| Marketing / landing / portfolio / docs home | Low: generous whitespace | High: type as image, bold layout | Freer, still with semantic roles | At most one choreographed sequence per page, never tied to scroll, removed under reduced motion |
| Reading surface (docs, articles, long forms) | Low | Low-medium | Mostly neutrals | Nearly none |

If one product spans rows (a marketing site plus an app), give each surface its own dial settings
over a shared token base. Do not let marketing expressiveness leak into the tool.

---

## 2. Typography

**Choosing faces.** Start from the role, not the font list.
- A system stack (`system-ui, -apple-system, "Segoe UI", Roboto, sans-serif`) is a legitimate,
  fast choice for tools. Choose it on purpose, not by omission.
- One family with a good weight range (ideally a variable font) covers most products. Add a second
  family only when it contrasts clearly on one axis: serif vs sans, geometric vs humanist,
  proportional vs monospace for code or data.
- Before committing, check: glyph coverage for every language you ship (accents, Cyrillic, CJK
  fallbacks), tabular figures, legible small sizes, and a license that allows web embedding or
  self-hosting. A beautiful face without the glyphs your users need is not a choice, it is a bug.

**Type scale.**
- Body size: 16px for reading surfaces; 14px is acceptable in dense tools if line height and
  contrast are generous; avoid anything people must read below 12px.
- Ratio by context: about 1.125 to 1.2 for dense UI, about 1.25 for general product UI, 1.333 and up
  for editorial or marketing display sizes. Round results to whole pixels; a scale is a guide, not
  a law.
- Keep 6 to 9 named steps. Name them by role (`display`, `title`, `heading`, `body`, `label`,
  `caption`), not by size, so a later rebalance does not rename everything.
- Each step is a bundle: size, line height, weight, letter spacing. Ship them together so nobody
  pairs a 32px size with body line height.
- Fluid sizes (`clamp()`) suit display text only. Always include a `rem` term, for example
  `clamp(2rem, 1.25rem + 2.5vw, 3.5rem)`: a size made only of `vw` does not grow when the user
  zooms, which breaks text resizing (WCAG 1.4.4).

**Rhythm and measure.**
- Line height, unitless: body about 1.45 to 1.6, headings about 1.1 to 1.25. Tighten as size grows.
- Reading width: roughly 45 to 75 characters. `max-width: 65ch` is a reasonable start; confirm by
  eye, since `ch` is the width of the "0" glyph and varies by font.
- Letter spacing: slightly negative for large display sizes, zero for body, slightly positive only
  for small all-caps text (and use all-caps sparingly; it is harder to read).
- Weights: two or three. Build hierarchy with size and weight first, color second. If everything is
  bold, nothing is.
- Numbers in tables, timers, and prices: `font-variant-numeric: tabular-nums` so columns align and
  values do not jitter as they change.
- Headings: `text-wrap: balance` avoids one-word last lines (progressive enhancement).
- Left-align text in left-to-right languages for anything longer than a line. Center only short,
  symmetric content.

**Loading.** Limit families and weights (each file costs time). Self-host or preconnect, preload
the primary text weight, use `font-display: swap` (or `optional` where a late swap would be
jarring), and match fallback metrics with `@font-face` descriptors such as `size-adjust` and
`ascent-override` so the swap does not shift layout.

---

## 3. Spacing and sizing

- Base unit 4px. A practical scale: 0, 2, 4, 8, 12, 16, 20, 24, 32, 40, 48, 64, 80, 96, 128 (px),
  expressed in `rem` so it respects user font settings. Use the 4px steps inside components and the
  8px-multiple steps for layout.
- Name steps by index (`space-1` = 4px ... ) or by t-shirt size; pick one convention and keep it.
- Proximity carries meaning: space inside a group is smaller than space between groups. If a label
  sits equally far from its own field and the next one, the form reads wrong no matter the colors.
- Do not invent in-between values (13px, 18px, 22px). If no step fits, the layout usually needs a
  different structure, not a new number.
- Control heights as tokens tied to density, for example 32 / 40 / 48px for small / medium / large.
- Icon sizes as tokens aligned to text sizes, for example 16 / 20 / 24px.
- Pointer targets: at least 24 by 24 CSS px (WCAG 2.5.8, AA) or enough spacing around smaller ones;
  aim for about 44 by 44 for primary touch controls (common platform guidance is 44pt on iOS and
  48dp on Android).

---

## 4. Color

**Architecture: three tiers.**
1. *Primitives*: raw ramps (`blue-50 ... blue-950`, `neutral-0 ... neutral-1000`). No component
   ever references these.
2. *Semantic roles*: what a color is for (`text-primary`, `surface-raised`, `accent-rest`). This is
   the tier components use, and the tier that changes between light and dark.
3. *Component tokens* (optional): `button-primary-bg` aliases a semantic token. Add them only when
   a component needs to diverge from the role, or when a large system needs per-component theming.

**Building ramps.** Build in OKLCH: hold hue roughly constant, step lightness evenly, and ease
chroma down toward the very light and very dark ends. Equal lightness steps in OKLCH look like
equal steps; equal steps in HSL do not. Very saturated OKLCH values fall outside sRGB; keep
chroma inside the sRGB gamut, or provide an sRGB fallback, unless you deliberately target wide-gamut
displays. Neutrals can be pure gray or tinted slightly toward the brand hue (chroma around 0.005 to
0.02); decide, because mixing both looks muddy.

**Semantic roles to define** (rename to the project's conventions):

| Group | Roles |
|---|---|
| Surface | canvas, raised, sunken, overlay, inverse |
| Text | primary, secondary, disabled, inverse, on-accent, link |
| Border | subtle (dividers), control (inputs), strong, focus |
| Accent | rest, hover, pressed, subtle (tinted background), on-accent |
| Status | success, warning, danger, info; each with fg, bg, border |
| Other | selection, scrim, highlight |

**Budget.** One accent hue does the work of "interactive or important". Status colors mean status
and nothing else. Never let color be the only signal (WCAG 1.4.1): pair it with text, an icon, or
a pattern. Charts get their own tier (below) so series colors never borrow status or accent roles.

**Contrast targets (WCAG 2.2 AA).**

| Pair | Minimum |
|---|---|
| Body and UI text, placeholder text | 4.5:1 |
| Large text (at least 24px, or 18.66px bold) | 3:1 |
| Boundaries that identify a control (input border when it is the only edge), meaningful icons, chart marks | 3:1 against adjacent colors |
| Focus indicator | 3:1 against the colors next to it |
| Disabled controls | exempt, but keep them recognizable as controls |

Check every pair that actually occurs, in every theme, with `scripts/token-contrast.mjs` (pairs
name tokens, so re-runs follow token edits). Common misses: secondary text on sunken or tinted
surfaces, text on the hover state of a colored button, status text on its own status background,
chart marks on the plot background, and the focus ring drawn directly on an accent-colored button.

**Data visualization.** Chart libraries ship their own palettes, so on a dashboard the most visible
off-system colors are usually the series colors. Give charts a semantic group of their own:

| Need | Build | Tokens |
|---|---|---|
| Categorical (series, segments) | 6 to 8 hues from the primitive ramps, spread around the hue circle, with lightness inside a narrow band (about 0.55 to 0.75 OKLCH L in light mode) so no series dominates by brightness alone. Order them so neighbors in the legend differ most. Beyond 8 series, group the tail into "Other" or label directly rather than adding hues. | `chart-cat-1` ... `chart-cat-8` |
| Sequential (low to high) | One hue, or two adjacent hues, stepping lightness monotonically over 5 to 9 steps; chroma peaks mid-ramp | `chart-seq-1` ... `chart-seq-7` |
| Diverging (below / above a meaningful midpoint) | Two sequential ramps of contrasting hue meeting at a neutral that represents zero, target, or average | `chart-div-neg-*`, `chart-div-mid`, `chart-div-pos-*` |
| Chrome | Grid lines, axes, labels, tooltip surface | `chart-grid`, `chart-axis`, `chart-label`, `chart-tooltip-bg` |

- Remap the group per theme like any semantic token: dark plots need lighter, slightly less
  saturated marks.
- Contrast (WCAG 1.4.11): every mark needed to read the chart has at least 3:1 against the plot
  background; add each categorical step to the pairs file with `kind: ui`. Adjacent filled areas
  (stacked bars, pie or donut slices) either differ by 3:1 or are separated by a gap or a border in
  the surface color.
- Color is never the only key (WCAG 1.4.1): label lines and the largest segments directly, vary
  marker shape or dash pattern by series, keep the legend in series order, and offer the numbers
  in a table or tooltip.
- Check the categorical set under simulated color-vision deficiency (protanopia, deuteranopia,
  tritanopia, achromatopsia): Chrome DevTools, Rendering panel, "Emulate vision deficiencies"; in
  automation, Chromium's CDP command `Emulation.setEmulatedVisionDeficiency` through a CDP session
  (Playwright: `page.context().newCDPSession(page)`), then screenshot. Two series that merge in a
  simulation need a larger lightness difference (about 0.1 OKLCH L or more), not just another hue;
  the narrow lightness band above is a starting point that this check is allowed to break.
- Theme the chart library once, from the tokens: set its global defaults or theme object by reading
  the custom properties at runtime (`getComputedStyle(document.documentElement).getPropertyValue('--chart-cat-1')`)
  and re-apply on theme change. A color passed to one chart's options is a literal like any other.

**Dark mode is a second mapping, not an inversion.**
- Surfaces get lighter as they rise in elevation, because shadows barely show on dark backgrounds.
- Avoid pure white text on pure black for long reading; a slightly lifted canvas and off-white text
  reduce glare. Lower the chroma of large colored fills; saturated areas vibrate on dark.
- Accents usually need a lighter step than in light mode to keep contrast; re-run every pair.
- Set `color-scheme: light dark` (or the active scheme) so native controls and scrollbars match.
- Default to `prefers-color-scheme`, allow a user override, and apply the chosen theme before first
  paint (an attribute set by a tiny inline script or by the server) to avoid a flash of the wrong
  theme.

**Forced colors (Windows high contrast).** The browser replaces your palette and removes box
shadows. Draw focus indicators with `outline` (an outline whose color is `transparent` still appears
in forced colors, at `var(--focus-ring-width)`), do not convey state through background color alone,
and test with `@media (forced-colors: active)` adjustments where needed.

---

## 5. Shape: radius, borders, separation

- Pick a shape personality (sharp, softened, round) from the concept and apply it everywhere.
- Radius scale of 4 to 6 steps (`none`, `sm`, `md`, `lg`, `xl`, `full`). Scale radius with element
  size: a 24px chip and a 600px panel should not share the same radius.
- Nested corners: inner radius = outer radius minus the gap between them (never below 0). Equal
  radii on nested elements look pinched.
- Choose one primary separation device per surface: whitespace, hairline borders, tonal surface
  steps, or shadow. Combining all four on the same card is noise.
- Hairlines (1px) are fine as literals; everything thicker belongs to a border-width token.
- The focus ring has its own tokens: `focus-ring-width` (2px is a common minimum; the WCAG 2.4.13
  AAA guidance describes a 2px-thick perimeter) and `focus-ring-offset`, so every control draws the
  same ring and a ring on an accent button can be offset onto the canvas.

---

## 6. Elevation and layering

- Three or four levels, each with a meaning: resting (flat), raised (cards, sticky headers),
  floating (menus, popovers), modal (dialogs, sheets). A level nobody can explain should be cut.
- Shadows read as physical when they combine a soft wide ambient layer with a tighter key layer.
  Store each level as one token.
- In dark mode, express elevation with lighter surfaces plus a subtle border; keep shadows weak.
- Stacking order as named tokens: base, dropdown, sticky, overlay, modal, popover, toast, tooltip.
  Magic z-index numbers lead to escalating wars (9999, 99999).

---

## 7. Motion

- Motion must earn its place: give feedback (a press registered), show continuity (where the panel
  came from), or direct attention (one thing changed). Decoration-only motion in product UI is cost.
- Duration tokens: fast about 100 to 150ms (hover, press, small fades); base about 200 to 250ms
  (expand, collapse, small overlays); slow about 300 to 400ms (large panels, page-level changes).
  Longer feels sluggish for UI responses.
- Easing tokens: decelerate (ease-out) for things entering, accelerate (ease-in) for things leaving,
  standard (ease-in-out) for things moving within the view.
- Animate `transform` and `opacity`; animating `width`, `height`, `top`, or `left` forces layout
  work every frame and stutters on slow devices.
- `prefers-reduced-motion: reduce`: replace movement and parallax with a fade or an instant change.
  Do not remove feedback entirely; remove travel.
- Never make content wait for an animation to finish before it can be read or used.
- Loading indicators: for fast operations, delay showing a spinner by a few hundred milliseconds to
  avoid a flash; once shown, keep it long enough to be perceived. Prefer skeletons when the layout
  of the result is known.

---

## 8. Layout, grid, breakpoints

- Design the smallest viewport first, then add layout as space allows (`min-width` queries).
- Breakpoints go where the content breaks, not at device names. A common starting set is about
  40em, 48em, 64em, 80em (640, 768, 1024, 1280px at default font size). Media queries in `em` respond
  to the user's font size. Note that `var()` cannot be used inside a media query condition; keep
  breakpoints as build-time tokens (preprocessor variables, a framework's breakpoint config, or
  `@custom-media` with a PostCSS plugin).
- Grid: for example 4 columns on small, 8 on medium, 12 on large, gutters from the spacing scale,
  and a maximum content width so lines and layouts do not stretch on wide screens.
- Components that appear in containers of different widths (sidebar vs main) should respond to
  their container (`@container` queries), not the viewport.
- Content must reflow at 320 CSS px wide without horizontal page scrolling (WCAG 1.4.10). Wide data
  tables may scroll inside their own container; keep the first column sticky so rows stay
  identifiable.
- Mobile viewport height: prefer `dvh` or `svh` over `vh`; respect notches with
  `env(safe-area-inset-*)`.
- Use logical properties (`margin-inline`, `padding-block`, `inset-inline-start`) so a right-to-left
  locale mirrors correctly.
- Primary action placement and order should be consistent across screens; users learn positions.

---

## 9. Iconography and imagery

- One icon set, one grid, one stroke weight (or one fill style). Mixing sets is visible at a glance.
- Size icons with icon-size tokens matched to adjacent text; color them with `currentColor` so they
  follow text and state colors.
- Pair icons with text labels unless the meaning is universal in context (close, search, menu).
  Icon-only buttons need an accessible name and usually a tooltip. Decorative icons are hidden from
  assistive technology.
- Do not use emoji as interface icons: they render differently on every platform, cannot follow
  your color tokens, and screen readers announce their full names.
- Pick a set whose license suits the project (many popular open sets use MIT or ISC; verify).
- Images: reserve their space (width and height attributes or `aspect-ratio`) to prevent layout
  shift, give meaningful images real alt text and decorative ones empty alt, and decide one
  treatment (crop ratios, corner radius, overlays) for the whole product.
