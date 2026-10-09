# Ruby Sink Cheat Sheet (Rails, Sinatra)

Candidates to trace, not findings. Several Ruby and Rails defaults changed across versions, so check `.ruby-version`, `Gemfile.lock`, and `config.load_defaults` before deciding.

## Where untrusted input enters

- **Rails:** `params` (path, query, and body merged; values can be strings, arrays, or nested hashes), `request.headers`, `request.env`, `cookies` (plain cookies are client-controlled; `cookies.signed`/`encrypted` are only as safe as `secret_key_base`), `request.body`, uploaded files (`original_filename`, `content_type` are client-supplied).
- **Sinatra/Rack:** `params`, `request.env`, `env['rack.input']`.
- Also: Active Job and Sidekiq arguments originating from requests, Action Cable channel params, Active Storage blobs, webhook controllers.

## Sinks

| Category | Dangerous | Safer |
|---|---|---|
| SQL | String interpolation into `where("name = '#{x}'")`, `find_by_sql("... #{x}")`, `joins("... #{x}")`, `group`, `having`, `select(x)`, `pluck(x)`, `order(params[:sort])`, `reorder`, `from`, `lock(x)`, `exists?(params[:id])` when passed a string, `calculate`/`sum(params[:col])`, `connection.execute("... #{x}")` | Hash conditions `where(name: x)`. Placeholders `where("name = ?", x)` or named `where("name = :n", n: x)`. `sanitize_sql_array`. Allowlists for order columns and directions (`order(col => dir)` after validating both) |
| Command | `system("cmd #{x}")`, backticks, `%x()`, `exec("... #{x}")`, `IO.popen(string)`, `Open3.capture2/popen3(string)`, `spawn(string)`. `Kernel#open("\|cmd")` and `URI.open("\|cmd")` (deprecated in 3.3, removed in Ruby 4.0) | Multi-argument forms: `system("git", "log", "--", x)`, `Open3.capture2("prog", arg)`, `IO.popen(["prog", arg])` |
| Code eval and reflection | `eval`, `instance_eval(str)`, `class_eval(str)`, `send(params[:m])` / `public_send(params[:m])`, `params[:type].constantize` / `safe_constantize` / `Object.const_get(user)` (instantiates arbitrary classes) | An explicit allowlist hash mapping input to a method or class |
| Templates and rendering | `render inline: params[:x]`, `ERB.new(user).result`, `render params[:view]`, `render file: params[:path]`, `render template: user` | Fixed templates and partial names (map through an allowlist) |
| XSS | `raw(x)`, `x.html_safe`, `<%== x %>`, `content_tag(:div, x.html_safe)`, `link_to "x", params[:url]` (a `javascript:` URL), `sanitize(x, tags: ..., attributes: ...)` with permissive lists, `render html: x.html_safe` | Default ERB escaping `<%= %>`. `sanitize` with conservative defaults. URL scheme allowlist |
| Deserialization | `Marshal.load` on untrusted data. `YAML.load` on Psych below 4 (Ruby below 3.1), and `YAML.unsafe_load` anywhere. `Oj.load` in `:object` mode. `JSON.load` (it has historically enabled object-creating "additions"). Cookie serializer `:marshal` with a leaked `secret_key_base` | `JSON.parse`. `YAML.safe_load(s, permitted_classes: [...])` (`YAML.load` is the safe variant on Psych 4+). Cookie serializer `:json` |
| XML | Nokogiri with `NOENT`/`DTDLOAD` options (`Nokogiri::XML(x) { \|c\| c.noent }`). REXML on old versions (entity expansion DoS) | Nokogiri defaults (`nonet`, no entity substitution). Keep gems current |
| Paths and files | `File.read(Rails.root.join("files", params[:name]))` (`Pathname#join` with an absolute argument discards the base; `..` escapes), `send_file(params[:path])`, `File.open(user)`. Active Storage blobs served inline with user-supplied content types | `File.basename`. `File.expand_path(name, base)` then `start_with?(base + File::SEPARATOR)`. Generated names. `disposition: :attachment` |
| SSRF | `Net::HTTP.get(URI(params[:url]))`, Faraday/HTTParty with user URLs, `URI.open(user)` (open-uri hands any string that doesn't look like `scheme://...` to `Kernel#open`, so it becomes a local file read) | Scheme allowlist. Resolve once, check the addresses, then pin the connection to the checked IP with `Net::HTTP#ipaddr=` (or the `ipaddr:` option to `Net::HTTP.start`), which keeps the hostname for `Host` and TLS; or route through an egress proxy that enforces the policy. Checking `Resolv.getaddresses` and then letting the client resolve again is not a fix. Redirects off or re-validated, timeouts |
| Open redirect | `redirect_to params[:url]`, `redirect_to user, allow_other_host: true`, `redirect_back` with an untrusted fallback | Rails 7+ `raise_on_open_redirects` (on for *new* apps; upgraded apps must opt in). `redirect_to url_from(params[:url]) \|\| root_path` |
| Regex validation | `^` and `$` in validations (they match at *line* boundaries, so `"evil\nvalid"` passes) | `\A` and `\z`. Rails format validators reject multiline anchors unless `multiline: true` |
| Randomness | `rand`, `Random.new` for tokens | `SecureRandom.hex`, `SecureRandom.urlsafe_base64`, `has_secure_token` |
| Hashing / comparison | `Digest::MD5/SHA1/SHA256` for passwords, `==` on tokens or digests | `has_secure_password` (bcrypt), `ActiveSupport::SecurityUtils.secure_compare`, `Rack::Utils.secure_compare` |
| TLS | `verify_mode = OpenSSL::SSL::VERIFY_NONE`, Faraday `ssl: { verify: false }` | Defaults |
| ReDoS | User-supplied patterns, nested quantifiers on request data | Ruby 3.2+ `Regexp.timeout`, length limits |

## Framework gotchas

1. **IDOR:** `Post.find(params[:id])` instead of `current_user.posts.find(params[:id])`, or a policy (`authorize @post` with Pundit, `load_and_authorize_resource` with CanCanCan). With Pundit, `after_action :verify_authorized` catches actions that forgot to authorize. Check that it isn't skipped.
2. **Strong parameters:** `params.permit!`, `params.to_unsafe_h`, or `permit(:role, :admin, :account_id)` on self-service endpoints. Nested attributes (`accepts_nested_attributes_for`) can reach associated records the user shouldn't edit.
3. **Skipped filters:** `skip_before_action :authenticate_user!` or `skip_before_action :verify_authenticity_token` broader than intended (the `only:`/`except:` lists). Controllers that inherit from a base class without auth.
4. **CSRF:** `protect_from_forgery with: :null_session` on cookie-authenticated APIs. Routes declared `via: :all` or `match` that accept GET for state changes.
5. **Secrets:** `secret_key_base`, `config/master.key`, or credentials keys committed. A leaked `secret_key_base` lets an attacker forge signed and encrypted cookies (and becomes code execution with the `:marshal` cookie serializer).
6. **Mass-assignment-adjacent:** `update(params[:user].to_unsafe_h)` in admin namespaces reachable by lower roles.
7. **Brakeman** (see `tooling.md`) covers most of the sinks above and is the fastest way to get Rails-specific leads.

## Search patterns (ripgrep regex, also usable with the Grep tool)

```bash
rg -n --type ruby -e '(where|having|joins|group|order|reorder|pluck|select|from|find_by_sql|execute|exists\?)\(\s*["\x27%][^)]*#\{' -e '\.(order|reorder|pluck|select|group)\(\s*params'
rg -n --type ruby -e '\bsystem\(\s*["\x27][^)]*#\{' -e '`[^`]*#\{' -e '%x[\(\{\[]' -e '\bexec\(\s*["\x27][^)]*#\{' -e 'IO\.popen\(\s*["\x27]' -e 'Open3\.\w+\(\s*["\x27][^)]*#\{' -e '\bopen\(\s*["\x27]\|'
rg -n --type ruby -e '\beval\(' -e '(instance|class|module)_eval\(\s*[^{]' -e '\b(public_)?send\(\s*params' -e '(safe_)?constantize' -e 'const_get\(' -e 'render\s*\(?\s*(inline|file|template):' -e 'render\s*\(?\s*params'
rg -n --type ruby -e 'Marshal\.load' -e 'YAML\.(unsafe_)?load\(' -e 'JSON\.load\(' -e 'Oj\.load\(' -e 'permit!' -e 'to_unsafe_h' -e 'allow_other_host:\s*true' -e 'redirect_to\s*\(?\s*params'
rg -n --type ruby -e 'html_safe' -e '\braw\(' -e 'VERIFY_NONE' -e 'verify:\s*false' -e 'skip_before_action\s+:(verify_authenticity_token|authenticate)' -e 'null_session' -e 'validates.*format.*/\^'
rg -n -g '*.erb' -g '*.haml' -g '*.slim' -e '<%==' -e '\braw\b' -e 'html_safe'
```
