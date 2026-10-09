# C# / .NET Sink Cheat Sheet (ASP.NET Core, EF Core, Blazor)

Candidates to trace, not findings. Check the target framework (`<TargetFramework>` in `*.csproj`) and package versions. Several defaults differ between .NET Framework and modern .NET.

## Where untrusted input enters

- **ASP.NET Core MVC / Web API / Minimal APIs:** `[FromQuery]`, `[FromRoute]`, `[FromBody]`, `[FromForm]`, `[FromHeader]`, implicitly bound action parameters and complex types (bound from several sources), `HttpContext.Request.*`, `IFormFile` (`FileName` and `ContentType` are client-supplied).
- **Blazor:** component parameters from query strings (`[SupplyParameterFromQuery]`), JS interop return values. In Blazor Server and WebAssembly, any `[Parameter]` can be influenced by the caller of the component.
- **Other:** SignalR hub method arguments, gRPC messages, queue consumers (`IHostedService` workers), Azure Functions-style triggers.

## Sinks

| Category | Dangerous | Safer |
|---|---|---|
| SQL | `new SqlCommand("..." + x)`, `$"... {x}"` passed as command text. EF Core `FromSqlRaw($"... {x}")` / `ExecuteSqlRaw($"... {x}")` (the interpolation runs before EF sees it). Dapper `conn.Query("..." + x)`. Dynamic LINQ string expressions built from input | `SqlParameter`s. EF Core `FromSql($"... {x}")` / `ExecuteSql($"...")` (EF Core 7+) or `FromSqlInterpolated`, which turn interpolations into parameters. `FromSqlRaw("... {0}", x)` with positional params. Dapper anonymous params `new { id }`. LINQ query operators. Allowlists for sort columns |
| Command | `Process.Start("cmd.exe", "/c " + x)`, `ProcessStartInfo { FileName = "bash", Arguments = "-c ..." }`, `ProcessStartInfo.Arguments` built by concatenation (argument injection even without a shell). `UseShellExecute = true` with a user-chosen file | `ProcessStartInfo.ArgumentList.Add(arg)` (each argument escaped separately). A fixed `FileName`. `UseShellExecute = false` |
| Deserialization | `BinaryFormatter` (its implementation was removed in .NET 9 and throws unless the unsupported compatibility package is added, so flag any use or package reference), `SoapFormatter`, `NetDataContractSerializer`, `LosFormatter`, `ObjectStateFormatter`. `JavaScriptSerializer` with a type resolver. Newtonsoft.Json `TypeNameHandling` other than `None` without a strict `ISerializationBinder`. `new XmlSerializer(Type.GetType(userInput))`. `DataContractSerializer` with known types taken from input | System.Text.Json into concrete DTOs. Polymorphism only through `[JsonDerivedType]` discriminators (opt-in, closed set). Newtonsoft `TypeNameHandling.None`, or an allowlist binder |
| XXE | `XmlDocument` with `XmlResolver = new XmlUrlResolver()`. `XmlReaderSettings { DtdProcessing = DtdProcessing.Parse }` with a non-null resolver. `XmlTextReader` or `XmlDocument` on old .NET Framework versions (before 4.5.2, defaults resolved DTDs) | Modern .NET defaults (DTDs prohibited and no resolver). `DtdProcessing.Prohibit`, `XmlResolver = null` set explicitly in code that may run on .NET Framework |
| XSS | Razor `@Html.Raw(x)`, `new HtmlString(x)`, Blazor `(MarkupString)userHtml`, `Content(userHtml, "text/html")`, building HTML in tag helpers with string concatenation | Razor `@x` (encoded). A sanitizer library for rich HTML. URL scheme allowlist on `href` |
| Paths and uploads | `Path.Combine(baseDir, user)` (a rooted `user` discards `baseDir`; `..` escapes). `File.ReadAllBytes/OpenRead/Delete` with user paths. `PhysicalFile(user, ...)`. `IFormFile.FileName` used as the storage name. Manual `ZipArchive.Entries` loops writing to `Path.Combine(dest, entry.FullName)` | `Path.GetRandomFileName()`, or generated IDs. `var full = Path.GetFullPath(Path.Combine(baseDir, name));` then check `full.StartsWith(Path.GetFullPath(baseDir) + Path.DirectorySeparatorChar, StringComparison.Ordinal)` (`OrdinalIgnoreCase` on Windows). Per-entry checks when extracting |
| SSRF | `HttpClient.GetAsync(userUrl)`. An `HttpClient` with `BaseAddress` where a user-supplied *absolute* URI overrides the base. `WebRequest.Create(userUrl)` (also supports `file://`) | Destination allowlist. A `SocketsHttpHandler.ConnectCallback` that validates the resolved IP. `AllowAutoRedirect = false` or re-validation. Timeouts |
| Open redirect | `Redirect(returnUrl)`, `Results.Redirect(user)` | `LocalRedirect(returnUrl)`, or `if (Url.IsLocalUrl(returnUrl))` |
| LDAP | `DirectorySearcher.Filter = "(uid=" + user + ")"` | Escape filter values (RFC 4515 escaping) and validate the format |
| Randomness | `new Random()`, `Random.Shared`, `Guid.NewGuid()` treated as a secret token | `RandomNumberGenerator.GetBytes(32)`, `RandomNumberGenerator.GetInt32(...)` |
| Hashing / crypto | `MD5`/`SHA1`/`SHA256.HashData(password)`. `Aes` with `Mode = CipherMode.ECB`. A static IV. `Rfc2898DeriveBytes` with SHA1 or a low iteration count | ASP.NET Core Identity `PasswordHasher<T>` (PBKDF2-HMAC-SHA512, 100,000 iterations by default since .NET 7; OWASP currently recommends 220,000 for PBKDF2-HMAC-SHA512, so raise `PasswordHasherOptions.IterationCount`) or an Argon2id library. `AesGcm` with a unique nonce per message |
| Comparison | `==`, `SequenceEqual`, `string.Equals` on MACs or tokens | `CryptographicOperations.FixedTimeEquals` |
| TLS | `ServerCertificateCustomValidationCallback = (_, _, _, _) => true`, `HttpClientHandler.DangerousAcceptAnyServerCertificateValidator`, `ServicePointManager.ServerCertificateValidationCallback` returning `true` | Default validation. A custom CA chain check |
| JWT | `TokenValidationParameters` with `ValidateIssuer = false`, `ValidateAudience = false`, `ValidateLifetime = false`, `ValidateIssuerSigningKey = false`, or `RequireSignedTokens = false`. A custom `SignatureValidator` that skips checks. `IssuerSigningKeyResolver` trusting a `kid` to fetch keys from arbitrary locations. Very large `ClockSkew` | Validate issuer, audience, lifetime, and signing key. Keys from configuration or the IdP's metadata. A `ValidAlgorithms` list |

## Framework gotchas

1. **Authorization defaults:** without a fallback policy, endpoints are anonymous unless they carry `[Authorize]` or `.RequireAuthorization()`. Look for `options.FallbackPolicy = new AuthorizationPolicyBuilder().RequireAuthenticatedUser().Build()`. `[AllowAnonymous]` overrides every `[Authorize]` on the endpoint, including controller-level ones.
2. **Resource-based authorization:** role attributes don't check *which* record. Look for `IAuthorizationService.AuthorizeAsync(User, resource, requirement)` or owner/tenant predicates in queries. EF Core global query filters (often used for tenancy or soft delete) are bypassed by `IgnoreQueryFilters()` and by raw SQL.
3. **Overposting (mass assignment):** binding `[FromBody] User user` then `_db.Update(user)` writes every property, including `Role` and `IsAdmin`. Use input DTOs, `[Bind("Name,Email")]` in MVC, or `TryUpdateModelAsync` with an include list.
4. **Antiforgery:** MVC POST actions using cookie auth need `[ValidateAntiForgeryToken]` or a global `AutoValidateAntiforgeryTokenAttribute`. Watch for `[IgnoreAntiforgeryToken]`. Minimal APIs that bind forms enforce antiforgery when `app.UseAntiforgery()` is configured (.NET 8+). `.DisableAntiforgery()` turns it off.
5. **CORS:** `AllowAnyOrigin()` combined with `AllowCredentials()` is rejected by the framework, so the risky form is `SetIsOriginAllowed(_ => true).AllowCredentials()`, or origin checks done with `Contains`/`EndsWith`.
6. **Error details:** `app.UseDeveloperExceptionPage()` or `ASPNETCORE_ENVIRONMENT=Development` in production. `ProblemDetails` that include exception messages.
7. **Secrets:** connection strings and keys in `appsettings*.json` committed to the repo. Use user-secrets for development and a vault or environment for production. Data Protection keys that aren't persisted or protected in multi-instance deployments (cookies break, or keys end up stored unencrypted).
8. **Fail-open catches:** `catch { return true; }` or `catch (Exception) { /* ignore */ }` around authorization handlers, signature checks, or license checks (A10).

## Search patterns (ripgrep regex, also usable with the Grep tool)

```bash
rg -n --type cs -e 'new SqlCommand\(\s*(\$"|"[^"]*"\s*\+)' -e '(FromSqlRaw|ExecuteSqlRaw|ExecuteSqlRawAsync)\(\s*(\$"|[^"(]*\+)' -e '\.Query(Async)?(<[^>]*>)?\(\s*(\$"|"[^"]*"\s*\+)'
rg -n --type cs -e 'Process\.Start\(' -e 'UseShellExecute\s*=\s*true' -e '\.Arguments\s*=' -e 'Filter\s*=\s*"[^"]*"\s*\+'
rg -n --type cs -e 'BinaryFormatter' -e 'SoapFormatter' -e 'NetDataContractSerializer' -e 'LosFormatter' -e 'ObjectStateFormatter' -e 'TypeNameHandling\.(All|Auto|Objects|Arrays)' -e 'Type\.GetType\(' -e 'DtdProcessing\.Parse' -e 'XmlUrlResolver'
rg -n --type cs -e 'Html\.Raw\(' -e 'new HtmlString\(' -e '\(MarkupString\)' -e '\bRedirect\(' -e 'Path\.Combine\(' -e '\.FileName\b'
rg -n --type cs -e 'new Random\(' -e 'Random\.Shared' -e '(MD5|SHA1)\.(Create|HashData)' -e 'CipherMode\.ECB' -e 'DangerousAcceptAnyServerCertificateValidator' -e 'ServerCertificateCustomValidationCallback' -e 'Validate(Issuer|Audience|Lifetime|IssuerSigningKey)\s*=\s*false' -e 'RequireSignedTokens\s*=\s*false'
rg -n --type cs -e '\[AllowAnonymous\]' -e 'IgnoreAntiforgeryToken' -e 'DisableAntiforgery' -e 'IgnoreQueryFilters' -e 'SetIsOriginAllowed' -e 'UseDeveloperExceptionPage' -e 'catch\s*(\(\s*Exception[^)]*\))?\s*\{\s*return\s+true'
rg -n -g '*.cshtml' -g '*.razor' -e 'Html\.Raw' -e 'MarkupString'
```
