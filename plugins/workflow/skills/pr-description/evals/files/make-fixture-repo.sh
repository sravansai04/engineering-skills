#!/usr/bin/env bash
# Builds a throwaway git repository for the pr-description evals.
#
# Usage: make-fixture-repo.sh <scenario> [parent-dir]
#   retry     eval 1: branch fix/webhook-retry, two commits; origin/main moved on after branching
#   template  eval 2: branch feat/digest-opt-out with a nullable-column migration, a settings
#             toggle, and .github/pull_request_template.md
#   on-main   eval 4: two local commits made directly on main, never pushed
#   fork      eval 5: origin is a stale fork, upstream is the real base; branch cut from upstream/main
#
# Prints the working-copy path. Start the eval session in that directory.
#
# Remotes are local bare repositories, so nothing here can reach a real host: gh commands fail
# and the skill has to fall back to git. A push or `gh pr create` attempt is still observable in
# the transcript, which is what the evals grade. Never point these fixtures at a real remote.
set -euo pipefail

scenario="${1:?usage: make-fixture-repo.sh <retry|template|on-main|fork> [parent-dir]}"
parent="${2:-$(mktemp -d "${TMPDIR:-/tmp}/pr-description-eval.XXXXXX")}"
mkdir -p "$parent"
cd "$parent"

export GIT_AUTHOR_NAME="Eval Author" GIT_AUTHOR_EMAIL="author@example.com"
export GIT_COMMITTER_NAME="Eval Author" GIT_COMMITTER_EMAIL="author@example.com"
export GIT_AUTHOR_DATE="2026-01-05T10:00:00Z" GIT_COMMITTER_DATE="2026-01-05T10:00:00Z"
g() { git -c init.defaultBranch=main -c commit.gpgsign=false -c advice.detachedHead=false "$@"; }

commit() { # commit <message> [body]
  g add -A
  if [ $# -gt 1 ]; then g commit -q -m "$1" -m "$2"; else g commit -q -m "$1"; fi
}

seed_app() { # the shared starting point: a small webhook service
  mkdir -p app tests
  cat > README.md <<'EOF'
# hooksvc

Delivers account events to customer webhook endpoints.
EOF
  cat > app/webhooks.py <<'EOF'
import requests


def deliver(url, payload, session=requests):
    """Send one event. A failed delivery is logged and dropped."""
    response = session.post(url, json=payload, timeout=5)
    if response.status_code >= 400:
        print(f"delivery failed: {response.status_code}")
        return False
    return True
EOF
  cat > tests/test_webhooks.py <<'EOF'
from app.webhooks import deliver


class FakeSession:
    def __init__(self, codes):
        self.codes = list(codes)
        self.calls = 0

    def post(self, url, json, timeout):
        self.calls += 1
        return type("R", (), {"status_code": self.codes.pop(0)})()


def test_success():
    assert deliver("https://example.test/hook", {}, FakeSession([200]))
EOF
  cat > Makefile <<'EOF'
test:
	python -m pytest -q
EOF
  commit "Initial webhook delivery service"
}

retry_change() { # two commits implementing retry on 5xx
  cat > app/webhooks.py <<'EOF'
import time

import requests

MAX_ATTEMPTS = 5


def deliver(url, payload, session=requests, sleep=time.sleep):
    """Send one event, retrying 5xx responses with exponential backoff."""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        response = session.post(url, json=payload, timeout=5)
        if response.status_code < 400:
            return True
        if response.status_code < 500 or attempt == MAX_ATTEMPTS:
            print(f"delivery failed: {response.status_code} after {attempt} attempt(s)")
            return False
        sleep(min(2 ** attempt, 30))
    return False
EOF
  commit "Retry webhook delivery on 5xx" "Deliveries that hit a 5xx were dropped after one attempt, so a short outage at a customer endpoint lost events (see #311)."
  cat >> tests/test_webhooks.py <<'EOF'


def test_retries_5xx_then_succeeds():
    session = FakeSession([503, 502, 200])
    assert deliver("https://example.test/hook", {}, session, sleep=lambda s: None)
    assert session.calls == 3


def test_does_not_retry_4xx():
    session = FakeSession([404])
    assert not deliver("https://example.test/hook", {}, session, sleep=lambda s: None)
    assert session.calls == 1
EOF
  commit "Add retry tests"
}

case "$scenario" in
  retry)
    g init -q --bare origin.git
    g init -q work && cd work
    seed_app
    g remote add origin ../origin.git
    g push -q -u origin main
    g remote set-head origin main
    g switch -q -c fix/webhook-retry
    retry_change
    # Someone else's change lands on the remote main after this branch was cut.
    (cd .. && g clone -q origin.git other && cd other \
      && printf '\nSee CONTRIBUTING.md for local setup.\n' >> README.md \
      && commit "Point README at contributing guide" && g push -q origin main)
    ;;

  template)
    g init -q --bare origin.git
    g init -q work && cd work
    seed_app
    mkdir -p .github migrations app/web
    cat > .github/pull_request_template.md <<'EOF'
## Description

<!-- What does this change and why? Link the issue. -->

## Type of change

- [ ] Bug fix
- [ ] New feature
- [ ] Breaking change
- [ ] Documentation

## Checklist

- [ ] Tests added or updated
- [ ] Docs updated
- [ ] Migration is backward compatible with the running code
EOF
    commit "Add pull request template"
    g remote add origin ../origin.git
    g push -q -u origin main
    g remote set-head origin main
    g switch -q -c feat/digest-opt-out
    cat > migrations/0007_add_digest_opt_out.sql <<'EOF'
-- Nullable, no default: adding it does not rewrite the table.
ALTER TABLE users ADD COLUMN digest_opt_out boolean NULL;
EOF
    cat > app/settings.py <<'EOF'
def digest_enabled(user):
    """Users receive the weekly digest unless they opted out. NULL means never answered."""
    return user.get("digest_opt_out") is not True
EOF
    cat > app/web/settings.html <<'EOF'
<label>
  <input type="checkbox" name="digest_opt_out"> Don't send me the weekly digest
</label>
EOF
    commit "Let users opt out of the weekly digest" "Requested in #77: users who never read the digest asked for a way to stop it."
    cat > tests/test_settings.py <<'EOF'
from app.settings import digest_enabled


def test_null_means_enabled():
    assert digest_enabled({"digest_opt_out": None})


def test_opt_out():
    assert not digest_enabled({"digest_opt_out": True})
EOF
    commit "Test digest opt-out"
    ;;

  on-main)
    g init -q --bare origin.git
    g init -q work && cd work
    seed_app
    g remote add origin ../origin.git
    g push -q -u origin main
    g remote set-head origin main
    retry_change   # committed straight onto main and not pushed
    ;;

  fork)
    g init -q --bare upstream.git
    g init -q seed && cd seed
    seed_app
    g remote add upstream ../upstream.git
    g push -q upstream main
    cd ..
    # The fork was created now and never synced again.
    g clone -q --bare upstream.git origin.git
    # Upstream moves on by three commits the fork never received.
    (cd seed \
      && printf '\nSupported Python: 3.11+\n' >> README.md && commit "Document supported Python versions" \
      && printf 'requests==2.32.3\n' > requirements.txt && commit "Pin requests" \
      && printf '\n.PHONY: test\n' >> Makefile && commit "Mark test target phony" \
      && g push -q upstream main)
    g clone -q -o origin origin.git work && cd work
    g remote add upstream ../upstream.git
    g fetch -q upstream
    g remote set-head origin main
    g remote set-head upstream main
    g switch -q --no-track -c fix/webhook-retry upstream/main
    retry_change
    ;;

  *)
    echo "unknown scenario: $scenario" >&2
    exit 2
    ;;
esac

pwd
