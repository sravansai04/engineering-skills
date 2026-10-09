#!/usr/bin/env node
// Automated WCAG scan with axe-core across pages, viewports AND UI states, grouped by rule with
// the WCAG success criteria each rule maps to. A clean result is a floor, not a pass: axe decides
// only part of WCAG, and its "incomplete" bucket lists checks a human must finish.
//
// Requires Node 20+ (Playwright's minimum), plus `playwright` (or `@playwright/test`) and
// `@axe-core/playwright` resolvable from the current working directory (run from the project
// root) or installed next to this script:
//   npm i -D playwright @axe-core/playwright && npx playwright install chromium
//
// usage: node axe-scan.mjs <url> [<url> ...]
//          [--viewports 1280x800,320x640]    default: one desktop + one 320px-wide reflow width
//          [--tags wcag2a,wcag2aa,wcag21a,wcag21aa,wcag22aa]
//          [--best-practice]                  also run axe best-practice rules (reported apart: no SC)
//          [--include <css>] [--exclude <css>] (repeatable)
//          [--wait-for <css>] [--storage-state auth.json] [--color-scheme light|dark]
//          [--setup <file.mjs>]               (repeatable) scan one extra STATE per file: the module's
//                                             default export `async (page) => {}` runs after load and
//                                             --wait-for, and must leave the page in that state
//          [--click <css>]                    (repeatable) shorthand: one extra state reached by clicking
//                                             these selectors in order
//          [--no-initial]                     skip the as-loaded state (scan only --setup/--click states)
//          [--allow-redirect]                 accept landing on a different page than the URL asked for
//          [--fail-on minor|moderate|serious|critical]   default: minor (any violation fails)
//          [--json out.json]
//        node axe-scan.mjs --selftest         check the pure helpers (tag mapping, argument parsing,
//                                             same-page test); needs no browser and no dependencies
//
// Every run refuses to scan an error page or a page it was redirected to (a login screen after an
// expired --storage-state, a 404 from a typo): those are reported as errors, never as "clean".
//
// Exit codes: 0 = no violations at or above --fail-on, 1 = violations, 2 = usage/runtime error
// (including any run that could not reach its page or state).

import { createRequire } from 'node:module';
import { writeFileSync } from 'node:fs';
import { pathToFileURL } from 'node:url';
import path from 'node:path';

const USAGE = `usage: node axe-scan.mjs <url> [<url> ...] [--viewports 1280x800,320x640] [--tags <list>] [--best-practice]
         [--include <css>] [--exclude <css>] [--wait-for <css>] [--storage-state auth.json]
         [--color-scheme light|dark] [--setup state.mjs]... [--click <css>]... [--no-initial]
         [--allow-redirect] [--fail-on minor|moderate|serious|critical] [--json out.json]
       node axe-scan.mjs --selftest     (checks the helpers; no browser needed)`;

const IMPACT_ORDER = ['critical', 'serious', 'moderate', 'minor'];
const DEFAULT_TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'];

function usageError(msg) {
  console.error(`axe-scan: ${msg}\n${USAGE}`);
  process.exit(2);
}

function parseArgs(argv) {
  const o = {
    urls: [],
    viewports: [
      { width: 1280, height: 800 },
      { width: 320, height: 640 },
    ],
    tags: DEFAULT_TAGS,
    bestPractice: false,
    include: [],
    exclude: [],
    setups: [],
    clicks: [],
    initial: true,
    allowRedirect: false,
    failOn: 'minor',
  };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    const next = () => {
      if (i + 1 >= argv.length) usageError(`${a} needs a value`);
      return argv[++i];
    };
    if (a === '--viewports') {
      o.viewports = next()
        .split(',')
        .map((v) => {
          const m = v.trim().match(/^(\d+)x(\d+)$/);
          if (!m) usageError(`bad viewport "${v}" (use WIDTHxHEIGHT)`);
          return { width: Number(m[1]), height: Number(m[2]) };
        });
    } else if (a === '--tags') o.tags = next().split(',').map((t) => t.trim()).filter(Boolean);
    else if (a === '--best-practice') o.bestPractice = true;
    else if (a === '--include') o.include.push(next());
    else if (a === '--exclude') o.exclude.push(next());
    else if (a === '--wait-for') o.waitFor = next();
    else if (a === '--storage-state') o.storageState = next();
    else if (a === '--color-scheme') o.colorScheme = next();
    else if (a === '--setup') o.setups.push(next());
    else if (a === '--click') o.clicks.push(next());
    else if (a === '--no-initial') o.initial = false;
    else if (a === '--allow-redirect') o.allowRedirect = true;
    else if (a === '--fail-on') {
      o.failOn = next();
      if (!IMPACT_ORDER.includes(o.failOn)) usageError(`--fail-on must be one of ${IMPACT_ORDER.join(', ')}`);
    } else if (a === '--json') o.json = next();
    else if (a === '-h' || a === '--help') {
      console.log(USAGE);
      process.exit(0);
    } else if (a.startsWith('--')) usageError(`unknown option ${a}`);
    else o.urls.push(a);
  }
  if (!o.urls.length) usageError('need at least one URL');
  if (o.colorScheme && !['light', 'dark'].includes(o.colorScheme)) usageError('--color-scheme must be light or dark');
  if (!o.initial && !o.setups.length && !o.clicks.length) usageError('--no-initial needs at least one --setup or --click state');
  return o;
}

function load(...names) {
  for (const base of [path.join(process.cwd(), 'noop.js'), import.meta.url]) {
    for (const name of names) {
      try {
        return createRequire(base)(name);
      } catch {
        /* try the next candidate */
      }
    }
  }
  console.error(
    `axe-scan: cannot find "${names[0]}". From the project root run:\n` +
      '  npm i -D playwright @axe-core/playwright && npx playwright install chromium',
  );
  process.exit(2);
}

// A state to scan: the page as loaded, a --setup module, or a --click sequence.
async function buildStates(o) {
  const states = [];
  if (o.initial) states.push({ name: 'initial', run: null });
  for (const file of o.setups) {
    let mod;
    try {
      mod = await import(pathToFileURL(path.resolve(file)).href);
    } catch (e) {
      usageError(`cannot load --setup ${file}: ${String(e.message).split('\n')[0]}`);
    }
    const fn = mod.default ?? mod.setup;
    if (typeof fn !== 'function') usageError(`--setup ${file} must export a default async function (page) => { ... }`);
    states.push({ name: path.basename(file).replace(/\.[cm]?js$/, ''), run: fn });
  }
  if (o.clicks.length) {
    const sels = [...o.clicks];
    states.push({
      name: `click ${sels.join(' > ')}`,
      run: async (page) => {
        for (const sel of sels) {
          await page.locator(sel).first().click();
          await page.waitForTimeout(300); // let the opened UI settle before the next click or the scan
        }
      },
    });
  }
  return states;
}

// Same page = same origin and path; a trailing slash or index.html difference is not a redirect.
const pageKey = (u) => {
  const x = new URL(u);
  return x.origin + x.pathname.replace(/\/index\.html?$/, '/').replace(/\/+$/, '');
};

// Navigate and refuse anything that is not the page we were asked to scan.
async function openTarget(page, url, o) {
  const resp = await page.goto(url, { waitUntil: 'load' });
  if (/^https?:$/.test(new URL(url).protocol)) {
    if (!resp) throw new Error(`no HTTP response for ${url}`);
    if (resp.status() >= 400) throw new Error(`HTTP ${resp.status()} for ${url}; refusing to scan an error page`);
  }
  const checkLanding = () => {
    if (!o.allowRedirect && pageKey(page.url()) !== pageKey(url)) {
      throw new Error(
        `landed on ${page.url()} instead of ${url} (login redirect? missing or expired --storage-state; ` +
          'pass --allow-redirect if the redirect is intended)',
      );
    }
  };
  checkLanding(); // server-side redirects
  if (o.waitFor) {
    try {
      await page.waitForSelector(o.waitFor, { state: 'visible' });
    } catch {
      throw new Error(`--wait-for "${o.waitFor}" never became visible on ${page.url()}`);
    }
  }
  checkLanding(); // client-side redirects that happened while the app booted
}

// axe tags like "wcag143" / "wcag1410" / "wcag2411" -> "1.4.3" / "1.4.10" / "2.4.11"
function scFromTags(tags) {
  return tags
    .map((t) => t.match(/^wcag(\d)(\d)(\d+)$/))
    .filter(Boolean)
    .map((m) => `${m[1]}.${m[2]}.${m[3]}`);
}

function levelFromTags(tags) {
  if (tags.some((t) => /^wcag2(?:1|2)?aaa$/.test(t))) return 'AAA';
  if (tags.some((t) => /^wcag2(?:1|2)?aa$/.test(t))) return 'AA';
  if (tags.some((t) => /^wcag2(?:1|2)?a$/.test(t))) return 'A';
  return null;
}

async function main() {
  const o = parseArgs(process.argv.slice(2));
  const states = await buildStates(o);
  const { chromium } = load('playwright', '@playwright/test'); // the test runner re-exports chromium
  const axeModule = load('@axe-core/playwright');
  const AxeBuilder = axeModule.default ?? axeModule.AxeBuilder ?? axeModule;

  const tags = o.bestPractice ? [...o.tags, 'best-practice'] : o.tags;
  const byRule = new Map(); // violations
  const review = new Map(); // incomplete ("needs review")
  const runs = [];
  let axeVersion = null;
  const browser = await chromium.launch();
  try {
    for (const url of o.urls) {
      for (const vp of o.viewports) {
        for (const state of states) {
          const context = await browser.newContext({
            viewport: vp,
            ...(o.colorScheme ? { colorScheme: o.colorScheme } : {}),
            ...(o.storageState ? { storageState: o.storageState } : {}),
          });
          const page = await context.newPage();
          const vpLabel = `${vp.width}x${vp.height}`;
          const at = state.name === 'initial' ? vpLabel : `${vpLabel} [${state.name}]`;
          const where = `${url} @${at}`;
          const run = { url, viewport: vpLabel, state: state.name, where };
          try {
            await openTarget(page, url, o);
            if (state.run) {
              try {
                await state.run(page);
              } catch (e) {
                throw new Error(`setup "${state.name}" failed: ${String(e.message).split('\n')[0]}`);
              }
            }
            run.finalUrl = page.url();
            let builder = new AxeBuilder({ page }).withTags(tags);
            for (const sel of o.include) builder = builder.include(sel);
            for (const sel of o.exclude) builder = builder.exclude(sel);
            const res = await builder.analyze();
            axeVersion ||= res.testEngine?.version ?? null;
            Object.assign(run, { violations: res.violations.length, incomplete: res.incomplete.length, passes: res.passes.length });
            for (const v of res.violations) {
              const entry =
                byRule.get(v.id) ||
                byRule.set(v.id, {
                  id: v.id,
                  impact: v.impact,
                  help: v.help,
                  helpUrl: v.helpUrl,
                  sc: scFromTags(v.tags),
                  level: levelFromTags(v.tags),
                  bestPractice: v.tags.includes('best-practice') && !scFromTags(v.tags).length,
                  nodes: [],
                }).get(v.id);
              for (const n of v.nodes) {
                // The same element failing at several viewports or states is ONE problem: merge, keep where.
                const target = n.target.map((t) => (Array.isArray(t) ? t.join(' >>> ') : t)).join(' | ');
                const existing = entry.nodes.find((x) => x.url === url && x.target === target);
                if (existing) existing.seenAt.push(at);
                else entry.nodes.push({ url, seenAt: [at], target, summary: n.failureSummary });
              }
            }
            for (const v of res.incomplete) {
              const entry = review.get(v.id) || review.set(v.id, { id: v.id, help: v.help, sc: scFromTags(v.tags), count: 0, examples: [] }).get(v.id);
              entry.count += v.nodes.length;
              for (const n of v.nodes.slice(0, 2)) if (entry.examples.length < 3) entry.examples.push(`${where}  ${n.target.join(' ')}`);
            }
          } catch (e) {
            run.error = String(e.message).split('\n')[0];
            run.finalUrl = page.url();
          } finally {
            runs.push(run);
            await context.close();
          }
        }
      }
    }
  } finally {
    await browser.close();
  }

  // ---- report ----
  const rules = [...byRule.values()].sort(
    (a, b) => IMPACT_ORDER.indexOf(a.impact) - IMPACT_ORDER.indexOf(b.impact) || b.nodes.length - a.nodes.length,
  );
  console.log(`axe-core ${axeVersion ?? '(version unknown: no run completed)'}  tags: ${tags.join(',')}`);
  if (!tags.includes('wcag22aa')) {
    console.log('  note: wcag22aa is not in the tags, so target-size (SC 2.5.8) did NOT run; it is off unless that tag is requested.');
  }
  for (const r of runs) {
    const landed = r.finalUrl && pageKey(r.finalUrl) !== pageKey(r.url) ? `  (landed on ${r.finalUrl})` : '';
    console.log(
      r.error
        ? `  ERROR  ${r.where}: ${r.error}`
        : `  ${r.where}: ${r.violations} rule(s) failing, ${r.incomplete} need review${landed}`,
    );
  }

  if (runs.every((r) => r.error)) {
    console.error('\nNo page could be scanned; fix the URLs, start the app, or pass --storage-state for logged-in pages.');
    process.exit(2);
  }

  const wcagRules = rules.filter((r) => !r.bestPractice);
  const bpRules = rules.filter((r) => r.bestPractice);
  const printRule = (r) => {
    const sc = r.sc.length ? `SC ${r.sc.join(', ')}${r.level ? ` (${r.level})` : ''}` : 'no SC: best practice';
    console.log(`\n[${(r.impact || 'n/a').toUpperCase()}] ${r.id}: ${r.help}`);
    console.log(`  ${sc}   ${r.nodes.length} element(s)   ${r.helpUrl}`);
    for (const n of r.nodes.slice(0, 5)) {
      console.log(`  - ${n.target}\n    at ${n.url} @${n.seenAt.join(', @')}`);
      const reasons = (n.summary || '')
        .split('\n')
        .map((l) => l.trim())
        .filter((l) => l && !/^Fix (any|all) of the following:?$/.test(l));
      if (reasons.length) console.log(`    why: ${reasons.slice(0, 2).join('; ')}`);
    }
    if (r.nodes.length > 5) console.log(`  … ${r.nodes.length - 5} more`);
  };

  console.log(`\n=== WCAG violations: ${wcagRules.length} rule(s) ===`);
  wcagRules.forEach(printRule);
  if (o.bestPractice) {
    console.log(`\n=== Best-practice issues (not WCAG failures; never cite an SC for these): ${bpRules.length} ===`);
    bpRules.forEach(printRule);
  }
  if (review.size) {
    console.log(`\n=== Needs human review (axe "incomplete"): ${review.size} rule(s) ===`);
    for (const r of review.values()) {
      console.log(`  ${r.id}${r.sc.length ? ` (SC ${r.sc.join(', ')})` : ''}: ${r.help}  x${r.count}`);
      for (const ex of r.examples) console.log(`    e.g. ${ex}`);
    }
  }
  console.log(
    '\nReminder: axe cannot judge alt-text quality, focus order, keyboard operation, focus management,\n' +
      'screen-reader announcements, meaningful headings/labels, or reflow behavior. Do the manual pass.',
  );

  if (o.json) {
    writeFileSync(
      o.json,
      JSON.stringify({ axeCore: axeVersion, tags, states: states.map((s) => s.name), runs, violations: rules, needsReview: [...review.values()] }, null, 2),
    );
    console.log(`JSON: ${path.resolve(o.json)}`);
  }

  const threshold = IMPACT_ORDER.indexOf(o.failOn);
  const failing = wcagRules.some((r) => IMPACT_ORDER.indexOf(r.impact) !== -1 && IMPACT_ORDER.indexOf(r.impact) <= threshold);
  const errored = runs.some((r) => r.error);
  if (errored) console.error('\nAt least one run did not reach its page or state (see ERROR lines): treat those as NOT scanned.');
  process.exit(errored ? 2 : failing ? 1 : 0);
}

// Non-exiting twin of load(), for --selftest's dependency report.
function resolvable(name) {
  for (const base of [path.join(process.cwd(), 'noop.js'), import.meta.url]) {
    try {
      createRequire(base).resolve(name);
      return true;
    } catch {
      /* try the next base */
    }
  }
  return false;
}

// Checks the logic that runs outside the browser. The scan itself needs a page; the fixtures in
// evals/files/ (see EXPECTED.md there) cover it end to end.
function selftest() {
  const failures = [];
  const expect = (label, condition) => {
    if (!condition) failures.push(label);
  };
  const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);

  expect('default tags request wcag22aa, so target-size (2.5.8) runs', DEFAULT_TAGS.includes('wcag22aa'));
  expect(
    'SC numbers from axe tags, including two-digit parts',
    same(scFromTags(['wcag2aa', 'wcag143', 'wcag1410', 'wcag2411', 'cat.color', 'best-practice']), ['1.4.3', '1.4.10', '2.4.11']),
  );
  expect('level tags are not SC numbers', same(scFromTags(['wcag2a', 'wcag21aa', 'wcag22aa']), []));
  expect('wcag22aa is AA', levelFromTags(['wcag258', 'wcag22aa']) === 'AA');
  expect('wcag21a is A', levelFromTags(['wcag21a']) === 'A');
  expect('wcag2aaa is AAA', levelFromTags(['wcag2aaa']) === 'AAA');
  expect('best-practice has no level', levelFromTags(['best-practice']) === null);

  expect('index.html is the same page as its folder', pageKey('http://x.test/a/index.html') === pageKey('http://x.test/a/'));
  expect('trailing slash is the same page', pageKey('http://x.test/a') === pageKey('http://x.test/a/'));
  expect('query and hash do not change the page', pageKey('http://x.test/a?q=1#top') === pageKey('http://x.test/a'));
  expect('a login redirect is a different page', pageKey('http://x.test/login') !== pageKey('http://x.test/checkout'));
  expect('another origin is a different page', pageKey('http://x.test/a') !== pageKey('http://y.test/a'));

  const d = parseArgs(['http://x.test/']);
  expect('one desktop and one 320 px viewport by default', same(d.viewports.map((v) => v.width), [1280, 320]));
  expect('any violation fails by default', d.failOn === 'minor' && d.initial === true && d.allowRedirect === false);
  const o = parseArgs([
    'http://x.test/a', 'http://x.test/b', '--viewports', '1024x768,375x667', '--tags', 'wcag2a, wcag22aa',
    '--setup', 'open.mjs', '--setup', 'err.mjs', '--click', '#menu', '--no-initial', '--fail-on', 'serious',
  ]);
  expect('several URLs', same(o.urls, ['http://x.test/a', 'http://x.test/b']));
  expect('custom viewports', same(o.viewports, [{ width: 1024, height: 768 }, { width: 375, height: 667 }]));
  expect('tags are trimmed', same(o.tags, ['wcag2a', 'wcag22aa']));
  expect('repeatable --setup and --click', same(o.setups, ['open.mjs', 'err.mjs']) && same(o.clicks, ['#menu']));
  expect('--no-initial and --fail-on', o.initial === false && o.failOn === 'serious');

  for (const name of ['playwright', '@playwright/test', '@axe-core/playwright']) {
    console.log(`info: ${name} ${resolvable(name) ? 'resolves' : 'does not resolve'} from ${process.cwd()} or the script folder`);
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
    console.error(`axe-scan: ${e?.stack || e}`);
    process.exit(2);
  });
}
