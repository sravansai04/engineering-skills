# Scanners and Audit Commands

Scanners find candidates fast and miss whole classes of bugs, authorization above all. Use them to generate leads for Step 5, then validate every hit with Step 6. Never paste raw scanner output into the report.

## 1. Use the project's own setup first

Before reaching for a generic tool, find what the team already runs. Their configuration encodes tuning, suppressions, and scope.

```bash
# CI definitions and task runners that may already invoke scanners
ls .github/workflows/ 2>/dev/null; ls .gitlab-ci.yml Jenkinsfile azure-pipelines.yml bitbucket-pipelines.yml 2>/dev/null
ls Makefile Taskfile.yml justfile .pre-commit-config.yaml 2>/dev/null
```

Then search them for tool names. With the Grep tool or ripgrep:

```bash
rg -n -i 'semgrep|codeql|bandit|gosec|brakeman|snyk|trivy|grype|osv-scanner|gitleaks|trufflehog|npm audit|pip-audit|govulncheck|dependency-check|composer audit|bundle.?audit|spotbugs|eslint-plugin-security|security' \
  .github .gitlab-ci.yml Makefile Taskfile.yml justfile package.json .pre-commit-config.yaml 2>/dev/null
```

If a command is defined there (e.g. `make security`, `npm run audit`), run that exact command.

## 2. Check what's installed

```bash
for t in semgrep gitleaks trufflehog osv-scanner bandit gosec govulncheck brakeman pip-audit cargo-audit; do
  command -v "$t" >/dev/null && echo "available: $t"
done
```

Don't install tools globally or add dev dependencies without asking. If nothing is available, say so in the report's scope line and rely on manual review.

**Know what leaves the machine.** Ask before running anything that sends secrets or source code to a third party: trufflehog's default live verification (it calls each provider's API with the candidate secret) and any hosted scanner that uploads code. The defaults below avoid both. Dependency auditors (`osv-scanner`, `npm audit`, `pip-audit`, `govulncheck`, and similar) send package names and versions to an advisory database. That's normal for public packages, but mention it when the manifest names private or internal packages, and use an offline mode where one exists.

## 3. Generic tools (multi-language)

| Purpose | Command | Notes |
|---|---|---|
| Static analysis (SAST) | `semgrep scan --config <repo config> --metrics off`, else `semgrep scan --config p/default --metrics off` | Use the repo's own config (`.semgrep.yml`, `.semgrep/`) when it has one. `p/default` downloads registry rules but sends no metrics. `--config auto` picks rules per detected language, but it requires metrics to be on, so treat it as an opt-in after asking. |
| Secrets in the working tree | `gitleaks dir .` | gitleaks v8.19+ syntax. Older releases use `gitleaks detect --no-git --source .` |
| Secrets in git history | `gitleaks git .` | Older releases: `gitleaks detect --source .`. For a branch only, add `--log-opts="origin/main..HEAD"`. |
| Secrets (alternative) | `trufflehog filesystem . --no-verification` or `trufflehog git file://. --no-verification` | Without `--no-verification`, trufflehog sends each candidate secret to its provider's API to check whether it is live. That tells you which hits are real, but run it only after the user agrees. Flags differ between v3 releases, so check `trufflehog --help`. |
| Known-vulnerable dependencies (all ecosystems) | `osv-scanner scan source -r .` | v2 syntax. Plain `osv-scanner -r .` is equivalent because `scan source` is the default. Reads lockfiles and SBOMs and queries osv.dev with the package list. To keep the list local, add `--offline-vulnerabilities --download-offline-databases` (downloads the advisory database, then matches locally). |

## 4. Ecosystem-specific

| Ecosystem | SAST | Dependency audit |
|---|---|---|
| Python | `bandit -r <src_dir>` | `pip-audit` (audits the current environment) or `pip-audit -r requirements.txt` |
| JavaScript / TypeScript | ESLint with a security plugin, if the project configures one | `npm audit --omit=dev` (production dependencies), `pnpm audit --prod`, `yarn npm audit` (Yarn 2+) or `yarn audit` (Yarn 1) |
| Java / Kotlin | SpotBugs with the Find Security Bugs plugin, if configured in the build | `mvn org.owasp:dependency-check-maven:check`, or the Gradle `dependencyCheckAnalyze` task when the plugin is applied |
| Go | `gosec ./...` | `govulncheck ./...` (reports only vulnerabilities whose affected functions the code actually calls) |
| PHP | (project-configured PHPStan/Psalm security rules, if any) | `composer audit` (Composer 2.4+) |
| Ruby / Rails | `brakeman` (run from the app root; `brakeman -q` for quieter output) | `bundle-audit check --update` (bundler-audit gem) |
| C# / .NET | Built-in Roslyn security analyzers (CA2100, CA2300–CA2330, CA3xxx, CA5xxx). Many are off by default, so check the project's `AnalysisMode` / `.editorconfig` before treating a clean build as meaningful | `dotnet list package --vulnerable --include-transitive` |
| Rust | (clippy lints) | `cargo audit` (cargo-audit crate) |
| Containers and IaC | `trivy config .` for IaC misconfigurations | `trivy fs .` for dependencies, `trivy image <image>` for built images |

Run these from the repo root (or the relevant package directory in a monorepo). Many exit non-zero when they find issues. That's expected and doesn't mean the tool failed.

## 5. Interpreting results

- **Diff reviews:** filter results to the changed files and lines. Report pre-existing issues separately ("pre-existing, not introduced by this change") so they don't block the PR unless they're severe.
- **Dependency advisories:** a vulnerable version isn't automatically a finding. Check whether the vulnerable function or feature is reachable from this code (govulncheck does this for Go). Check whether a fixed version exists, and whether the dependency is runtime or dev-only. Report a reachable vulnerability as a finding. Report an unreachable one as hardening ("upgrade when convenient").
- **Secret hits:** confirm a hit is a real credential (not a placeholder or public key) before reporting. A real credential in a test fixture or example file is still a finding. For redaction and rotation, follow "Secrets found during review" in SKILL.md.
- **SAST hits:** each is a candidate sink. Trace it back to a source using Step 5, and apply Step 6's four conditions. A high false-positive rate is normal, especially for "possible SQL injection" on concatenated constants and "weak hash" on non-security checksums.
- **Absence of hits proves nothing about authorization,** business logic, or race conditions. Those need the manual Pass B.

## 6. Quick manual searches

Each language cheat sheet ends with ripgrep patterns for its sinks. These cross-cutting ones work in any repo:

```bash
# Likely hard-coded secrets (then confirm by reading)
rg -n -i -e '(api[_-]?key|secret|passwd|password|token|private[_-]?key)\s*[:=]\s*["\x27][^"\x27\s]{8,}' \
   -e '-----BEGIN (RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----' -e 'AKIA[0-9A-Z]{16}'
# TLS verification switched off (several languages)
rg -n -i -e 'verify\s*=\s*False' -e 'InsecureSkipVerify\s*:\s*true' -e 'rejectUnauthorized\s*:\s*false' -e 'VERIFY_NONE' -e 'CURLOPT_SSL_VERIFYPEER\s*,\s*(false|0)'
# Auth/CSRF bypass markers worth reading around
rg -n -i -e 'csrf.{0,20}(exempt|disable|ignore|skip)' -e 'allow_?anonymous' -e 'permit_?all' -e 'skip_before_action' -e 'no_?auth'
```
