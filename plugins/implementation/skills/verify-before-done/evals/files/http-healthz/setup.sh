#!/usr/bin/env bash
# Builds the eval repo for "http-healthz": the service is committed on main,
# and the user's health-check work is left uncommitted (new, untracked files).
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
git -c user.name=eval -c user.email=eval@example.com commit -qm "Items service 0.4.0"
cp -R "$here/change/." "$dest/"
echo "repo ready at $dest (the health-check work is uncommitted)"
