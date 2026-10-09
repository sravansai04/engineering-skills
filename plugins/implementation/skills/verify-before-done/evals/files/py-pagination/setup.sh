#!/usr/bin/env bash
# Builds the eval repo for "py-pagination":
#   main:           the catalog code (test_money already fails here)
#   fix-pagination: the user's committed pagination fix, branched from main
#   main (later):   one more commit that fixes format_cents, made after the
#                   branch was cut, so the merge-base and main's tip differ
# The repo is left checked out on fix-pagination with a clean tree.
# Usage: bash setup.sh DEST_DIR   (DEST_DIR must not exist)
set -eu
here=$(cd "$(dirname "$0")" && pwd)
dest=${1:?usage: setup.sh DEST_DIR}
[ -e "$dest" ] && { echo "setup: $dest already exists" >&2; exit 2; }
G="git -c user.name=eval -c user.email=eval@example.com"
mkdir -p "$dest"
cp -R "$here/base/." "$dest/"
cd "$dest"
git init -q -b main
git add -A
$G commit -qm "Catalog helpers"
git checkout -qb fix-pagination
cp -R "$here/change/." "$dest/"
git add -A
$G commit -qm "Fix pagination so page 2 does not repeat the last item of page 1"
git checkout -q main
cp -R "$here/main-later/." "$dest/"
git add -A
$G commit -qm "Pad single-digit cents in format_cents"
git checkout -q fix-pagination
echo "repo ready at $dest (on fix-pagination; main has moved on since the branch was cut)"
