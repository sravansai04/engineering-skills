# Python Sink Cheat Sheet (Django, Flask, FastAPI)

Candidates to trace, not findings. Version-dependent defaults are noted where they change the verdict. Check the project's pinned versions before relying on one.

## Where untrusted input enters

- **Django:** `request.GET`, `request.POST`, `request.body`, `request.FILES` (name and content type are client-supplied), `request.headers`/`request.META` (including `HTTP_HOST`, `HTTP_X_FORWARDED_*`), `request.COOKIES`, URL kwargs. DRF: `request.data`, `request.query_params`.
- **Flask:** `request.args`, `request.form`, `request.get_json()`, `request.files`, `request.headers`, `request.cookies`, `request.view_args`.
- **FastAPI:** path, query, header, cookie, and body parameters. Pydantic validates *shape and type*. It does not decide whether the caller may touch the referenced object.
- Also: Celery task arguments that originate from requests, management commands that process uploaded files, and webhook payloads.

## Sinks

| Category | Dangerous | Safer |
|---|---|---|
| SQL | `cursor.execute(f"...{x}")`, `"..." % x`, `.format(x)`. Django `.raw(f"...")`, `.extra(where=[...])`, `RawSQL(f"...")`. SQLAlchemy `text(f"...")` | DB-API params `cursor.execute("... WHERE id = %s", (x,))` (`?` for sqlite3). Django ORM filters. `text("... :id").bindparams(id=x)`. Allowlist maps for column and sort names |
| Command | `os.system`, `os.popen`, `subprocess.*(..., shell=True)` with interpolation, `asyncio.create_subprocess_shell`, `["sh", "-c", cmd]` | `subprocess.run([prog, "--", arg], check=True)` with no shell. `shlex.quote` only when a shell is unavoidable (POSIX only) |
| Code eval | `eval`, `exec`, `compile`, `importlib.import_module(user)`, `getattr(obj, user)()` | `ast.literal_eval` for literals. An explicit dispatch dict |
| Template injection | `render_template_string(user_src)`, `jinja2.Template(user_src)`, `Environment().from_string(user_src)`, Django `Template(user_src)`, Mako `Template(user_src)` | Fixed templates with user data as context. A Jinja2 `SandboxedEnvironment` is not a hard boundary |
| XSS | `Markup(user)`, `\|safe`, `{% autoescape false %}` / `{% autoescape off %}`, Django `mark_safe(user)`, `format_html(f"...{x}")` (the f-string defeats it), `HttpResponse(user_html)` | Autoescaped templates. `format_html("<b>{}</b>", x)`. `bleach`-style allowlist sanitizers (note: bleach is deprecated; prefer a maintained one such as `nh3`) |
| Deserialization | `pickle.load(s)`, `dill`, `shelve`, `jsonpickle.decode`, `joblib.load`, `pandas.read_pickle`, `numpy.load(allow_pickle=True)`, `torch.load(..., weights_only=False)`, `yaml.load(s, Loader=yaml.Loader / UnsafeLoader / FullLoader)`, `yaml.unsafe_load`, `marshal.loads` | `json`. `yaml.safe_load`. `torch.load` with its default `weights_only=True` (the default since PyTorch 2.6). `safetensors` for model weights |
| XML / XXE | `lxml.etree` parsers with `resolve_entities=True`. `lxml.etree.iterparse`/`ETCompatXMLParser` before lxml 6.1 (defaulted to resolving). lxml 5.0–6.1.2 still fetch external *parameter* entities under the `'internal'` default | `defusedxml`. Or an lxml `XMLParser(resolve_entities=False, no_network=True, load_dtd=False)`. Current stdlib parsers don't fetch external entities; still prefer `defusedxml` for untrusted input |
| SSRF | `requests.get(user_url)`, `httpx`, `aiohttp`, `urllib.request.urlopen(user_url)` (also opens `file://` URLs) | Scheme allowlist, then enforce the IP policy on the connection actually made: route through an egress proxy that enforces it, or mount a custom `HTTPAdapter` (urllib3 connection class) or `httpx` transport that checks the connected socket's peer address. Resolving with `getaddrinfo`, checking, then calling `requests.get(url)` is not a fix: the client resolves again (DNS rebinding, checklist §5). `allow_redirects=False` or re-check each hop. Always pass `timeout=`; `requests` has no default timeout |
| Paths | `open(os.path.join(base, user))` (an absolute `user` discards `base`; `..` escapes). Flask `send_file(user_path)`. `tarfile.extractall()` without `filter=` on Python older than 3.14. `shutil.unpack_archive` on untrusted archives | `werkzeug.utils.secure_filename` for names. Flask `send_from_directory(dir, name)`. `p = (base / user).resolve()` then `p.is_relative_to(base.resolve())` (3.9+). `tarfile` `filter="data"` (3.12+, backported to security releases, and the default from 3.14; keep patch releases current, because CVE-2025-4517/4138 bypassed it). `zipfile` strips `..` and absolute names on extract but doesn't limit size |
| Open redirect | `redirect(request.args["next"])`, `HttpResponseRedirect(user)` | Django `url_has_allowed_host_and_scheme(url, allowed_hosts={request.get_host()}, require_https=True)`. A relative-path allowlist |
| Randomness | `random.random/randint/choice/getrandbits` for tokens, OTPs, or salts | `secrets.token_urlsafe()`, `secrets.choice`, `secrets.randbelow` |
| Hashing | `hashlib.md5/sha1/sha256(password)` | `argon2-cffi` (Argon2id), `bcrypt`, Django's default hashers |
| Comparison | `==` on tokens, MACs, signatures | `hmac.compare_digest` |
| TLS | `requests(..., verify=False)`, `ssl._create_unverified_context()`, `ssl.CERT_NONE` | Default verification. A custom CA bundle via `verify="/path/ca.pem"` |
| JWT (PyJWT) | `jwt.decode(t, options={"verify_signature": False})`, an `algorithms` list containing both HS* and RS* for one key, missing `audience`/`issuer` | `jwt.decode(t, key, algorithms=["RS256"], audience=..., issuer=...)` |
| ReDoS | `re` with user-supplied patterns, or nested-quantifier patterns on user input | Fixed linear patterns plus length limits. The `re2` bindings for user patterns |

## Framework gotchas

1. **Django ownership:** `Model.objects.get(pk=pk)` in a view behind `@login_required` is the classic IDOR. Look for `.filter(owner=request.user)`, or a scoped `get_queryset`.
2. **DRF object permissions:** `has_object_permission` runs only when a view calls `get_object()` (or `check_object_permissions`). It doesn't filter list endpoints. A `get_queryset()` returning `Model.objects.all()` with `permission_classes = [IsAuthenticated]` exposes every row.
3. **DRF and ModelForm mass assignment:** `fields = "__all__"` or `exclude = [...]` on serializers and forms makes new columns (e.g. `is_staff`, `role`, `owner`) writable automatically. Use explicit `fields` plus `read_only_fields`.
4. **Pydantic models reused for input and persistence:** a request model that includes `role` or `owner_id` lets clients set them. Use separate input models. Use `response_model` in FastAPI to avoid returning whole ORM objects.
5. **FastAPI auth lives in `Depends`:** a route missing the dependency, or a router included without router-level `dependencies=[...]`, is unauthenticated.
6. **Django settings:** `DEBUG = True` (leaks settings and stack traces), `ALLOWED_HOSTS = ["*"]` (host-header poisoning of reset links built with `request.build_absolute_uri`), a `SECRET_KEY` committed to the repo (session and signing forgery), `@csrf_exempt` on cookie-authenticated views, `SESSION_COOKIE_SECURE`/`CSRF_COOKIE_SECURE` false in production.
7. **Flask:** `app.run(debug=True)` reachable from a network exposes the Werkzeug debugger (code execution if the PIN is obtained). The default Flask session is a *signed, not encrypted* cookie, so don't put secrets in it. A hard-coded `secret_key` allows session forgery.
8. **Jinja2 outside Flask:** `jinja2.Environment()` has autoescape **off** by default. Use `autoescape=select_autoescape()`.
9. **`str.format` on user-supplied format strings:** `user_fmt.format(obj=some_obj)` can read attributes (`{obj.__class__.__init__.__globals__}`), which leaks secrets.
10. **`assert` for security checks** is stripped under `python -O`.

## Search patterns (ripgrep regex, also usable with the Grep tool)

```bash
rg -n --type py -e 'shell\s*=\s*True' -e 'os\.(system|popen)\(' -e '\b(eval|exec)\(' -e 'create_subprocess_shell'
rg -n --type py -e 'pickle\.loads?\(' -e 'yaml\.(unsafe_)?load\(' -e 'jsonpickle\.decode' -e 'torch\.load\(' -e 'allow_pickle\s*=\s*True' -e 'read_pickle\(' -e 'joblib\.load\('
rg -n --type py -e '\.execute\(\s*f["\x27]' -e '\.execute\([^,)]*["\x27]\s*%\s*' -e '\.execute\([^,)]*\.format\(' -e '\.raw\(\s*f["\x27]' -e '\.extra\(' -e 'RawSQL\(' -e 'text\(\s*f["\x27]'
rg -n --type py -e 'mark_safe\(' -e 'Markup\(' -e 'render_template_string\(' -e 'from_string\(' -e 'csrf_exempt' -e 'DEBUG\s*=\s*True' -e 'ALLOWED_HOSTS\s*=\s*\[\s*["\x27]\*'
rg -n --type py -e 'verify\s*=\s*False' -e 'verify_signature["\x27]?\s*:\s*False' -e '_create_unverified_context' -e 'resolve_entities\s*=\s*True' -e 'extractall\('
rg -n --type py -e '\brandom\.(random|randint|choice|choices|getrandbits|randrange)\(' -e 'hashlib\.(md5|sha1)\(' -e 'fields\s*=\s*["\x27]__all__["\x27]'
rg -n -g '*.html' -g '*.jinja*' -g '*.j2' -e '\|\s*safe\b' -e 'autoescape\s+(false|off)'
```
