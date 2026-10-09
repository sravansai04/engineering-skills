#!/usr/bin/env bash
# Builds the eval workspace for respond-to-review eval 1 (PR #57):
#   DEST/origin.git   a bare "remote" with main and fix/session-timeout
#   DEST/sessions     a clone, checked out on fix/session-timeout, in sync with it
#   DEST/bin/gh       a fake gh serving alice's review (4 inline threads, one
#                     CHANGES_REQUESTED summary, one bot comment); it refuses
#                     every write and logs all calls to DEST/gh-calls.log
# Usage: bash setup.sh DEST_DIR   (DEST_DIR must not exist; needs git and jq)
# Then:  export PATH="DEST_DIR/bin:$PATH"; cd DEST_DIR/sessions
set -eu
here=$(cd "$(dirname "$0")" && pwd)
dest=${1:?usage: setup.sh DEST_DIR}
[ -e "$dest" ] && { echo "setup: $dest already exists" >&2; exit 2; }
command -v jq >/dev/null 2>&1 || { echo "setup: jq is required" >&2; exit 2; }
mkdir -p "$dest"
dest=$(cd "$dest" && pwd)
G="git -c user.name=me -c user.email=me@example.com -c init.defaultBranch=main"
git init -q --bare "$dest/origin.git"
$G clone -q "$dest/origin.git" "$dest/sessions" 2>/dev/null
cd "$dest/sessions"
git checkout -q -b main 2>/dev/null || true
cp -R "$here/base/." .
git add -A
$G commit -qm "Add the shared token store"
git push -q origin main
git checkout -qb fix/session-timeout
cp -R "$here/branch/." .
git add -A
$G commit -qm "Rotate refresh tokens on every refresh"
printf -- '- A refresh token can be exchanged once; a session lasts 30 minutes.\n' >>README.md
git add -A
$G commit -qm "Document refresh-token rotation and the 30-minute session"
git push -q -u origin fix/session-timeout
head=$(git rev-parse HEAD)
mkdir -p "$dest/gh-fixtures" "$dest/bin"
cp "$here/fixtures/"*.json "$here/fixtures/fake-gh.sh" "$dest/gh-fixtures/"
sed "s/__HEAD_SHA__/$head/" "$here/fixtures/pr.json.template" >"$dest/gh-fixtures/pr.json"
sed "s/__HEAD_SHA__/$head/" "$here/fixtures/pull-57.json.template" >"$dest/gh-fixtures/pull-57.json"
cat >"$dest/bin/gh" <<GH
#!/usr/bin/env bash
export FAKE_GH_FIXTURES="$dest/gh-fixtures" FAKE_GH_LOG="$dest/gh-calls.log"
exec bash "$dest/gh-fixtures/fake-gh.sh" "\$@"
GH
chmod +x "$dest/bin/gh"
: >"$dest/gh-calls.log"
echo "ready: export PATH=\"$dest/bin:\$PATH\"; cd \"$dest/sessions\"  (writes are logged to $dest/gh-calls.log)"
