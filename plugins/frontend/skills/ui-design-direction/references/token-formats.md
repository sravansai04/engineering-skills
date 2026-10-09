# Finding the existing system, and writing tokens in the project's format

Read this in step 2 (discovery) and step 4 (encoding tokens). It covers where design systems hide,
how to measure whether a repo actually follows its system, copy-ready token shapes for the common
formats, consolidation, and how to read values from a running page.

Contents
1. Discovery commands
2. Deciding the mode from evidence
3. Token naming
4. Formats: CSS custom properties, Tailwind v4, Tailwind v3, DTCG JSON, CSS-in-JS / theme objects
5. Light, dark, and other themes
6. Consolidating a messy codebase
7. Reading values from a running page

---

## 1. Discovery commands

Run from the repository root. Always pass an explicit path (`.`) to ripgrep: with no path and a
non-terminal stdin (the normal case for agents and scripts), `rg` reads stdin and appears to hang.
If your environment has dedicated search tools, the same globs and patterns apply.

```bash
# Is this a monorepo? The design system often lives in a workspace package (packages/ui, libs/design)
rg --files -g 'pnpm-workspace.yaml' -g 'turbo.json' -g 'nx.json' -g 'lerna.json' .
rg -l '"workspaces"' -g 'package.json' -g '!**/node_modules/**' .

# Candidate token / theme / config files, in every package
rg --files -g '*tailwind.config.*' -g '*token*' -g '*theme*' -g 'components.json' \
   -g '*.tokens' -g '*.tokens.json' -g 'panda.config.*' -g 'uno.config.*' -g '*.css.ts' .

# Tailwind v4 (CSS-first config) and where @theme lives (either quote style)
rg -l -e '@import\s+["\x27]tailwindcss' -e '@theme\b' -g '*.css' .

# Where custom properties are defined
rg -c -e '--[\w-]+\s*:' -g '*.{css,scss,less}' . | sort -t: -k2 -rn | head

# Component libraries and styling stacks, in EVERY package.json (not only the root)
rg -o -e '"(@mui/material|@chakra-ui/react|@mantine/core|antd|@radix-ui/[a-z-]+|@headlessui/(react|vue)|react-aria-components|@ark-ui/[a-z-]+|bootstrap|vuetify|@angular/material|primevue|quasar|styled-components|@emotion/react|@vanilla-extract/css|@pandacss/dev|@stitches/react|style-dictionary|@tokens-studio/sd-transforms)"' \
   -g 'package.json' -g '!**/node_modules/**' .

# Storybook or a docs site that documents the system
rg --files -g '*.stories.*' -g '*.mdx' . | head
```

Signals and what they mean:
- `components.json` at a package root usually means shadcn/ui: components are copied into the repo
  and themed through CSS variables in the global stylesheet. Extend those variables; do not add a
  parallel palette.
- A `*.tokens.json` or Style Dictionary / Tokens Studio dependency means tokens are generated.
  Edit the source JSON and run the existing build script (look in `package.json` scripts), never
  the generated CSS.
- A component library (MUI, Chakra, Mantine, Ant Design, Vuetify, Angular Material) means the theme
  object is the token source. Customize through its theme API, not by overriding its CSS classes.
- In a monorepo, the package whose `package.json` declares the component library or Style
  Dictionary is usually the system's home; apps import from it. Add tokens there, not in the app.
- Native apps: look for `Color.xcassets` / asset catalogs (iOS), `colors.xml`, `themes.xml`,
  or a Compose `Theme.kt` (Android), and Flutter `ThemeData`. The same tiering applies.

Also read: the design or contributing docs, a recent well-reviewed UI pull request, and two or
three existing screens closest to what you are building. Those show the system as practiced, which
can differ from the system as documented.

## 2. Deciding the mode from evidence

Count rather than guess, with one tool so both numbers cover the same files:

```bash
node <skill-dir>/scripts/scan-hardcoded.mjs . --show 0
# scanned 412 file(s); token references: 2310 var(--...), 95 theme reads
# excluded 6 file(s) as token sources ...: src/styles/tokens.css, ...
# ...
# 640 potential hard-coded value(s).
```

Run it on the app or package you are working in (`apps/web`), not the whole monorepo, when packages
differ in maturity.

| Evidence | Mode |
|---|---|
| A token source exists and token references are at least about 3x the literal hits in component code | **Conform** |
| Some tokens exist, but literals are common (fewer than ~3 references per hit), there are several competing palettes, or an established look is built entirely from literals | **Consolidate** |
| No token source and no established look (a new app or prototype), or the user asked for a new look or rebrand | **Author** |

The 3x line is a rule of thumb, not a threshold to argue about; it separates "the system is the norm
and literals are exceptions" from "literals are the norm". Tailwind utility classes and component
library props are token use the counter cannot see, so in those codebases read a few components
before deciding. A component library used with its stock theme counts as a system to conform to
unless the user asked for a new look.

## 3. Token naming

- Pattern: `{category}-{role}-{variant}-{state}`, dropping parts that do not apply:
  `color-text-secondary`, `color-accent-hover`, `space-4`, `radius-md`, `shadow-floating`,
  `duration-fast`, `ease-standard`, `z-modal`, `focus-ring-width`.
- Name semantic tokens by purpose, never by appearance: `color-danger-fg`, not `color-red-text`.
  When the brand turns the danger color orange, the name should still be true.
- Keep primitives clearly separate (`palette-blue-600`) so it is obvious when a component reaches
  past the semantic tier.
- Spacing keys are multipliers of the 4px base everywhere they appear: `space-4` is 16px in CSS,
  `theme.space[4]` is 16px in a theme object, and Tailwind's `p-4` is 16px with `--spacing: 0.25rem`.
  Never let the same key mean different sizes in different formats.
- Follow the project's existing casing and separator; consistency beats any convention above.

## 4. Formats

### CSS custom properties (framework-free; works with any stack)

```css
/* tokens.css: primitives, then semantics. Components reference semantics only. */
:root {
  /* primitives */
  --palette-neutral-0: oklch(0.99 0.004 255);
  --palette-neutral-900: oklch(0.24 0.02 255);
  --palette-blue-500: oklch(0.55 0.18 255);
  --palette-blue-600: oklch(0.52 0.16 255);

  /* semantics */
  --color-surface-canvas: var(--palette-neutral-0);
  --color-text-primary: var(--palette-neutral-900);
  --color-accent-rest: var(--palette-blue-600);
  --color-border-focus: var(--palette-blue-500);

  --space-1: 0.25rem;  --space-2: 0.5rem;  --space-3: 0.75rem;  --space-4: 1rem;  --space-6: 1.5rem;
  --radius-sm: 0.25rem; --radius-md: 0.5rem;
  --font-body: "Source Sans 3", system-ui, sans-serif;
  --text-body-size: 1rem; --text-body-leading: 1.5;
  --duration-fast: 120ms; --duration-base: 220ms;
  --ease-standard: cubic-bezier(0.4, 0, 0.2, 1);   /* moving or changing within the view: hover, press */
  --ease-enter: cubic-bezier(0, 0, 0.2, 1);        /* decelerate: things arriving */
  --ease-exit: cubic-bezier(0.4, 0, 1, 1);         /* accelerate: things leaving */
  --focus-ring-width: 2px; --focus-ring-offset: 2px;
  --shadow-floating: 0 1px 2px oklch(0 0 0 / 0.08), 0 8px 24px oklch(0 0 0 / 0.12);
}

/* component: no literals */
.button {
  padding: var(--space-2) var(--space-4);
  border-radius: var(--radius-md);
  background: var(--color-accent-rest);
  transition: background-color var(--duration-fast) var(--ease-standard);
}
.button:focus-visible {
  outline: var(--focus-ring-width) solid var(--color-border-focus);
  outline-offset: var(--focus-ring-offset);
}
```

A fuller color-only example, with a dark theme, is [../scripts/tokens.example.css](../scripts/tokens.example.css);
it is the stylesheet the example contrast pairs file resolves against.

### Tailwind CSS v4 (CSS-first)

Theme variables in `@theme` generate utilities (`--color-*` gives `bg-*`, `text-*`; `--spacing`
sets the base unit for spacing utilities; `--radius-*`, `--shadow-*`, `--font-*`, `--text-*`,
`--breakpoint-*`, `--ease-*`, `--animate-*` likewise). `--color-*: initial;` removes the default
palette, including `white` and `black`, so only project colors generate utilities. Unknown color
classes such as `bg-blue-500` or `text-white` then produce no CSS at all, with no warning: a button
can lose its text color silently. Pair the reset with `scan-hardcoded.mjs --tailwind-palette`, which
flags default-palette class names, and add back `--color-white` / `--color-black` only if the
direction uses them.

```css
@import "tailwindcss";

@theme {
  --color-*: initial;                 /* only our colors generate utilities */
  --font-sans: "Source Sans 3", system-ui, sans-serif;
  --radius-md: 0.5rem;
}

/* theme variables whose value is another variable: use `inline` so each utility
   resolves the variable where it is used (this is what makes per-theme swaps work) */
@theme inline {
  --color-canvas: var(--canvas);
  --color-ink: var(--ink);
  --color-accent: var(--accent);
  --color-focus: var(--focus);
}

/* values that change per theme live outside @theme */
:root { --canvas: oklch(0.99 0.004 255); --ink: oklch(0.24 0.02 255); --accent: oklch(0.52 0.16 255); --focus: oklch(0.55 0.18 255);
        --focus-ring-width: 2px; --focus-ring-offset: 2px; }
[data-theme="dark"] { --canvas: oklch(0.2 0.012 255); --ink: oklch(0.94 0.008 255); --accent: oklch(0.74 0.13 255); --focus: oklch(0.74 0.13 255); }

/* a token-built utility, usable with variants: focus-visible:focus-ring */
@utility focus-ring {
  outline: var(--focus-ring-width) solid var(--color-focus);
  outline-offset: var(--focus-ring-offset);
}
```

### Tailwind CSS v3 (`tailwind.config.js`)

```js
// Point theme keys at CSS variables so light/dark is a variable swap, not a class swap.
export default {
  theme: {
    colors: {                       // replaces (not extends) the default palette
      canvas: 'var(--canvas)',
      ink: 'var(--ink)',
      accent: { DEFAULT: 'var(--accent)', hover: 'var(--accent-hover)' },
      focus: 'var(--focus)',
      transparent: 'transparent',
      current: 'currentColor',
    },
    extend: { borderRadius: { md: '0.5rem' } },
  },
};
// Opacity modifiers (bg-accent/50) need channel-only variables in v3:
// accent: 'rgb(var(--accent-rgb) / <alpha-value>)'  with  --accent-rgb: 20 103 194;
```

In v3, declare the focus utility in CSS so variants apply to it:
`@layer utilities { .focus-ring { outline: var(--focus-ring-width) solid var(--focus); outline-offset: var(--focus-ring-offset); } }`.
(v3's `outline-2` sets only the width; the style comes from the `outline` class or the browser.)

### Design Tokens Community Group format (tool-neutral JSON)

The DTCG format reached its first stable version (2025.10). Tokens are objects with `$value`;
`$type` can be set on a group and inherited; aliases use `{group.token}`. In 2025.10, color values
are objects (`colorSpace`, `components`, optional `alpha` and `hex`) and dimensions are
`{ "value": n, "unit": "px" | "rem" }`. Older tools may still expect the earlier string values,
so check what the repo's pipeline accepts (Style Dictionary added the object forms during v5).

```json
{
  "palette": {
    "$type": "color",
    "blue-600": { "$value": { "colorSpace": "oklch", "components": [0.52, 0.16, 255], "hex": "#1467c2" } }
  },
  "color": {
    "$type": "color",
    "accent-rest": { "$value": "{palette.blue-600}", "$description": "Primary interactive color" }
  },
  "space": {
    "$type": "dimension",
    "4": { "$value": { "value": 1, "unit": "rem" } }
  }
}
```

Build to CSS with the repo's existing pipeline, for example
`npx style-dictionary build --config ./sd.config.js` (Style Dictionary's `build` command;
`-p/--platform` builds one platform). The `hex` field above is a fallback for tools that cannot read
OKLCH: regenerate it from the components rather than typing it by hand. Point the contrast pairs
file's `$css` at the generated CSS so contrast checks follow the source tokens.

### CSS-in-JS and component-library theme objects

```ts
// One typed theme object; components read from it, never from literals.
// space is keyed by multiplier of 4px, matching --space-N (space[4] = 1rem = 16px).
export const theme = {
  color: { surface: { canvas: 'var(--canvas)' }, text: { primary: 'var(--ink)', onAccent: 'var(--on-accent)' }, accent: { rest: 'var(--accent)' } },
  space: { 0: '0', 1: '0.25rem', 2: '0.5rem', 3: '0.75rem', 4: '1rem', 6: '1.5rem', 8: '2rem', 12: '3rem' },
  radius: { sm: '0.25rem', md: '0.5rem', full: '9999px' },
} as const;
```

Pointing theme values at CSS variables keeps theme switching a CSS concern (no re-render, no flash)
and lets plain CSS and the JS theme share one source. Libraries with their own theme APIs (MUI
`createTheme`, Chakra `extendTheme` / `createSystem`, Mantine `createTheme`) should be configured
through those APIs; check the installed major version's docs, since these APIs change across
majors. Note that some libraries treat a bare number as a scale index rather than pixels (theme-ui
`p: 3`); keep the library's convention and do not mix it with pixel numbers.

## 5. Light, dark, and other themes

```css
:root { color-scheme: light; /* light semantic values */ }
[data-theme="dark"] { color-scheme: dark; /* dark semantic values */ }

@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) { color-scheme: dark; /* dark semantic values */ }
}
```

- Only the semantic tier changes per theme. If a component needs a `dark:` override, a semantic
  token is missing.
- Where the theme attribute sits matters for tokens built from other tokens. A custom property
  inherits its computed value: if `:root` declares `--color-text: var(--ink)` and the theme only
  remaps `--ink` on an INNER element (`<body class="dark">`, a wrapper), `--color-text` keeps the
  `:root` value. Set the theme attribute on `<html>`, or redeclare the semantic tokens in the theme
  block. `token-contrast.mjs` models both cases (`"$scope": "root"` or `"descendant"`).
- `light-dark(<light>, <dark>)` picks a value based on the used `color-scheme`; it is newer, so
  check your browser support targets before relying on it. The contrast script resolves it when the
  group sets `"$scheme"`.
- Density or brand themes follow the same pattern: a selector that remaps a subset of semantics.

## 6. Consolidating a messy codebase

1. Inventory the de facto values by frequency, with merge proposals:
   ```bash
   node <skill-dir>/scripts/scan-hardcoded.mjs src --inventory
   ```
   It reads the same files and literal forms as the scan (hex of every length, `rgb()` / `hsl()` /
   `oklch()` / `color()`, named colors, px and rem, unitless style numbers) and prints:
   - colors grouped when they are within 0.02 of each other in OKLab and share an alpha (about one
     just-noticeable difference; change it with `--cluster-de`), with the most used value first;
   - lengths with rem converted at 16px, split into values already on the 4px grid and values off
     it, each with its nearest step (a value exactly between two steps lists both: the layout
     decides).
2. Map each color cluster to a ramp step or semantic role and each off-grid length to its step.
   Values that are far from everything else are either a real role (a status color) or a mistake;
   decide which, do not mint a token for each.
3. Capture visual baselines before changing anything, so the migration can prove it changed nothing
   by accident. With Playwright tests, add `await expect(page).toHaveScreenshot('invoices.png', { maxDiffPixelRatio: 0.001 })`
   for the affected screens and run `npx playwright test --update-snapshots` on the unmigrated code;
   without a test suite, capture page-smoke shots (browser-testing) at the same widths and compare
   them with a pixel diff tool. Expect zero differences except where a cluster merge moved a value
   on purpose; list those.
4. Write the token file, then migrate only the components your task touches. List the remaining
   hot spots (files with the most hits in `scan-hardcoded.mjs --json`) as follow-up work instead of
   rewriting the whole codebase in one change.
5. Re-run the screenshots against the baselines. A consolidation that changes appearance by accident
   is a regression.

## 7. Reading values from a running page

The browser is the ground truth for what a user sees: it has resolved every `var()`, `color-mix()`,
theme attribute, and cascade layer. Use it when matching a live reference, when tokens live in a
format the contrast script cannot read, or to confirm a suspicious result. Run this through the
browser tool's evaluate step (or the DevTools console), once per theme:

```js
// Rendered values for one element: text color, the first non-transparent background behind it,
// and the box and type values worth mapping to tokens.
(selector) => {
  const el = document.querySelector(selector);
  const cs = getComputedStyle(el);
  let node = el;
  let bg = 'rgba(0, 0, 0, 0)';
  while (node && /^(rgba\(0, 0, 0, 0\)|transparent)$/.test(bg)) {
    bg = getComputedStyle(node).backgroundColor;
    node = node.parentElement;
  }
  return {
    color: cs.color, background: bg, borderColor: cs.borderTopColor,
    padding: cs.padding, radius: cs.borderRadius, gap: cs.gap,
    font: `${cs.fontWeight} ${cs.fontSize}/${cs.lineHeight} ${cs.fontFamily}`,
  };
}
```

- Colors come back as `rgb()`, `oklch()`, `oklab()`, or `color(srgb ...)` depending on how they were
  written; `token-contrast.mjs` accepts all of them, so paste them in directly.
- The background walk stops at the first opaque-or-translucent color. If that color is translucent,
  or the element sits on an image or gradient, the real backdrop is a composite: check the worst
  point of the image with a scrim pair instead (see the scrim example in the pairs file).
- A token's resolved value for the current theme:
  `getComputedStyle(document.documentElement).getPropertyValue('--color-text-secondary').trim()`.
  For tokens defined with `color-mix()` this returns the unevaluated expression; set it as an
  element's `color` and read `getComputedStyle(el).color` to get the computed color.
- Computed lengths are in CSS pixels; map them to the nearest scale step, and record anything that
  matches no step as a deviation rather than a new token.
