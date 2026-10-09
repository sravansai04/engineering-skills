#!/usr/bin/env node
// WCAG 2.2 contrast checker with alpha compositing and passing-color suggestions.
// Zero dependencies. Node 18+.
//
//   node contrast.mjs <foreground> <background> [--base <color>] [--target <ratio>] [--json]
//   node contrast.mjs --selftest     check the color math against known ratios
//
// Colors: #rgb  #rgba  #rrggbb  #rrggbbaa  rgb(r, g, b)  rgba(r, g, b, a)  rgb(r g b / a)
//         hsl(h s% l% / a)  hsla(h, s%, l%, a)  oklch(L C h / a)   plus the keywords white/black
//         (rgb channels 0-255 or percentages; alpha 0-1 or a percentage)
// oklch values outside the sRGB gamut are clipped per channel; browsers gamut-map instead,
// so for such colors confirm against the computed rgb() value the browser reports.
//
// A translucent foreground is composited over the background; a translucent background is
// composited over --base (default #ffffff, i.e. the page). Pass/fail compares the UNROUNDED
// ratio: WCAG does not allow rounding 4.499:1 up to 4.5:1. The displayed ratio is truncated
// (never rounded up) for the same reason.
//
// Exit codes: 0 = meets --target (default 4.5), 1 = below target, 2 = usage error.

import { pathToFileURL } from 'node:url';

const USAGE = `usage: node contrast.mjs <foreground> <background> [--base <color>] [--target <ratio>] [--json]
  e.g. node contrast.mjs '#767676' '#fff'
       node contrast.mjs 'rgba(0,0,0,0.54)' '#f5f5f5' --target 4.5
       node contrast.mjs '#9ca3af' '#ffffff' --target 3      # a UI component boundary (SC 1.4.11)
       node contrast.mjs 'oklch(55.1% 0.027 264.364)' 'hsl(210 40% 98%)'
       node contrast.mjs --selftest                           # check the color math`;

function fail(message) {
  console.error(`contrast: ${message}\n${USAGE}`);
  process.exit(2);
}

function parseChannel(token) {
  const t = token.trim();
  if (t.endsWith('%')) return clamp((parseFloat(t) / 100) * 255, 0, 255);
  const n = Number(t);
  if (!Number.isFinite(n)) throw new Error(`bad channel "${token}"`);
  return clamp(n, 0, 255);
}

function parseAlpha(token) {
  if (token === undefined) return 1;
  const t = token.trim();
  const n = t.endsWith('%') ? parseFloat(t) / 100 : Number(t);
  if (!Number.isFinite(n)) throw new Error(`bad alpha "${token}"`);
  return clamp(n, 0, 1);
}

function clamp(n, lo, hi) {
  return Math.min(hi, Math.max(lo, n));
}

export function parseColor(input) {
  const s = String(input).trim().toLowerCase();
  if (s === 'white') return { r: 255, g: 255, b: 255, a: 1 };
  if (s === 'black') return { r: 0, g: 0, b: 0, a: 1 };
  let m = s.match(/^#([0-9a-f]{3,4}|[0-9a-f]{6}|[0-9a-f]{8})$/);
  if (m) {
    let hex = m[1];
    if (hex.length <= 4) hex = [...hex].map((c) => c + c).join('');
    const r = parseInt(hex.slice(0, 2), 16);
    const g = parseInt(hex.slice(2, 4), 16);
    const b = parseInt(hex.slice(4, 6), 16);
    const a = hex.length === 8 ? parseInt(hex.slice(6, 8), 16) / 255 : 1;
    return { r, g, b, a };
  }
  m = s.match(/^rgba?\((.*)\)$/);
  if (m) {
    const { parts, alpha } = splitFunctionArgs(m[1]);
    if (parts.length !== 3) throw new Error(`expected 3 channels in "${input}"`);
    const [r, g, b] = parts.map(parseChannel);
    return { r, g, b, a: parseAlpha(alpha) };
  }
  m = s.match(/^hsla?\((.*)\)$/);
  if (m) {
    const { parts, alpha } = splitFunctionArgs(m[1]);
    if (parts.length !== 3) throw new Error(`expected 3 components in "${input}"`);
    const h = (((parseFloat(parts[0]) % 360) + 360) % 360) / 360;
    const sat = clamp(parseFloat(parts[1]) / 100, 0, 1);
    const light = clamp(parseFloat(parts[2]) / 100, 0, 1);
    if ([h, sat, light].some((v) => !Number.isFinite(v))) throw new Error(`bad hsl() value "${input}"`);
    return { ...hslToRgb({ h, s: sat, l: light }), a: parseAlpha(alpha) };
  }
  m = s.match(/^oklch\((.*)\)$/);
  if (m) {
    const { parts, alpha } = splitFunctionArgs(m[1]);
    if (parts.length !== 3) throw new Error(`expected 3 components in "${input}"`);
    const L = parts[0].endsWith('%') ? parseFloat(parts[0]) / 100 : Number(parts[0]);
    const C = parts[1].endsWith('%') ? (parseFloat(parts[1]) / 100) * 0.4 : Number(parts[1]);
    const H = parts[2] === 'none' ? 0 : parseFloat(parts[2]);
    if ([L, C, H].some((v) => !Number.isFinite(v))) throw new Error(`bad oklch() value "${input}"`);
    return { ...oklchToRgb(L, C, H), a: parseAlpha(alpha) };
  }
  throw new Error(`unsupported color "${input}" (use hex, rgb(), hsl() or oklch())`);
}

function splitFunctionArgs(body) {
  const trimmed = body.trim();
  if (trimmed.includes(',')) {
    const parts = trimmed.split(',').map((p) => p.trim());
    const alpha = parts.length === 4 ? parts.pop() : undefined;
    return { parts, alpha };
  }
  const [channels, alpha] = trimmed.split('/');
  return { parts: channels.trim().split(/\s+/), alpha };
}

// OKLCH -> OKLab -> linear sRGB (Ottosson's published matrices) -> gamma-encoded sRGB 0-255.
function oklchToRgb(L, C, hDeg) {
  const h = (hDeg * Math.PI) / 180;
  const a = C * Math.cos(h);
  const b = C * Math.sin(h);
  const l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3;
  const m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3;
  const s = (L - 0.0894841775 * a - 1.291485548 * b) ** 3;
  const lin = [
    4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
    -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
    -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s,
  ];
  const enc = (c) => {
    const x = clamp(c, 0, 1);
    return (x <= 0.0031308 ? 12.92 * x : 1.055 * x ** (1 / 2.4) - 0.055) * 255;
  };
  const [r, g, bl] = lin.map(enc);
  return { r, g, b: bl };
}

// Source-over compositing in gamma-encoded sRGB, which is what browsers do by default.
export function composite(top, bottom) {
  const a = top.a;
  return {
    r: top.r * a + bottom.r * (1 - a),
    g: top.g * a + bottom.g * (1 - a),
    b: top.b * a + bottom.b * (1 - a),
    a: 1,
  };
}

// Relative luminance exactly as defined in the WCAG 2.2 glossary (0.04045 threshold).
export function luminance({ r, g, b }) {
  const lin = (c8) => {
    const c = c8 / 255;
    return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
}

export function ratio(c1, c2) {
  const l1 = luminance(c1);
  const l2 = luminance(c2);
  const [hi, lo] = l1 >= l2 ? [l1, l2] : [l2, l1];
  return (hi + 0.05) / (lo + 0.05);
}

function toHex({ r, g, b }) {
  return '#' + [r, g, b].map((v) => Math.round(clamp(v, 0, 255)).toString(16).padStart(2, '0')).join('');
}

function rgbToHsl({ r, g, b }) {
  const [rn, gn, bn] = [r / 255, g / 255, b / 255];
  const max = Math.max(rn, gn, bn);
  const min = Math.min(rn, gn, bn);
  const l = (max + min) / 2;
  if (max === min) return { h: 0, s: 0, l };
  const d = max - min;
  const s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
  let h;
  if (max === rn) h = (gn - bn) / d + (gn < bn ? 6 : 0);
  else if (max === gn) h = (bn - rn) / d + 2;
  else h = (rn - gn) / d + 4;
  return { h: h / 6, s, l };
}

function hslToRgb({ h, s, l }) {
  if (s === 0) return { r: l * 255, g: l * 255, b: l * 255, a: 1 };
  const hue = (p, q, t) => {
    if (t < 0) t += 1;
    if (t > 1) t -= 1;
    if (t < 1 / 6) return p + (q - p) * 6 * t;
    if (t < 1 / 2) return q;
    if (t < 2 / 3) return p + (q - p) * (2 / 3 - t) * 6;
    return p;
  };
  const q = l < 0.5 ? l * (1 + s) : l + s - l * s;
  const p = 2 * l - q;
  return { r: hue(p, q, h + 1 / 3) * 255, g: hue(p, q, h) * 255, b: hue(p, q, h - 1 / 3) * 255, a: 1 };
}

// Walk the lightness of `color` (keeping hue and saturation) until the ROUNDED hex result
// meets `target` against `against`. Prefer the direction that keeps the current polarity
// (a light color gets lighter, a dark one darker) because that preserves the design intent;
// fall back to inverting the polarity only when the first direction cannot reach the target.
export function suggest(color, against, target) {
  const start = rgbToHsl(color);
  const keepPolarity = luminance(color) >= luminance(against) ? 1 : -1;
  for (const dir of [keepPolarity, -keepPolarity]) {
    for (let step = 1; step <= 1000; step++) {
      const l = start.l + dir * step * 0.001;
      if (l < 0 || l > 1) break;
      const hex = toHex(hslToRgb({ ...start, l }));
      const r = ratio(parseColor(hex), against);
      if (r >= target) return { hex, ratio: r, invertsPolarity: dir !== keepPolarity };
    }
  }
  return null;
}

const fmt = (r) => `${(Math.floor(r * 100) / 100).toFixed(2)}:1`;

function main(argv) {
  const positional = [];
  const opts = { base: '#ffffff', target: 4.5, json: false };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--json') opts.json = true;
    else if (a === '--base') opts.base = argv[++i];
    else if (a === '--target') opts.target = Number(argv[++i]);
    else if (a === '-h' || a === '--help') {
      console.log(USAGE);
      process.exit(0);
    } else if (a === '--selftest') process.exit(selftest());
    else if (a.startsWith('--')) fail(`unknown option ${a}`);
    else positional.push(a);
  }
  if (positional.length !== 2) fail('need exactly a foreground and a background color');
  if (!Number.isFinite(opts.target) || opts.target < 1 || opts.target > 21) fail('--target must be between 1 and 21');

  let fgRaw;
  let bgRaw;
  let base;
  try {
    fgRaw = parseColor(positional[0]);
    bgRaw = parseColor(positional[1]);
    base = parseColor(opts.base);
  } catch (e) {
    fail(e.message);
  }
  if (base.a < 1) fail('--base must be opaque');
  const bg = bgRaw.a < 1 ? composite(bgRaw, base) : bgRaw;
  const fg = fgRaw.a < 1 ? composite(fgRaw, bg) : fgRaw;
  const r = ratio(fg, bg);

  const checks = [
    { label: 'Normal text            SC 1.4.3 (AA)  4.5:1', min: 4.5 },
    { label: 'Large text*            SC 1.4.3 (AA)  3:1', min: 3 },
    { label: 'UI component / graphic SC 1.4.11 (AA) 3:1', min: 3 },
    { label: 'Normal text            SC 1.4.6 (AAA) 7:1', min: 7 },
  ].map((c) => ({ ...c, pass: r >= c.min }));

  const meets = r >= opts.target;
  const fgSuggestion = meets ? null : suggest(fg, bg, opts.target);
  const bgSuggestion = meets ? null : suggest(bg, fg, opts.target);

  if (opts.json) {
    console.log(
      JSON.stringify(
        {
          foreground: { input: positional[0], effective: toHex(fg) },
          background: { input: positional[1], effective: toHex(bg) },
          ratio: r,
          target: opts.target,
          meetsTarget: meets,
          checks: checks.map(({ label, min, pass }) => ({ label: label.replace(/\s+/g, ' '), min, pass })),
          suggestions: { foreground: fgSuggestion, background: bgSuggestion },
        },
        null,
        2,
      ),
    );
  } else {
    const note = (raw, eff, input) =>
      raw.a < 1
        ? ` (alpha ${raw.a.toFixed(2)} -> effective ${toHex(eff)})`
        : input.trim().startsWith('#')
          ? ''
          : ` (= ${toHex(eff)})`;
    console.log(`Foreground: ${positional[0]}${note(fgRaw, fg, positional[0])}`);
    console.log(`Background: ${positional[1]}${note(bgRaw, bg, positional[1])}`);
    console.log(`Contrast:   ${fmt(r)}  (unrounded ${r.toFixed(4)})\n`);
    for (const c of checks) console.log(`  ${c.pass ? 'PASS' : 'FAIL'}  ${c.label}`);
    console.log('\n  * large = at least 18pt (24 CSS px) regular, or 14pt (~18.67 CSS px) bold.');
    if (!meets) {
      console.log(`\nBelow target ${opts.target}:1. Nearest passing colors (same hue/saturation):`);
      const show = (sg) =>
        sg ? `${sg.hex} (${fmt(sg.ratio)})${sg.invertsPolarity ? '  [inverts light/dark: a design change]' : ''}` : 'not reachable';
      console.log(`  change foreground -> ${show(fgSuggestion)}`);
      console.log(`  change background -> ${show(bgSuggestion)}`);
    } else {
      console.log(`\nMeets target ${opts.target}:1.`);
    }
  }
  process.exit(meets ? 0 : 1);
}

// Known values: WCAG's own extremes, the classic 4.5:1 boundary grey, and the eval's placeholder grey.
function selftest() {
  const failures = [];
  const expect = (label, condition) => {
    if (!condition) failures.push(label);
  };
  const near = (a, b, tol) => Math.abs(a - b) <= tol;
  const white = parseColor('#ffffff');
  const black = parseColor('black');

  expect('black on white is 21:1', near(ratio(black, white), 21, 1e-9));
  expect('a color against itself is 1:1', near(ratio(white, parseColor('#fff')), 1, 1e-9));
  expect('#767676 on white passes 4.5:1', ratio(parseColor('#767676'), white) >= 4.5);
  expect('#777777 on white fails 4.5:1', ratio(parseColor('#777777'), white) < 4.5);
  expect('#9ca3af on white is about 2.54:1', near(ratio(parseColor('#9ca3af'), white), 2.5388, 0.001));
  expect('the display truncates, never rounds up', fmt(4.4999) === '4.49:1' && fmt(2.5388) === '2.53:1');

  const half = parseColor('rgba(0, 0, 0, 0.5)');
  expect('rgba alpha is parsed', near(half.a, 0.5, 1e-9));
  expect('alpha composites over the background', near(composite(half, white).r, 127.5, 1e-9));
  expect('#0008 is translucent', near(parseColor('#0008').a, 0x88 / 255, 1e-9));
  expect('space syntax with a percentage alpha', near(parseColor('rgb(100% 0% 0% / 50%)').a, 0.5, 1e-9) && parseColor('rgb(100% 0% 0% / 50%)').r === 255);
  const hslWhite = parseColor('hsl(0 0% 100%)');
  expect('hsl() white', near(hslWhite.r, 255, 1e-6) && near(hslWhite.b, 255, 1e-6));
  const okWhite = parseColor('oklch(1 0 0)');
  expect('oklch(1 0 0) is white', near(okWhite.r, 255, 0.5) && near(okWhite.g, 255, 0.5) && near(okWhite.b, 255, 0.5));
  expect('oklch(0% 0 none) is black', near(luminance(parseColor('oklch(0% 0 none)')), 0, 1e-9));
  let threw = false;
  try {
    parseColor('papayawhip');
  } catch {
    threw = true;
  }
  expect('unsupported keywords are rejected, not guessed', threw);

  const sg = suggest(parseColor('#9ca3af'), white, 4.5);
  expect('a suggestion meets the target after hex rounding', sg && ratio(parseColor(sg.hex), white) >= 4.5);
  expect('the suggestion keeps the light/dark polarity', sg && sg.invertsPolarity === false);
  const ui = suggest(parseColor('#d1d5db'), white, 3);
  expect('a 3:1 suggestion for a UI boundary', ui && ui.ratio >= 3);

  if (failures.length) {
    for (const label of failures) console.error(`FAIL: ${label}`);
    return 1;
  }
  console.log('selftest: all checks passed');
  return 0;
}

const invokedDirectly =
  process.argv[1] &&
  (import.meta.url === pathToFileURL(process.argv[1]).href || process.argv[1].endsWith('contrast.mjs'));
if (invokedDirectly) main(process.argv.slice(2));
