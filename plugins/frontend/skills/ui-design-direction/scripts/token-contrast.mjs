#!/usr/bin/env node
// WCAG 2.x contrast checker for design-token color pairs, per theme. Zero dependencies (Node 18+).
//
// usage:
//   node token-contrast.mjs --pairs <pairs.json> [--css <tokens.css>]... [--suggest] [--verbose] [--json]
//   node token-contrast.mjs <fg> <bg> [--kind text|large-text|ui | --target <ratio>] [--backdrop <color>]
//                           [--css <file>]... [--selector <sel>] [--media <text>] [--scope root|descendant]
//                           [--scheme light|dark] [--suggest] [--verbose] [--json]
//
// --verbose prints the token chain behind every pair (it is always printed for failing pairs).
// --base is accepted as an alias of --backdrop.
//
// Colors may be literals or, when a token stylesheet is given (--css, or "$css" in the pairs file),
// token references: "--color-text-secondary" in a pairs file, 'var(--color-text-secondary)' anywhere.
// Token references are resolved from the stylesheet for the theme selector of each group, following
// var() chains, so re-running after a token edit checks the NEW values. Literal pairs are copies and
// go stale when tokens change; prefer token references.
//
// Literal syntax:
//   #rgb #rgba #rrggbb #rrggbbaa         rgb()/rgba(), hsl()/hsla() (comma or space syntax, optional alpha)
//   oklch(L C h)  oklab(L a b)  lab(L a b)  lch(L C h)     (L as a number or %, optional "/ alpha")
//   color(srgb r g b)  color(srgb-linear r g b)  color(display-p3 r g b)
//   white | black | transparent
// Browsers report computed colors in these forms (getComputedStyle returns color(srgb ...) or
// oklab(...) for color-mix results), so values read from a running page can be pasted in directly.
// color-mix(), relative color syntax and other named colors are rejected: there is no browser here
// to compute them. Read the computed value from the page instead.
//
// Pairs file (see pairs.example.json):
//   { "$css": "relative/to/this/file/tokens.css",
//     "light": { "$selector": ":root", "pairs": [ { "name": "...", "fg": "--color-text-primary", "bg": "--color-surface-canvas" } ] },
//     "dark":  { "$selector": "[data-theme=dark]", "pairs": [ ... ] } }
//   Group keys: $selector (default :root), $media (only declarations inside an at-rule whose prelude
//   contains this text are added, e.g. "(prefers-color-scheme: dark)"), $scope ("root" when the theme
//   selector is set on <html>, the default; "descendant" when it is set on an inner element), $scheme
//   ("light" | "dark", picks the branch of light-dark()). A group may also be a plain array of pairs.
//   Pair keys: name, fg, bg, kind (text | large-text | ui; default text), target (overrides kind),
//   backdrop (opaque color under a translucent bg; default white).
//
// Thresholds (WCAG 2.2):
//   text        1.4.3 AA 4.5:1   1.4.6 AAA 7:1
//   large-text  1.4.3 AA 3:1     1.4.6 AAA 4.5:1   (>= 24px regular or >= 18.66px bold)
//   ui          1.4.11 AA 3:1    (control boundaries, focus indicators, meaningful icons, chart marks)
//
// --suggest prints, for each failing pair, the nearest passing foreground (and background) found by
// moving OKLCH lightness at fixed hue, reducing chroma only when needed to stay inside sRGB, in both
// oklch() and hex. Map the suggestion to the nearest step of your ramp; do not paste it as a one-off.
//
// Translucent colors: the foreground is composited over the background, and a translucent background
// over the backdrop, in gamma-encoded sRGB (how browsers blend by default). A ratio is never rounded
// up to a pass (WCAG compares unrounded values).
//
// --selftest checks the color math, the token resolver, and the bundled example files, then exits.
//
// exit: 0 every pair meets AA (or --target), 1 any pair fails, 2 usage, parse, or token-resolution error.
//       With --selftest: 0 every self-check passed, 1 any failed.

import { readFileSync, realpathSync } from 'node:fs';
import { dirname, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const THRESHOLDS = {
  'text': { aa: 4.5, aaa: 7, sc: '1.4.3' },
  'large-text': { aa: 3, aaa: 4.5, sc: '1.4.3' },
  'ui': { aa: 3, aaa: null, sc: '1.4.11' },
};

const NAMED = {
  white: [1, 1, 1, 1],
  black: [0, 0, 0, 1],
  transparent: [0, 0, 0, 0],
};

export class ParseError extends Error {}

const clamp01 = x => Math.min(1, Math.max(0, x));

// sRGB transfer functions (IEC 61966-2-1).
function toLinear(c) {
  const s = Math.sign(c);
  const a = Math.abs(c);
  return s * (a <= 0.04045 ? a / 12.92 : Math.pow((a + 0.055) / 1.055, 2.4));
}
function toGamma(c) {
  const s = Math.sign(c);
  const a = Math.abs(c);
  return s * (a <= 0.0031308 ? 12.92 * a : 1.055 * Math.pow(a, 1 / 2.4) - 0.055);
}

const mul = (m, v) => m.map(row => row[0] * v[0] + row[1] * v[1] + row[2] * v[2]);

// Matrices from the CSS Color 4 sample code.
const P3_TO_XYZ = [
  [0.4865709486482162, 0.26566769316909306, 0.1982172852343625],
  [0.2289745640697488, 0.6917385218365064, 0.079286914093745],
  [0, 0.04511338185890264, 1.043944368900976],
];
const XYZ_TO_SRGB = [
  [3.2409699419045226, -1.537383177570094, -0.4986107602930034],
  [-0.9692436362808796, 1.8759675015077202, 0.04155505740717559],
  [0.05563007969699366, -0.20397695888897652, 1.0569715142428786],
];
const D50_TO_D65 = [
  [0.955473421488075, -0.02309845494876471, 0.06325924320057072],
  [-0.0283697093338637, 1.0099953980813041, 0.021041441191917323],
  [0.012314014864481998, -0.020507649298898964, 1.330365926242124],
];
const D50_WHITE = [0.3457 / 0.3585, 1, (1 - 0.3457 - 0.3585) / 0.3585];

// OKLab <-> linear sRGB (Ottosson's published matrices).
function oklabToLinearSrgb(L, a, b) {
  const l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3;
  const m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3;
  const s = (L - 0.0894841775 * a - 1.291485548 * b) ** 3;
  return [
    4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
    -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
    -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s,
  ];
}
function linearSrgbToOklab([r, g, b]) {
  const l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b);
  const m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b);
  const s = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b);
  return [
    0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s,
    1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s,
    0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s,
  ];
}
// Gamma-encoded sRGB (0-1) -> OKLab [L, a, b].
export function srgbToOklab(rgb) {
  return linearSrgbToOklab(rgb.slice(0, 3).map(toLinear));
}

function labToLinearSrgb(L, a, b) {
  const k = 24389 / 27;
  const e = 216 / 24389;
  const f1 = (L + 16) / 116;
  const f0 = a / 500 + f1;
  const f2 = f1 - b / 200;
  const xyz50 = [
    (f0 ** 3 > e ? f0 ** 3 : (116 * f0 - 16) / k) * D50_WHITE[0],
    (L > k * e ? ((L + 16) / 116) ** 3 : L / k) * D50_WHITE[1],
    (f2 ** 3 > e ? f2 ** 3 : (116 * f2 - 16) / k) * D50_WHITE[2],
  ];
  return mul(XYZ_TO_SRGB, mul(D50_TO_D65, xyz50));
}

function splitArgs(body) {
  // "a b c / d" or "a, b, c, d" -> component strings plus optional alpha.
  let main = body.trim();
  let alpha = null;
  if (main.includes('/')) {
    const idx = main.indexOf('/');
    alpha = main.slice(idx + 1).trim();
    main = main.slice(0, idx).trim();
  }
  let parts = (main.includes(',') ? main.split(',') : main.split(/\s+/)).map(s => s.trim()).filter(Boolean);
  if (alpha === null && parts.length === 4) alpha = parts.pop();
  return { parts, alpha };
}

function num(token, percentScale = 1) {
  if (token === undefined) throw new ParseError('missing component');
  if (token === 'none') return 0;
  const m = /^([-+]?\d*\.?\d+(?:e[-+]?\d+)?)(%|deg)?$/i.exec(token);
  if (!m) throw new ParseError(`cannot read component "${token}"`);
  const v = parseFloat(m[1]);
  return m[2] === '%' ? (v / 100) * percentScale : v;
}

function hslToRgb(h, s, l) {
  h = ((h % 360) + 360) % 360;
  const k = n => (n + h / 30) % 12;
  const a = s * Math.min(l, 1 - l);
  const f = n => l - a * Math.max(-1, Math.min(k(n) - 3, 9 - k(n), 1));
  return [f(0), f(8), f(4)];
}

function fromLinear(lin, raw, warnings) {
  const eps = 1e-4;
  if (lin.some(c => c < -eps || c > 1 + eps)) {
    warnings.push(`"${raw}" is outside the sRGB gamut; the ratio uses a clipped value and is approximate (confirm against the computed color on the target display)`);
  }
  return lin.map(c => clamp01(toGamma(clamp01(c))));
}

// Returns { rgba: [r, g, b, a] gamma-encoded 0-1, warnings: [] }.
export function parseColor(input) {
  const raw = String(input).trim();
  const s = raw.toLowerCase();
  const warnings = [];
  if (NAMED[s]) return { rgba: NAMED[s].slice(), warnings };

  if (s.startsWith('#')) {
    const hex = s.slice(1);
    if (!/^[0-9a-f]+$/.test(hex) || ![3, 4, 6, 8].includes(hex.length)) throw new ParseError(`invalid hex color "${raw}"`);
    const full = hex.length <= 4 ? [...hex].map(ch => ch + ch).join('') : hex;
    const vals = full.match(/../g).map(h => parseInt(h, 16) / 255);
    if (vals.length === 3) vals.push(1);
    return { rgba: vals, warnings };
  }

  const fn = /^([a-z-]+)\((.*)\)$/s.exec(s);
  if (!fn) throw new ParseError(`unsupported color "${raw}" (use hex, rgb(), hsl(), oklch(), oklab(), lab(), lch(), color(), white, black)`);
  const [, name, body] = fn;
  if (['var', 'color-mix', 'env', 'attr', 'calc', 'light-dark'].includes(name) || /var\(|calc\(|\bfrom\b/.test(body)) {
    throw new ParseError(`"${raw}" is not a resolved literal: give a token stylesheet (--css) for var(), or read the computed color from the page for color-mix() and relative colors`);
  }

  if (name === 'color') {
    const [space, ...rest] = body.trim().split(/\s+/);
    const { parts, alpha } = splitArgs(rest.join(' '));
    if (parts.length !== 3) throw new ParseError(`expected 3 components in "${raw}"`);
    const a = clamp01(num(alpha ?? '1'));
    const ch = parts.map(p => num(p, 1));
    if (space === 'srgb') return { rgba: [...ch.map(clamp01), a], warnings };
    if (space === 'srgb-linear') return { rgba: [...fromLinear(ch, raw, warnings), a], warnings };
    if (space === 'display-p3') return { rgba: [...fromLinear(mul(XYZ_TO_SRGB, mul(P3_TO_XYZ, ch.map(toLinear))), raw, warnings), a], warnings };
    throw new ParseError(`unsupported color space "${space}" in "${raw}" (use srgb, srgb-linear, display-p3)`);
  }

  const { parts, alpha } = splitArgs(body);
  if (parts.length !== 3) throw new ParseError(`expected 3 components in "${raw}"`);
  const a = clamp01(num(alpha ?? '1'));
  switch (name) {
    case 'rgb':
    case 'rgba':
      return { rgba: [...parts.map(p => clamp01(p.endsWith('%') ? num(p) : num(p) / 255)), a], warnings };
    case 'hsl':
    case 'hsla': {
      const sat = parts[1].endsWith('%') ? num(parts[1]) : num(parts[1]) / 100;
      const lig = parts[2].endsWith('%') ? num(parts[2]) : num(parts[2]) / 100;
      return { rgba: [...hslToRgb(num(parts[0]), clamp01(sat), clamp01(lig)), a], warnings };
    }
    case 'oklch':
    case 'oklab': {
      const L = num(parts[0], 1);
      let A;
      let B;
      if (name === 'oklch') {
        const C = num(parts[1], 0.4);
        const h = (num(parts[2]) * Math.PI) / 180;
        A = C * Math.cos(h);
        B = C * Math.sin(h);
      } else {
        A = num(parts[1], 0.4);
        B = num(parts[2], 0.4);
      }
      return { rgba: [...fromLinear(oklabToLinearSrgb(L, A, B), raw, warnings), a], warnings };
    }
    case 'lab':
    case 'lch': {
      const L = num(parts[0], 100);
      let A;
      let B;
      if (name === 'lch') {
        const C = num(parts[1], 150);
        const h = (num(parts[2]) * Math.PI) / 180;
        A = C * Math.cos(h);
        B = C * Math.sin(h);
      } else {
        A = num(parts[1], 125);
        B = num(parts[2], 125);
      }
      return { rgba: [...fromLinear(labToLinearSrgb(L, A, B), raw, warnings), a], warnings };
    }
    default:
      throw new ParseError(`unsupported color function "${name}()" in "${raw}"`);
  }
}

function over(top, bottom) {
  const a = top[3];
  return [0, 1, 2].map(i => top[i] * a + bottom[i] * (1 - a)).concat(1);
}
const luminance = ([r, g, b]) => 0.2126 * toLinear(r) + 0.7152 * toLinear(g) + 0.0722 * toLinear(b);
function ratioOf(c1, c2) {
  const [hi, lo] = [luminance(c1), luminance(c2)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

// Resolve fg/bg/backdrop rgba to the opaque pair a user sees.
function composite(fgRgba, bgRgba, backdropRgba) {
  const bg = bgRgba[3] < 1 ? over(bgRgba, backdropRgba) : bgRgba;
  const fg = fgRgba[3] < 1 ? over(fgRgba, bg) : fgRgba;
  return { fg, bg };
}

// Never display a passing number for a failing ratio.
function show(r, need) {
  const rounded = r.toFixed(2);
  if (parseFloat(rounded) >= need && r < need) return (Math.floor(r * 1000) / 1000).toFixed(3);
  return rounded;
}

// ---------------------------------------------------------------- token stylesheet resolution

function normSelector(sel) {
  return sel
    .replace(/\s+/g, ' ')
    .replace(/\s*([>+~,])\s*/g, '$1')
    .replace(/\[\s*([\w-]+)\s*([~|^$*]?=)\s*(["'])(.*?)\3\s*\]/g, '[$1$2$4]')
    .trim();
}

function splitTopLevel(text, sepChar) {
  const out = [];
  let depth = 0;
  let cur = '';
  for (const ch of text) {
    if (ch === '(' || ch === '[') depth++;
    else if (ch === ')' || ch === ']') depth--;
    if (ch === sepChar && depth === 0) {
      out.push(cur);
      cur = '';
    } else cur += ch;
  }
  out.push(cur);
  return out;
}

// Collect custom-property declarations with their selector and at-rule context.
function parseStylesheet(text, file) {
  const decls = [];
  const src = text.replace(/\/\*[\s\S]*?\*\//g, ' ');
  const stack = [];
  let buf = '';
  const flush = () => {
    const m = /^\s*(--[\w-]+)\s*:([\s\S]*)$/.exec(buf);
    if (m && stack.length) {
      const preludes = stack.slice();
      const at = preludes.filter(p => p.startsWith('@'));
      const rule = [...preludes].reverse().find(p => !p.startsWith('@'));
      const theme = at.find(p => /^@theme\b/.test(p));
      let selectors = rule ? splitTopLevel(rule, ',').map(normSelector) : [];
      if (!rule && theme) selectors = [':root'];
      decls.push({
        name: m[1],
        value: m[2].replace(/!important\s*$/i, '').trim(),
        selectors,
        conditions: at.filter(p => /^@(media|supports|container|scope|document)\b/i.test(p)).map(p => p.toLowerCase().replace(/\s+/g, ' ')),
        inline: Boolean(theme && /\binline\b/.test(theme)),
        file,
      });
    }
    buf = '';
  };
  for (let i = 0; i < src.length; i++) {
    const ch = src[i];
    if (ch === '"' || ch === "'") {
      let j = i + 1;
      while (j < src.length && src[j] !== ch) j += src[j] === '\\' ? 2 : 1;
      buf += src.slice(i, j + 1);
      i = j;
    } else if (ch === '{') {
      stack.push(buf.trim().replace(/\s+/g, ' '));
      buf = '';
    } else if (ch === '}') {
      flush();
      stack.pop();
    } else if (ch === ';') {
      flush();
    } else {
      buf += ch;
    }
  }
  return decls;
}

const ROOT_SELECTORS = new Set([':root', 'html']);

export function loadStylesheets(files) {
  const decls = [];
  for (const f of files) {
    let text;
    try {
      text = readFileSync(f, 'utf8');
    } catch (e) {
      throw new ParseError(`cannot read token stylesheet ${f}: ${e.message}`);
    }
    decls.push(...parseStylesheet(text, f));
  }
  decls.forEach((d, i) => { d.order = i; });
  return { decls, files };
}

// Build a resolver for one theme context.
function makeResolver(sheet, group) {
  const selector = normSelector(group.selector || ':root');
  const media = group.media ? group.media.toLowerCase().replace(/\s+/g, ' ') : null;
  const scope = group.scope || 'root';
  if (!['root', 'descendant'].includes(scope)) throw new ParseError(`$scope must be "root" or "descendant", got "${scope}"`);
  const condOk = d => d.conditions.every(c => media && c.includes(media));
  const rootMap = new Map();
  const themeMap = new Map();
  const isRoot = ROOT_SELECTORS.has(selector);
  for (const d of sheet.decls) {
    if (!condOk(d)) continue;
    if (d.selectors.some(s => ROOT_SELECTORS.has(s))) rootMap.set(d.name, d);
    if (!isRoot && d.selectors.includes(selector)) themeMap.set(d.name, d);
  }
  if (!isRoot && themeMap.size === 0) {
    throw new ParseError(`no custom properties are declared for selector "${group.selector}"${media ? ` inside "${group.media}"` : ''} in ${sheet.files.join(', ')} (check the exact selector text)`);
  }
  // scope "root": the theme selector matches <html>, so its declarations and :root's apply to one
  // element; theme declarations win. scope "descendant": the theme element inherits :root's
  // COMPUTED values, so a :root token whose var() refers to a remapped primitive keeps the :root
  // value (the classic reason semantic tokens must be redeclared, or @theme inline used).
  const merged = new Map([...rootMap, ...themeMap]);

  function lookup(name, ctx) {
    if (scope === 'root' || isRoot) return merged.has(name) ? { d: merged.get(name), ctx: 'merged' } : null;
    if (ctx === 'theme' && themeMap.has(name)) return { d: themeMap.get(name), ctx: 'theme' };
    if (rootMap.has(name)) {
      const d = rootMap.get(name);
      // @theme inline values are substituted where the utility is used, i.e. in the theme context.
      return { d, ctx: d.inline && ctx === 'theme' ? 'theme' : 'root' };
    }
    return null;
  }

  function resolveName(name, ctx, seen, chain) {
    if (seen.has(name)) throw new ParseError(`cyclic token reference: ${[...seen, name].join(' -> ')}`);
    const hit = lookup(name, ctx);
    if (!hit) return null;
    chain.push(name);
    const next = new Set(seen).add(name);
    return substitute(hit.d.value, hit.ctx, next, chain);
  }

  function substitute(value, ctx, seen, chain) {
    let out = '';
    let i = 0;
    while (i < value.length) {
      const at = value.indexOf('var(', i);
      if (at === -1) {
        out += value.slice(i);
        break;
      }
      out += value.slice(i, at);
      let depth = 0;
      let j = at + 3;
      for (; j < value.length; j++) {
        if (value[j] === '(') depth++;
        else if (value[j] === ')' && --depth === 0) break;
      }
      const inner = value.slice(at + 4, j);
      const [ref, ...fallbackParts] = splitTopLevel(inner, ',');
      const name = ref.trim();
      let resolved = resolveName(name, ctx, seen, chain);
      if (resolved === null) {
        if (!fallbackParts.length) {
          throw new ParseError(`token ${name} is not declared for ${group.selector || ':root'} (searched ${sheet.files.join(', ')})`);
        }
        resolved = substitute(fallbackParts.join(',').trim(), ctx, seen, chain);
      }
      out += resolved;
      i = j + 1;
    }
    out = out.trim();
    const ld = /^light-dark\((.*)\)$/s.exec(out);
    if (ld) {
      if (!group.scheme) throw new ParseError(`"${out}" uses light-dark(); set "$scheme": "light" or "dark" on the group`);
      const [l, d] = splitTopLevel(ld[1], ',').map(s => s.trim());
      out = group.scheme === 'dark' ? d : l;
    }
    return out;
  }

  return function resolveColor(input) {
    const raw = String(input).trim();
    const start = raw.startsWith('--') ? `var(${raw})` : raw;
    if (!start.includes('var(') && !/^light-dark\(/.test(start)) return { value: raw, chain: [] };
    const chain = [];
    const value = substitute(start, scope === 'descendant' && !isRoot ? 'theme' : 'merged', new Set(), chain);
    if (/^color-mix\(/i.test(value)) {
      throw new ParseError(`${raw} resolves to "${value}"; color-mix() cannot be computed here. Read the computed color in the browser (getComputedStyle) and check that literal`);
    }
    return { value, chain };
  };
}

// ---------------------------------------------------------------- evaluation and suggestions

function thresholdFor(pair) {
  const kind = pair.kind || 'text';
  const t = THRESHOLDS[kind];
  if (!t) throw new ParseError(`unknown kind "${kind}" (use text, large-text, ui)`);
  if (pair.target !== undefined) {
    const n = Number(pair.target);
    if (!Number.isFinite(n) || n < 1 || n > 21) throw new ParseError(`target must be a ratio between 1 and 21, got "${pair.target}"`);
    return { kind, need: n, aaa: null, sc: t.sc };
  }
  return { kind, need: t.aa, aaa: t.aaa, sc: t.sc };
}

function evaluate(pair, resolver) {
  const t = thresholdFor(pair);
  for (const k of ['fg', 'bg']) if (pair[k] === undefined) throw new ParseError(`pair is missing "${k}"`);
  const resolveOne = v => {
    if (resolver) return resolver(v);
    if (/^--|var\(/.test(String(v).trim())) {
      throw new ParseError(`"${v}" is a token reference; give the token stylesheet with --css or "$css"`);
    }
    return { value: String(v), chain: [] };
  };
  const fgR = resolveOne(pair.fg);
  const bgR = resolveOne(pair.bg);
  const bdR = resolveOne(pair.backdrop || 'white');
  const fg = parseColor(fgR.value);
  const bg = parseColor(bgR.value);
  const backdrop = parseColor(bdR.value);
  const warnings = [...fg.warnings, ...bg.warnings, ...backdrop.warnings];
  if (backdrop.rgba[3] < 1) throw new ParseError('backdrop must be opaque');
  if (bg.rgba[3] < 1 && !pair.backdrop) warnings.push(`background "${bgR.value}" is translucent; composited over white (set a backdrop to be exact)`);
  const c = composite(fg.rgba, bg.rgba, backdrop.rgba);
  const r = ratioOf(c.fg, c.bg);
  return {
    name: pair.name || `${pair.fg} on ${pair.bg}`,
    kind: t.kind,
    ratio: r,
    need: t.need,
    pass: r >= t.need,
    aaa: t.aaa === null ? null : r >= t.aaa,
    sc: t.sc,
    fg: { input: pair.fg, value: fgR.value, chain: fgR.chain },
    bg: { input: pair.bg, value: bgR.value, chain: bgR.chain },
    warnings,
    _rgba: { fg: fg.rgba, bg: bg.rgba, backdrop: backdrop.rgba },
  };
}

function inGamut(lin) {
  return lin.every(v => v >= -1e-6 && v <= 1 + 1e-6);
}
// OKLCH -> gamma sRGB, reducing chroma (binary search) until inside the sRGB gamut.
function oklchToSrgb(L, C, h) {
  const rad = (h * Math.PI) / 180;
  const lin = c => oklabToLinearSrgb(L, c * Math.cos(rad), c * Math.sin(rad));
  let c = C;
  if (!inGamut(lin(c))) {
    let lo = 0;
    let hi = C;
    for (let k = 0; k < 30; k++) {
      const mid = (lo + hi) / 2;
      if (inGamut(lin(mid))) lo = mid;
      else hi = mid;
    }
    c = lo;
  }
  return { rgb: lin(c).map(v => clamp01(toGamma(clamp01(v)))), C: c };
}
const toHex = rgb => `#${rgb.map(v => Math.round(clamp01(v) * 255).toString(16).padStart(2, '0')).join('')}`;
const fmt = (x, d) => Number(x.toFixed(d)).toString();

// Find the smallest lightness change for one side that makes the pair pass.
function suggestSide(result, side) {
  const { fg, bg, backdrop } = result._rgba;
  const orig = side === 'fg' ? fg : bg;
  const alpha = orig[3];
  const [L0, a0, b0] = srgbToOklab(orig);
  const C0 = Math.hypot(a0, b0);
  const h0 = C0 < 1e-4 ? 0 : ((Math.atan2(b0, a0) * 180) / Math.PI + 360) % 360;
  const passesWith = rgb => {
    const cand = [...rgb, alpha];
    const c = side === 'fg' ? composite(cand, bg, backdrop) : composite(fg, cand, backdrop);
    return ratioOf(c.fg, c.bg) >= result.need;
  };
  const atL = L => oklchToSrgb(L, C0, h0);
  const options = [];
  for (const end of [0, 1]) {
    if (!passesWith(atL(end).rgb)) continue;
    let near = L0;
    let far = end;
    for (let k = 0; k < 40; k++) {
      const mid = (near + far) / 2;
      if (passesWith(atL(mid).rgb)) far = mid;
      else near = mid;
    }
    // Round in the passing direction and confirm the PRINTED values pass.
    const step = end === 1 ? 0.001 : -0.001;
    let L = end === 1 ? Math.ceil(far * 1000) / 1000 : Math.floor(far * 1000) / 1000;
    let out = null;
    for (let k = 0; k < 50 && L >= 0 && L <= 1; k++, L += step) {
      const { rgb, C } = atL(L);
      const Cr = Math.floor(C * 1000) / 1000;
      const okText = `oklch(${fmt(L, 3)} ${fmt(Cr, 3)} ${fmt(h0, 1)}${alpha < 1 ? ` / ${fmt(alpha, 3)}` : ''})`;
      const hex = toHex(rgb) + (alpha < 1 ? Math.round(alpha * 255).toString(16).padStart(2, '0') : '');
      if (passesWith(parseColor(okText).rgba.slice(0, 3)) && passesWith(parseColor(hex).rgba.slice(0, 3))) {
        const c = side === 'fg' ? composite(parseColor(hex).rgba, bg, backdrop) : composite(fg, parseColor(hex).rgba, backdrop);
        out = { side, oklch: okText, hex, ratio: ratioOf(c.fg, c.bg), deltaL: L - L0, chromaReduced: Cr < C0 - 0.001, direction: end === 1 ? 'lighter' : 'darker' };
        break;
      }
    }
    if (out) options.push(out);
  }
  options.sort((x, y) => Math.abs(x.deltaL) - Math.abs(y.deltaL));
  return options[0] || null;
}

// ---------------------------------------------------------------- output

function printGroup(title, results, suggest, verbose) {
  if (title) console.log(`\n== ${title} ==`);
  const nameWidth = Math.max(4, ...results.map(r => r.name.length));
  console.log(`${'pair'.padEnd(nameWidth)}  ${'kind'.padEnd(10)}  ratio   AA (need)      AAA`);
  for (const r of results) {
    const aa = `${r.pass ? 'pass' : 'FAIL'} (${r.need}:1)`;
    const aaa = r.aaa === null ? 'n/a' : r.aaa ? 'pass' : 'no';
    console.log(`${r.name.padEnd(nameWidth)}  ${r.kind.padEnd(10)}  ${show(r.ratio, r.need).padStart(5)}   ${aa.padEnd(13)}  ${aaa}`);
    const pad = ' '.repeat(nameWidth + 2);
    for (const k of ['fg', 'bg']) {
      if (r[k].chain.length && (verbose || !r.pass)) console.log(`${pad}${k} ${r[k].chain.join(' -> ')} = ${r[k].value}`);
    }
    for (const w of r.warnings) console.log(`${pad}warning: ${w}`);
    if (suggest && !r.pass) {
      for (const s of [r.suggest?.fg, r.suggest?.bg]) {
        if (!s) continue;
        const chain = r[s.side].chain;
        const token = chain.length > 1 ? `; re-point ${chain[0]} at the ramp step nearest this value` : chain.length ? `; change ${chain[0]}` : '';
        console.log(`${pad}suggest ${s.side}: ${s.oklch}  ${s.hex}  -> ${show(s.ratio, r.need)}:1, ${s.direction} by ${fmt(Math.abs(s.deltaL), 3)} L${s.chromaReduced ? ', chroma reduced to stay in sRGB' : ''}${token}`);
      }
      if (!r.suggest?.fg && !r.suggest?.bg) console.log(`${pad}suggest: no lightness change at this hue reaches ${r.need}:1; change hue or chroma`);
    }
  }
}

function usage(msg, code = 2) {
  if (msg) console.error(`error: ${msg}\n`);
  (code === 0 ? console.log : console.error)(`usage: node token-contrast.mjs --pairs <pairs.json> [--css <tokens.css>]... [--suggest] [--verbose] [--json]
       node token-contrast.mjs <fg> <bg> [--kind text|large-text|ui | --target <ratio>] [--backdrop <color>]
                               [--css <file>]... [--selector <sel>] [--media <text>] [--scope root|descendant]
                               [--scheme light|dark] [--suggest] [--verbose] [--json]
       node token-contrast.mjs --selftest
  Token references in arguments use var(): 'var(--color-text-secondary)'. --base is an alias of --backdrop.
  Exit: 0 every pair passes, 1 any pair fails, 2 usage, parse, or token-resolution error.`);
  process.exit(code);
}

function parseCli(argv) {
  const opts = { css: [], positional: [], suggest: false, json: false, verbose: false };
  const takesValue = new Set(['--pairs', '--css', '--kind', '--target', '--backdrop', '--base', '--selector', '--media', '--scope', '--scheme']);
  for (let i = 0; i < argv.length; i++) {
    let a = argv[i];
    let v;
    if (a === '--') {
      opts.positional.push(...argv.slice(i + 1));
      break;
    }
    if (a.startsWith('--') && a.includes('=')) [a, v] = [a.slice(0, a.indexOf('=')), a.slice(a.indexOf('=') + 1)];
    if (a === '-h' || a === '--help') usage(null, 0);
    if (takesValue.has(a)) {
      if (v === undefined) {
        v = argv[++i];
        if (v === undefined || v.startsWith('--')) usage(`${a} needs a value${v?.startsWith('--') ? ' (write token references as var(--name))' : ''}`);
      }
      if (a === '--css') opts.css.push(v);
      else if (a === '--base') opts.backdrop = v;
      else opts[a.slice(2)] = v;
    } else if (a === '--suggest') opts.suggest = true;
    else if (a === '--json') opts.json = true;
    else if (a === '--verbose') opts.verbose = true;
    else if (a.startsWith('--')) usage(`unknown option ${a}${/^--[\w-]+$/.test(a) ? ' (write a token reference as var(' + a + '))' : ''}`);
    else opts.positional.push(a);
  }
  if (opts.kind !== undefined && !THRESHOLDS[opts.kind]) usage(`--kind must be one of ${Object.keys(THRESHOLDS).join(', ')}`);
  return opts;
}

function main(argv) {
  if (argv.length === 0) usage();
  if (argv.includes('--selftest')) {
    if (argv.length > 1) usage('--selftest takes no other arguments');
    process.exit(selftest());
  }
  const opts = parseCli(argv);
  const groups = [];
  let sheet = null;

  try {
    if (opts.pairs) {
      if (opts.positional.length) usage('give either --pairs or two colors, not both');
      for (const k of ['selector', 'media', 'scope', 'scheme', 'kind', 'target', 'backdrop']) {
        if (opts[k] !== undefined) usage(`--${k} applies to a single pair; in a pairs file set it per group ($${k === 'kind' || k === 'target' || k === 'backdrop' ? `{pair}.${k}` : k}) instead`);
      }
      let data;
      try {
        data = JSON.parse(readFileSync(opts.pairs, 'utf8'));
      } catch (e) {
        usage(`cannot read ${opts.pairs}: ${e.message}`);
      }
      const base = dirname(resolve(opts.pairs));
      let cssFiles = opts.css;
      if (!cssFiles.length && !Array.isArray(data) && data.$css) {
        cssFiles = (Array.isArray(data.$css) ? data.$css : [data.$css]).map(f => relative(process.cwd(), resolve(base, f)) || '.');
      }
      if (cssFiles.length) sheet = loadStylesheets(cssFiles);
      const entries = Array.isArray(data) ? [['', data]] : Object.entries(data).filter(([k]) => !k.startsWith('$'));
      for (const [title, g] of entries) {
        const spec = Array.isArray(g) ? { pairs: g } : g;
        if (!spec || !Array.isArray(spec.pairs)) usage(`group "${title}" must be an array of pairs or an object with a "pairs" array`);
        groups.push({ title, selector: spec.$selector, media: spec.$media, scope: spec.$scope, scheme: spec.$scheme, pairs: spec.pairs });
      }
    } else {
      if (opts.positional.length !== 2) usage('expected exactly two colors (or --pairs <file>)');
      if (opts.css.length) sheet = loadStylesheets(opts.css);
      groups.push({
        title: '',
        selector: opts.selector,
        media: opts.media,
        scope: opts.scope,
        scheme: opts.scheme,
        pairs: [{ fg: opts.positional[0], bg: opts.positional[1], kind: opts.kind, target: opts.target, backdrop: opts.backdrop }],
      });
    }
  } catch (e) {
    if (!(e instanceof ParseError)) throw e;
    usage(e.message);
  }

  let failed = 0;
  let total = 0;
  const report = [];
  for (const g of groups) {
    let resolver = null;
    const results = [];
    try {
      if (sheet) resolver = makeResolver(sheet, g);
      else if (g.selector && g.selector !== ':root') throw new ParseError(`group "${g.title}" names a selector but no token stylesheet was given (--css or "$css")`);
    } catch (e) {
      if (!(e instanceof ParseError)) throw e;
      console.error(`error in ${g.title || 'pair'}: ${e.message}`);
      process.exit(2);
    }
    for (const p of g.pairs) {
      try {
        const r = evaluate({ ...p, kind: p.kind ?? opts.kind, target: p.target ?? opts.target }, resolver);
        if (!r.pass && opts.suggest) r.suggest = { fg: suggestSide(r, 'fg'), bg: suggestSide(r, 'bg') };
        results.push(r);
      } catch (e) {
        if (!(e instanceof ParseError)) throw e;
        console.error(`error in ${g.title ? `${g.title} / ` : ''}${p.name || JSON.stringify(p)}: ${e.message}`);
        process.exit(2);
      }
    }
    total += results.length;
    failed += results.filter(r => !r.pass).length;
    report.push({ title: g.title, selector: g.selector || ':root', results });
  }

  if (opts.json) {
    const clean = report.map(g => ({ ...g, results: g.results.map(({ _rgba, ...r }) => r) }));
    console.log(JSON.stringify({ stylesheets: sheet ? sheet.files : [], total, passed: total - failed, groups: clean }, null, 2));
  } else {
    if (sheet) console.log(`tokens resolved from: ${sheet.files.join(', ')}`);
    for (const g of report) printGroup(g.title ? `${g.title} (${g.selector})` : '', g.results, opts.suggest, opts.verbose);
    console.log(`\n${total - failed}/${total} pairs meet ${opts.target ? `${opts.target}:1` : 'WCAG AA'}${failed ? `; ${failed} FAIL${opts.suggest ? '' : ' (add --suggest for nearest passing values)'}` : ''}.`);
  }
  process.exit(failed ? 1 : 0);
}

// ---------------------------------------------------------------- self-test

// Reference values are computed independently from the WCAG relative-luminance formula.
function selftest() {
  const results = [];
  const check = (label, fn) => {
    let ok = false;
    let detail = '';
    try {
      const out = fn();
      ok = out === true;
      if (!ok && out !== false) detail = String(out);
    } catch (e) {
      detail = e.message;
    }
    results.push(ok);
    console.log(`${ok ? 'ok  ' : 'FAIL'} ${label}${detail ? ` (${detail})` : ''}`);
  };
  const near = (a, b, eps) => Math.abs(a - b) <= eps;
  const pair = (fg, bg, extra = {}) => evaluate({ fg, bg, ...extra }, null);
  const rgbaNear = (input, want, eps = 0.002) => {
    const got = parseColor(input).rgba;
    return got.every((v, i) => near(v, want[i], eps)) || got.map(v => v.toFixed(4)).join(' ');
  };
  const throwsParse = fn => {
    try {
      fn();
      return 'no error raised';
    } catch (e) {
      return e instanceof ParseError || e.message;
    }
  };

  // Ratios and thresholds.
  check('black on white is 21:1', () => near(pair('#000', '#fff').ratio, 21, 1e-9));
  check('#777777 on white is 4.48:1 and fails body text', () => {
    const r = pair('#777777', '#ffffff');
    return (near(r.ratio, 4.478, 0.001) && !r.pass) || r.ratio;
  });
  check('#767676 on white is 4.54:1 and passes body text', () => {
    const r = pair('#767676', '#ffffff');
    return (near(r.ratio, 4.542, 0.001) && r.pass) || r.ratio;
  });
  check('large-text and ui need 3:1 (#949494 passes, #959595 fails)', () =>
    pair('#949494', 'white', { kind: 'large-text' }).pass && !pair('#959595', 'white', { kind: 'ui' }).pass);
  check('--target overrides the kind threshold', () => !pair('#767676', '#fff', { target: 7 }).pass);
  check('a failing ratio is never printed as a pass', () => show(4.4999, 4.5) === '4.499' || show(4.4999, 4.5));

  // Literal syntaxes resolve to the same color.
  for (const red of ['#f00', '#ff0000ff', 'rgb(255 0 0)', 'rgb(255, 0, 0)', 'rgb(100% 0% 0%)', 'hsl(0 100% 50%)',
    'hsl(0, 100%, 50%)', 'color(srgb 1 0 0)', 'oklch(0.62796 0.25768 29.234)', 'lab(54.29 80.82 69.88)']) {
    check(`${red} parses as sRGB red`, () => rgbaNear(red, [1, 0, 0, 1], 0.005));
  }
  check('8-digit hex carries alpha', () => rgbaNear('#00000080', [0, 0, 0, 128 / 255]));
  check('translucent text is composited over its background', () =>
    near(pair('rgba(0, 0, 0, 0.5)', '#ffffff').ratio, 3.98, 0.01) || pair('rgba(0, 0, 0, 0.5)', '#ffffff').ratio);
  check('color-mix() is rejected, not guessed', () => throwsParse(() => parseColor('color-mix(in srgb, red, blue)')));
  check('a token reference without a stylesheet is rejected', () => throwsParse(() => pair('var(--x)', '#fff')));

  // Token resolution per theme, in memory.
  const css = `
    :root { --ink: #111111; --paper: #ffffff; --text: var(--ink); --bg: var(--paper);
            --soft: var(--missing, #222222); --both: light-dark(#000000, #ffffff);
            --loop-a: var(--loop-b); --loop-b: var(--loop-a); }
    [data-theme="dark"] { --ink: #eeeeee; --paper: #111111; }
    .inner-dark { --ink: #eeeeee; }`;
  const decls = parseStylesheet(css, 'selftest.css');
  decls.forEach((d, i) => { d.order = i; });
  const sheet = { decls, files: ['selftest.css'] };
  const value = (group, token) => makeResolver(sheet, group)(token).value;
  check('var() chain resolves for :root', () => value({}, '--text') === '#111111' || value({}, '--text'));
  check('theme selector on <html> remaps the semantic token', () =>
    value({ selector: '[data-theme=dark]' }, '--text') === '#eeeeee' || value({ selector: '[data-theme=dark]' }, '--text'));
  check('theme on an inner element keeps the inherited :root value ($scope descendant)', () =>
    value({ selector: '.inner-dark', scope: 'descendant' }, '--text') === '#111111');
  check('var() fallback is used for an undeclared token', () => value({}, '--soft') === '#222222');
  check('light-dark() follows $scheme', () => value({ scheme: 'dark' }, '--both') === '#ffffff');
  check('light-dark() without $scheme is an error', () => throwsParse(() => value({}, '--both')));
  check('cyclic references are an error', () => throwsParse(() => value({}, '--loop-a')));
  check('an unknown theme selector is an error', () => throwsParse(() => makeResolver(sheet, { selector: '.nope' })));

  // Suggestions pass at the printed values.
  check('--suggest finds a passing foreground', () => {
    const r = pair('#777777', '#ffffff');
    const s = suggestSide(r, 'fg');
    return (s !== null && pair(s.hex, '#ffffff').pass) || JSON.stringify(s);
  });

  // The bundled example: every pair resolves, and only the deliberate focus-on-accent pair fails.
  check('pairs.example.json against tokens.example.css: 1 deliberate failure', () => {
    const dir = dirname(fileURLToPath(import.meta.url));
    const data = JSON.parse(readFileSync(resolve(dir, 'pairs.example.json'), 'utf8'));
    const exampleSheet = loadStylesheets([resolve(dir, data.$css)]);
    const failing = [];
    for (const [title, g] of Object.entries(data).filter(([k]) => !k.startsWith('$'))) {
      const resolver = makeResolver(exampleSheet, { selector: g.$selector, media: g.$media, scope: g.$scope, scheme: g.$scheme });
      for (const p of g.pairs) if (!evaluate(p, resolver).pass) failing.push(`${title}: ${p.name}`);
    }
    return (failing.length === 1 && failing[0] === 'light: border.focus on accent.rest') || failing.join('; ');
  });

  const passed = results.filter(Boolean).length;
  console.log(`${passed}/${results.length} self-tests passed`);
  return passed === results.length ? 0 : 1;
}

const isMain = (() => {
  try {
    return realpathSync(process.argv[1]) === realpathSync(fileURLToPath(import.meta.url));
  } catch {
    return false;
  }
})();
if (isMain) main(process.argv.slice(2));
