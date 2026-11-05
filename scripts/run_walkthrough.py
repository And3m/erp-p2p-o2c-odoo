"""Run procure-to-pay and order-to-cash cycles in Odoo 18 and record every journal entry.

The script talks to Odoo only through its standard external API (XML-RPC), so it
drives the ERP exactly the way a user does through the screens: confirm the
order, validate the stock transfer, create and post the invoice, register the
payment. After each step it reads back the journal entries Odoo posted.

Prerequisites: an Odoo 18 database with Accounting, Purchase, Sales, Inventory,
and the Indian localization (l10n_in) installed, company country set to India.

Usage:
    python scripts/run_walkthrough.py --url http://localhost:8069 --db erp_demo \
        --user admin --password admin
Outputs:
    output/walkthrough_log.json   every step, document, and journal line
    docs/journal_entries.md       the same, as readable tables
"""
from __future__ import annotations

import argparse
import json
import xmlrpc.client
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class Odoo:
    def __init__(self, url, db, user, password):
        self.db, self.password = db, password
        common = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common")
        self.uid = common.authenticate(db, user, password, {})
        if not self.uid:
            raise SystemExit("Odoo login failed")
        self.models = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object", allow_none=True)

    def call(self, model, method, *args, **kw):
        try:
            return self.models.execute_kw(self.db, self.uid, self.password, model, method, list(args), kw)
        except xmlrpc.client.Fault as e:
            # Some button methods return a UI action containing None values. The method has
            # already run and committed; only the reply cannot be marshalled, so treat as done.
            if "cannot marshal None" in e.faultString:
                return None
            raise

    def search(self, model, domain, limit=0):
        return self.call(model, "search", domain, limit=limit)

    def read(self, model, ids, fields):
        return self.call(model, "read", ids, fields=fields)

    def create(self, model, vals, context=None):
        return self.call(model, "create", vals, context=context or {})

    def ref(self, xmlid):
        module, name = xmlid.split(".")
        rec = self.call("ir.model.data", "search_read", [("module", "=", module), ("name", "=", name)],
                        fields=["res_id"], limit=1)
        return rec[0]["res_id"]


# ------------------------------------------------------------------ setup

def account_id(o, code):
    ids = o.search("account.account", [("code", "=", code)], limit=1)
    return ids[0] if ids else None


def ensure_account(o, code, name, account_type):
    return account_id(o, code) or o.create("account.account", {"code": code, "name": name,
                                                               "account_type": account_type})


def setup(o):
    """Master data and accounting configuration for perpetual (real-time) inventory."""
    company_id = o.call("res.users", "read", [o.uid], fields=["company_id"])[0]["company_id"][0]
    o.call("res.company", "write", [company_id], {"anglo_saxon_accounting": True})

    valuation = account_id(o, "100310")                                     # Inventories
    received = ensure_account(o, "100320", "Stock Interim (Received)", "asset_current")
    delivered = ensure_account(o, "100330", "Stock Interim (Delivered)", "asset_current")
    cogs = ensure_account(o, "212400", "Cost of Goods Sold", "expense_direct_cost")
    sale_journal = o.read("account.journal", o.search("account.journal", [("type", "=", "sale")], limit=1),
                          ["default_account_id"])[0]
    sales = sale_journal["default_account_id"][0]                           # 200110 Local Sales
    stock_journal = o.search("account.journal", [("code", "=", "STJ")], limit=1) or [
        o.create("account.journal", {"name": "Inventory Valuation", "code": "STJ", "type": "general"})]

    categ = o.create("product.category", {
        "name": "Packaged Goods",
        "property_cost_method": "average",
        "property_valuation": "real_time",
        "property_stock_valuation_account_id": valuation,
        "property_stock_account_input_categ_id": received,
        "property_stock_account_output_categ_id": delivered,
        "property_stock_journal": stock_journal[0],
        "property_account_expense_categ_id": cogs,
        "property_account_income_categ_id": sales,
    })

    gst_s = o.search("account.tax", [("name", "=", "18% GST S"), ("type_tax_use", "=", "sale")], limit=1)
    gst_p = o.search("account.tax", [("name", "=", "18% GST P"), ("type_tax_use", "=", "purchase")], limit=1)
    hsn = {"Detergent Powder 1kg": "34022010", "Toilet Soap 100g x4": "34011190", "Shampoo 340ml": "33051090"}
    products = {}
    for name, cost, price in [("Detergent Powder 1kg", 92.0, 125.0), ("Toilet Soap 100g x4", 118.0, 160.0),
                              ("Shampoo 340ml", 186.0, 249.0)]:
        products[name] = o.create("product.product", {
            "name": name, "type": "consu", "is_storable": True, "categ_id": categ,
            "standard_price": cost, "list_price": price, "l10n_in_hsn_code": hsn[name],
            "taxes_id": [(6, 0, gst_s)], "supplier_taxes_id": [(6, 0, gst_p)],
            "purchase_method": "receive", "invoice_policy": "delivery",
        })

    india = o.ref("base.in")
    state = lambda code: o.search("res.country.state", [("code", "=", code), ("country_id", "=", india)], limit=1)[0]
    partners = {
        "vendor_ka": o.create("res.partner", {"name": "Kaveri Personal Care Pvt Ltd", "is_company": True,
                                              "city": "Mysuru", "state_id": state("KA"), "country_id": india,
                                              "l10n_in_gst_treatment": "regular", "vat": "29AABCK1234M1Z5"}),
        "customer_ka": o.create("res.partner", {"name": "Sri Lakshmi Supermarket", "is_company": True,
                                                "city": "Bengaluru", "state_id": state("KA"), "country_id": india,
                                                "l10n_in_gst_treatment": "regular", "vat": "29AAGFS5678L1Z2"}),
        "customer_ts": o.create("res.partner", {"name": "Green Valley Mart", "is_company": True,
                                                "city": "Hyderabad", "state_id": state("TS"), "country_id": india,
                                                "l10n_in_gst_treatment": "regular", "vat": "36AAHCG9012K1Z8"}),
    }
    return products, partners


# ------------------------------------------------------------------ journal capture

class Recorder:
    def __init__(self, o):
        self.o, self.steps = o, []
        self.last_move = max(o.search("account.move", [], limit=0) or [0])

    def step(self, cycle, title, document, note):
        new = self.o.search("account.move", [("id", ">", self.last_move), ("state", "=", "posted")])
        entries = []
        for mv in self.o.read("account.move", sorted(new), ["name", "date", "journal_id", "ref"]):
            lines = self.o.read("account.move.line",
                                self.o.search("account.move.line", [("move_id", "=", mv["id"])]),
                                ["account_id", "name", "debit", "credit", "partner_id"])
            entries.append({"move": mv["name"], "date": mv["date"], "journal": mv["journal_id"][1],
                            "lines": [{"account": l["account_id"][1], "label": l["name"] or "",
                                       "debit": l["debit"], "credit": l["credit"]} for l in lines]})
        if new:
            self.last_move = max(new)
        self.steps.append({"cycle": cycle, "step": title, "document": document, "note": note,
                           "entries": entries})
        print(f"  {cycle:<4} {title:<34} {document:<22} {len(entries)} journal entr{'y' if len(entries) == 1 else 'ies'}")


# ------------------------------------------------------------------ cycles

def validate_picking(o, picking_ids):
    for pid in picking_ids:
        moves = o.search("stock.move", [("picking_id", "=", pid)])
        for m in o.read("stock.move", moves, ["product_uom_qty"]):
            o.call("stock.move", "write", [m["id"]], {"quantity": m["product_uom_qty"], "picked": True})
        o.call("stock.picking", "button_validate", [pid])
    return ", ".join(p["name"] for p in o.read("stock.picking", picking_ids, ["name"]))


def register_payment(o, move_id, amount=None, on=None):
    vals = {"payment_date": (on or date.today()).isoformat()}
    if amount is not None:
        vals.update({"amount": amount, "payment_difference_handling": "open"})
    ctx = {"active_model": "account.move", "active_ids": [move_id]}
    wiz = o.create("account.payment.register", vals, context=ctx)
    o.call("account.payment.register", "action_create_payments", [wiz], context=ctx)


def procure_to_pay(o, rec, products, vendor, lines, pay=True, bill=True, label="P2P"):
    po = o.create("purchase.order", {"partner_id": vendor, "order_line": [
        (0, 0, {"product_id": products[p], "product_qty": q, "price_unit": price}) for p, q, price in lines]})
    po_name = o.read("purchase.order", [po], ["name"])[0]["name"]
    rec.step(label, "1. Request for quotation", po_name, "Draft purchase order. No accounting impact.")

    o.call("purchase.order", "button_confirm", [po])
    rec.step(label, "2. Confirm purchase order", po_name,
             "Commitment to the vendor. Still no journal entry: nothing has been received or billed.")

    picks = o.read("purchase.order", [po], ["picking_ids"])[0]["picking_ids"]
    grn = validate_picking(o, picks)
    rec.step(label, "3. Goods receipt (GRN)", grn,
             "Stock enters the warehouse at purchase cost. Inventory is debited against the "
             "Stock Interim (Received) clearing account until the vendor bill arrives.")

    if not bill:
        return po, None

    o.call("purchase.order", "action_create_invoice", [po])
    bill = o.read("purchase.order", [po], ["invoice_ids"])[0]["invoice_ids"][0]
    o.call("account.move", "write", [bill], {"invoice_date": date.today().isoformat(),
                                             "ref": f"KPC/{po_name[-4:]}"})
    o.call("account.move", "action_post", [bill])
    bill_name = o.read("account.move", [bill], ["name"])[0]["name"]
    rec.step(label, "4. Vendor bill (3-way match)", bill_name,
             "Bill matched to the PO and the receipt. It clears Stock Interim (Received), books input "
             "CGST and SGST as recoverable credit, and raises the payable to the vendor.")

    if pay:
        register_payment(o, bill)
        rec.step(label, "5. Vendor payment", bill_name,
                 "Payment clears the payable. Odoo posts to Outstanding Payments until the bank "
                 "statement line is reconciled.")
    return po, bill


def order_to_cash(o, rec, products, customer, lines, paid_share=1.0, label="O2C"):
    so = o.create("sale.order", {"partner_id": customer, "order_line": [
        (0, 0, {"product_id": products[p], "product_uom_qty": q, "price_unit": price}) for p, q, price in lines]})
    so_name = o.read("sale.order", [so], ["name"])[0]["name"]
    rec.step(label, "1. Quotation", so_name, "Draft sales quotation. No accounting impact.")

    o.call("sale.order", "action_confirm", [so])
    rec.step(label, "2. Confirm sales order", so_name,
             "Customer commitment and stock reservation. No journal entry yet.")

    picks = o.read("sale.order", [so], ["picking_ids"])[0]["picking_ids"]
    do = validate_picking(o, picks)
    rec.step(label, "3. Delivery", do,
             "Goods leave at average cost: Inventory is credited against the Stock Interim "
             "(Delivered) clearing account.")

    ctx = {"active_model": "sale.order", "active_ids": [so], "active_id": so}
    wiz = o.create("sale.advance.payment.inv", {"advance_payment_method": "delivered"}, context=ctx)
    o.call("sale.advance.payment.inv", "create_invoices", [wiz], context=ctx)
    inv = o.read("sale.order", [so], ["invoice_ids"])[0]["invoice_ids"][0]
    o.call("account.move", "write", [inv], {"invoice_date": date.today().isoformat()})
    o.call("account.move", "action_post", [inv])
    info = o.read("account.move", [inv], ["name", "amount_total", "fiscal_position_id"])[0]
    fpos = info["fiscal_position_id"][1] if info["fiscal_position_id"] else "none"
    rec.step(label, "4. Customer invoice", info["name"],
             f"Revenue and output GST recognised (fiscal position: {fpos}). With perpetual "
             "inventory Odoo also moves the cost of the delivered goods from Stock Interim "
             "(Delivered) into Cost of Goods Sold, matching cost to revenue.")

    if paid_share > 0:
        amount = round(info["amount_total"] * paid_share, 2)
        register_payment(o, inv, amount if paid_share < 1 else None)
        what = "full" if paid_share >= 1 else f"partial ({paid_share:.0%})"
        rec.step(label, f"5. Customer receipt, {what}", info["name"],
                 "Receipt reduces the receivable; any short payment stays open on the customer "
                 "ledger and shows in aging.")
    return so, inv


def opening_capital(o, rec, amount=500_000.0):
    capital = ensure_account(o, "110100", "Share Capital", "equity")
    bank = account_id(o, "100201")
    misc = o.search("account.journal", [("code", "=", "MISC")], limit=1)[0]
    move = o.create("account.move", {"move_type": "entry", "journal_id": misc, "ref": "Opening capital",
                                     "date": date.today().isoformat(), "line_ids": [
        (0, 0, {"account_id": bank, "name": "Share capital introduced", "debit": amount, "credit": 0}),
        (0, 0, {"account_id": capital, "name": "Share capital introduced", "debit": 0, "credit": amount})]})
    o.call("account.move", "action_post", [move])
    rec.step("OPEN", "0. Opening capital", "Manual journal",
             "Owners introduce working capital into the bank account before trading starts.")


# ------------------------------------------------------------------ output

def write_markdown(steps, path):
    out = ["# Journal entries posted by Odoo at each step", "",
           "Generated by `scripts/run_walkthrough.py` from the live Odoo 18 database. "
           "Amounts in INR.", ""]
    for s in steps:
        out += [f"## {s['cycle']} | {s['step']} | {s['document']}", "", s["note"], ""]
        if not s["entries"]:
            out += ["_No journal entry posted._", ""]
        for e in s["entries"]:
            out += [f"**{e['move']}** ({e['journal']}, {e['date']})", "",
                    "| Account | Label | Debit | Credit |", "|---|---|---:|---:|"]
            for l in e["lines"]:
                d = f"{l['debit']:,.2f}" if l["debit"] else ""
                c = f"{l['credit']:,.2f}" if l["credit"] else ""
                out.append(f"| {l['account']} | {l['label']} | {d} | {c} |")
            td = sum(l["debit"] for l in e["lines"])
            tc = sum(l["credit"] for l in e["lines"])
            out += [f"| **Total** | | **{td:,.2f}** | **{tc:,.2f}** |", ""]
    path.write_text("\n".join(out), encoding="utf-8")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--url", default="http://localhost:8069")
    p.add_argument("--db", default="erp_demo")
    p.add_argument("--user", default="admin")
    p.add_argument("--password", default="admin")
    a = p.parse_args()

    o = Odoo(a.url, a.db, a.user, a.password)
    print("Setting up master data and perpetual inventory valuation")
    products, partners = setup(o)
    rec = Recorder(o)

    print("Running cycles")
    opening_capital(o, rec)
    procure_to_pay(o, rec, products, partners["vendor_ka"], [
        ("Detergent Powder 1kg", 600, 92.0), ("Toilet Soap 100g x4", 400, 118.0), ("Shampoo 340ml", 250, 186.0)],
        label="P2P-1")
    order_to_cash(o, rec, products, partners["customer_ka"], [
        ("Detergent Powder 1kg", 240, 125.0), ("Toilet Soap 100g x4", 150, 160.0)], label="O2C-1")
    order_to_cash(o, rec, products, partners["customer_ts"], [
        ("Shampoo 340ml", 120, 249.0), ("Detergent Powder 1kg", 100, 125.0)], paid_share=0.6, label="O2C-2")
    procure_to_pay(o, rec, products, partners["vendor_ka"], [("Shampoo 340ml", 200, 182.0)],
                   pay=False, label="P2P-2")
    procure_to_pay(o, rec, products, partners["vendor_ka"], [("Toilet Soap 100g x4", 300, 118.0)],
                   bill=False, label="P2P-3")

    (ROOT / "output").mkdir(exist_ok=True)
    (ROOT / "output" / "walkthrough_log.json").write_text(json.dumps(rec.steps, indent=2), encoding="utf-8")
    write_markdown(rec.steps, ROOT / "docs" / "journal_entries.md")
    print("Wrote output/walkthrough_log.json and docs/journal_entries.md")


if __name__ == "__main__":
    main()
