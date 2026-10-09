# JavaScript / TypeScript Sink Cheat Sheet (Node, Express, Next.js, Browser, React/Vue/Angular)

Candidates to trace, not findings. Check the project's pinned versions before relying on any version-dependent default noted here.

## Where untrusted input enters

- **Express/Koa/Fastify:** `req.params`, `req.query`, `req.body`, `req.headers`, `req.cookies`, uploaded files (`originalname` and `mimetype` are client-supplied). Values aren't always strings: JSON bodies carry objects and arrays, and Express 4's default "extended" query parser builds nested objects from `a[b]=c` (Express 5 defaults to the "simple" parser, unless the app sets `query parser` to `extended`).
- **Next.js and similar full-stack frameworks:** route handlers, API routes, and **server actions** (`"use server"` functions). Server actions are reachable by direct POST, so each one must authenticate and authorize inside itself, regardless of which page renders it. Middleware isn't a sufficient sole authorization layer (CVE-2025-29927 let a crafted header skip Next.js middleware entirely).
- **GraphQL:** resolver `args`, plus field resolvers reached through nested queries.
- **Browser:** `location.*` (search, hash, pathname), `document.referrer`, `window.name`, `postMessage` event data, `localStorage`/`sessionStorage`, URL-fragment routing params, and data from any API that echoes user content.
- **TypeScript types are not validation.** `req.body as CreateUser` checks nothing at runtime. Look for a schema validator (zod, valibot, ajv, class-validator) on the path.

## Sinks (server side)

| Category | Dangerous | Safer |
|---|---|---|
| SQL | Template literals or `+` into `db.query`, `pool.query`. `sequelize.query(\`...${x}\`)`, `Sequelize.literal(user)`. Knex `.raw(\`...${x}\`)`, `whereRaw(\`...${x}\`)`. Prisma `$queryRawUnsafe`/`$executeRawUnsafe` with interpolation, `Prisma.raw(user)`. TypeORM `.query(str)`, `.where(\`id = ${id}\`)` | Placeholders (`$1`, `?`) with value arrays. Sequelize `replacements`/`bind`. Knex `?` bindings. Prisma tagged `$queryRaw\`... ${x}\`` (parameterized). TypeORM `.where("id = :id", { id })`. Allowlists for `ORDER BY` and column names |
| NoSQL | `collection.find({ email: req.body.email, password: req.body.password })` (operator injection with `{"$ne": null}`). `$where`, `$function`, `$accumulator` with input | Validate types (`typeof x === "string"`). Mongoose `sanitizeFilter` option (Mongoose 6+). Never build `$where` from input |
| Command | `child_process.exec/execSync(\`cmd ${x}\`)`, `spawn(cmd, { shell: true })` with input, `execa` with `shell: true`. Argument injection via `-`-prefixed values even without a shell | `execFile`/`spawn(prog, ["--", arg])` with no shell. On Windows, Node refuses to spawn `.bat`/`.cmd` without `shell: true` since the CVE-2024-27980 fix, and enabling the shell reintroduces quoting risk |
| Code eval | `eval`, `new Function(user)`, `setTimeout/setInterval(string)`, `vm.runInNewContext(user)` (Node's `vm` is documented as *not* a security mechanism), dynamic `require(user)` / `import(user)` | No evaluation of input. Process- or OS-level isolation if untrusted code must run |
| Templates (SSTI/XSS) | Compiling user input as a template: `ejs.render(userSrc)`, `pug.render(userSrc)`, `_.template(userSrc)`, `Handlebars.compile(userSrc)`. Unescaped output: EJS `<%- %>`, Pug `!{}`/`!=`, Handlebars `{{{ }}}` / `new SafeString(user)`, Nunjucks `\| safe` or `autoescape: false`. Passing `req.query`/`req.body` wholesale as the render data object (some engines read options from it) | Fixed templates. Escaped interpolation (`<%= %>`, `#{}`, `{{ }}`). Pass an explicit data object |
| Deserialization | `node-serialize`'s `unserialize` (revives functions, so attacker input runs as code), any `eval`-based revival of serialized data, YAML loaders configured with custom JS types, `JSON.parse` followed by recursive merge (see prototype pollution) | Plain `JSON.parse` into a validated schema |
| Prototype pollution | Recursive merge, deep-clone, or set-by-path utilities applied to user JSON (`__proto__`, `constructor.prototype` keys). Old versions of lodash `merge`/`set`/`defaultsDeep`, `jQuery.extend(true, ...)`, homemade `deepMerge` | Reject those keys. `Object.create(null)` or `Map` for user-keyed data. Schema validation that strips unknown keys. Up-to-date libraries. Node's `--disable-proto=delete` as hardening |
| SSRF | `fetch(userUrl)`, `axios(userUrl)`, `got`, `http.request`, headless browsers (`page.goto(userUrl)`), HTML-to-PDF renderers loading user HTML. A client configured with a base URL where an absolute user URL can override the base | Scheme allowlist, resolve-then-check-then-pin (custom `lookup` on an `http.Agent`), no redirects (`redirect: "manual"` / `maxRedirects: 0`), timeouts |
| Paths | `fs.readFile(path.join(base, user))`, `res.sendFile(path.join(dir, req.params.f))`, `res.download(user)`, archive extraction that trusts entry names (zip slip) | `res.sendFile(name, { root: dir })` (rejects traversal out of `root`). `path.resolve(base, user)` then `startsWith(path.resolve(base) + path.sep)`. Generated file names |
| Open redirect | `res.redirect(req.query.next)`, `reply.redirect(user)` | Relative paths only: must start with a single `/`, reject `//` and `/\`. Or an origin allowlist checked with `new URL()` |
| Headers | `res.setHeader(name, user)` (Node rejects CR/LF in header values, so this is mainly about *which* header and value). `Content-Type` echoed from input | A fixed header set |
| Randomness | `Math.random()` for tokens, IDs used as secrets, OTPs | `crypto.randomBytes`, `crypto.randomUUID()`, `crypto.randomInt`. In browsers, `crypto.getRandomValues` |
| Crypto | `createHash('md5'\|'sha1'\|'sha256')` for passwords. `createCipheriv('aes-*-ecb', ...)`. A static or reused IV with GCM/CTR. `===` comparing secrets | `crypto.scrypt` or an Argon2/bcrypt library. `aes-256-gcm` with a random 12-byte IV per message. `crypto.timingSafeEqual` (buffers must be equal length, so compare digests) |
| TLS | `rejectUnauthorized: false`, `NODE_TLS_REJECT_UNAUTHORIZED=0` | Defaults. A custom `ca` for private CAs |
| JWT | `jwt.decode()` used as if verified. `jwt.verify(t, key)` without `{ algorithms: [...] }`. Missing `audience`/`issuer` options. Weak HMAC secrets | `jwt.verify(t, key, { algorithms: ["RS256"], audience, issuer })`, or `jose`'s `jwtVerify` with explicit options |
| ReDoS | `new RegExp(userInput)`. Nested quantifiers (`(a+)+`, `(\w+\s?)*`) applied to request data | Escape user text before building a regex. Length limits. A linear-time regex library for user patterns |
| CORS | `cors({ origin: true, credentials: true })`, reflecting `req.headers.origin`, an unanchored regex origin | An explicit origin allowlist |
| Sessions | Hard-coded `express-session` `secret`. Cookie without `secure`/`httpOnly`/`sameSite`. No `req.session.regenerate()` after login | Secrets from env or a secret store. Explicit cookie flags. Regenerate the session on login |

## Sinks (browser and frameworks)

| Category | Dangerous | Safer |
|---|---|---|
| DOM HTML | `el.innerHTML = x`, `outerHTML`, `insertAdjacentHTML`, `document.write`, `iframe.srcdoc`, `Range.createContextualFragment`, jQuery `$(userString)`/`.html(x)`/`.append(x)` | `textContent`, `createElement` plus properties, DOMPurify for required rich HTML, Trusted Types |
| URLs | `location = x`, `location.href = x`, `window.open(x)`, `a.href = x`, `setAttribute("href"\|"src"\|"action", x)` | Parse with `new URL(x, location.origin)` and allow only `http:`/`https:` (and same-origin, where required) |
| Code | `eval`, `Function`, `setTimeout(string)`, `script.src = userUrl` | Not evaluating input |
| React | `dangerouslySetInnerHTML={{ __html: x }}`. User URLs in `href`/`src`: React 19 blocks `javascript:` URLs there, earlier versions only warn, and neither validates `data:` or other schemes. `ref.current.innerHTML = x` | Render as text. Sanitize when HTML is required. Validate URL schemes |
| Vue | `v-html`, `:href="userUrl"`, `innerHTML` in render functions, compiling user strings as templates | `{{ }}` interpolation, URL validation |
| Angular | `bypassSecurityTrustHtml/Url/ResourceUrl/Script/Style(user)`, `ElementRef.nativeElement.innerHTML` | Angular's built-in sanitization through `[innerHTML]` binding (it sanitizes), no bypass on user data |
| Svelte / Lit | `{@html x}`, `unsafeHTML(x)` | Text bindings |
| Messaging | `addEventListener("message", e => use(e.data))` without checking `e.origin`. `postMessage(secret, "*")` | Check `e.origin` against an exact allowlist. Give a specific target origin |

## Framework gotchas

1. **Authorization in Next.js-style apps:** check the data-access function, not just the layout or middleware. Client components can't enforce anything, and server actions are public endpoints.
2. **Leaking to the client bundle:** env vars with a public prefix (`NEXT_PUBLIC_`, `VITE_`, `REACT_APP_`) are inlined into browser code. Secrets must not use them. Also check server data passed as props to client components: everything in a prop is serialized to the browser.
3. **Mongoose/Sequelize mass assignment:** `Model.create(req.body)` and `doc.set(req.body)` write any field in the schema, including `role` or `isAdmin`. Pick fields explicitly.
4. **`express.static`/`serve-static`** with `dotfiles: "allow"` or serving the project root exposes `.env` and `.git`.
5. **Error handlers** that send `err.stack` or `err.message` from database drivers to clients (A10).
6. **`helmet` absent** isn't a finding by itself. Check which headers the deployed responses actually carry (a proxy may set them).
7. **`npm` lifecycle scripts:** a new dependency with `preinstall`/`install`/`postinstall` scripts runs code at install time, in CI and on developer machines. Note it in supply-chain review.

## Search patterns (ripgrep regex, also usable with the Grep tool)

```bash
rg -n --type js --type ts -e 'child_process' -e '\bexec(Sync)?\(' -e 'shell\s*:\s*true' -e '\beval\(' -e 'new Function\(' -e 'vm\.runIn'
rg -n --type js --type ts -e 'query(Raw)?Unsafe' -e 'executeRawUnsafe' -e '\.(raw|whereRaw|orderByRaw|havingRaw)\(\s*`' -e 'Sequelize\.literal\(' -e '\.query\(\s*`[^`]*\$\{' -e '\$where'
rg -n --type js --type ts -e 'dangerouslySetInnerHTML' -e '\.innerHTML\s*=' -e 'outerHTML\s*=' -e 'insertAdjacentHTML' -e 'document\.write' -e 'bypassSecurityTrust' -e 'v-html' -e '\{@html' -e 'unsafeHTML'
rg -n --type js --type ts -e 'res\.redirect\(\s*req\.' -e 'sendFile\(' -e 'path\.join\([^)]*req\.' -e 'addEventListener\(\s*["\x27]message' -e 'postMessage\([^)]*["\x27]\*["\x27]'
rg -n --type js --type ts -e 'Math\.random\(' -e 'createHash\(\s*["\x27](md5|sha1)' -e 'rejectUnauthorized\s*:\s*false' -e 'jwt\.decode\(' -e 'jwt\.verify\(' -e 'origin\s*:\s*true' -e 'new RegExp\('
rg -n --type js --type ts -e '__proto__' -e 'constructor\.prototype' -e 'defaultsDeep\(' -e 'extend\(\s*true' -e 'deep(Merge|Extend|Assign|Set)\('
rg -n -g '*.ejs' -g '*.pug' -g '*.hbs' -g '*.handlebars' -g '*.njk' -e '<%-' -e '!\{' -e '\{\{\{' -e '\|\s*safe\b'
```
