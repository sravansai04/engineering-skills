# Frontend Performance Review

Read this when the change touches client-side code: components, pages, routing, data fetching in the browser, assets, fonts, or the build and bundle configuration.

## Contents

1. [What "good" means](#what-good-means)
2. [Bundle size](#bundle-size)
3. [Request waterfalls](#request-waterfalls)
4. [Rendering and re-renders](#rendering-and-re-renders)
5. [Layout thrash and animation](#layout-thrash-and-animation)
6. [Images, fonts, and third-party scripts](#images-fonts-and-third-party-scripts)
7. [Delivery and caching](#delivery-and-caching)
8. [Main-thread work and input responsiveness](#main-thread-work-and-input-responsiveness)
9. [Memory in long-lived pages](#memory-in-long-lived-pages)
10. [Measuring](#measuring)

---

## What "good" means

Anchor findings to Core Web Vitals, which are measured at the **75th percentile** of page loads, separately for mobile and desktop:

| Metric | Measures | Good |
|---|---|---|
| LCP (Largest Contentful Paint) | Loading | 2.5 s or less |
| INP (Interaction to Next Paint) | Responsiveness. It replaced FID in March 2024 | 200 ms or less |
| CLS (Cumulative Layout Shift) | Visual stability | 0.1 or less |

Name the metric a finding affects ("delays LCP on the product page", "long task on every keystroke hurts INP"). That ties the finding to something the team already tracks. Assume a mid-range phone on a mediocre network, not the reviewer's laptop.

---

## Bundle size

**Red flags**
- Whole-library imports where only one function is used, e.g. `import _ from "lodash"` or an entire icon set.
- Date, i18n, or charting libraries that pull every locale or chart type into the main bundle.
- A heavy dependency added for a trivial job (a deep-equal library, a 300 KB utility for one helper).
- Two versions of the same package in the build. Check with `npm ls PACKAGE`, `yarn why PACKAGE`, or `pnpm why PACKAGE`.
- Rarely visited routes, modals, editors, or charts loaded eagerly instead of with a dynamic `import()`.
- Large JSON or data files imported straight into the bundle instead of fetched on demand.
- Server-only code or secrets-adjacent config leaking into the client bundle.
- Polyfills shipped to browsers the project's support targets don't need.

**Fixes.** Import per function or per module (`lodash-es`, named imports that tree-shake), lazy-load by route and by interaction, swap heavy dependencies for lighter ones or a few lines of code, dedupe versions, and add a size budget to CI (`size-limit`, or the bundler's own size warnings) so the regression can't come back unnoticed.

**Evidence.** Build the project the way production does (find the build script in `package.json`), then inspect it with the analyzer that fits the bundler: `npx source-map-explorer 'dist/**/*.js'` (needs source maps), `webpack-bundle-analyzer` against a stats file, `rollup-plugin-visualizer` for Rollup and Vite. For Next.js 16.1 and later, where Turbopack is the default bundler, use `next experimental-analyze` (add `--output` to save a report you can compare before and after). `@next/bundle-analyzer` only produces a report for webpack builds (`next build --webpack`). Compare before and after sizes, gzip or brotli compressed.

---

## Request waterfalls

**Red flags**
- Sequential `await`s for independent requests.
- Fetch-on-render chains: a parent fetches, renders a child, the child fetches, and so on. Each level adds a full round trip.
- A client-side N+1: a list where every row fetches its own details.
- Critical resources discovered late: a hero image set from CSS or JS, fonts referenced only from CSS, data fetched only after the JS bundle has loaded and run.
- Search-as-you-type that fires a request per keystroke without debouncing or cancelling stale requests.

**Fixes**
- Run independent requests concurrently (`Promise.all`), and hoist data fetching to the route or loader level so it starts before rendering.
- Batch per-row requests into one list request, or have the server return the joined data.
- Use `<link rel="preload">` for late-discovered critical resources, and `<link rel="preconnect">` for critical third-party origins.
- Debounce input-driven requests and cancel superseded ones with `AbortController`.

```js
// Before: two round trips in series
const user = await getUser(id);
const prefs = await getPrefs(id);

// After: one round trip of wall time
const [user, prefs] = await Promise.all([getUser(id), getPrefs(id)]);
```

---

## Rendering and re-renders

**Red flags (component frameworks in general)**
- State held higher than it needs to be, so a keystroke re-renders a whole page.
- New object, array, or function props created on every render, which defeats memoized children.
- A context or store value rebuilt on every render, which re-renders every consumer.
- Unstable list keys. Random keys force every row to remount. Index keys on reorderable lists cause remounts and state bugs.
- Expensive derived data recomputed on every render instead of memoized or computed once.
- Long lists (hundreds of rows or more) rendered in full rather than virtualized or paginated.

**Framework notes**
- React: `React.memo`, `useMemo`, and `useCallback` only help when inputs are stable. Split contexts by update frequency. If the project uses React Compiler, it memoizes automatically, so check before asking for manual memoization. Virtualize with a library such as `react-window` or TanStack Virtual.
- Vue: prefer `computed` over methods for derived values. `v-memo` and `shallowRef` help with large, rarely changing structures.
- Angular: `ChangeDetectionStrategy.OnPush`, and a `track` expression in `@for` (or `trackBy` with `*ngFor`).

**Evidence.** Use the React DevTools Profiler (or the framework's equivalent) to record the interaction and count renders, or the browser's Performance panel to find long scripting tasks. Ask for this before demanding memoization everywhere. Memoization has its own cost and clutters code.

---

## Layout thrash and animation

**Red flags**
- A loop that alternates layout reads (`offsetWidth`, `offsetHeight`, `getBoundingClientRect()`, `scrollTop`, `getComputedStyle`) with style writes. Every read after a write forces a synchronous layout.
- Animating `top`, `left`, `width`, `height`, or `margin` instead of `transform` and `opacity`.
- Scroll or resize handlers that do layout work on every event without throttling or `requestAnimationFrame`.
- Content inserted above existing content without reserved space, which causes CLS.

```js
// Before: forces layout on every iteration
for (const el of items) el.style.width = container.offsetWidth / 2 + "px";

// After: read once, then write
const half = container.offsetWidth / 2;
for (const el of items) el.style.width = half + "px";
```

**Fixes.** Batch reads, then writes. Animate compositor-friendly properties. Use `ResizeObserver` and `IntersectionObserver` instead of polling layout. Reserve space for late content with fixed dimensions, `aspect-ratio`, or skeletons.

---

## Images, fonts, and third-party scripts

**Images**
- Always set `width` and `height` (or CSS `aspect-ratio`) so the browser reserves space and avoids CLS.
- Serve responsive sizes (`srcset` and `sizes`) and modern formats (AVIF or WebP with a fallback). Don't ship a 4000 px original to a 400 px slot.
- Add `loading="lazy"` to below-the-fold images, but **not to the LCP image**. Lazy-loading the hero image delays LCP. Give the LCP image `fetchpriority="high"` instead.
- Replace large animated GIFs with video, and use SVG for icons.

**Fonts.** Use `font-display: swap` or `optional`, preload only the one or two critical font files, subset to the needed character ranges, and avoid many weights. A font preload needs the `crossorigin` attribute even for same-origin fonts. Without it the browser can't reuse the preloaded file, so it downloads the font twice.

**Third-party scripts.** Tag managers, chat widgets, A/B testing, and analytics often dominate main-thread time. Load them with `async` or `defer`, after interaction where possible, or behind a lightweight facade for embeds. Flag any new synchronous third-party script in `<head>`.

---

## Delivery and caching

**Red flags**
- Build assets (JS, CSS, fonts, images) served without content-hashed filenames, or without a long-lived cache header, so every visit downloads the bundle again.
- HTML served with a long cache lifetime, which pins users to stale asset references after a deploy.
- Text assets (HTML, JS, CSS, JSON, SVG) served without brotli or gzip compression.
- Large component trees shipped to the client and hydrated even though they aren't interactive, such as static content, layout, and read-only tables.

**Fixes.** Give hashed build assets `Cache-Control: public, max-age=31536000, immutable`, and give HTML a short lifetime or `no-cache` so it revalidates. Enable brotli or gzip at the server or CDN for text responses. Keep non-interactive UI out of the client bundle by rendering it on the server or using the framework's partial hydration (server components, islands), and hydrate only the parts that respond to input.

**Evidence.** In the browser's Network panel, check the response headers (`Cache-Control`, `Content-Encoding`) and compare the transferred size with the resource size. A repeat visit that transfers the full bundle again means caching is broken. For hydration cost, record a page load in the Performance panel and look at the scripting time after the HTML arrives.

---

## Main-thread work and input responsiveness

**Red flags**
- Long tasks (over 50 ms) in input, click, or scroll handlers: large synchronous parsing, sorting, or filtering, or rendering big trees.
- Unthrottled `input`, `scroll`, `resize`, or `mousemove` handlers.
- Heavy computation (diffing, parsing large files, crypto, image processing) on the main thread.

**Fixes.** Debounce or throttle handlers. Break up long work and yield to the browser between chunks (`scheduler.yield()` where supported, otherwise `setTimeout` or `requestAnimationFrame`). Move heavy computation to a Web Worker. Use `content-visibility: auto` for large offscreen sections.

---

## Memory in long-lived pages

Single-page apps and dashboards stay open for hours, so per-navigation leaks add up.

- Event listeners, intervals, observers, sockets, and store subscriptions that are not cleaned up on unmount (the React effect cleanup, Vue `onUnmounted`, Angular `ngOnDestroy`).
- Detached DOM nodes still referenced from JavaScript.
- Client caches or stores that grow without bound (infinite scroll that never drops old pages, unbounded query caches).

**Evidence.** In the browser's Memory panel, take a heap snapshot, repeat the navigation or interaction several times, take another, and compare. Steady growth in retained objects or detached nodes confirms the leak.

---

## Measuring

- **Lab:** `npx lighthouse URL --only-categories=performance --view` (it emulates mobile by default, and `--preset=desktop` switches that). Use the browser Performance panel with CPU and network throttling to find long tasks, forced reflows, and waterfalls.
- **Field:** real-user data (RUM) through the `web-vitals` library (`onLCP`, `onINP`, `onCLS`) or the project's existing analytics. Field data at p75 outranks a single lab run.
- Compare before and after on the same build mode, device profile, and throttling, over several runs. Lab scores vary from run to run, so treat single-run differences of a few points as noise.
