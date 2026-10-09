#!/usr/bin/env bash
# Builds a scratch setup for eval 3: a feature branch whose last commit says
# "fixed stuff", pushed WITHOUT -u (so the branch has no upstream configured),
# and a teammate who has since pushed a commit on top of it. The local clone has
# not fetched the teammate's commit. Usage: pushed-shared-branch.sh [target-dir].
# Prints the path of the clone to work in.
set -euo pipefail
export GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1

dir=${1:-$(mktemp -d)}
mkdir -p "$dir"
cd "$dir"
git init -q --bare origin.git
git -C origin.git symbolic-ref HEAD refs/heads/main

git clone -q origin.git you 2>/dev/null
cd you
git config user.name "Eval User"
git config user.email "eval.user@example.com"
git symbolic-ref HEAD refs/heads/main
mkdir -p src
cat > src/search.py <<'EOF'
PAGE_SIZE = 20


def paginate(results, page):
    """Return one page of results; pages are numbered from 1."""
    start = page * PAGE_SIZE
    return results[start:start + PAGE_SIZE]
EOF
git add -A
git commit -qm "feat(search): paginate search results"
git push -q origin main

git switch -q -c feature/search-filters
cat >> src/search.py <<'EOF'


def filter_by_status(results, status):
    return [r for r in results if r.get("status") == status]
EOF
git commit -qam "feat(search): filter results by status"

# The commit with the bad message: a real off-by-one fix in pagination.
sed -i.bak 's/start = page \* PAGE_SIZE/start = (page - 1) * PAGE_SIZE/' src/search.py && rm -f src/search.py.bak
git commit -qam "fixed stuff"

# Pushed without -u: a remote branch exists, but no upstream is configured.
git push -q origin feature/search-filters
cd ..

# A teammate builds on the pushed branch.
git clone -q origin.git teammate 2>/dev/null
cd teammate
git config user.name "Teammate"
git config user.email "teammate@example.com"
git switch -q feature/search-filters
mkdir -p tests
cat > tests/test_search.py <<'EOF'
from src.search import filter_by_status


def test_filter_by_status_keeps_matching_results():
    results = [{"status": "open"}, {"status": "closed"}]
    assert filter_by_status(results, "open") == [{"status": "open"}]
EOF
git add -A
git commit -qm "test(search): cover the status filter"
git push -q origin feature/search-filters
cd ../you

pwd
