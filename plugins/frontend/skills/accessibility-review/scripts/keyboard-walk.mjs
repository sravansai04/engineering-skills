#!/usr/bin/env node
// Keyboard walk: press Tab through a page the way a keyboard user does and record what
// receives focus, in order, with leads for manual confirmation:
//
//   NO-INDICATOR  SC 2.4.7   no pixel visibly changed around the element when it gained focus
//   OBSCURED      SC 2.4.11  focused element entirely covered by other content (sticky bars, banners)
//   INVISIBLE     SC 2.4.7   focused element is not rendered visibly (1px/clipped/opacity 0, e.g. a skip link that never appears)
//   OFFSCREEN     SC 2.4.7   focused element sits outside the viewport (moved off-canvas, not scrolled into view)
//   NO-ROLE       SC 4.1.2   focusable element exposes no role (a div/span with tabindex): give it one or drop the tab stop
//   NO-NAME       SC 4.1.2   focusable element with an empty accessible name
//   AT-HIDDEN     SC 4.1.2   focusable element that is hidden from assistive technology (aria-hidden)
//   POS-TABINDEX  SC 2.4.3   tabindex > 0 overrides the natural order
//   TRAP          SC 2.1.2   focus cycles without ever returning to the page start
//   STUCK         SC 2.1.1   Tab stops moving focus part-way through the page (focus lost to the document)
//   UNREACHED     SC 2.1.1   visible native controls the walk never reached (a native radio group counts
//                            once: Tab reaches only one radio per group, by design)
//   POINTER-ONLY  SC 2.1.1   cursor:pointer elements that cannot take focus (likely click-only divs)
//
// Every flag is a LEAD, not a verdict: confirm it by hand before reporting it.
//
// Side effects: it presses only Tab (and Escape when probing a suspected trap), briefly blurs and
// re-focuses each stop to compare pixels, and sets data-kbwalk-* attributes. It never clicks or
// types, but blur handlers (e.g. validate-on-blur) will run, so point it at a dev/test build.
//
// When a modal is open (a native <dialog> opened with showModal(), or a visible [aria-modal="true"]),
// the reachability and pointer-only checks are scoped to that modal, since the page behind it is
// supposed to be unreachable.
//
// Requires Node 20+ and `playwright` >= 1.49 (or `@playwright/test`; the role/name checks use
// locator.ariaSnapshot) resolvable from the current working directory (run from the project root)
// or installed next to this script:
//   npm i -D playwright && npx playwright install chromium
//
// usage: node keyboard-walk.mjs <url> [--max 200] [--viewport 1280x800] [--wait-for <css>]
//          [--storage-state auth.json] [--setup state.mjs] [--click <css>]... [--allow-redirect]
//          [--screenshot focus-order.png] [--json out.json] [--headed]
//        node keyboard-walk.mjs --selftest   check the logic that runs outside the browser (argument
//                                            parsing, PNG decoding, the pixel diff); no dependencies
//
//   --setup <file.mjs>  walk a non-default STATE: the module's default export `async (page) => {}`
//                       runs after load and --wait-for (e.g. opens a dialog) and must wait for it
//   --click <css>       (repeatable) shorthand state: click these selectors in order before walking
//   --allow-redirect    accept landing on a different page than the URL asked for (by default an
//                       HTTP error or a redirect, e.g. to a login page, is a runtime error, exit 2)
//
// Exit codes: 0 = no flags, 1 = at least one flag, 2 = usage or runtime error.

import { createRequire } from 'node:module';
import { writeFileSync } from 'node:fs';
import { deflateSync, inflateSync } from 'node:zlib';
import { pathToFileURL } from 'node:url';
import path from 'node:path';

const USAGE = `usage: node keyboard-walk.mjs <url> [--max 200] [--viewport 1280x800] [--wait-for <css>]
         [--storage-state auth.json] [--setup state.mjs] [--click <css>]... [--allow-redirect]
         [--screenshot focus-order.png] [--json out.json] [--headed]
       node keyboard-walk.mjs --selftest     (checks the helpers; no browser needed)`;

const FLAG_SC = {
  'NO-INDICATOR': '2.4.7 Focus Visible',
  OBSCURED: '2.4.11 Focus Not Obscured (Minimum)',
  INVISIBLE: '2.4.7 Focus Visible',
  OFFSCREEN: '2.4.7 Focus Visible',
  'NO-ROLE': '4.1.2 Name, Role, Value',
  'NO-NAME': '4.1.2 Name, Role, Value',
  'AT-HIDDEN': '4.1.2 Name, Role, Value',
  'POS-TABINDEX': '2.4.3 Focus Order',
  TRAP: '2.1.2 No Keyboard Trap',
  STUCK: '2.1.1 Keyboard',
  UNREACHED: '2.1.1 Keyboard',
  'POINTER-ONLY': '2.1.1 Keyboard',
};

function parseArgs(argv) {
  const o = { max: 200, viewport: { width: 1280, height: 800 }, headed: false, clicks: [], allowRedirect: false };
  const rest = [];
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    const next = () => {
      if (i + 1 >= argv.length) usageError(`${a} needs a value`);
      return argv[++i];
    };
    if (a === '--max') o.max = Number(next());
    else if (a === '--viewport') {
      const m = next().match(/^(\d+)x(\d+)$/);
      if (!m) usageError('--viewport must look like 1280x800');
      o.viewport = { width: Number(m[1]), height: Number(m[2]) };
    } else if (a === '--wait-for') o.waitFor = next();
    else if (a === '--storage-state') o.storageState = next();
    else if (a === '--setup') o.setup = next();
    else if (a === '--click') o.clicks.push(next());
    else if (a === '--allow-redirect') o.allowRedirect = true;
    else if (a === '--screenshot') o.screenshot = next();
    else if (a === '--json') o.json = next();
    else if (a === '--headed') o.headed = true;
    else if (a === '-h' || a === '--help') {
      console.log(USAGE);
      process.exit(0);
    } else if (a.startsWith('--')) usageError(`unknown option ${a}`);
    else rest.push(a);
  }
  if (rest.length !== 1) usageError('need exactly one URL');
  if (!Number.isInteger(o.max) || o.max < 1) usageError('--max must be a positive integer');
  o.url = rest[0];
  return o;
}

// The state to walk: a --setup module and/or a --click sequence (setup first), or null.
async function loadState(o) {
  const steps = [];
  const names = [];
  if (o.setup) {
    let mod;
    try {
      mod = await import(pathToFileURL(path.resolve(o.setup)).href);
    } catch (e) {
      usageError(`cannot load --setup ${o.setup}: ${String(e.message).split('\n')[0]}`);
    }
    const fn = mod.default ?? mod.setup;
    if (typeof fn !== 'function') usageError(`--setup ${o.setup} must export a default async function (page) => { ... }`);
    steps.push(fn);
    names.push(path.basename(o.setup).replace(/\.[cm]?js$/, ''));
  }
  if (o.clicks.length) {
    const sels = [...o.clicks];
    steps.push(async (page) => {
      for (const sel of sels) {
        await page.locator(sel).first().click();
        await page.waitForTimeout(300);
      }
    });
    names.push(`click ${sels.join(' > ')}`);
  }
  if (!steps.length) return null;
  return {
    name: names.join(' + '),
    run: async (page) => {
      for (const step of steps) await step(page);
    },
  };
}

// Same page = same origin and path; a trailing slash or index.html difference is not a redirect.
const pageKey = (u) => {
  const x = new URL(u);
  return x.origin + x.pathname.replace(/\/index\.html?$/, '/').replace(/\/+$/, '');
};

// Navigate and refuse anything that is not the page we were asked to walk: walking a 404 or a
// login screen would report "no leads" for a page that was never tested.
async function openTarget(page, opts) {
  const resp = await page.goto(opts.url, { waitUntil: 'load' });
  if (/^https?:$/.test(new URL(opts.url).protocol)) {
    if (!resp) throw new Error(`no HTTP response for ${opts.url}`);
    if (resp.status() >= 400) throw new Error(`HTTP ${resp.status()} for ${opts.url}; refusing to walk an error page`);
  }
  const checkLanding = () => {
    if (!opts.allowRedirect && pageKey(page.url()) !== pageKey(opts.url)) {
      throw new Error(
        `landed on ${page.url()} instead of ${opts.url} (login redirect? missing or expired --storage-state; ` +
          'pass --allow-redirect if the redirect is intended)',
      );
    }
  };
  checkLanding();
  if (opts.waitFor) {
    try {
      await page.waitForSelector(opts.waitFor, { state: 'visible' });
    } catch {
      throw new Error(`--wait-for "${opts.waitFor}" never became visible on ${page.url()}`);
    }
  }
  checkLanding();
}

function usageError(msg) {
  console.error(`keyboard-walk: ${msg}\n${USAGE}`);
  process.exit(2);
}

async function loadPlaywright() {
  // `@playwright/test` re-exports the browser launchers, so a test-runner-only install works too.
  for (const base of [path.join(process.cwd(), 'noop.js'), import.meta.url]) {
    for (const name of ['playwright', '@playwright/test']) {
      try {
        return createRequire(base)(name);
      } catch {
        /* try the next candidate */
      }
    }
  }
  console.error(
    'keyboard-walk: cannot find the "playwright" package. Run from a project that has it installed:\n' +
      '  npm i -D playwright && npx playwright install chromium',
  );
  process.exit(2);
}

// ---- in-page helpers (serialised into the browser; keep them self-contained) -------------

// Mark the deepest focused element (through open shadow roots) in THIS frame and describe it.
function markActive(marker) {
  const clear = (root) => {
    root.querySelectorAll(`[${marker}]`).forEach((n) => n.removeAttribute(marker));
    root.querySelectorAll('*').forEach((n) => n.shadowRoot && clear(n.shadowRoot));
  };
  clear(document);
  let el = document.activeElement;
  while (el && el.shadowRoot && el.shadowRoot.activeElement) el = el.shadowRoot.activeElement;
  if (!el || el === document.body || el === document.documentElement) return { kind: 'none' };
  el.setAttribute(marker, '');
  const isFrame = el.tagName === 'IFRAME' || el.tagName === 'FRAME';

  const cssPath = (node) => {
    const parts = [];
    let n = node;
    while (n && n.nodeType === 1 && parts.length < 5 && n !== document.body && n !== document.documentElement) {
      if (n.id && !/\d{3,}/.test(n.id)) {
        parts.unshift(`#${CSS.escape(n.id)}`);
        break;
      }
      let part = n.tagName.toLowerCase();
      const cls = [...n.classList].filter((c) => !/[:[\]/]/.test(c)).slice(0, 2);
      if (cls.length) part += '.' + cls.map((c) => CSS.escape(c)).join('.');
      const root = n.getRootNode();
      const siblingsOf = n.parentElement || (root instanceof ShadowRoot ? root : null);
      if (siblingsOf) {
        const same = [...siblingsOf.children].filter((c) => c.tagName === n.tagName);
        if (same.length > 1) part += `:nth-of-type(${same.indexOf(n) + 1})`;
      }
      if (!n.parentElement && root instanceof ShadowRoot) {
        parts.unshift(`::shadow ${part}`);
        n = root.host;
        continue;
      }
      parts.unshift(part);
      n = n.parentElement;
    }
    return parts.join(' > ').replace(/ > ::shadow /g, '::shadow > ');
  };

  const r = el.getBoundingClientRect();
  const tabindexAttr = el.getAttribute('tabindex');
  const atHidden = !!el.closest('[aria-hidden="true"]');
  return {
    kind: isFrame ? 'frame' : 'element',
    selector: cssPath(el),
    tag: el.tagName.toLowerCase(),
    tabindex: tabindexAttr === null ? null : Number(tabindexAttr),
    atHidden,
    rect: { x: r.x, y: r.y, w: r.width, h: r.height },
    scroll: { x: window.scrollX, y: window.scrollY },
    viewport: { w: window.innerWidth, h: window.innerHeight },
  };
}

// Is the marked element covered at every sample point? (elementFromPoint ignores
// pointer-events:none overlays, so this under-reports rather than over-reports.)
function coverage(marker) {
  const find = (root) => {
    const direct = root.querySelector(`[${marker}]`);
    if (direct) return direct;
    for (const n of root.querySelectorAll('*')) if (n.shadowRoot) { const hit = find(n.shadowRoot); if (hit) return hit; }
    return null;
  };
  const el = find(document);
  if (!el) return { state: 'unknown' };
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  // A visually-hidden native input (custom checkbox/radio/switch) is fine when its <label>
  // is what the user sees, so judge visibility on the label in that case.
  const rendered = (node) => {
    const rr = node.getBoundingClientRect();
    const cs = getComputedStyle(node);
    return rr.width >= 4 && rr.height >= 4 && Number(cs.opacity) > 0 && cs.visibility !== 'hidden';
  };
  const labels = el.labels ? [...el.labels] : [];
  const target = rendered(el) ? el : labels.find(rendered);
  if (!target) return { state: 'invisible' };
  const r = target.getBoundingClientRect();
  if (r.right <= 0 || r.bottom <= 0 || r.left >= vw || r.top >= vh) return { state: 'offscreen' };
  const owns = (hit) => {
    if (!hit) return false;
    if (hit === el || el.contains(hit) || (el.shadowRoot && el.shadowRoot.contains(hit))) return true;
    return labels.some((l) => l === hit || l.contains(hit));
  };
  const pts = [
    [0.5, 0.5],
    [0.25, 0.25],
    [0.75, 0.25],
    [0.25, 0.75],
    [0.75, 0.75],
  ];
  let inViewport = 0;
  let visibleHits = 0;
  for (const [fx, fy] of pts) {
    const x = r.left + r.width * fx;
    const y = r.top + r.height * fy;
    if (x < 0 || y < 0 || x >= vw || y >= vh) continue;
    inViewport++;
    let hit = document.elementFromPoint(x, y);
    while (hit && hit.shadowRoot) {
      const inner = hit.shadowRoot.elementFromPoint(x, y);
      if (!inner || inner === hit) break;
      hit = inner;
    }
    if (owns(hit)) visibleHits++;
  }
  if (inViewport === 0) return { state: 'offscreen' };
  return { state: visibleHits === 0 ? 'covered' : 'visible' };
}

// Region to screenshot for the focus-indicator check: the element plus its <label>s, padded.
function indicatorClip([marker, pad]) {
  const find = (root) => {
    const direct = root.querySelector(`[${marker}]`);
    if (direct) return direct;
    for (const n of root.querySelectorAll('*')) if (n.shadowRoot) { const hit = find(n.shadowRoot); if (hit) return hit; }
    return null;
  };
  const el = find(document);
  if (!el) return null;
  const rects = [el.getBoundingClientRect(), ...(el.labels ? [...el.labels].map((l) => l.getBoundingClientRect()) : [])].filter(
    (r) => r.width > 0 && r.height > 0,
  );
  if (!rects.length) return null;
  const x1 = Math.max(0, Math.min(...rects.map((r) => r.left)) - pad);
  const y1 = Math.max(0, Math.min(...rects.map((r) => r.top)) - pad);
  const x2 = Math.min(window.innerWidth, Math.max(...rects.map((r) => r.right)) + pad);
  const y2 = Math.min(window.innerHeight, Math.max(...rects.map((r) => r.bottom)) + pad);
  if (x2 - x1 < 1 || y2 - y1 < 1) return null;
  return { x: x1, y: y1, width: x2 - x1, height: y2 - y1 };
}

// Blur the marked element; report whether it matched :focus-visible first.
function blurMarked(marker) {
  const find = (root) => {
    const direct = root.querySelector(`[${marker}]`);
    if (direct) return direct;
    for (const n of root.querySelectorAll('*')) if (n.shadowRoot) { const hit = find(n.shadowRoot); if (hit) return hit; }
    return null;
  };
  const el = find(document);
  if (!el) return false;
  const fv = el.matches(':focus-visible');
  el.blur();
  return fv;
}

// Put focus back on the marked element. True only if it is focused again and, when it was
// showing a keyboard focus style before, it is showing one again.
function refocusMarked([marker, wasFocusVisible]) {
  const find = (root) => {
    const direct = root.querySelector(`[${marker}]`);
    if (direct) return direct;
    for (const n of root.querySelectorAll('*')) if (n.shadowRoot) { const hit = find(n.shadowRoot); if (hit) return hit; }
    return null;
  };
  const el = find(document);
  if (!el) return false;
  el.focus({ preventScroll: true });
  let active = document.activeElement;
  while (active && active.shadowRoot && active.shadowRoot.activeElement) active = active.shadowRoot.activeElement;
  return active === el && (!wasFocusVisible || el.matches(':focus-visible'));
}

function candidateOf(marker) {
  const el = document.querySelector(`[${marker}]`);
  return el && el.hasAttribute('data-kbwalk-candidate') ? Number(el.getAttribute('data-kbwalk-candidate')) : null;
}

// Visible native controls + explicit tab stops, and cursor:pointer elements that cannot focus.
// Scoped to the open modal when there is one; a native radio group is ONE candidate, because Tab
// reaches only one radio per group (the checked one, or the first) and arrows move inside it.
function census() {
  const visible = (el) => {
    const r = el.getBoundingClientRect();
    if (r.width < 2 || r.height < 2) return false;
    const cs = getComputedStyle(el);
    return cs.visibility !== 'hidden' && cs.display !== 'none' && Number(cs.opacity) > 0;
  };
  const isModal = (d) => {
    try {
      return d.matches(':modal');
    } catch {
      return d.open && getComputedStyle(d).position === 'fixed'; // browsers without :modal
    }
  };
  const modals = [
    ...[...document.querySelectorAll('dialog')].filter(isModal),
    ...[...document.querySelectorAll('[aria-modal="true"]')].filter((el) => el.tagName !== 'DIALOG' && visible(el)),
  ];
  const scope = modals.length ? modals[modals.length - 1] : document.body;
  const focusableSel =
    'a[href], area[href], button, input:not([type="hidden"]), select, textarea, summary, iframe, ' +
    '[tabindex], [contenteditable=""], [contenteditable="true"], audio[controls], video[controls]';
  const isFocusable = (el) => el.matches(focusableSel) && !el.matches(':disabled') && el.getAttribute('tabindex') !== '-1';
  // iframes are excluded: focus moves into their content, which is walked separately.
  const raw = [...scope.querySelectorAll(focusableSel)].filter(
    (el) =>
      el.tagName !== 'IFRAME' && isFocusable(el) && visible(el) && !el.closest('[inert]') && !el.closest('fieldset:disabled'),
  );
  const labelOf = (el) => {
    const img = el.querySelector && el.querySelector('img[alt]');
    const fieldLike = /^(INPUT|SELECT|TEXTAREA)$/.test(el.tagName);
    const label = el.labels && el.labels.length ? el.labels[0].textContent : '';
    return (
      el.getAttribute('aria-label') ||
      label ||
      (fieldLike ? el.getAttribute('placeholder') : '') ||
      (fieldLike ? '' : el.textContent) ||
      (img && img.alt) ||
      el.getAttribute('title') ||
      el.getAttribute('href') ||
      ''
    )
      .trim()
      .replace(/\s+/g, ' ');
  };
  const describe = (el) => {
    let id = el.tagName.toLowerCase();
    if (el.tagName === 'INPUT') id += `[type=${el.type}]${el.name ? `[name=${el.name}]` : ''}`;
    if (el.id) id += '#' + el.id;
    const cls = [...el.classList].slice(0, 2).join('.');
    const t = labelOf(el);
    return `${id}${cls ? '.' + cls : ''}${t ? ` "${t.slice(0, 40)}"` : ''}`;
  };

  const candidates = [];
  const groups = new Map(); // radio group key -> candidate
  for (const el of raw) {
    if (el.tagName === 'INPUT' && el.type === 'radio' && el.name) {
      const key = `${el.form ? [...document.forms].indexOf(el.form) : 'noform'}|${el.name}`;
      const existing = groups.get(key);
      if (existing) {
        existing.size++;
        el.setAttribute('data-kbwalk-candidate', String(existing.index));
        continue;
      }
      const c = { index: candidates.length, el, group: key, size: 1 };
      groups.set(key, c);
      candidates.push(c);
    } else candidates.push({ index: candidates.length, el });
    el.setAttribute('data-kbwalk-candidate', String(candidates.length - 1));
  }

  const pointerOnly = [];
  for (const el of scope.querySelectorAll('*')) {
    if (pointerOnly.length >= 25) break;
    if (getComputedStyle(el).cursor !== 'pointer' || !visible(el)) continue;
    if (el.closest('[inert]')) continue;
    if (el.matches(focusableSel) || el.closest(focusableSel) || el.closest('label')) continue;
    if (el.querySelector(focusableSel)) continue;
    if (el.parentElement && getComputedStyle(el.parentElement).cursor === 'pointer' && !el.parentElement.matches('body')) continue;
    pointerOnly.push(el);
  }
  const scopeName =
    scope === document.body
      ? null
      : `${scope.tagName.toLowerCase()}${scope.id ? '#' + scope.id : ''}${scope.getAttribute('aria-label') ? ` "${scope.getAttribute('aria-label')}"` : ''}`;
  return {
    scope: scopeName,
    candidates: candidates.map((c) => ({
      index: c.index,
      label: c.group ? `radio group [name=${c.el.name}] (${c.size} option${c.size === 1 ? '' : 's'}), e.g. ${describe(c.el)}` : describe(c.el),
    })),
    pointerOnly: pointerOnly.map(describe),
  };
}

// ---- driver -------------------------------------------------------------------------------

const MARK = 'data-kbwalk-active';

async function deepActive(page) {
  // Follow focus into iframes; return the innermost frame and a description.
  let frame = page.mainFrame();
  const chain = [];
  for (let depth = 0; depth < 5; depth++) {
    const info = await frame.evaluate(markActive, MARK);
    if (info.kind !== 'frame') return { frame, info, chain };
    chain.push(info.selector);
    const handle = await frame.$(`[${MARK}]`);
    const child = handle ? await handle.contentFrame() : null;
    if (!child) return { frame, info: { ...info, kind: 'element' }, chain };
    const inner = await child.evaluate(markActive, MARK);
    if (inner.kind === 'none') return { frame, info: { ...info, kind: 'element' }, chain };
    frame = child;
  }
  return { frame, info: { kind: 'none' }, chain };
}

async function roleAndName(frame) {
  try {
    const snap = await frame.locator(`[${MARK}]`).first().ariaSnapshot({ timeout: 2000 });
    const first = snap.split('\n')[0] || '';
    if (/^- text\b/.test(first)) return { role: '', name: '', hiddenFromAT: false };
    const m = first.match(/^- ([a-z][\w-]*)(?: ("(?:[^"\\]|\\.)*"))?/);
    if (!m) return { role: '', name: '', hiddenFromAT: snap.trim() === '' };
    return { role: m[1], name: m[2] ? JSON.parse(m[2]) : '', hiddenFromAT: false };
  } catch {
    return { role: '?', name: '?', hiddenFromAT: false };
  }
}

// Minimal PNG decoder (8-bit RGB/RGBA, non-interlaced: what Chromium screenshots produce) so
// the focused/blurred comparison can ignore sub-visible anti-aliasing noise.
function decodePng(buf) {
  let off = 8;
  let w;
  let h;
  let bitDepth;
  let colorType;
  let interlace;
  const idat = [];
  while (off < buf.length) {
    const len = buf.readUInt32BE(off);
    const type = buf.toString('ascii', off + 4, off + 8);
    const data = buf.subarray(off + 8, off + 8 + len);
    if (type === 'IHDR') {
      w = data.readUInt32BE(0);
      h = data.readUInt32BE(4);
      bitDepth = data[8];
      colorType = data[9];
      interlace = data[12];
    } else if (type === 'IDAT') idat.push(data);
    else if (type === 'IEND') break;
    off += 12 + len;
  }
  if (bitDepth !== 8 || interlace !== 0 || (colorType !== 2 && colorType !== 6)) return null;
  const bpp = colorType === 6 ? 4 : 3;
  const stride = w * bpp;
  const raw = inflateSync(Buffer.concat(idat));
  const out = Buffer.alloc(h * stride);
  for (let y = 0; y < h; y++) {
    const filter = raw[y * (stride + 1)];
    const line = raw.subarray(y * (stride + 1) + 1, (y + 1) * (stride + 1));
    for (let x = 0; x < stride; x++) {
      const a = x >= bpp ? out[y * stride + x - bpp] : 0;
      const b = y > 0 ? out[(y - 1) * stride + x] : 0;
      const c = x >= bpp && y > 0 ? out[(y - 1) * stride + x - bpp] : 0;
      let v = line[x];
      if (filter === 1) v += a;
      else if (filter === 2) v += b;
      else if (filter === 3) v += (a + b) >> 1;
      else if (filter === 4) {
        const p = a + b - c;
        const pa = Math.abs(p - a);
        const pb = Math.abs(p - b);
        const pc = Math.abs(p - c);
        v += pa <= pb && pa <= pc ? a : pb <= pc ? b : c;
      }
      out[y * stride + x] = v & 255;
    }
  }
  return { w, h, bpp, data: out };
}

// Count pixels that changed by a visible amount (any channel >= 24 levels).
function visiblyChangedPixels(bufA, bufB) {
  const a = decodePng(bufA);
  const b = decodePng(bufB);
  if (!a || !b || a.w !== b.w || a.h !== b.h) return Buffer.compare(bufA, bufB) === 0 ? 0 : Infinity;
  let n = 0;
  for (let i = 0; i < a.w * a.h; i++) {
    for (let k = 0; k < 3; k++) {
      if (Math.abs(a.data[i * a.bpp + k] - b.data[i * b.bpp + k]) >= 24) {
        n++;
        break;
      }
    }
  }
  return n;
}

// Page-coordinate screenshot region around the marked element (plus its labels), computed
// while it is focused and reused for the blurred shot so both images cover the same pixels.
async function focusRegion(page, frame) {
  const clip = await frame.evaluate(indicatorClip, [MARK, 8]);
  if (!clip) return null;
  let offX = 0;
  let offY = 0;
  if (frame !== page.mainFrame()) {
    const owner = await frame.frameElement();
    const box = owner ? await owner.boundingBox() : null;
    if (!box) return null;
    offX = box.x;
    offY = box.y;
  }
  const vp = page.viewportSize();
  const x = Math.max(0, clip.x + offX);
  const y = Math.max(0, clip.y + offY);
  const region = { x, y, width: Math.min(clip.width, vp.width - x), height: Math.min(clip.height, vp.height - y) };
  return region.width >= 1 && region.height >= 1 ? region : null;
}

async function indicatorCheck(page, frame) {
  // Focused (reached by keyboard) vs. blurred, same region. Then restore focus so the
  // sequential-navigation starting point is unchanged.
  const region = await focusRegion(page, frame);
  if (!region) return 'unknown';
  const shot = () => page.screenshot({ clip: region, animations: 'disabled', caret: 'hide' });
  const focused = await shot();
  const wasFocusVisible = await frame.evaluate(blurMarked, MARK);
  await page.waitForTimeout(30);
  const blurred = await shot();
  const restored = await frame.evaluate(refocusMarked, [MARK, wasFocusVisible]);
  await page.waitForTimeout(30);
  if (!restored) return 'unknown';
  // A real indicator changes dozens of pixels even on a 16px icon; fewer than 4 is rendering noise.
  return visiblyChangedPixels(focused, blurred) >= 4 ? 'changed' : 'none';
}

async function main() {
  const opts = parseArgs(process.argv.slice(2));
  const state = await loadState(opts);
  const { chromium } = await loadPlaywright();
  const browser = await chromium.launch({ headless: !opts.headed });
  let exitCode = 0;
  try {
    const context = await browser.newContext({
      viewport: opts.viewport,
      reducedMotion: 'reduce',
      ...(opts.storageState ? { storageState: opts.storageState } : {}),
    });
    const page = await context.newPage();
    if (typeof page.locator('body').ariaSnapshot !== 'function') {
      // Without it every stop would get role/name "?" and the NO-ROLE, NO-NAME and AT-HIDDEN checks
      // would silently pass: refuse rather than report a false clean.
      throw new Error('needs playwright >= 1.49 (locator.ariaSnapshot) for the role and name checks; upgrade playwright');
    }
    await openTarget(page, opts);
    if (state) {
      try {
        await state.run(page);
      } catch (e) {
        throw new Error(`setup "${state.name}" failed: ${String(e.message).split('\n')[0]}`);
      }
    }
    try {
      // Smooth scrolling would make the before/after indicator screenshots differ for the wrong reason.
      await page.addStyleTag({ content: 'html, body { scroll-behavior: auto !important; }' });
    } catch {
      /* a strict CSP can refuse injected styles; the walk still works */
    }
    await page.waitForTimeout(300);

    const { candidates, pointerOnly, scope } = await page.evaluate(census);
    await page.evaluate(() => {
      if (document.activeElement && document.activeElement !== document.body) document.activeElement.blur();
      window.scrollTo(0, 0);
    });

    const stops = [];
    const seen = new Map();
    let ending = `stopped after --max ${opts.max} stops`;
    let trap = null;
    let stuck = false;

    for (let i = 0; i < opts.max; i++) {
      await page.keyboard.press('Tab');
      await page.waitForTimeout(40);
      let { frame, info, chain } = await deepActive(page);
      if (info.kind === 'none') {
        // Normal at the end of the page (focus passes to the browser UI). Tab once more: a healthy
        // page wraps back to its first stop; a broken one leaves focus stuck on the document.
        await page.keyboard.press('Tab');
        await page.waitForTimeout(40);
        ({ frame, info, chain } = await deepActive(page));
        if (info.kind === 'none') {
          ending = stops.length
            ? `focus got stuck on the document after stop ${stops.length}: further Tabs reach nothing (check UNREACHED; a script may be swallowing Tab or calling blur() on focus)`
            : 'nothing on the page took focus';
          if (stops.length) stuck = true;
          break;
        }
        const wrappedKey = [...chain, info.selector].join(' >>> ');
        if (stops.length && wrappedKey === stops[0].key) {
          ending = `focus left the page after ${stops.length} stops and wrapped to the first stop (normal)`;
          break;
        }
      }
      const key = [...chain, info.selector].join(' >>> ');
      if (seen.has(key)) {
        const firstIdx = seen.get(key);
        if (firstIdx === 0) {
          ending = `focus wrapped back to the first stop after ${stops.length} stops`;
        } else {
          // Re-visited a mid-page element without passing the start: a cycle. Try Escape.
          const cycle = stops.slice(firstIdx).map((s) => s.selector);
          await page.keyboard.press('Escape');
          await page.keyboard.press('Tab');
          const after = await deepActive(page);
          const afterKey = after.info.kind === 'none' ? null : [...after.chain, after.info.selector].join(' >>> ');
          const escaped = afterKey === null || !stops.slice(firstIdx).some((s) => s.key === afterKey);
          trap = { from: firstIdx + 1, size: cycle.length, escapeReleases: escaped };
          ending = `focus cycled among stops ${firstIdx + 1}-${stops.length} without returning to the page start`;
        }
        break;
      }
      seen.set(key, stops.length);

      const { role, name, hiddenFromAT } = await roleAndName(frame);
      const cov = await frame.evaluate(coverage, MARK);
      const indicator = cov.state === 'visible' ? await indicatorCheck(page, frame) : 'n/a';
      const candidateIndex = frame === page.mainFrame() ? await frame.evaluate(candidateOf, MARK) : null;

      const flags = [];
      if (cov.state === 'invisible') flags.push('INVISIBLE');
      if (cov.state === 'offscreen') flags.push('OFFSCREEN');
      if (cov.state === 'covered') flags.push('OBSCURED');
      if (indicator === 'none') flags.push('NO-INDICATOR');
      if (info.atHidden || hiddenFromAT) flags.push('AT-HIDDEN');
      else if (!role || role === 'generic' || role === 'text') flags.push('NO-ROLE');
      else if (!name && role !== '?' && !['iframe', 'document'].includes(role)) flags.push('NO-NAME');
      if (info.tabindex !== null && info.tabindex > 0) flags.push('POS-TABINDEX');

      stops.push({
        step: stops.length + 1,
        key,
        selector: chain.length ? `${chain.join(' >>> ')} >>> ${info.selector}` : info.selector,
        role,
        name,
        tabindex: info.tabindex,
        pagePos: chain.length ? null : { x: info.rect.x + info.scroll.x, y: info.rect.y + info.scroll.y, w: info.rect.w, h: info.rect.h },
        visibility: cov.state,
        indicator,
        candidateIndex,
        flags,
      });
    }

    const reached = new Set(stops.map((s) => s.candidateIndex).filter((n) => n !== null));
    const unreached = trap || ending.startsWith('stopped') ? [] : candidates.filter((c) => !reached.has(c.index));

    // ---- report ----
    console.log(`Keyboard walk: ${opts.url}  (viewport ${opts.viewport.width}x${opts.viewport.height}, reduced motion)`);
    if (pageKey(page.url()) !== pageKey(opts.url)) console.log(`Walked page: ${page.url()}`);
    if (state) console.log(`State: ${state.name}`);
    if (scope) console.log(`Scope: open modal ${scope} (reachability and pointer-only checks cover only the modal)`);
    console.log(`Result: ${ending}.\n`);
    const pad = (s, n) => (s.length > n ? s.slice(0, n - 1) + '…' : s.padEnd(n));
    console.log(`${'#'.padStart(3)}  ${pad('role', 11)} ${pad('name', 30)} ${pad('selector', 44)} flags`);
    for (const s of stops) {
      console.log(
        `${String(s.step).padStart(3)}  ${pad(s.role || '-', 11)} ${pad(JSON.stringify(s.name), 30)} ${pad(s.selector, 44)} ${s.flags.join(' ')}`,
      );
    }

    const flagged = {};
    for (const s of stops) for (const f of s.flags) (flagged[f] ||= []).push(`#${s.step} ${s.selector}`);
    if (trap) {
      flagged.TRAP = [
        `stops ${trap.from}-${stops.length} form a closed loop; Escape ${trap.escapeReleases ? 'DID' : 'did NOT'} release focus` +
          (trap.escapeReleases ? ' (acceptable if this is a modal dialog the user opened)' : ''),
      ];
    }
    if (stuck) flagged.STUCK = [`after stop ${stops.length} (${stops[stops.length - 1].selector}) Tab no longer moves focus`];
    if (unreached.length) flagged.UNREACHED = unreached.map((c) => c.label);
    if (pointerOnly.length) flagged['POINTER-ONLY'] = pointerOnly;

    const unknownRole = stops.filter((s) => s.role === '?');
    if (unknownRole.length) {
      console.log(
        `\nWARNING: role/name could not be read for ${unknownRole.length} stop(s) (${unknownRole.map((s) => '#' + s.step).join(', ')}); ` +
          'NO-ROLE, NO-NAME and AT-HIDDEN were NOT checked for them. Inspect those in the accessibility tree.',
      );
    }

    const flagNames = Object.keys(flagged);
    console.log('');
    if (!flagNames.length) {
      console.log('No leads raised. This does not prove keyboard accessibility: still check order matches the visual');
      console.log('layout, that every control OPERATES with Enter/Space/arrows, and that focus is managed on dialogs and route changes.');
    } else {
      console.log('Leads to confirm manually (not verdicts):');
      for (const f of flagNames) {
        console.log(`\n  ${f}  (SC ${FLAG_SC[f]})  x${flagged[f].length}`);
        for (const line of flagged[f].slice(0, 15)) console.log(`    - ${line}`);
        if (flagged[f].length > 15) console.log(`    … ${flagged[f].length - 15} more`);
      }
      exitCode = 1;
    }
    console.log('\nNot checked here: whether the focus ORDER matches the visual/reading order (compare the table with');
    console.log('the page, or use --screenshot), indicator CONTRAST (SC 1.4.11), and operation of each control.');

    if (opts.screenshot) {
      const marks = stops.filter((s) => s.pagePos).map((s) => ({ n: s.step, ...s.pagePos, bad: s.flags.length > 0 }));
      await page.evaluate(([ms, inModal]) => {
        const layer = document.createElement('div');
        layer.id = '__kbwalk_overlay';
        layer.style.cssText = 'position:absolute;left:0;top:0;width:0;height:0;z-index:2147483647;pointer-events:none';
        for (const m of ms) {
          const box = document.createElement('div');
          const color = m.bad ? '#b00020' : '#0b57d0';
          box.style.cssText = `position:absolute;left:${m.x}px;top:${m.y}px;width:${Math.max(m.w, 4)}px;height:${Math.max(m.h, 4)}px;outline:2px solid ${color};`;
          const tag = document.createElement('span');
          tag.textContent = String(m.n);
          tag.style.cssText = `position:absolute;left:-2px;top:${m.y < 18 ? 'calc(100% + 2px)' : '-18px'};background:${color};color:#fff;font:bold 12px/16px sans-serif;padding:0 4px;border-radius:3px`;
          box.appendChild(tag);
          layer.appendChild(box);
        }
        document.body.appendChild(layer);
        if (inModal && typeof layer.showPopover === 'function') {
          // An open modal sits in the browser's top layer, above any z-index; promote the overlay
          // into the top layer too (as a popover) so the numbers stay visible over the modal.
          layer.setAttribute('popover', 'manual');
          layer.style.cssText += ';inset:auto;left:0;top:0;margin:0;padding:0;border:0;background:transparent;overflow:visible';
          layer.showPopover();
        }
      }, [marks, !!scope]);
      await page.screenshot({ path: opts.screenshot, fullPage: true });
      await page.evaluate(() => document.getElementById('__kbwalk_overlay')?.remove());
      console.log(`\nFocus-order screenshot: ${path.resolve(opts.screenshot)} (red = flagged stop)`);
    }

    if (opts.json) {
      writeFileSync(
        opts.json,
        JSON.stringify(
          {
            url: opts.url,
            walkedUrl: page.url(),
            viewport: opts.viewport,
            state: state ? state.name : 'initial',
            scope,
            ending,
            stops,
            roleNameUnchecked: unknownRole.map((s) => s.step),
            trap,
            unreached,
            pointerOnly,
            flagSc: FLAG_SC,
          },
          null,
          2,
        ),
      );
      console.log(`JSON: ${path.resolve(opts.json)}`);
    }
  } catch (e) {
    console.error(`keyboard-walk: ${String(e.message).split('\n')[0]}`);
    exitCode = 2;
  } finally {
    await browser.close();
  }
  process.exit(exitCode);
}

// Encode raw pixels as a PNG using the given per-row filter types, so the selftest exercises every
// branch of decodePng(). CRCs are left as zero because decodePng() does not read them.
function encodeTestPng(w, h, bpp, pixels, filters) {
  const stride = w * bpp;
  const rows = [];
  for (let y = 0; y < h; y++) {
    const f = filters[y % filters.length];
    const row = Buffer.alloc(stride + 1);
    row[0] = f;
    for (let x = 0; x < stride; x++) {
      const a = x >= bpp ? pixels[y * stride + x - bpp] : 0;
      const b = y > 0 ? pixels[(y - 1) * stride + x] : 0;
      const c = x >= bpp && y > 0 ? pixels[(y - 1) * stride + x - bpp] : 0;
      let pred = 0;
      if (f === 1) pred = a;
      else if (f === 2) pred = b;
      else if (f === 3) pred = (a + b) >> 1;
      else if (f === 4) {
        const p = a + b - c;
        const pa = Math.abs(p - a);
        const pb = Math.abs(p - b);
        const pc = Math.abs(p - c);
        pred = pa <= pb && pa <= pc ? a : pb <= pc ? b : c;
      }
      row[x + 1] = (pixels[y * stride + x] - pred) & 255;
    }
    rows.push(row);
  }
  const chunk = (type, data) => {
    const len = Buffer.alloc(4);
    len.writeUInt32BE(data.length);
    return Buffer.concat([len, Buffer.from(type, 'ascii'), data, Buffer.alloc(4)]);
  };
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(w, 0);
  ihdr.writeUInt32BE(h, 4);
  ihdr[8] = 8;
  ihdr[9] = bpp === 4 ? 6 : 2;
  return Buffer.concat([
    Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]),
    chunk('IHDR', ihdr),
    chunk('IDAT', deflateSync(Buffer.concat(rows))),
    chunk('IEND', Buffer.alloc(0)),
  ]);
}

// Checks the logic that runs outside the browser. The in-page helpers need a real page; the
// fixtures in evals/files/ (see EXPECTED.md there) cover them end to end.
function selftest() {
  const failures = [];
  const expect = (label, condition) => {
    if (!condition) failures.push(label);
  };
  const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);

  const flags = ['NO-INDICATOR', 'OBSCURED', 'INVISIBLE', 'OFFSCREEN', 'NO-ROLE', 'NO-NAME', 'AT-HIDDEN',
    'POS-TABINDEX', 'TRAP', 'STUCK', 'UNREACHED', 'POINTER-ONLY'];
  expect('every flag maps to a success criterion', same(Object.keys(FLAG_SC).sort(), [...flags].sort()));
  expect('every mapping starts with an SC number', Object.values(FLAG_SC).every((v) => /^\d\.\d\.\d+ \S/.test(v)));
  expect('a trap is 2.1.2', FLAG_SC.TRAP.startsWith('2.1.2 '));

  const d = parseArgs(['http://x.test/']);
  expect('defaults', d.url === 'http://x.test/' && d.max === 200 && same(d.viewport, { width: 1280, height: 800 }));
  const o = parseArgs(['http://x.test/a', '--max', '400', '--viewport', '390x844', '--click', '#menu', '--click', '#more',
    '--setup', 'open.mjs', '--allow-redirect']);
  expect('options', o.max === 400 && same(o.viewport, { width: 390, height: 844 }) && o.setup === 'open.mjs' && o.allowRedirect);
  expect('repeatable --click keeps its order', same(o.clicks, ['#menu', '#more']));

  expect('index.html is the same page as its folder', pageKey('http://x.test/a/index.html') === pageKey('http://x.test/a/'));
  expect('a login redirect is a different page', pageKey('http://x.test/login') !== pageKey('http://x.test/checkout'));

  for (const bpp of [3, 4]) {
    const w = 5;
    const h = 5;
    const px = Buffer.alloc(w * h * bpp);
    for (let i = 0; i < px.length; i++) px[i] = (i * 37 + 11) & 255; // varied values so every filter matters
    const png = encodeTestPng(w, h, bpp, px, [0, 1, 2, 3, 4]);
    const img = decodePng(png);
    expect(`decodes ${bpp === 4 ? 'RGBA' : 'RGB'} with filter types 0-4`, img && img.w === w && img.h === h && Buffer.compare(img.data, px) === 0);
    expect('identical images differ in no pixels', visiblyChangedPixels(png, png) === 0);
    const faint = Buffer.from(px);
    faint[0] = (faint[0] + 10) & 255; // below the 24-level visibility threshold
    expect('a sub-visible change is noise', visiblyChangedPixels(png, encodeTestPng(w, h, bpp, faint, [0, 1, 2, 3, 4])) === 0);
    const ring = Buffer.from(px);
    ring[bpp * 6] = (ring[bpp * 6] + 128) & 255; // pixel (1,1)
    ring[bpp * 7 + 1] = (ring[bpp * 7 + 1] + 128) & 255; // pixel (2,1)
    expect('a visible change counts each pixel once', visiblyChangedPixels(png, encodeTestPng(w, h, bpp, ring, [4, 3, 2, 1, 0])) === 2);
  }

  if (failures.length) {
    for (const label of failures) console.error(`FAIL: ${label}`);
    return 1;
  }
  console.log('selftest: all checks passed');
  return 0;
}

if (process.argv.slice(2).includes('--selftest')) {
  process.exit(selftest());
} else {
  main().catch((e) => {
    console.error(`keyboard-walk: ${e?.stack || e}`);
    process.exit(2);
  });
}
