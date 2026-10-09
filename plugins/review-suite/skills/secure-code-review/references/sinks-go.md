# Go Sink Cheat Sheet (net/http, Gin, Echo, chi, gRPC)

Candidates to trace, not findings. Check the module's `go` directive and dependency versions before relying on a version-dependent API noted here.

## Where untrusted input enters

- **net/http:** `r.URL.Query()`, `r.FormValue`, `r.PostFormValue`, `r.PathValue` (Go 1.22+ patterns), `r.Header`, `r.Cookie`, `r.Body` (JSON decoders), `r.MultipartForm` (the `FileHeader.Filename` and `Header` fields are client-supplied), `r.Host`.
- **Frameworks:** Gin `c.Query/Param/PostForm/ShouldBind*`, Echo `c.QueryParam/Param/Bind`, chi `chi.URLParam`, gorilla `mux.Vars`.
- **gRPC:** every request message field, plus metadata.
- Also: queue consumers, CLI flags in privileged tools, files read from shared storage.

## Sinks

| Category | Dangerous | Safer |
|---|---|---|
| SQL | `db.Query(fmt.Sprintf("... %s", x))`, `"..." + x` into `Query/Exec/QueryRow`. GORM `db.Where(fmt.Sprintf(...))`, `db.Raw(fmt.Sprintf(...))`, `db.Exec(str)`, and `db.Where(userString)` / `Order(userString)` / `Select(userString)` / `Group(userString)`, where GORM treats the string as SQL. `sqlx` with formatted strings | Placeholders with args: `db.Query("... WHERE id = $1", id)` (`$1` for PostgreSQL drivers, `?` for MySQL/SQLite). GORM `db.Where("name = ?", x)`. Allowlist maps for sort columns and directions |
| Command | `exec.Command("sh", "-c", userCmd)`, `exec.Command("bash", "-c", ...)`, `exec.Command(userProgram, ...)`. Option injection via `-`-prefixed args | `exec.Command(fixedProg, "--", arg)` with no shell. An allowlisted program |
| Templates / XSS | `text/template` used to render HTML (no escaping). `html/template` bypassed by casting input to `template.HTML`, `template.JS`, `template.URL`, `template.HTMLAttr`, `template.CSS`. Parsing user-supplied template text (`template.New("").Parse(user)`) exposes methods of the data passed in. `w.Write([]byte(userHTML))` with an HTML content type | `html/template` with plain string data. Cast to `template.HTML` only for sanitized or constant content. Fixed templates |
| Paths | `os.Open(filepath.Join(base, user))` (`Join` cleans `..` but the result can still escape `base`). `http.ServeFile(w, r, userPath)`. `archive/zip` and `archive/tar` entry names joined to a destination (zip slip). `http.FileServer(http.Dir(dir))` follows symlinks that already exist inside `dir` | `os.OpenInRoot(dir, name)` or `root, _ := os.OpenRoot(dir); root.Open(name)` (Go 1.24+; more methods such as `ReadFile`/`WriteFile`/`MkdirAll` arrived in 1.25). `filepath.IsLocal(name)` (1.20+) before joining. Per-entry checks during extraction |
| SSRF | `http.Get(userURL)`, `http.NewRequest(m, userURL, ...)` with `http.DefaultClient` (follows up to 10 redirects, no timeout) | A client with `Timeout`, a `CheckRedirect` that rejects or re-validates, and a `net.Dialer{Control: ...}` that checks the *resolved* IP at connect time (defeats DNS rebinding) |
| Open redirect | `http.Redirect(w, r, r.URL.Query().Get("next"), http.StatusFound)` | Relative-path allowlist: parse with `url.Parse`, require an empty scheme and host, reject a leading `//` or `/\` |
| Deserialization | Mostly a DoS and type-confusion risk rather than code execution. `encoding/gob` from untrusted peers. Unbounded `json.NewDecoder(r.Body)` | `http.MaxBytesReader`. Decode into concrete structs. `dec.DisallowUnknownFields()` where strictness helps |
| XML | `encoding/xml` doesn't process external entities or DTDs, so XXE needs a cgo libxml2 binding. Watch for those | Stay on `encoding/xml`. Bound the input size |
| Randomness | `math/rand` or `math/rand/v2` for tokens, OTPs, nonces, or IDs used as secrets | `crypto/rand`: `rand.Read(b)` (can't fail since Go 1.24) or `rand.Text()` (Go 1.24+, at least 128 bits) |
| Crypto | `md5`/`sha1`/`sha256` of passwords. `cipher.NewCBCEncrypter` without a MAC. A reused nonce with `cipher.NewGCM`. Hard-coded keys | `golang.org/x/crypto/argon2` (`IDKey`) or `golang.org/x/crypto/bcrypt`. `cipher.NewGCM` with a fresh nonce from `crypto/rand` per message |
| Comparison | `==`, `bytes.Equal`, `reflect.DeepEqual` on MACs or tokens | `hmac.Equal`, `subtle.ConstantTimeCompare` |
| TLS | `tls.Config{InsecureSkipVerify: true}` | Default verification. `RootCAs` for private CAs |
| JWT (golang-jwt) | `jwt.Parse(t, keyFunc)` where `keyFunc` doesn't check `t.Method`. `ParseUnverified` used for authorization decisions. No `exp`/`aud`/`iss` validation | `jwt.Parse(t, keyFunc, jwt.WithValidMethods([]string{"RS256"}), jwt.WithAudience(..), jwt.WithIssuer(..))` (v5 parser options) |
| Integer handling | `strconv.Atoi` followed by narrowing (`int32(n)`, `uint(n)`) in size, offset, or limit checks. Negative values passed where unsigned is expected | Parse with explicit bit sizes (`strconv.ParseUint(s, 10, 32)`) and range-check before converting |

## Go-specific gotchas

1. **Ignored errors in security paths (fail-open, A10):** `claims, _ := parse(token)` followed by use of `claims`. `if err != nil { log.Println(err) }` that falls through to the allowed branch. `_ = tx.Rollback()` after a partial write.
2. **No server timeouts:** `http.ListenAndServe(addr, h)` uses a server without `ReadHeaderTimeout`/`ReadTimeout`, which allows slow-request DoS. Construct `http.Server` with timeouts.
3. **Shared state across goroutines:** handlers writing to package-level maps without locks cause data races, which crash the process (DoS) or mix users' data. A per-request value stored in a global struct field is a cross-user leak.
4. **Context-derived identity:** values put into `context.Context` by auth middleware read back with an unchecked type assertion (`ctx.Value(userKey).(*User)`). A missing middleware on a route yields a nil user, which may panic or, worse, take a permissive default branch.
5. **Binding request JSON straight into DB models** (`json.Decode(&user)` then `db.Save(&user)`) is mass assignment. Fields like `Role`, `IsAdmin`, `OrgID` need `json:"-"` or a separate input struct.
6. **gRPC auth:** interceptors registered for unary but not streaming calls (or the reverse). Reflection or admin services exposed on the public listener.
7. **CORS (rs/cors and similar):** `AllowOriginFunc` returning `true` together with `AllowCredentials: true`.

## Search patterns (ripgrep regex, also usable with the Grep tool)

```bash
rg -n --type go -e 'fmt\.Sprintf\([^)]*(SELECT|INSERT|UPDATE|DELETE|WHERE|ORDER BY)' -e '\.(Query|QueryRow|Exec|QueryContext|ExecContext)\([^,)]*\+' -e '\.Raw\(\s*fmt\.Sprintf' -e '\.(Where|Order|Select|Group)\(\s*fmt\.Sprintf'
rg -n --type go -e 'exec\.Command(Context)?\(\s*"(sh|bash|cmd|cmd\.exe|powershell)"' -e 'exec\.Command(Context)?\(\s*[a-z]\w*\s*[,)]'
rg -n --type go -e '"text/template"' -e 'template\.(HTML|JS|URL|HTMLAttr|CSS)\(' -e '\.Parse\(\s*[a-z]\w*\s*\)'
rg -n --type go -e 'filepath\.Join\([^)]*(r\.|req\.|c\.(Param|Query))' -e 'http\.ServeFile\(' -e 'archive/(zip|tar)' -e 'http\.Redirect\('
rg -n --type go -e '"math/rand(/v2)?"' -e 'InsecureSkipVerify\s*:\s*true' -e 'ParseUnverified' -e 'jwt\.Parse\(' -e 'crypto/(md5|sha1)"' -e 'http\.ListenAndServe(TLS)?\('
rg -n --type go -e 'http\.(Get|Post|Head)\(' -e 'http\.DefaultClient' -e 'AllowOriginFunc' -e ',\s*_\s*:?=\s*[\w.]*(Parse|Verify|Validate|Authoriz)\w*\('
```
