# Java / Kotlin Sink Cheat Sheet (Spring, Jakarta EE)

Candidates to trace, not findings. Kotlin uses the same libraries and sinks. Check the project's pinned library versions before relying on any version-dependent default noted here.

## Where untrusted input enters

- **Spring MVC/WebFlux:** `@RequestParam`, `@PathVariable`, `@RequestBody`, `@RequestHeader`, `@CookieValue`, `@ModelAttribute` (binds *every* matching request parameter onto the object), `MultipartFile` (`getOriginalFilename()` and `getContentType()` are client-supplied).
- **Servlet / Jakarta EE:** `HttpServletRequest.getParameter/getHeader/getInputStream/getPathInfo/getQueryString`, JAX-RS `@QueryParam`/`@PathParam`/`@FormParam`/`@HeaderParam`.
- Message listeners (`@KafkaListener`, `@RabbitListener`, `@JmsListener`), scheduled jobs reading external data, and files from object storage.

## Sinks

| Category | Dangerous | Safer |
|---|---|---|
| SQL | `Statement.executeQuery("..." + x)`, `jdbcTemplate.query("..." + x, ...)`, `em.createQuery("... " + x)` (JPQL/HQL injection), `createNativeQuery` with concatenation. MyBatis `${x}` (text substitution). `JpaSort.unsafe(user)` | `PreparedStatement` with `?`. `jdbcTemplate.query(sql, rowMapper, args...)`. `NamedParameterJdbcTemplate`. `setParameter`. MyBatis `#{x}` (bound). Criteria API. Allowlists for sort and column names |
| Command | `Runtime.getRuntime().exec(cmdString)` (tokenized on whitespace, no shell, but injection via a user-chosen program or `sh -c`). `new ProcessBuilder("sh", "-c", cmd)`, `cmd.exe /c` | `new ProcessBuilder(List.of(prog, "--", arg))`. An allowlisted program |
| Expression languages | SpEL `parser.parseExpression(user).getValue(new StandardEvaluationContext())`, OGNL, MVEL, JEXL, `ELProcessor.eval(user)`, `@Value`-style resolution of user strings | Don't evaluate input. If unavoidable, SpEL `SimpleEvaluationContext.forReadOnlyDataBinding()` |
| Template injection / XSS | A controller returning a **view name built from input** (`return "pages/" + lang;`); with Thymeleaf this enables expression preprocessing. FreeMarker/Velocity templates compiled from user strings (FreeMarker `?new`). Thymeleaf `th:utext`. JSP `<%= request.getParameter(...) %>` and `${param.x}` outside `<c:out>`. `@ResponseBody` HTML strings built with user data | Fixed view names (map input through an allowlist). `th:text`. `<c:out>`/`fn:escapeXml`. Output-format-aware auto-escaping in FreeMarker |
| JNDI / Log4j | `new InitialContext().lookup(user)`. Log4j 2 versions before 2.17.1 (Log4Shell family) logging user data | No user-controlled lookups. Log4j ≥ 2.17.1 (Java 8+) or the current release |
| Deserialization | `ObjectInputStream.readObject` on untrusted bytes, `XMLDecoder`, XStream without an allowlist (versions before 1.4.18 used a denylist by default). Jackson `activateDefaultTyping`/`enableDefaultTyping`, or `@JsonTypeInfo(use = Id.CLASS)` on `Object`/`Serializable`/broad base types. SnakeYAML before 2.0 `new Yaml().load(untrusted)`. Kryo without class registration. Hessian/Burlap, RMI | JSON into concrete DTOs. Jackson `Id.NAME` with registered subtypes, or a strict `PolymorphicTypeValidator`. SnakeYAML 2.x defaults (global tags blocked) or `new Yaml(new SafeConstructor(new LoaderOptions()))`. `ObjectInputFilter` allowlists (JEP 290) if native serialization can't be removed |
| XXE | `DocumentBuilderFactory`, `SAXParserFactory`, `XMLInputFactory`, `TransformerFactory`, `SchemaFactory`, `Validator`, dom4j `SAXReader`, JDOM `SAXBuilder`, `Unmarshaller` from a raw stream. JAXP factories process DTDs by default, so set the features explicitly instead of relying on the JDK version | `dbf.setFeature("http://apache.org/xml/features/disallow-doctype-decl", true)`. StAX: `XMLInputFactory.SUPPORT_DTD=false`, `IS_SUPPORTING_EXTERNAL_ENTITIES=false`. Transformer and Schema: set `XMLConstants.ACCESS_EXTERNAL_DTD` and `ACCESS_EXTERNAL_STYLESHEET`/`ACCESS_EXTERNAL_SCHEMA` to `""` |
| SSRF | `new URL(user).openConnection()` (also `file:`, `jar:`), `RestTemplate`/`WebClient`/`HttpClient`/OkHttp with a user URL, image and PDF libraries fetching remote resources | Destination allowlist. Enforce the IP check inside the client's resolver so it covers the connection actually made: an OkHttp `Dns` implementation or an Apache HttpClient 5 `DnsResolver` that drops private, loopback, link-local, and metadata addresses (or an egress proxy). Checking `InetAddress.getAllByName` first and then letting the client resolve again is not a fix. Redirects off (`followRedirects(false)`, `HttpClient.Redirect.NEVER`) or re-validated per hop. Timeouts |
| Paths | `Paths.get(base).resolve(user)` (an absolute `user` replaces `base`), `new File(base, user)` and `Paths.get(base, user)` (`..` escapes), `getOriginalFilename()` used as a storage name, `ZipInputStream` entry names joined to a target dir (zip slip) | `Path p = base.resolve(user).normalize();` then `p.startsWith(base)` on real paths (`toRealPath()` for symlinks). Generated names. Per-entry containment checks |
| Open redirect | `return "redirect:" + url;`, `response.sendRedirect(user)`, `RedirectView(user)` | Relative-path allowlist, or validated origins |
| Randomness | `java.util.Random`, `Math.random`, `ThreadLocalRandom` for tokens or IDs used as secrets | `SecureRandom` |
| Crypto | `MessageDigest.getInstance("MD5"/"SHA-1"/"SHA-256")` for passwords. `Cipher.getInstance("AES")` (resolves to ECB with the default provider). `AES/CBC` without a MAC. Reused GCM IVs. Hard-coded `SecretKeySpec` bytes | Spring Security `Argon2PasswordEncoder`/`BCryptPasswordEncoder`/`Pbkdf2PasswordEncoder` with current parameters. `AES/GCM/NoPadding` with a fresh 12-byte IV |
| Comparison | `String.equals`/`Arrays.equals` on MACs or tokens | `MessageDigest.isEqual` |
| TLS | A `TrustManager` whose `checkServerTrusted` is empty, a `HostnameVerifier` returning `true`, `SSLContext` built with trust-all managers | Default trust, or a pinned private CA |
| JWT | auth0 `JWT.decode(token)` used as verification. jjwt generic `parse(...)` / `parseClaimsJwt` (no "s"), which can accept unsigned tokens in older versions. No algorithm, issuer, or audience constraints | auth0 `JWT.require(Algorithm.RSA256(pub, null)).withIssuer(..).withAudience(..).build().verify(t)`. jjwt `Jwts.parser().verifyWith(key).build().parseSignedClaims(t)` (0.12+) or `parseClaimsJws` (older) |
| LDAP | `ctx.search(base, "(uid=" + user + ")", ...)` | Filter arguments `search(base, "(uid={0})", new Object[]{user}, ...)`, or Spring LDAP query builders |

## Framework gotchas

1. **Mass assignment:** binding `@ModelAttribute` or `@RequestBody` directly to JPA entities lets clients set `role`, `owner`, `enabled`, `id`. Use DTOs, `@InitBinder` `setAllowedFields`, or Jackson `@JsonProperty(access = READ_ONLY)` on server-owned fields.
2. **Method security silently off:** `@PreAuthorize`/`@Secured`/`@RolesAllowed` do nothing unless method security is enabled (`@EnableMethodSecurity`, or older `@EnableGlobalMethodSecurity(prePostEnabled = true)`). Proxy-based checks also don't apply to **self-invocation** (calling an annotated method from the same class).
3. **URL authorization rules:** order matters (first match wins). `permitAll()` patterns broader than intended (`/api/public/**` vs `/api/**`). Path matching differences (trailing slash, case, matrix parameters, encoded characters) have caused bypasses. Layer method-level or data-level checks under URL rules.
4. **CSRF disabled** (`csrf(c -> c.disable())`, the method-reference form `csrf(AbstractHttpConfigurer::disable)` that most Spring Security 6 code uses, or the older `csrf().disable()`) while authentication still uses session cookies.
5. **Actuator exposure:** `management.endpoints.web.exposure.include=*` on a public port exposes `heapdump` (contains secrets), `env`, `configprops`, `loggers`, `mappings`. Require auth or a separate management port.
6. **Ownership in Spring Data:** `repository.findById(id)` behind an authenticated endpoint is the classic IDOR. Look for `findByIdAndOwnerId`, a `@PostAuthorize` check, or a query filter.
7. **Verbose errors:** `server.error.include-stacktrace=always` or `include-message=always` in production config.
8. **Kotlin:** platform types from Java APIs (`String!`) can be null despite Kotlin-looking non-null code. A null security context can fall through to permissive branches (A10).

## Search patterns (ripgrep regex, also usable with the Grep tool)

```bash
rg -n --type java --type kotlin -e 'createStatement\(' -e 'executeQuery\(\s*"[^"]*"\s*\+' -e 'create(Native)?Query\(\s*"[^"]*"\s*\+' -e 'JpaSort\.unsafe' -e 'Runtime\.getRuntime\(\)\.exec' -e 'ProcessBuilder\('
rg -n -g '*.xml' -g '!pom.xml' -e '\$\{[^}]+\}'   # MyBatis ${} substitution; also matches config placeholders, so read the hits
rg -n --type java --type kotlin -e '@(Select|Update|Delete|Insert)\([^)]*\$\{'   # ${} in MyBatis annotations
rg -n --type java --type kotlin -e 'parseExpression\(' -e 'StandardEvaluationContext' -e 'InitialContext\(\)' -e '\.lookup\(' -e 'th:utext' -e '"redirect:"\s*\+' -e 'sendRedirect\('
rg -n --type java --type kotlin -e 'ObjectInputStream' -e 'readObject\(' -e 'XMLDecoder' -e 'XStream\(' -e '(activate|enable)DefaultTyping' -e 'JsonTypeInfo\.Id\.CLASS' -e 'new Yaml\('
rg -n --type java --type kotlin -e 'DocumentBuilderFactory' -e 'SAXParserFactory' -e 'XMLInputFactory' -e 'TransformerFactory' -e 'SchemaFactory' -e 'SAXReader' -e 'SAXBuilder'
rg -n --type java --type kotlin -e 'new Random\(' -e 'Math\.random\(' -e 'getInstance\(\s*"(MD5|SHA-?1|AES|DES)"' -e 'checkServerTrusted' -e 'HostnameVerifier' -e 'JWT\.decode\(' -e 'parseClaimsJwt\('
rg -n -g '*.java' -g '*.kt' -g '*.properties' -g '*.yml' -g '*.yaml' -e 'csrf\(\)?\.disable|csrf\s*\(\s*\w+\s*->\s*\w+\.disable' -e 'csrf\(\s*\w*::disable' -e 'permitAll\(\)' -e 'exposure\.include\s*[:=]\s*["\x27]?\*' -e 'include-stacktrace'
```
