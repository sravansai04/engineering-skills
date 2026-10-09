# OWASP and CWE Mapping

Use this when tagging findings or reporting OWASP coverage. Tag each finding with the most specific CWE you can defend, then the OWASP category that contains it. When a CWE isn't in a category's official mapping (several injection CWEs, for example), tag the closest category by name and don't invent an official mapping.

Editions verified for this skill: **OWASP Top 10:2025** (final, the 8th edition), **OWASP API Security Top 10:2023** (still the current API edition; no newer one had been published when this was written), and **OWASP Top 10 for LLM Applications 2025**. Check owasp.org before quoting them as "current" in a long-lived document.

## OWASP Top 10:2025 (web applications)

| ID | Category | What it covers | Checklist section(s) |
|---|---|---|---|
| A01:2025 | Broken Access Control | IDOR/BOLA, missing or incorrect authorization, privilege escalation, CSRF, path traversal, open redirects, and (since 2025) **SSRF** | §2, §5, §6, §8, §9 |
| A02:2025 | Security Misconfiguration | Insecure defaults, debug and verbose errors, permissive CORS, cookie flags, **XXE** (parser config) | §7 (XXE), §9 (CORS), §17 |
| A03:2025 | Software Supply Chain Failures | Vulnerable, unmaintained, or untrustworthy components. Build systems and distribution infrastructure (expanded from 2021's "Vulnerable and Outdated Components") | §18 |
| A04:2025 | Cryptographic Failures | Weak algorithms and modes, bad randomness, weak password hashing, key management, improper signature verification | §12, §13 (JWT, SAML), §20 |
| A05:2025 | Injection | SQL, OS command, argument, LDAP, XPath, expression language, code injection, **XSS**, header injection | §3, §4 |
| A06:2025 | Insecure Design | Missing threat modeling and controls by design. Race conditions, workflow enforcement, unrestricted file upload, clickjacking, improper privilege management (CWE-269), trust-boundary violations | §2 (privilege escalation), §6 (uploads), §9 (framing), §14 |
| A07:2025 | Authentication Failures | Weak authentication, brute force, spoofing, replay, session fixation and expiry, weak recovery, hard-coded credentials, certificate validation | §1, §11, §12 (TLS), §13, §20 (replay) |
| A08:2025 | Software or Data Integrity Failures | **Unsafe deserialization**, mass assignment, untrusted code inclusion, downloads without integrity checks, insufficient verification of data authenticity | §7, §10, §18, §20 |
| A09:2025 | Security Logging and Alerting Failures | Insufficient logging and alerting of security events, sensitive data in logs, log injection | §3 (log injection), §11 |
| A10:2025 | Mishandling of Exceptional Conditions | Fail-open logic, unchecked return values, error messages exposing sensitive data, unhandled exceptions (new in 2025) | §15 |

Changes from 2021 worth knowing when older reports or tools use the old IDs: SSRF (2021-A10) merged into A01. "Vulnerable and Outdated Components" became A03 Software Supply Chain Failures. Security Misconfiguration rose to A02. Injection fell to A05. A10 Mishandling of Exceptional Conditions is new. A07 was renamed from "Identification and Authentication Failures", and A09 now emphasizes alerting.

## OWASP API Security Top 10:2023

| ID | Risk | Review question | Checklist |
|---|---|---|---|
| API1:2023 | Broken Object Level Authorization | Does every object lookup by ID check the caller's access to *that* object? | §2 |
| API2:2023 | Broken Authentication | Are tokens, credentials, and auth flows sound and throttled? | §1, §13 |
| API3:2023 | Broken Object Property Level Authorization | Can callers read or write fields they shouldn't (excessive exposure, mass assignment)? | §2, §10 |
| API4:2023 | Unrestricted Resource Consumption | Are sizes, rates, costs, and timeouts bounded? | §16 |
| API5:2023 | Broken Function Level Authorization | Are privileged operations role-checked on the server? | §2 |
| API6:2023 | Unrestricted Access to Sensitive Business Flows | Can a flow (purchase, signup, booking, messaging) be automated or abused at scale? | §14 |
| API7:2023 | Server Side Request Forgery | Can the caller steer server-side fetches? | §5 |
| API8:2023 | Security Misconfiguration | Headers, CORS, verbose errors, unpatched systems, unnecessary features | §9, §17 |
| API9:2023 | Improper Inventory Management | Are old versions, debug, or undocumented endpoints still exposed? | §17 |
| API10:2023 | Unsafe Consumption of APIs | Is data from third-party APIs validated and treated as untrusted (including injection via their responses)? | §3, §5, §18 |

Injection and logging aren't separate items in the 2023 API list. Injection through third-party data falls under API10. Tag API injection findings with A05:2025 as well.

## OWASP Top 10 for LLM Applications 2025

The items most relevant to code review: LLM01 Prompt Injection, LLM02 Sensitive Information Disclosure, LLM05 Improper Output Handling, LLM06 Excessive Agency, LLM07 System Prompt Leakage, LLM10 Unbounded Consumption. See checklist §19.

## Common CWE quick reference

| Weakness | CWE | OWASP 2025 |
|---|---|---|
| IDOR / user-controlled key | CWE-639 | A01 |
| Missing authorization | CWE-862 | A01 |
| Incorrect authorization | CWE-863 | A01 |
| Improper privilege management | CWE-269 | A06 (prefer CWE-862/863/639 under A01 when a check is missing or wrong) |
| SSRF | CWE-918 | A01 |
| Path traversal | CWE-22 | A01 |
| Open redirect | CWE-601 | A01 |
| CSRF | CWE-352 | A01 |
| Missing origin validation in WebSockets | CWE-1385 | closest: A01 (with CSRF) |
| Exposure of sensitive information | CWE-200 | A01 |
| XXE | CWE-611 | A02 |
| Permissive CORS | CWE-942 | A02 |
| Cookie without Secure / HttpOnly | CWE-614 / CWE-1004 | A02 |
| Dependency on vulnerable component | CWE-1395 | A03 |
| Broken or risky crypto algorithm | CWE-327 | A04 |
| Weak PRNG | CWE-338 | A04 |
| Weak password hash (insufficient effort) | CWE-916 | A04 |
| Improper signature verification | CWE-347 | A04 |
| Insufficient verification of data authenticity | CWE-345 | A08 |
| SQL injection | CWE-89 | A05 |
| OS command injection / argument injection | CWE-78 / CWE-88 | A05 |
| XSS | CWE-79 | A05 |
| LDAP / XPath injection | CWE-90 / CWE-643 | A05 |
| Expression language injection | CWE-917 | A05 |
| Code injection | CWE-94 | A05 |
| HTTP response splitting | CWE-113 | A05 |
| Template injection (SSTI) | CWE-1336 | closest: A05 |
| NoSQL injection | CWE-943 | closest: A05 |
| Prototype pollution | CWE-1321 | closest: A08 or A05, by impact |
| Unrestricted file upload | CWE-434 | A06 |
| Race condition | CWE-362 | A06 |
| Workflow not enforced | CWE-841 | A06 |
| Clickjacking | CWE-1021 | A06 |
| Improper authentication | CWE-287 | A07 |
| Brute force not restricted | CWE-307 | A07 |
| Authentication bypass by spoofing | CWE-290 | A07 |
| Capture-replay | CWE-294 | A07 |
| Spoofable client IP used for a security decision | CWE-348 | closest: A07 |
| Session fixation / expiration | CWE-384 / CWE-613 | A07 |
| Hard-coded credentials | CWE-798 | A07 |
| Certificate validation | CWE-295 | A07 |
| Unsafe deserialization | CWE-502 | A08 |
| Mass assignment | CWE-915 | A08 |
| Download without integrity check | CWE-494 | A08 |
| Sensitive data in logs | CWE-532 | A09 |
| Log injection | CWE-117 | A09 |
| Error message information leak | CWE-209 | A10 |
| Failing open | CWE-636 | A10 |
| Unchecked return value | CWE-252 | A10 |
| Wildcard injection in `LIKE` | CWE-155 | closest: A05 |
| ReDoS | CWE-1333 | API4 (no 2025 web category) |
| Uncontrolled resource consumption | CWE-400 / CWE-770 | API4 (no 2025 web category) |
| Memory safety (out-of-bounds write/read, use after free, format string, size overflow) | CWE-787 / CWE-125 / CWE-416 / CWE-134 / CWE-190 | none (no 2025 web category; tag the CWE alone) |
