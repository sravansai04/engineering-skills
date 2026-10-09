#!/usr/bin/env bash
# Builds the eval repo for "node-cli-json": the released CLI is committed on
# main, and the user's --json work is left uncommitted on top of it.
# Usage: bash setup.sh DEST_DIR   (DEST_DIR must not exist)
set -eu
here=$(cd "$(dirname "$0")" && pwd)
dest=${1:?usage: setup.sh DEST_DIR}
[ -e "$dest" ] && { echo "setup: $dest already exists" >&2; exit 2; }
mkdir -p "$dest"
cp -R "$here/base/." "$dest/"
cd "$dest"
git init -q -b main
git add -A
git -c user.name=eval -c user.email=eval@example.com commit -qm "Release 1.2.0"
cp -R "$here/change/." "$dest/"
echo "repo ready at $dest (the --json work is uncommitted)"
