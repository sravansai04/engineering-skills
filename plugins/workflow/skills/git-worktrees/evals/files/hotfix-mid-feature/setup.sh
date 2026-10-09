#!/usr/bin/env bash
# Builds the eval workspace for git-worktrees eval 1 (hotfix-mid-feature):
#   DEST/origin.git  a bare "remote" with main, release/2.3 and feat/billing-v2
#   DEST/app         a clone checked out on feat/billing-v2 with uncommitted work:
#                    a modified src/billing.js, an untracked src/invoice-v2.js,
#                    and an ignored .env (fake values)
# release/2.3 carries the production bug: formatTotal() drops the cents.
# The project uses npm with a lockfile and no dependencies, `npm test` runs
# node --test, and `npm run dev` serves on $PORT (default 3000).
# Usage: bash setup.sh DEST_DIR   (DEST_DIR must not exist; needs git and node)
set -eu
dest=${1:?usage: setup.sh DEST_DIR}
[ -e "$dest" ] && { echo "setup: $dest already exists" >&2; exit 2; }
mkdir -p "$dest"
dest=$(cd "$dest" && pwd)
G="git -c user.name=eval -c user.email=eval@example.com -c init.defaultBranch=main"
$G init -q --bare "$dest/origin.git"
$G init -q "$dest/app"
cd "$dest/app"
git remote add origin "$dest/origin.git"
mkdir -p src test
cat > package.json <<'JSON'
{
  "name": "app",
  "version": "2.3.0",
  "private": true,
  "scripts": {
    "test": "node --test",
    "dev": "node src/server.js"
  }
}
JSON
cat > package-lock.json <<'JSON'
{
  "name": "app",
  "version": "2.3.0",
  "lockfileVersion": 3,
  "requires": true,
  "packages": {
    "": {
      "name": "app",
      "version": "2.3.0"
    }
  }
}
JSON
printf 'node_modules/\n.env\n' > .gitignore
cat > src/billing.js <<'JS'
// Formats an amount in integer cents as dollars.
function formatTotal(cents) {
  return "$" + Math.floor(cents / 100);
}
module.exports = { formatTotal };
JS
cat > src/server.js <<'JS'
const http = require("node:http");
const { formatTotal } = require("./billing");
const port = Number(process.env.PORT || 3000);
http.createServer((req, res) => res.end(formatTotal(12345) + "\n"))
  .listen(port, () => console.log("listening on " + port));
JS
cat > test/billing.test.js <<'JS'
const test = require("node:test");
const assert = require("node:assert");
const { formatTotal } = require("../src/billing");
test("formats whole dollars", () => assert.strictEqual(formatTotal(500), "$5"));
JS
git add -A
$G commit -qm "Billing totals"
git push -q origin main
git checkout -qb release/2.3
$G commit -q --allow-empty -m "Release 2.3"
git push -q origin release/2.3
git checkout -q main
git checkout -qb feat/billing-v2
cat > src/billing.js <<'JS'
// Billing v2: totals now come from line items (refactor in progress).
function formatTotal(cents) {
  return "$" + Math.floor(cents / 100);
}
function lineItemsTotal(items) {
  return items.reduce((sum, item) => sum + item.cents, 0);
}
module.exports = { formatTotal, lineItemsTotal };
JS
git add -A
$G commit -qm "WIP: start billing v2"
git push -q -u origin feat/billing-v2
# Uncommitted work the user must not lose.
cat >> src/billing.js <<'JS'
// TODO(v2): move tax into line items
JS
cat > src/invoice-v2.js <<'JS'
// Draft of the v2 invoice renderer (not committed yet).
module.exports = {};
JS
printf 'STRIPE_KEY=example-not-a-real-key-0000\n' > .env
echo "ready: $dest/app is on feat/billing-v2 with uncommitted changes; origin has release/2.3"
