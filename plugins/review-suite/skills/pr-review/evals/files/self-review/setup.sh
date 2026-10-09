#!/usr/bin/env bash
# Builds the working copy for eval 2 (self-review with uncommitted and untracked
# changes). Usage: setup.sh TARGET_DIR. Creates TARGET_DIR/origin.git (a bare
# "remote" whose default branch is trunk, not main) and TARGET_DIR/work, a clone
# on branch add-discounts with:
#   - one commit that wires discounts into cart.py,
#   - an uncommitted edit to the tracked file src/shop/cart.py,
#   - an untracked new file src/shop/discounts.py (never git-added).
# Run the eval with TARGET_DIR/work as the working directory.
set -euo pipefail
target=${1:?usage: setup.sh TARGET_DIR}
mkdir -p "$target"
cd "$target"
git init -q --bare -b trunk origin.git
git clone -q origin.git work 2>/dev/null
cd work
git config user.email dev@example.com
git config user.name Dev
git checkout -q -b trunk

mkdir -p src/shop tests
cat > pyproject.toml <<'EOF'
[tool.ruff]
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "I"]
EOF
cat > src/shop/cart.py <<'EOF'
def cart_total(items):
    """Total in integer cents."""
    return sum(item.price_cents * item.quantity for item in items)
EOF
cat > tests/test_cart.py <<'EOF'
from types import SimpleNamespace

from shop.cart import cart_total


def test_cart_total():
    items = [SimpleNamespace(price_cents=250, quantity=2)]
    assert cart_total(items) == 500
EOF
git add .
git commit -q -m "Cart totals"
git push -q origin trunk
git remote set-head origin trunk

git checkout -q -b add-discounts
cat > src/shop/cart.py <<'EOF'
import os

from shop.discounts import apply_discount


def cart_total(items, discount_percent=0):
    """Total in integer cents, after an optional percentage discount."""
    subtotal = sum(item.price_cents * item.quantity for item in items)
    return apply_discount(subtotal, discount_percent)
EOF
git add src/shop/cart.py
git commit -q -m "Apply percentage discounts to cart totals"

# Uncommitted edit to a tracked file.
cat > src/shop/cart.py <<'EOF'
import os

from shop.discounts import apply_discount


def cart_total(items, discount_percent=0):
    """Total in integer cents, after an optional percentage discount."""
    subtotal = sum(item.price_cents * item.quantity for item in items)
    if discount_percent:
        return apply_discount(subtotal, discount_percent)
    return subtotal
EOF

# Untracked new module, never added to git.
cat > src/shop/discounts.py <<'EOF'
def apply_discount(total_cents, percent):
    """Return the total in integer cents after a percentage discount, never below zero."""
    return total_cents - total_cents * percent / 100
EOF
