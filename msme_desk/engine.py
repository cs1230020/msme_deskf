"""Deterministic calculator. Takes ONE concrete reading of the facts and returns, per invoice,
the amount disallowed and the trail of rule ids that produced it. No model is called here.
"""
import calendar
from dataclasses import dataclass, field
from datetime import date, timedelta

from .rulepack import fy_info
from .textutil import rupees


def d(s):
    return date.fromisoformat(s) if isinstance(s, str) else s


@dataclass
class InvoiceResult:
    invoice: str
    amount: int
    applicable: bool
    acceptance: date | None
    due: date | None
    outstanding_at_fye: int
    disallowed: int
    late: bool                      # any payment after due date (MSMED s.16 interest exposure)
    flags: list = field(default_factory=list)   # hard flags force human review
    trail: list = field(default_factory=list)   # (rule id, plain-words reason)


def compute(ledger: dict, facts: dict, policy: dict, as_of: date) -> list[InvoiceResult]:
    """facts: concrete values (no alternates):
         category: micro|small|medium|none
         activity: manufacturing|services|trading
         registration_date: 'YYYY-MM-DD' | None
         payment_term: {days, basis, instrument}
         objections: [{invoice, raised, removed, in_writing}]
       policy: {exclude_capital: bool, invoice_terms_are_agreement: bool}
    """
    fy = fy_info(ledger["fy"])
    fye = fy["end"]
    po_date = d(ledger["po_date"])
    results = []

    # ---- applicability (same for every invoice of this vendor)
    app_trail, applicable = [], True
    cat = facts["category"]
    if cat not in ("micro", "small"):
        applicable = False
        app_trail.append(("APP-01", f"supplier is '{cat}' for FY {ledger['fy']}: not a micro/small 'supplier'"))
    if facts["activity"] == "trading":
        applicable = False
        app_trail.append(("APP-02", "supplier is a trader: outside s.15"))
    reg = d(facts["registration_date"]) if facts["registration_date"] else None
    if reg is None or reg > po_date:
        applicable = False
        app_trail.append(("APP-03", f"Udyam registration {reg} is after the order date {po_date}"))
    if ledger.get("capital") and policy.get("exclude_capital", True):
        applicable = False
        app_trail.append(("APP-04", "capital purchase: outside s.43B(h) under firm policy"))
    if applicable:
        app_trail.append(("APP-01", f"supplier is '{cat}', {facts['activity']}, registered {reg}"))

    term = facts["payment_term"] or {"days": None, "basis": None, "instrument": "none"}

    for inv in ledger["invoices"]:
        trail = list(app_trail)
        flags = []
        amount = int(inv["amount"])
        delivery, inv_date = d(inv["delivery"]), d(inv["invoice_date"])
        pays = sorted([p for p in ledger["payments"] if p["invoice"] == inv["no"]], key=lambda p: p["date"])

        # ---- day of acceptance
        acceptance = delivery
        trail.append(("ACC-01", f"delivered {delivery}"))
        for o in facts.get("objections") or []:
            if o.get("invoice") != inv["no"] or not o.get("in_writing", True):
                continue
            raised = d(o["raised"])
            if (raised - delivery).days <= 15:
                if o.get("removed"):
                    acceptance = d(o["removed"])
                    trail.append(("ACC-02", f"written objection {raised} (within 15 days), removed {acceptance}"))
                else:
                    acceptance = None
                    flags.append("objection_unresolved")
                    trail.append(("ACC-02", f"written objection {raised} not yet removed: goods not accepted"))
            else:
                trail.append(("ACC-03", f"objection {raised} came {(raised - delivery).days} days after delivery: ignored"))

        # ---- due date
        due = None
        if acceptance is not None:
            cap = acceptance + timedelta(days=45)
            instr = term.get("instrument")
            agreed = term.get("days") is not None and (
                instr in ("buyer_po", "contract") or
                (instr == "supplier_invoice_only" and policy.get("invoice_terms_are_agreement") is True))
            if instr == "supplier_invoice_only":
                trail.append(("DUE-03", "term only on supplier invoice; treated as "
                              + ("an agreement" if agreed else "NO agreement") + " per policy"))
            if agreed:
                basis = term.get("basis") or "acceptance"
                anchor = {"acceptance": acceptance, "delivery": delivery, "invoice": inv_date,
                          "other": acceptance}.get(basis)
                if basis == "month_end":
                    anchor = inv_date.replace(day=calendar.monthrange(inv_date.year, inv_date.month)[1])
                agreed_date = anchor + timedelta(days=int(term["days"]))
                due = min(agreed_date, cap)
                trail.append(("DUE-02", f"agreed {term['days']} days from {basis} = {agreed_date}; "
                                        f"cap {cap}; due {due}"))
            else:
                due = acceptance + timedelta(days=15)
                trail.append(("DUE-01", f"no written agreement: due {due}"))

        # ---- money
        paid_by_fye = sum(p["amount"] for p in pays if d(p["date"]) <= fye)
        outstanding = max(0, amount - paid_by_fye)
        total_paid = sum(p["amount"] for p in pays)
        late = due is not None and (any(d(p["date"]) > due for p in pays) or
                                    (total_paid < amount and as_of > due))
        disallowed = 0
        if not applicable:
            pass
        elif acceptance is None:
            pass
        elif outstanding == 0:
            trail.append((fy["tax_rule"], f"fully paid by {fye}: deduction allowed this year"
                                          + (" (paid late: MSMED interest exposure)" if late else "")))
        else:
            remaining, on_time = outstanding, 0
            for p in pays:
                pd = d(p["date"])
                if pd <= fye or remaining <= 0:
                    continue
                take = min(p["amount"], remaining)
                if pd <= due:
                    on_time += take
                remaining -= take
            disallowed = outstanding - on_time
            trail.append((fy["tax_rule"], f"{rupees(outstanding)} unpaid at {fye}; {rupees(on_time)} paid by due {due}; "
                                          f"{rupees(disallowed)} disallowed for FY {ledger['fy']}, allowed in year of payment"))
        results.append(InvoiceResult(inv["no"], amount, applicable, acceptance, due, outstanding,
                                     disallowed, late, flags, trail))
    return results
