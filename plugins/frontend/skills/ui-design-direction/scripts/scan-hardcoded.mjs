#!/usr/bin/env node
// Find raw visual values in UI code that should come from design tokens. Zero dependencies (Node 18+);
// imports the color parser from ./token-contrast.mjs for --inventory.
//
// usage:
//   node scan-hardcoded.mjs [path ...] [options]          files or directories (default: .)
//   node scan-hardcoded.mjs --changed [path ...]          only files changed vs the base branch
//
// options:
//   --changed              scan files that differ from the merge-base with --base: committed, staged,
//                          unstaged, and untracked. Each hit is tagged new (on an added line) or
//                          pre-existing; the exit code reflects NEW hits only. Paths narrow the set.
//   --base <ref>           base for --changed (default: origin/HEAD, then origin/main, origin/master,
//                          main, master)
//   --new-only             with --changed, list only hits on added lines
//   --tailwind-palette     also flag Tailwind default-palette classes (bg-blue-600, text-gray-500,
//                          text-white). Use it when the project defines its own color names.
//   --inventory            list literal colors and lengths by frequency, with proposed merges
//                          (colors within --cluster-de in OKLab, lengths snapped to the 4px grid); exit 0
//   --cluster-de <n>       OKLab distance treated as "the same color" by --inventory (default 0.02)
//   --exclude <glob>       skip matching paths (repeatable, case-insensitive)
//   --no-default-excludes  also scan token-source files (see below)
//   --show <n>             hits listed per check (default 15); --json prints all
//   --json                 machine-readable output
//   --selftest             check the detectors on built-in snippets and, when git is available, the
//                          --changed exit codes in a throwaway repository under the temp directory
//   -h, --help             print usage
//
// Scope rules:
// - Directories are listed with `git ls-files` inside a work tree (so .gitignore is respected),
//   otherwise walked with build/vendor directories skipped. Files named explicitly are always read.
// - Token sources are skipped by default and LISTED in the output: tokens.*, *.tokens.json,
//   theme.*, themes.*, variables.*, vars.*, palette.*, colors.*, anything under a tokens/,
//   design-tokens/, theme/, or themes/ directory, tailwind.config.*, and *.min.* (whole-name match,
//   case-insensitive: ThemeToggle.tsx and theme-toggle.tsx ARE scanned).
// - Custom-property and Sass/Less variable definitions are token definitions only inside :root,
//   html, body, :host, [data-theme...], .dark/.light, .theme-*, or @theme blocks. Anywhere else a
//   definition holding a raw value is reported as local-var-literal, so moving a literal into a
//   local variable does not hide it.
// - Comment-only lines are skipped. Keep a deliberate literal with `token-exempt: <reason>` in a
//   comment on the same line.
//
// Blind spots: a clean result is NOT proof that a component is token-only.
// - Values built at runtime: `${size}px`, values passed in props or read from data, numbers handed
//   to chart or canvas libraries through variables.
// - Numeric JSX props (`<Icon size={16} />`), unitless numbers outside known style keys, and a
//   property and its value split across lines.
// - Named colors outside color properties, font names outside font-family, font-weight, opacity,
//   and em-based letter-spacing.
// - Tailwind default-palette classes unless --tailwind-palette is given.
// - Native code (Swift, Kotlin, Java, Dart, Android XML) and .svg files: listed as not scanned.
// - Brace tracking for definition scope is heuristic; a definition in an unusual wrapper can be
//   misclassified.
// Known noise: id selectors that look like hex (#add), href="#bad" anchors, px breakpoints in
// plain CSS media queries (dropped: var() cannot be used there), and theme-ui/styled-system scale
// indexes such as `fontSize: 2` (flagged as unitless).
//
// exit: 0 scanned and clean (with --changed: no new hits, or nothing changed in scope)
//       1 hits found (with --changed: new hits)
//       2 usage error, a named path is missing, a git error, or nothing scannable was found
//       With --selftest: 0 every self-check passed, 1 any failed.

import { execFileSync } from 'node:child_process';
import { appendFileSync, existsSync, mkdtempSync, readdirSync, readFileSync, rmSync, statSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, relative, sep } from 'node:path';
import { fileURLToPath } from 'node:url';
import { parseColor, srgbToOklab } from './token-contrast.mjs';

const EXTENSIONS = new Set([
  'css', 'scss', 'sass', 'less', 'styl', 'pcss', 'js', 'jsx', 'ts', 'tsx', 'mjs', 'cjs', 'mts', 'cts',
  'vue', 'svelte', 'astro', 'html', 'htm', 'erb', 'hbs', 'njk', 'liquid', 'php', 'heex', 'cshtml',
  'razor', 'mdx',
]);
const JS_LIKE = new Set(['js', 'jsx', 'ts', 'tsx', 'mjs', 'cjs', 'mts', 'cts', 'vue', 'svelte', 'astro', 'mdx']);
const CSS_LIKE = new Set(['css', 'scss', 'sass', 'less', 'styl', 'pcss']);
const NOT_COVERED = new Set(['swift', 'kt', 'kts', 'java', 'dart', 'svg', 'xaml']);
const SKIP_DIRS = new Set([
  'node_modules', '.git', 'dist', 'build', 'out', '.next', '.nuxt', '.svelte-kit', '.output',
  'coverage', 'vendor', '.turbo', '.cache', 'storybook-static',
]);
const TOKEN_STEMS = new Set(['tokens', 'token', 'design-tokens', 'theme', 'themes', 'variables', 'vars', 'palette', 'colors', 'colours']);
const TOKEN_DIRS = new Set(['tokens', 'design-tokens', 'theme', 'themes']);

const NAMED_COLORS = (
  'aliceblue antiquewhite aqua aquamarine azure beige bisque black blanchedalmond blue blueviolet brown ' +
  'burlywood cadetblue chartreuse chocolate coral cornflowerblue cornsilk crimson cyan darkblue darkcyan ' +
  'darkgoldenrod darkgray darkgreen darkgrey darkkhaki darkmagenta darkolivegreen darkorange darkorchid ' +
  'darkred darksalmon darkseagreen darkslateblue darkslategray darkslategrey darkturquoise darkviolet ' +
  'deeppink deepskyblue dimgray dimgrey dodgerblue firebrick floralwhite forestgreen fuchsia gainsboro ' +
  'ghostwhite gold goldenrod gray green greenyellow grey honeydew hotpink indianred indigo ivory khaki ' +
  'lavender lavenderblush lawngreen lemonchiffon lightblue lightcoral lightcyan lightgoldenrodyellow ' +
  'lightgray lightgreen lightgrey lightpink lightsalmon lightseagreen lightskyblue lightslategray ' +
  'lightslategrey lightsteelblue lightyellow lime limegreen linen magenta maroon mediumaquamarine ' +
  'mediumblue mediumorchid mediumpurple mediumseagreen mediumslateblue mediumspringgreen mediumturquoise ' +
  'mediumvioletred midnightblue mintcream mistyrose moccasin navajowhite navy oldlace olive olivedrab ' +
  'orange orangered orchid palegoldenrod palegreen paleturquoise palevioletred papayawhip peachpuff peru ' +
  'pink plum powderblue purple rebeccapurple red rosybrown royalblue saddlebrown salmon sandybrown ' +
  'seagreen seashell sienna silver skyblue slateblue slategray slategrey snow springgreen steelblue tan ' +
  'teal thistle tomato turquoise violet wheat white whitesmoke yellow yellowgreen'
).split(' ');
const NAMED_ALT = NAMED_COLORS.join('|');
const COLOR_PROPS =
  'color|background(?:-color)?|border(?:-(?:top|right|bottom|left|block|inline)(?:-(?:start|end))?)?(?:-color)?|' +
  'outline(?:-color)?|fill|stroke|caret-color|accent-color|text-decoration(?:-color)?|column-rule(?:-color)?|' +
  'stop-color|flood-color|lighting-color|backgroundColor|borderColor|border(?:Top|Right|Bottom|Left)Color|' +
  'outlineColor|textDecorationColor|caretColor|accentColor|stopColor|shadowColor|tintColor';

const COMMENT_START = /^\s*(\/\/|\/\*|<!--|\{#|\{\/\*)/;
const COMMENT_CONTINUATION = /^\s*\*(\s|\/|$)/;
const EXEMPT = /token-exempt:/;
const DEFINITION = /(?<![\w-])(?:--|\$|@)[\w-]+\s*:(?!:)[^;{}]*/g;
const ROOT_SCOPE =
  /(?:^|[^\w-])(?::root|html|body|:host)(?![\w-])|\[data-(?:theme|mode|color-scheme|scheme)\b|(?:^|[\s,>(])\.(?:dark|light)(?![\w-])|\.theme-[\w-]+|@theme\b/;

const HEX = /(?<![&\w])#(?:[0-9a-f]{8}|[0-9a-f]{6}|[0-9a-f]{3,4})\b/gi;
const COLOR_FN =
  /(?<![a-z0-9-])(?:(?:rgba?|hsla?|oklch|oklab|lab|lch|hwb)\(\s*[-+]?[\d.]|color\(\s*(?:srgb|srgb-linear|display-p3|a98-rgb|prophoto-rgb|rec2020|xyz|xyz-d50|xyz-d65)\s)/i;
const COLOR_FN_FULL = /(?<![a-z0-9-])(?:rgba?|hsla?|oklch|oklab|lab|lch|hwb|color)\([^()]*\)/gi;
const LENGTH = /(?<![\w[.-])-?(?:\d+\.?\d*|\.\d+)(px|rem)\b/g;
const LENGTH_LOOSE = /(?<![a-zA-Z0-9.-])-?(?:\d+\.?\d*|\.\d+)(px|rem)\b/g;
const MEDIA_PRELUDE = /@(?:media|container|custom-media)\b[^{;]*/g;
const NAMED_IN_PROP = new RegExp(`(?<![\\w-])(?:${COLOR_PROPS})['"]?\\s*[:=]\\s*[^;{}]*?(?<![\\w.$@#/-])(${NAMED_ALT})(?![\\w.-])`, 'i');
const NAMED_WORD = new RegExp(`(?<![\\w.$@#/-])(${NAMED_ALT})(?![\\w.-])`, 'i');
const ARBITRARY = /(?<![\w])([a-z][a-z0-9-]*)-\[([^\]\s'"`]+)\](?!:)/gi;
const ARBITRARY_PROP = /(?<![\w\]-])\[((?:--)?[a-z][\w-]*):([^\]\s'"`]+)\](?!:)/gi;
const LAYOUT_ONLY = /^(?:(?:\d+(?:\.\d+)?|\.\d+)(?:%|fr|vh|vw|dvh|svh|lvh|ch|cqw|cqh)|\d+\/\d+|auto|min-content|max-content|fit-content|span|subgrid|full|[_,()])+$/i;
const PALETTE =
  /(?<![\w-])(?:bg|text|border(?:-[xytrblse])?|ring|ring-offset|outline|fill|stroke|from|via|to|divide|placeholder|decoration|shadow|inset-shadow|inset-ring|accent|caret)-(?:(?:slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose)-(?:50|[1-9]00|950)|white|black)(?:\/\d+)?(?![\w-])/;
const JS_STYLE_KEYS = (() => {
  const sides = ['', 'Top', 'Right', 'Bottom', 'Left', 'Horizontal', 'Vertical', 'Inline', 'Block', 'InlineStart', 'InlineEnd', 'BlockStart', 'BlockEnd', 'Start', 'End'];
  const keys = ['padding', 'margin'].flatMap(p => sides.map(s => p + s));
  keys.push(
    'gap', 'rowGap', 'columnGap', 'borderRadius', 'borderTopLeftRadius', 'borderTopRightRadius',
    'borderBottomLeftRadius', 'borderBottomRightRadius', 'borderWidth', 'borderTopWidth', 'borderRightWidth',
    'borderBottomWidth', 'borderLeftWidth', 'fontSize', 'lineHeight', 'letterSpacing', 'width', 'height',
    'minWidth', 'maxWidth', 'minHeight', 'maxHeight', 'top', 'right', 'bottom', 'left', 'inset',
    'outlineWidth', 'outlineOffset', 'elevation', 'shadowRadius',
  );
  return keys.join('|');
})();
const JS_UNITLESS = new RegExp(`(?<![\\w$.-])['"]?(?:${JS_STYLE_KEYS})['"]?\\s*:\\s*(-?(?:\\d+\\.?\\d*|\\.\\d+))(?![\\w.%'"\`])`, 'g');

function rawLengths(text) {
  const out = [];
  for (const m of text.replace(MEDIA_PRELUDE, '').matchAll(LENGTH)) {
    const n = Math.abs(parseFloat(m[0]));
    if (n === 0 || (m[1] === 'px' && (n === 1 || n === 0.5))) continue;
    out.push(m[0]);
  }
  return out;
}

function hexHits(text, cssLike) {
  const out = [];
  for (const m of text.matchAll(HEX)) {
    if (cssLike) {
      const before = text.slice(0, m.index);
      if (!/[:=(,]/.test(before) && /\{/.test(text.slice(m.index))) continue; // `#add {` is a selector
    }
    out.push(m[0]);
  }
  return out;
}

// Does a variable definition's value hold a raw visual value (rather than alias a token)?
function literalReason(value) {
  if (hexHits(value, false).length || COLOR_FN.test(value)) return 'color';
  if (NAMED_WORD.test(value)) return 'named color';
  if (rawLengths(value).length) return 'length';
  if (/(?<![\w.-])\d*\.?\d+m?s\b/.test(value) || /cubic-bezier\(\s*[\d.]/.test(value)) return 'motion';
  return null;
}

function arbitraryIsLiteral(utility, value) {
  if (/^content$/i.test(utility)) return false;
  if (/^(?:[a-z-]+:)?(?:var\(|--|theme\(|url\()/i.test(value)) return false;
  if (LAYOUT_ONLY.test(value)) return false;
  if (/^(?:repeat|minmax)\(/i.test(value) && !/\d(?:px|rem|em)\b|#|rgb|hsl|oklch/i.test(value)) return false;
  return true;
}

const CHECKS = [
  {
    id: 'hex-color',
    why: 'use a semantic color token',
    test: (u, c) => hexHits(u, c.cssLike).length > 0,
  },
  {
    id: 'color-function',
    why: 'literal rgb()/hsl()/oklch()/color(); reference a color token',
    test: u => COLOR_FN.test(u),
  },
  {
    id: 'named-color',
    why: 'named CSS color in a color property; use a semantic color token',
    test: u => NAMED_IN_PROP.test(u),
  },
  {
    id: 'raw-length',
    why: 'use a spacing/size/radius/type token (0, 1px and 0.5px hairlines are fine)',
    test: u => rawLengths(u).length > 0,
  },
  {
    id: 'js-unitless',
    why: 'a bare number on a style key is a pixel literal in CSS-in-JS and React Native; read it from the theme',
    test: (u, c) => c.jsLike && [...u.matchAll(JS_UNITLESS)].some(m => Math.abs(parseFloat(m[1])) > 1),
  },
  {
    id: 'tailwind-arbitrary',
    why: 'bracket values bypass the theme; use a theme step or add a token',
    test: u =>
      [...u.matchAll(ARBITRARY)].some(m => arbitraryIsLiteral(m[1], m[2])) ||
      [...u.matchAll(ARBITRARY_PROP)].some(m => {
        const v = m[2].replace(/_/g, ' ');
        return !/^(?:var\(|--)/.test(v) && (literalReason(v) !== null || /^-?\d*\.?\d+$/.test(v));
      }),
  },
  {
    id: 'tailwind-palette',
    why: "Tailwind default palette, not the project's tokens (if the theme resets --color-*, these classes silently produce no CSS)",
    optIn: 'tailwindPalette',
    test: u => PALETTE.test(u),
  },
  {
    id: 'font-family',
    why: 'font stacks belong in a font token',
    test: u => /(?:font-family|fontFamily)\s*:/.test(u) && !/var\(|theme\(|tokens?\.|\binherit\b|\$/.test(u),
  },
  {
    id: 'shadow',
    why: 'use an elevation token',
    test: u => {
      const m = /(?:box-shadow|boxShadow|text-shadow|textShadow)\s*:\s*([^;}]*)|drop-shadow\(([^)]*)\)/.exec(u);
      if (!m) return false;
      const v = m[1] ?? m[2];
      return rawLengths(v).length > 0 || hexHits(v, false).length > 0 || COLOR_FN.test(v) || NAMED_WORD.test(v);
    },
  },
  {
    id: 'motion',
    why: 'use duration/easing tokens so tuning and reduced-motion live in one place',
    test: (u, c) =>
      /(?:transition|animation)(?:-duration|-delay|Duration|Delay)?\s*:[^;]*?(?<![\w-])\d*\.?\d+m?s\b/.test(u) ||
      /cubic-bezier\(\s*[\d.]/.test(u) ||
      (c.jsLike && /(?<![\w$.-])(?:duration|delay|transitionDuration|animationDuration)\s*:\s*(?:0?\.\d*[1-9]|[1-9]\d*\.?\d*)(?![\w.%'"`])/.test(u)),
  },
  {
    id: 'z-index',
    why: 'use a named layer scale (dropdown, sticky, overlay, modal, toast)',
    test: u => /(?:z-index|zIndex)\s*:\s*['"]?-?\d{2,}/.test(u),
  },
  {
    id: 'inline-style',
    why: 'inline visual styles cannot follow theme or state; move to classes/tokens',
    test: u =>
      /style=\{\{[^}]*\b(?:color|background|margin|padding|font|border|shadow)|style="[^"]*\b(?:color|background|margin|padding|font|border|shadow)/.test(u),
  },
  {
    id: 'emoji',
    why: 'if used as an icon, use the project icon set (emoji vary by platform and are read aloud verbosely)',
    test: u => /\p{Emoji_Presentation}|\p{Extended_Pictographic}\uFE0F/u.test(u),
  },
  {
    id: 'local-var-literal',
    why: 'a component-scoped variable holds a raw value; alias a semantic token instead (var(--...))',
    test: () => false, // reported from the definition pass
  },
];

// ---------------------------------------------------------------- arguments

function usage(msg, code = 2) {
  if (msg) console.error(`error: ${msg}\n`);
  (code === 0 ? console.log : console.error)(`usage: node scan-hardcoded.mjs [path ...] [--changed [--base <ref>] [--new-only]] [--tailwind-palette]
                                [--inventory [--cluster-de <n>]] [--exclude <glob>]... [--no-default-excludes]
                                [--show <n>] [--json]
       node scan-hardcoded.mjs --selftest
  Exit: 0 clean (with --changed: no new hits), 1 hits found, 2 usage error or nothing scannable.`);
  process.exit(code);
}

function parseArgs(argv) {
  const opts = {
    paths: [], excludes: [], defaultExcludes: true, show: 15, json: false, changed: false, base: null,
    newOnly: false, tailwindPalette: false, inventory: false, clusterDe: 0.02,
  };
  const takesValue = new Set(['--exclude', '--show', '--base', '--cluster-de']);
  for (let i = 0; i < argv.length; i++) {
    let a = argv[i];
    let v;
    if (a === '--') {
      opts.paths.push(...argv.slice(i + 1));
      break;
    }
    if (a.startsWith('--') && a.includes('=')) [a, v] = [a.slice(0, a.indexOf('=')), a.slice(a.indexOf('=') + 1)];
    if (takesValue.has(a) && v === undefined) {
      v = argv[++i];
      if (v === undefined || v.startsWith('--')) usage(`${a} needs a value`);
    }
    switch (a) {
      case '-h':
      case '--help':
        usage(null, 0);
        break;
      case '--exclude': opts.excludes.push(v); break;
      case '--show': opts.show = Number(v); break;
      case '--base': opts.base = v; break;
      case '--cluster-de': opts.clusterDe = Number(v); break;
      case '--json': opts.json = true; break;
      case '--changed': opts.changed = true; break;
      case '--new-only': opts.newOnly = true; break;
      case '--tailwind-palette': opts.tailwindPalette = true; break;
      case '--inventory': opts.inventory = true; break;
      case '--no-default-excludes': opts.defaultExcludes = false; break;
      case '--selftest': opts.selftest = true; break;
      default:
        if (a.startsWith('-')) usage(`unknown option ${a}`);
        opts.paths.push(a);
    }
  }
  if (!Number.isFinite(opts.show) || opts.show < 0) usage('--show needs a non-negative number');
  if (!Number.isFinite(opts.clusterDe) || opts.clusterDe < 0) usage('--cluster-de needs a non-negative number');
  if ((opts.base || opts.newOnly) && !opts.changed) usage('--base and --new-only only apply with --changed');
  if (opts.inventory && opts.json) usage('--inventory prints a text report; drop --json');
  if (opts.selftest && argv.length > 1) usage('--selftest takes no other arguments');
  return opts;
}

// ---------------------------------------------------------------- file selection

function git(args) {
  return execFileSync('git', args, { encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'], maxBuffer: 256 * 1024 * 1024 });
}
function inGitWorkTree() {
  try {
    return git(['rev-parse', '--is-inside-work-tree']).trim() === 'true';
  } catch {
    return false;
  }
}
const errLine = e => String(e.stderr || e.message).trim().split('\n')[0];

function globToRegExp(glob) {
  let re = '';
  for (let i = 0; i < glob.length; i++) {
    const c = glob[i];
    if (c === '*') {
      if (glob[i + 1] === '*') {
        re += '.*';
        i++;
        if (glob[i + 1] === '/') i++;
      } else re += '[^/]*';
    } else if (c === '?') re += '[^/]';
    else re += c.replace(/[.+^${}()|[\]\\]/g, '\\$&');
  }
  return new RegExp(`(^|/)${re}$`, 'i');
}

function tokenSourceReason(file) {
  const segs = file.toLowerCase().split('/');
  const base = segs.pop();
  if (base.startsWith('tailwind.config.')) return 'Tailwind config';
  if (/\.min\.[a-z]+$/.test(base)) return 'minified';
  if (/\.tokens(\.json)?$/.test(base)) return 'token file';
  if (TOKEN_STEMS.has(base.replace(/^_+/, '').split('.')[0])) return 'token source (file name)';
  if (segs.some(s => TOKEN_DIRS.has(s))) return 'token source (directory)';
  return null;
}

function walk(dir, out) {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    if (entry.isDirectory()) {
      if (!SKIP_DIRS.has(entry.name)) walk(join(dir, entry.name), out);
    } else if (entry.isFile()) out.push(join(dir, entry.name));
  }
}

function filesUnderDirs(dirs) {
  if (!dirs.length) return [];
  if (inGitWorkTree()) {
    try {
      return git(['ls-files', '-z', '--cached', '--others', '--exclude-standard', '--', ...dirs])
        .split('\0')
        .filter(f => f && existsSync(f));
    } catch {
      // fall through to a walk (e.g. a directory outside this work tree)
    }
  }
  const out = [];
  for (const d of dirs) walk(d, out);
  return out;
}

function detectBase() {
  try {
    const r = git(['rev-parse', '--abbrev-ref', 'origin/HEAD']).trim();
    if (r && r !== 'origin/HEAD') return r;
  } catch {
    // no remote HEAD
  }
  for (const r of ['origin/main', 'origin/master', 'main', 'master']) {
    try {
      git(['rev-parse', '--verify', '--quiet', `${r}^{commit}`]);
      return r;
    } catch {
      // try the next candidate
    }
  }
  usage('cannot find a base branch; pass --base <ref>');
}

// Files changed since the merge-base (working tree vs merge-base, plus untracked) and their added lines.
function changedSet(opts) {
  if (!inGitWorkTree()) usage('--changed needs a git work tree');
  const ref = opts.base || detectBase();
  let mb;
  try {
    mb = git(['merge-base', ref, 'HEAD']).trim();
  } catch (e) {
    usage(`cannot find a merge-base between "${ref}" and HEAD (${errLine(e)}); pass --base <ref>`);
  }
  const spec = opts.paths.length ? ['--', ...opts.paths] : [];
  const common = ['-c', 'core.quotePath=false', 'diff', '--no-ext-diff', '--no-color', '--relative', '--diff-filter=d'];
  let tracked;
  let untracked;
  try {
    tracked = git([...common, '--name-only', '-z', mb, ...spec]).split('\0').filter(Boolean);
    untracked = git(['ls-files', '-z', '--others', '--exclude-standard', ...spec]).split('\0').filter(Boolean);
  } catch (e) {
    usage(`git failed: ${errLine(e)}`);
  }
  const added = new Map();
  for (const f of untracked) added.set(f, 'all');
  if (tracked.length) {
    const diff = git([...common, '-U0', '--src-prefix=a/', '--dst-prefix=b/', mb, '--', ...tracked]);
    let cur = null;
    for (const line of diff.split('\n')) {
      if (line.startsWith('+++ ')) {
        const p = line.slice(4).replace(/\t$/, '');
        cur = p === '/dev/null' ? null : p.replace(/^b\//, '');
        if (cur && !added.has(cur)) added.set(cur, new Set());
        continue;
      }
      const m = cur && /^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@/.exec(line);
      if (m) {
        const start = Number(m[1]);
        const count = m[2] === undefined ? 1 : Number(m[2]);
        for (let k = 0; k < count; k++) added.get(cur).add(start + k);
      }
    }
  }
  return { ref, mb: mb.slice(0, 10), files: [...new Set([...tracked, ...untracked])].filter(f => existsSync(f)), added };
}

// ---------------------------------------------------------------- scanning

function isCommentLine(line) {
  if (COMMENT_START.test(line)) return true;
  return COMMENT_CONTINUATION.test(line) && !/[{};]/.test(line);
}

function scanFile(file, opts, inv) {
  let text;
  try {
    text = readFileSync(file, 'utf8');
  } catch {
    return null;
  }
  if (text.includes('\0')) return null; // binary
  return scanText(text, file.split('.').pop().toLowerCase(), opts, inv);
}

function scanText(text, ext, opts, inv) {
  const ctx = { jsLike: JS_LIKE.has(ext), cssLike: CSS_LIKE.has(ext) };
  const hits = [];
  let tokenRefs = 0;
  let themeReads = 0;
  const stack = [];
  let prelude = '';

  text.split(/\r?\n/).forEach((line, idx) => {
    if (isCommentLine(line)) return;
    const exempt = EXEMPT.test(line);

    // Definitions, each judged by the block it sits in at that column.
    const defs = new Map();
    for (const m of line.matchAll(DEFINITION)) defs.set(m.index, m[0]);
    const localLiterals = [];
    for (let c = 0; c < line.length; c++) {
      if (defs.has(c)) {
        const def = defs.get(c);
        const value = def.slice(def.indexOf(':') + 1);
        const rootScope = stack.some(p => ROOT_SCOPE.test(p));
        if (!rootScope && literalReason(value)) localLiterals.push(value);
      }
      const ch = line[c];
      if (ch === '{') {
        stack.push(prelude.slice(-300));
        prelude = '';
      } else if (ch === '}') {
        stack.pop();
        prelude = '';
      } else if (ch === ';') prelude = '';
      else prelude += ch;
    }
    prelude += ' ';

    tokenRefs += (line.match(/var\(\s*--/g) || []).length;
    themeReads += (line.match(/\btheme(?:\.[a-zA-Z]|\()|\$theme\b/g) || []).length;
    if (exempt) return;

    const usage = line.replace(DEFINITION, '');
    const found = [];
    for (const check of CHECKS) {
      if (check.optIn && !opts[check.optIn]) continue;
      if (check.test(usage, ctx)) found.push(check.id);
    }
    if (localLiterals.length) found.push('local-var-literal');
    for (const id of found) hits.push({ check: id, line: idx + 1, text: line.trim().slice(0, 160) });

    if (inv) collectInventory(usage, localLiterals, ctx, inv);
  });
  return { hits, tokenRefs, themeReads };
}

function collectInventory(usage, localLiterals, ctx, inv) {
  const sources = [usage, ...localLiterals];
  for (const s of sources) {
    for (const h of hexHits(s, ctx.cssLike && s === usage)) inv.colors.push(h);
    for (const m of s.matchAll(COLOR_FN_FULL)) if (/\(\s*[-+]?[\d.]|\(\s*(?:srgb|display-p3)/i.test(m[0])) inv.colors.push(m[0]);
    const named = s === usage ? NAMED_IN_PROP.exec(s) : NAMED_WORD.exec(s);
    if (named) inv.named.push(named[1].toLowerCase());
    for (const m of s.replace(MEDIA_PRELUDE, '').matchAll(LENGTH_LOOSE)) inv.lengths.push(m[0]);
  }
  if (ctx.jsLike) for (const m of usage.matchAll(JS_UNITLESS)) inv.lengths.push(`${m[1]}px`);
}

// ---------------------------------------------------------------- inventory report

function tally(list) {
  const map = new Map();
  for (const v of list) map.set(v, (map.get(v) || 0) + 1);
  return [...map.entries()].sort((a, b) => b[1] - a[1]);
}

function printInventory(inv, deltaE) {
  const toHex = rgba => `#${rgba.slice(0, 3).map(v => Math.round(v * 255).toString(16).padStart(2, '0')).join('')}${rgba[3] < 1 ? Math.round(rgba[3] * 255).toString(16).padStart(2, '0') : ''}`;
  const colors = new Map(); // normalized hex -> { count, raws: Map, lab, alpha }
  const unparsed = [];
  for (const raw of inv.colors) {
    let rgba;
    try {
      rgba = parseColor(raw.replace(/_/g, ' ')).rgba;
    } catch {
      unparsed.push(raw);
      continue;
    }
    const key = toHex(rgba);
    if (!colors.has(key)) colors.set(key, { count: 0, raws: new Map(), lab: srgbToOklab(rgba), alpha: rgba[3] });
    const c = colors.get(key);
    c.count++;
    c.raws.set(raw.toLowerCase(), (c.raws.get(raw.toLowerCase()) || 0) + 1);
  }
  const entries = [...colors.entries()].sort((a, b) => b[1].count - a[1].count);
  const used = new Set();
  const clusters = [];
  for (const [key, c] of entries) {
    if (used.has(key)) continue;
    used.add(key);
    const members = [[key, c]];
    for (const [k2, c2] of entries) {
      if (used.has(k2) || Math.abs(c2.alpha - c.alpha) > 0.05) continue;
      if (Math.hypot(c.lab[0] - c2.lab[0], c.lab[1] - c2.lab[1], c.lab[2] - c2.lab[2]) < deltaE) {
        members.push([k2, c2]);
        used.add(k2);
      }
    }
    clusters.push(members);
  }
  const uses = entries.reduce((n, [, c]) => n + c.count, 0);
  console.log(`\n== colors: ${entries.length} distinct value(s), ${uses} use(s) ==`);
  const merges = clusters.filter(m => m.length > 1);
  if (merges.length) {
    console.log(`merge candidates (OKLab distance < ${deltaE}, same alpha); keep the most used, map the rest to it:`);
    for (const m of merges) {
      const total = m.reduce((n, [, c]) => n + c.count, 0);
      console.log(`  ${m[0][0]}  x${total}  <- ${m.map(([k, c]) => `${k} (${c.count})`).join(', ')}`);
    }
  }
  const singles = clusters.filter(m => m.length === 1).slice(0, 30);
  if (singles.length) {
    console.log('distinct values by frequency (candidates for ramp steps or semantic roles):');
    console.log(`  ${singles.map(([[k, c]]) => `${k} x${c.count}`).join('  ')}`);
  }
  const named = tally(inv.named);
  if (named.length) console.log(`named colors: ${named.map(([k, n]) => `${k} x${n}`).join('  ')}`);
  if (unparsed.length) console.log(`not parsed (review by hand): ${tally(unparsed).map(([k, n]) => `${k} x${n}`).join('  ')}`);

  const px = new Map();
  for (const raw of inv.lengths) {
    const v = parseFloat(raw);
    const p = Math.abs(raw.endsWith('rem') ? v * 16 : v);
    if (p === 0 || p === 1 || p === 0.5) continue;
    const k = Number(p.toFixed(2));
    if (!px.has(k)) px.set(k, { count: 0, raws: new Set() });
    px.get(k).count++;
    px.get(k).raws.add(raw.replace(/^-/, ''));
  }
  const lens = [...px.entries()].sort((a, b) => b[1].count - a[1].count);
  console.log(`\n== lengths: ${lens.length} distinct value(s) (rem counted as 16px) ==`);
  const off = lens.filter(([p]) => p !== 2 && p % 4 !== 0);
  const on = lens.filter(([p]) => p === 2 || p % 4 === 0);
  if (on.length) console.log(`on the 4px grid: ${on.slice(0, 30).map(([p, d]) => `${p}px x${d.count}`).join('  ')}`);
  if (off.length) {
    console.log('off the grid -> nearest step (a tie means the layout decides):');
    for (const [p, d] of off.slice(0, 40)) {
      const lo = Math.floor(p / 4) * 4;
      const hi = lo + 4;
      const target = p - lo === hi - p ? `${lo || 2}px or ${hi}px` : `${p - lo < hi - p ? lo || 2 : hi}px`;
      console.log(`  ${`${p}px`.padEnd(8)} x${String(d.count).padEnd(4)} -> ${target}   (${[...d.raws].join(', ')})`);
    }
  }
}

// ---------------------------------------------------------------- self-test

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
  const ids = (text, ext, extra = {}) => scanText(text, ext, { tailwindPalette: false, ...extra }, null).hits.map(h => h.check);
  const flags = (id, text, ext = 'css', extra) => ids(text, ext, extra).includes(id) || `got: ${ids(text, ext, extra).join(', ') || 'nothing'}`;

  // Literals that must be reported.
  check('hex color in a rule', () => flags('hex-color', '.btn { color: #3366ff; }'));
  check('rgb() literal', () => flags('color-function', '.btn { background: rgb(10 20 30); }'));
  check('named color in a color property', () => flags('named-color', '.btn { color: red; }'));
  check('off-scale px length', () => flags('raw-length', '.card { padding: 13px; }'));
  check('rem length', () => flags('raw-length', '.card { margin: 1.25rem; }'));
  check('bare number on a CSS-in-JS style key', () => flags('js-unitless', 'const s = { padding: 12 };', 'tsx'));
  check('inline visual style in JSX', () => flags('inline-style', '<div style={{ margin: "4px" }} />', 'tsx'));
  check('Tailwind arbitrary length', () => flags('tailwind-arbitrary', '<div className="p-[13px]" />', 'tsx'));
  check('literal duration', () => flags('motion', '.x { transition: opacity 200ms ease; }'));
  check('magic z-index', () => flags('z-index', '.x { z-index: 999; }'));
  check('literal font stack', () => flags('font-family', '.x { font-family: Inter, sans-serif; }'));
  check('literal box-shadow', () => flags('shadow', '.x { box-shadow: 0 2px 4px #0003; }'));
  check('emoji in markup', () => flags('emoji', '<li>\u2705 Done</li>', 'html'));
  check('component-scoped variable holding a literal', () => flags('local-var-literal', '.card {\n  --card-bg: #ffffff;\n}'));
  check('Tailwind palette class only with --tailwind-palette', () =>
    !ids('<p className="text-gray-500" />', 'tsx').includes('tailwind-palette') &&
    flags('tailwind-palette', '<p className="text-gray-500" />', 'tsx', { tailwindPalette: true }));

  // Code that must stay quiet.
  const quiet = [
    ['token references', '.btn { padding: var(--space-2) var(--space-4); color: var(--color-text); }', 'css'],
    ['token definitions in :root', ':root {\n  --brand: #3366ff;\n  --space-4: 1rem;\n}', 'css'],
    ['token definitions in a theme block', '[data-theme="dark"] {\n  --brand: #99bbff;\n}', 'css'],
    ['hairlines and zero', '.x { border: 1px solid var(--c); margin: 0; }', 'css'],
    ['px inside a media query', '@media (min-width: 640px) { .x { display: grid; } }', 'css'],
    ['id selector that looks like hex', '#add { display: none; }', 'css'],
    ['same-line token-exempt comment', '.logo { color: #ff6600; } /* token-exempt: brand mark */', 'css'],
    ['comment-only line', '// padding: 13px was too tight', 'ts'],
    ['layout-only Tailwind brackets', '<div className="grid-cols-[1fr_2fr] w-[50%]" />', 'tsx'],
  ];
  for (const [label, text, ext] of quiet) {
    check(`quiet: ${label}`, () => ids(text, ext).length === 0 || `got: ${ids(text, ext).join(', ')}`);
  }
  check('counts var() references for the mode decision', () =>
    scanText('.a { color: var(--x); background: var(--y); }', 'css', {}, null).tokenRefs === 2);

  // Token sources are skipped by name, components with "theme" in the name are not.
  check('tokens.css is a token source', () => tokenSourceReason('src/styles/tokens.css') !== null);
  check('a theme/ directory is a token source', () => tokenSourceReason('packages/ui/theme/index.ts') !== null);
  check('tailwind.config.ts is a token source', () => tokenSourceReason('tailwind.config.ts') !== null);
  check('ThemeToggle.tsx is scanned', () => tokenSourceReason('src/components/ThemeToggle.tsx') === null);
  check('--exclude globs match nested paths', () => globToRegExp('**/*.stories.tsx').test('src/ui/Button.stories.tsx'));

  // End to end: --changed tags new versus pre-existing hits and drives the exit code.
  let haveGit = true;
  try {
    execFileSync('git', ['--version'], { stdio: 'ignore' });
  } catch {
    haveGit = false;
  }
  if (!haveGit) {
    console.log('skip --changed checks: git is not installed');
  } else {
    const self = fileURLToPath(import.meta.url);
    const repo = mkdtempSync(join(tmpdir(), 'scan-hardcoded-selftest-'));
    const git = (...args) => execFileSync('git', [
      '-c', 'core.hooksPath=/dev/null', '-c', 'commit.gpgsign=false',
      '-c', 'user.name=selftest', '-c', 'user.email=selftest@example.com', ...args,
    ], { cwd: repo, stdio: 'ignore' });
    const run = (...args) => {
      try {
        return { code: 0, out: execFileSync(process.execPath, [self, ...args], { cwd: repo, encoding: 'utf8', stdio: 'pipe' }) };
      } catch (e) {
        return { code: e.status, out: `${e.stdout || ''}${e.stderr || ''}` };
      }
    };
    try {
      const file = join(repo, 'card.css');
      git('init', '-q');
      writeFileSync(file, '.old { color: #123456; }\n');
      git('add', 'card.css');
      git('commit', '-q', '--no-verify', '-m', 'base');
      appendFileSync(file, '.new { padding: 13px; }\n');
      const first = run('--changed', '--base', 'HEAD', '--json');
      check('--changed exits 1 on a hit in an added line', () => first.code === 1 || `exit ${first.code}: ${first.out.trim().split('\n')[0]}`);
      check('--changed tags 1 new and 1 pre-existing hit', () => {
        const j = JSON.parse(first.out);
        return (j.new === 1 && j.preexisting === 1) || `new ${j.new}, pre-existing ${j.preexisting}`;
      });
      writeFileSync(file, '.old { color: #123456; }\n.new { padding: 13px; } /* token-exempt: selftest */\n');
      const second = run('--changed', '--base', 'HEAD');
      check('--changed exits 0 when only pre-existing hits remain', () => second.code === 0 || `exit ${second.code}`);
      const missing = run('no-such-dir');
      check('a missing path exits 2 instead of reporting clean', () => missing.code === 2 || `exit ${missing.code}`);
    } catch (e) {
      check('throwaway git repository for the --changed checks', () => e.message);
    } finally {
      rmSync(repo, { recursive: true, force: true });
    }
  }

  const passed = results.filter(Boolean).length;
  console.log(`${passed}/${results.length} self-tests passed`);
  return passed === results.length ? 0 : 1;
}

// ---------------------------------------------------------------- main

function main() {
  const opts = parseArgs(process.argv.slice(2));
  if (opts.selftest) process.exit(selftest());
  const userExcludes = opts.excludes.map(globToRegExp);
  const missing = [];
  let candidates;
  let explicitFiles = new Set();
  let changed = null;

  if (opts.changed) {
    for (const p of opts.paths) if (!existsSync(p)) missing.push(p);
    if (missing.length) usage(`path not found: ${missing.join(', ')}`);
    changed = changedSet(opts);
    candidates = changed.files;
  } else {
    const named = opts.paths.length ? opts.paths : ['.'];
    const files = [];
    const dirs = [];
    for (const p of named) {
      if (!existsSync(p)) missing.push(p);
      else if (statSync(p).isDirectory()) dirs.push(p);
      else files.push(p);
    }
    for (const m of missing) console.error(`warning: path not found: ${m}${/^[^./]/.test(m) && inGitWorkTree() ? ' (paths from `git diff` are repo-root relative; use --changed, or git diff --relative)' : ''}`);
    if (missing.length && !files.length && !dirs.length) usage('none of the named paths exist; nothing was scanned');
    explicitFiles = new Set(files.map(f => relative('.', f).split(sep).join('/')));
    candidates = [...files, ...filesUnderDirs(dirs)];
  }

  const norm = [...new Set(candidates.map(f => relative('.', f).split(sep).join('/')))];
  const excluded = [];
  const notCovered = [];
  const toScan = [];
  for (const f of norm) {
    const ext = f.includes('.') ? f.split('.').pop().toLowerCase() : '';
    if (!EXTENSIONS.has(ext)) {
      if (NOT_COVERED.has(ext) || (ext === 'xml' && /(^|\/)res\//.test(f))) notCovered.push(f);
      continue;
    }
    if (userExcludes.some(re => re.test(f))) {
      excluded.push({ file: f, reason: '--exclude' });
      continue;
    }
    const reason = opts.defaultExcludes ? tokenSourceReason(f) : null;
    if (reason) {
      excluded.push({ file: f, reason });
      continue;
    }
    toScan.push(f);
  }

  const inv = opts.inventory ? { colors: [], named: [], lengths: [] } : null;
  const findings = Object.fromEntries(CHECKS.map(c => [c.id, []]));
  let tokenRefs = 0;
  let themeReads = 0;
  let scanned = 0;
  for (const file of toScan) {
    const r = scanFile(file, opts, inv);
    if (!r) continue;
    scanned++;
    tokenRefs += r.tokenRefs;
    themeReads += r.themeReads;
    const addedLines = changed ? changed.added.get(file) : null;
    for (const h of r.hits) {
      const entry = { file, line: h.line, text: h.text };
      if (changed) entry.new = addedLines === 'all' || Boolean(addedLines && addedLines.has(h.line));
      findings[h.check].push(entry);
    }
  }

  const all = Object.values(findings).flat();
  const newCount = changed ? all.filter(f => f.new).length : all.length;
  const total = all.length;
  const explicitExcluded = excluded.filter(e => explicitFiles.has(e.file) && e.reason !== '--exclude');

  // Exit status: never report "clean" for a scan that looked at nothing.
  let status;
  let note = '';
  if (missing.length) {
    status = 2;
    note = `named path(s) not found: ${missing.join(', ')}`;
  } else if (scanned === 0) {
    if (changed && notCovered.length === 0) {
      status = 0;
      note = !candidates.length
        ? `no changed files since ${changed.ref} (merge-base ${changed.mb})`
        : excluded.length
          ? `nothing to scan since ${changed.ref}: the changed UI files are token sources (check them with token-contrast.mjs)`
          : `no changed UI files since ${changed.ref} (${candidates.length} changed file(s) are not UI code)`;
    } else {
      status = 2;
      note = notCovered.length
        ? `nothing scanned: ${notCovered.length} file(s) are native or SVG code this scanner does not read (use the grep in SKILL.md step 6)`
        : 'nothing scanned: no UI files under the given paths (check the path, or --no-default-excludes if they are all token sources)';
    }
  } else {
    status = newCount ? 1 : 0;
  }
  if (opts.inventory && status !== 2) status = 0;

  if (opts.json) {
    const out = {
      filesScanned: scanned,
      tokenReferences: { var: tokenRefs, themeReads },
      excluded,
      notScanned: notCovered,
      missing,
      total,
      ...(changed ? { base: changed.ref, mergeBase: changed.mb, new: newCount, preexisting: total - newCount } : {}),
      findings: Object.fromEntries(Object.entries(findings).filter(([, l]) => l.length)),
      status,
      note,
    };
    console.log(JSON.stringify(out, null, 2));
    process.exit(status);
  }

  console.log(`scanned ${scanned} file(s)${changed ? ` changed since ${changed.ref} (merge-base ${changed.mb})` : ''}; token references: ${tokenRefs} var(--...), ${themeReads} theme reads`);
  if (excluded.length) {
    const sample = excluded.slice(0, 5).map(e => e.file).join(', ');
    console.log(`excluded ${excluded.length} file(s) as token sources or by --exclude: ${sample}${excluded.length > 5 ? ', ...' : ''}`);
  }
  for (const e of explicitExcluded) console.log(`warning: ${e.file} was named but skipped as a ${e.reason}; pass --no-default-excludes to scan it`);
  if (notCovered.length) console.log(`warning: not scanned (native or SVG; use the grep in SKILL.md step 6): ${notCovered.slice(0, 5).join(', ')}${notCovered.length > 5 ? `, ... (${notCovered.length})` : ''}`);
  if (note) console.log(note);

  if (opts.inventory) {
    printInventory(inv, opts.clusterDe);
    process.exit(status);
  }

  const clean = CHECKS.filter(c => findings[c.id].length === 0 && (!c.optIn || opts[c.optIn])).map(c => c.id);
  if (scanned && clean.length) console.log(`clean: ${clean.join(', ')}`);
  for (const check of CHECKS) {
    let list = findings[check.id];
    if (changed && opts.newOnly) list = list.filter(f => f.new);
    if (list.length === 0) continue;
    const label = changed ? `${list.filter(f => f.new).length} new, ${list.filter(f => !f.new).length} pre-existing` : String(list.length);
    console.log(`\n== ${check.id}: ${label} ==  (${check.why})`);
    const ordered = changed ? [...list].sort((a, b) => Number(b.new) - Number(a.new)) : list;
    for (const f of ordered.slice(0, opts.show)) console.log(`  ${changed ? (f.new ? '+ ' : '  ') : ''}${f.file}:${f.line}: ${f.text}`);
    if (ordered.length > opts.show) console.log(`   ... ${ordered.length - opts.show} more (use --show or --json)`);
  }
  if (changed && scanned) {
    console.log(`\n${newCount} new, ${total - newCount} pre-existing potential hard-coded value(s) in ${scanned} changed file(s).`);
  } else if (scanned) {
    console.log(`\n${total} potential hard-coded value(s).`);
  }
  process.exit(status);
}

main();
