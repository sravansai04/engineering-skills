# PHP Sink Cheat Sheet (Laravel, Symfony, plain PHP)

Candidates to trace, not findings. Several PHP defaults changed in 8.0 and 8.1, so check the runtime version (`composer.json` `require.php`, Dockerfiles, CI) before deciding.

## Where untrusted input enters

- **Plain PHP:** `$_GET`, `$_POST`, `$_REQUEST`, `$_COOKIE`, `$_FILES` (`name` and `type` are client-supplied), `$_SERVER['HTTP_*']`, `$_SERVER['PHP_SELF']`/`REQUEST_URI`/`QUERY_STRING`, `file_get_contents('php://input')`.
- **Laravel:** `$request->input/all/query/post/json/file/header/cookie`, route parameters, implicit route-model binding (it resolves an ID to a model, which is *not* an authorization check).
- **Symfony:** `$request->query`, `$request->request`, `$request->attributes`, `$request->headers`, `$request->files`, `getContent()`.

## Sinks

| Category | Dangerous | Safer |
|---|---|---|
| SQL | `mysqli_query($db, "... $id")`, `$pdo->query("... $x")`, `$pdo->exec(...)`, `$pdo->prepare("... $x")` (interpolating before preparing defeats it). Laravel `DB::raw($x)`, `whereRaw("... $x")`, `selectRaw`, `orderByRaw`, `havingRaw`, `DB::select("... $x")`. Column names from input in `orderBy($request->sort)` or `where($request->field, ...)`. Doctrine `createQuery("... $x")` (DQL injection) | PDO/mysqli prepared statements with bound values (set the charset in the DSN). Laravel bindings `whereRaw('x = ?', [$x])`. Query builder methods with values. Doctrine `setParameter`. Allowlists for column and sort names |
| Command | `system`, `exec`, `shell_exec`, `passthru`, `popen`, `proc_open($stringCmd)`, backticks. `escapeshellcmd` alone (it still allows argument injection) | `proc_open([$prog, '--', $arg], ...)` (array form, PHP 7.4+, no shell). Symfony `Process` with an array. `escapeshellarg` per argument when a shell is unavoidable |
| Code eval | `eval`, `assert($string)` (evaluated strings before PHP 8.0), `create_function` (removed in 8.0), `preg_replace` with `/e` (removed in 7.0), `call_user_func($user)`, `$func()` / `new $class()` with user-chosen names, `$$var`, `extract($_GET)`/`extract($request->all())` (overwrites local variables), `parse_str($s)` without a result array (removed in 8.0) | Explicit dispatch maps. `parse_str($s, $out)` |
| File inclusion | `include`/`require`/`include_once`/`require_once` with user-influenced paths. Wrapper abuse (`php://filter`, `data://`, `phar://`) | Fixed include paths, or an allowlist map from key to file |
| Deserialization | `unserialize($user)`, which allows object injection via `__wakeup`/`__destruct`/`__toString` gadgets. `Phar::getMetadata()` on untrusted archives. On PHP before 8.0, any filesystem function on a `phar://` path auto-unserialized metadata | `json_decode`. If `unserialize` must stay, use `['allowed_classes' => false]` on trusted-origin data only |
| XXE | Passing `LIBXML_NOENT`, `LIBXML_DTDLOAD`, or `LIBXML_DTDVALID` to `simplexml_load_string`, `DOMDocument::loadXML`, or `XMLReader` on untrusted XML (`LIBXML_NOENT` *enables* entity substitution, despite its name). libxml2 before 2.9 (external entities on by default) | Default flags (libxml2 ≥ 2.9 doesn't load external entities). `libxml_disable_entity_loader()` is deprecated since 8.0 and unnecessary there. PHP 8.4 adds `LIBXML_NO_XXE` (libxml2 2.13+) for when substitution is genuinely needed |
| XSS | `echo $x`, `<?= $x ?>` without escaping. `htmlspecialchars($x)` relying on default flags on PHP before 8.1 (single quotes weren't escaped). Blade `{!! $x !!}`. Twig `\|raw` or `{% autoescape false %}`. `$_SERVER['PHP_SELF']` in a form `action` | `htmlspecialchars($x, ENT_QUOTES \| ENT_SUBSTITUTE, 'UTF-8')`. Blade `{{ }}`. Twig autoescape. URL scheme allowlist for `href` |
| Paths and uploads | `file_get_contents($base . $_GET['f'])`, `readfile`, `fopen`, `unlink`, `file_put_contents` with user paths. `move_uploaded_file($tmp, $dir . $_FILES['f']['name'])`. Storing uploads in the web root with executable extensions (`.php`, `.phtml`, `.phar`, `.pht`). Trusting `$_FILES[..]['type']` | `basename()` for name-only input, generated names, `realpath()` plus a prefix check on the base, storage outside the web root, content sniffing (`finfo`) with a type allowlist, serving via a controller with `Content-Disposition: attachment` |
| SSRF | `file_get_contents($url)`, `fopen($url)`, `curl_exec` with a user URL (with `CURLOPT_FOLLOWLOCATION`), Guzzle requests to user URLs | Scheme allowlist: restrict cURL with `CURLOPT_PROTOCOLS_STR` and `CURLOPT_REDIR_PROTOCOLS_STR` set to `"http,https"` (PHP 8.3+; older code uses `CURLOPT_PROTOCOLS`/`CURLOPT_REDIR_PROTOCOLS` with `CURLPROTO_HTTP \| CURLPROTO_HTTPS`). Resolve once, check the addresses, then pin the connection to the checked IP with `CURLOPT_RESOLVE` (`["host:443:203.0.113.7"]`), or route through an egress proxy. Checking `gethostbynamel()` and then letting cURL resolve again is not a fix. Redirects off or re-validated, timeouts |
| Open redirect | `header("Location: " . $_GET['url'])`, Laravel `redirect($request->input('next'))`, `redirect()->away($user)` | `redirect()->intended()` with a validated default. A relative-path allowlist. Symfony `RedirectResponse` only with validated targets |
| Type juggling | `==`/`!=` on secrets, hashes, or role strings (`"0e123" == "0e456"` is true). `in_array($x, $allow)` without `true` as the third argument. `strcmp($a, $b) == 0` with array input (returns null on PHP 7, so the comparison is true; throws `TypeError` on 8) | `===`, `hash_equals()` for secrets, `in_array($x, $allow, true)` |
| Randomness | `rand`, `mt_rand`, `uniqid`, `lcg_value`, `str_shuffle` for tokens | `random_bytes`, `random_int`, `bin2hex(random_bytes(32))` |
| Hashing / crypto | `md5`, `sha1`, `hash('sha256', $pw)`, `crypt` with weak schemes for passwords. `openssl_encrypt` with `*-ecb` or a static IV. `mcrypt` (removed in 7.2) | `password_hash($pw, PASSWORD_ARGON2ID)` or `PASSWORD_DEFAULT`, `password_verify`, `password_needs_rehash`. `sodium_crypto_secretbox` or `aes-256-gcm` with random IVs |
| TLS | `CURLOPT_SSL_VERIFYPEER => false`, `CURLOPT_SSL_VERIFYHOST => 0`, Guzzle `'verify' => false`, stream context `verify_peer => false` | Defaults |
| Sessions | No `session_regenerate_id(true)` after login. `session.use_strict_mode=0`. Cookies without `secure`/`httponly`/`samesite` | Regenerate on login and privilege change. Strict mode. Cookie flags in `php.ini` or `session_set_cookie_params` |

## Framework gotchas

1. **Laravel mass assignment:** `protected $guarded = [];`, or a `$fillable` list including `role`, `is_admin`, `team_id`, combined with `Model::create($request->all())` / `->fill($request->all())` / `->update($request->all())`. Prefer `$request->validated()` or `$request->only([...])`.
2. **Laravel authorization:** route-model binding loads `/posts/{post}` for anyone. Look for `$this->authorize('update', $post)`, `Gate::authorize`, `can:` middleware, policies, or scoped queries (`$request->user()->posts()->findOrFail($id)`). Nested bindings without `scopeBindings()` let `/users/{user}/posts/{post}` load a post that doesn't belong to that user.
3. **Laravel config:** `APP_DEBUG=true` in production (the error page leaks environment details). `APP_KEY` committed or leaked (forges encrypted and signed cookies, and payloads that are unserialized become code execution). CSRF exclusions (`$except` in the `VerifyCsrfToken` middleware in older versions, `validateCsrfTokens(except: [...])` in newer bootstrap config) covering cookie-authenticated routes.
4. **Symfony:** `access_control` patterns that are unanchored or ordered wrongly (first match wins). `security: false` firewalls. Voters that return `ACCESS_ABSTAIN` everywhere with `allow_if_all_abstain: true`. `APP_ENV=dev` or the profiler/debug toolbar exposed in production.
5. **Raw output of JSON into scripts:** `<script>var d = <?= json_encode($data) ?>;</script>` needs `JSON_HEX_TAG | JSON_HEX_AMP | JSON_HEX_APOS | JSON_HEX_QUOT` so `</script>` can't break out.
6. **Error display:** `display_errors=On` in production, or `ini_set('display_errors', 1)` in code.

## Search patterns (ripgrep regex, also usable with the Grep tool)

```bash
rg -n --type php -e '\b(system|exec|shell_exec|passthru|popen|proc_open)\s*\(' -e '`[^`]*\$' -e '\beval\s*\(' -e '\bassert\s*\(\s*\$' -e '\bextract\s*\(' -e 'create_function'
rg -n --type php -e '\b(include|require)(_once)?\b[^;]*\$' -e '\bunserialize\s*\(' -e 'getMetadata\s*\(' -e 'LIBXML_(NOENT|DTDLOAD|DTDVALID)'
rg -n --type php -e '(mysqli_query|->query|->exec|->prepare)\s*\([^;]*(\$\w+|"\s*\.)' -e '(whereRaw|selectRaw|orderByRaw|havingRaw|DB::raw|DB::select|DB::statement)\s*\([^;]*\$' -e 'createQuery\s*\([^;]*\$'
rg -n --type php -e '\$_(GET|POST|REQUEST|COOKIE|SERVER)\[' -e 'PHP_SELF' -e 'header\s*\(\s*["\x27]Location:[^;]*\$' -e 'move_uploaded_file'
rg -n --type php -e '\b(rand|mt_rand|uniqid|lcg_value|str_shuffle)\s*\(' -e '\b(md5|sha1)\s*\(\s*\$' -e 'VERIFY(PEER|HOST)\s*["\x27]?\s*(=>|,)\s*(false|0)' -e '["\x27]verify["\x27]\s*=>\s*false' -e '\$guarded\s*=\s*\[\s*\]'
rg -n -g '*.blade.php' -g '*.twig' -e '\{!!' -e '\|\s*raw\b' -e 'autoescape\s+false'
```
