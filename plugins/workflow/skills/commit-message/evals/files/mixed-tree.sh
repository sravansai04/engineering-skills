#!/usr/bin/env bash
# Builds a scratch repo for eval 1: one working tree that mixes a formatter run,
# a rename across three files, and a bug fix, all unstaged, plus untracked
# coverage output. Usage: mixed-tree.sh [target-dir]. Prints the repo path.
set -euo pipefail
# Isolate fixture creation from the caller's git config (signing, color, hooks).
export GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1

dir=${1:-$(mktemp -d)}
mkdir -p "$dir"
cd "$dir"
git init -q -b main repo 2>/dev/null || { git init -q repo; git -C repo symbolic-ref HEAD refs/heads/main; }
cd repo
git config user.name "Eval User"
git config user.email "eval.user@example.com"
mkdir -p src test

cat > package.json <<'EOF'
{
  "name": "cart-demo",
  "private": true,
  "scripts": {
    "test": "vitest run",
    "format": "prettier --write src test"
  },
  "devDependencies": {
    "prettier": "3.3.3",
    "vitest": "2.1.4"
  }
}
EOF
cat > .prettierrc <<'EOF'
{ "semi": false, "singleQuote": true }
EOF
printf 'node_modules/\n' > .gitignore
cat > src/config.ts <<'EOF'
export const TAX_RATE = 0.08
EOF
cat > src/types.ts <<'EOF'
export interface LineItem {
  sku: string
  unitPrice: number
  quantity: number
}

export interface Cart {
  items: LineItem[]
  discount: number
}
EOF
git add -A
git commit -qm "chore: add prettier config and cart types"

cat > src/cart.ts <<'EOF'
import { TAX_RATE } from "./config"
import type { Cart, LineItem } from "./types"

export function lineSubtotal(item: LineItem): number {
  return item.unitPrice * item.quantity
}

export function itemCount(cart: Cart): number {
  let count=0
  for (const item of cart.items){
    count+=item.quantity
  }
  return count
}

export function isEmpty(cart: Cart): boolean {
  return cart.items.length === 0
}

export function hasDiscount(cart: Cart): boolean {
  return cart.discount > 0
}

// Total charged at checkout, in cents.
export function calculateTotal(cart: Cart): number {
  const subtotal = cart.items.reduce((sum, item) => sum + lineSubtotal(item), 0)
  const taxed = Math.round(subtotal * (1 + TAX_RATE))
  return taxed - cart.discount
}
EOF
cat > test/cart.test.ts <<'EOF'
import { describe, expect, it } from 'vitest'
import { calculateTotal } from '../src/cart'

const item = { sku: 'A1', unitPrice: 1000, quantity: 2 }

describe('calculateTotal', () => {
  it('adds tax to the subtotal', () => {
    expect(calculateTotal({ items: [item], discount: 0 })).toBe(2160)
  })
})
EOF
git add -A
git commit -qm "feat(cart): compute order totals with tax"

cat > src/checkout.ts <<'EOF'
import { calculateTotal } from './cart'
import type { Cart } from './types'

export function checkoutSummary(cart: Cart): string {
  return `Total: ${(calculateTotal(cart) / 100).toFixed(2)}`
}
EOF
cat > src/invoice.ts <<'EOF'
import { calculateTotal } from './cart'
import type { Cart } from './types'

export function invoiceLine(cart: Cart, orderId: string): string {
  return `${orderId},${calculateTotal(cart)}`
}
EOF
git add -A
git commit -qm "feat(checkout): show the order total on the summary and invoice"

# ---- Uncommitted work: formatter run + rename + bug fix, all unstaged ----
cat > src/cart.ts <<'EOF'
import { TAX_RATE } from './config'
import type { Cart, LineItem } from './types'

export function lineSubtotal(item: LineItem): number {
  return item.unitPrice * item.quantity
}

export function itemCount(cart: Cart): number {
  let count = 0
  for (const item of cart.items) {
    count += item.quantity
  }
  return count
}

export function isEmpty(cart: Cart): boolean {
  return cart.items.length === 0
}

export function hasDiscount(cart: Cart): boolean {
  return cart.discount > 0
}

// Total charged at checkout, in cents.
export function computeOrderTotal(cart: Cart): number {
  const subtotal = cart.items.reduce((sum, item) => sum + lineSubtotal(item), 0)
  const discounted = Math.max(subtotal - cart.discount, 0)
  return Math.round(discounted * (1 + TAX_RATE))
}
EOF
sed -i.bak 's/calculateTotal/computeOrderTotal/g' src/checkout.ts src/invoice.ts && rm -f src/*.bak
cat > test/cart.test.ts <<'EOF'
import { describe, expect, it } from 'vitest'
import { computeOrderTotal } from '../src/cart'

const item = { sku: 'A1', unitPrice: 1000, quantity: 2 }

describe('computeOrderTotal', () => {
  it('adds tax to the subtotal', () => {
    expect(computeOrderTotal({ items: [item], discount: 0 })).toBe(2160)
  })

  it('applies the discount before tax', () => {
    expect(computeOrderTotal({ items: [item], discount: 500 })).toBe(1620)
  })
})
EOF
mkdir -p coverage
printf 'TN:\nSF:src/cart.ts\nend_of_record\n' > coverage/lcov.info

pwd
