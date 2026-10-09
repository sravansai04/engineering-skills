"""Invoice assembly. Output is handed to the PDF renderer line by line."""

import uuid
from datetime import date, timedelta

EU_COUNTRIES = {"DE", "FR", "NL", "IE", "ES", "IT"}


def build_invoice(order, customer):
    # --- header ---
    today = date.today()
    number = "INV-" + uuid.uuid4().hex[:8].upper()
    if customer.get("terms") == "net60":
        due = today + timedelta(days=60)
    elif customer.get("terms") == "net30":
        due = today + timedelta(days=30)
    else:
        due = today

    # --- line totals and discounts ---
    subtotal = 0.0
    lines = []
    for item in order["items"]:
        amount = item["qty"] * item["unit_price"]
        if item["qty"] >= 10:
            amount = amount * 0.95  # bulk discount
        if item.get("sku", "").startswith("PROMO"):
            amount = amount - 5
        subtotal += amount
        lines.append((item["description"], item["qty"], amount))

    discount = 0.0
    if customer.get("tier") == "gold":
        discount = subtotal * 0.10
    elif customer.get("tier") == "silver" and subtotal > 500:
        discount = subtotal * 0.05
    if order.get("coupon"):
        discount = discount + order["coupon"]["amount"]
    net = subtotal - discount

    # --- tax ---
    country = customer["country"]
    if country == "US":
        state_rates = {"CA": 0.0725, "NY": 0.04, "TX": 0.0625}
        tax_rate = state_rates.get(customer.get("state"), 0)
    elif country in EU_COUNTRIES:
        if customer.get("vat_id"):
            tax_rate = 0  # reverse charge
        else:
            tax_rate = 0.19 if country == "DE" else 0.20
    else:
        tax_rate = 0
    tax = round(net * tax_rate, 2)
    total = net + tax

    # --- formatting for the PDF renderer ---
    symbol = {"USD": "$", "EUR": "€"}.get(order["currency"], order["currency"] + " ")
    out = []
    out.append(f"Invoice {number}")
    out.append(f"Date: {today.isoformat()}   Due: {due.isoformat()}")
    out.append(f"Bill to: {customer['name']}")
    if customer.get("vat_id"):
        out.append(f"VAT ID: {customer['vat_id']}")
    out.append("")
    for description, qty, amount in lines:
        out.append(f"{description[:40]:<40} {qty:>4} {symbol}{amount:>10.2f}")
    out.append("")
    out.append(f"{'Subtotal':<45} {symbol}{subtotal:>10.2f}")
    if discount:
        out.append(f"{'Discount':<45} -{symbol}{discount:>9.2f}")
    if tax_rate == 0 and country in EU_COUNTRIES:
        out.append("VAT reverse charge applies")
    else:
        out.append(f"{'Tax':<45} {symbol}{tax:>10.2f}")
    out.append(f"{'Total':<45} {symbol}{total:>10.2f}")
    return {"number": number, "due": due, "total": total, "lines": out}
