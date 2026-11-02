"""Non-AI baseline: the rules a careful engineer would write in an afternoon.

Kept on purpose. It is (1) the 'why not just regex?' comparison, and (2) a second, independent
reader: when it disagrees with the LLM, both readings go to the sensitivity check.
"""
import re
from datetime import date

FY_DEFAULT = "2025-26"


def _dmy(s):
    m = re.search(r"(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})", s)
    if not m:
        return None
    try:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1))).isoformat()
    except ValueError:
        return None


def extract(docs: dict, fy: str = FY_DEFAULT, invoices=()) -> dict:
    u = docs.get("udyam", "")
    out = {}

    # category: the row for the FY, else the first category word anywhere
    cat, q = None, ""
    for ln in u.splitlines():
        if fy in ln and re.search(r"\b(Micro|Small|Medium)\b", ln):
            cat, q = re.search(r"\b(Micro|Small|Medium)\b", ln).group(1).lower(), ln.strip()
            break
    if cat is None:
        for ln in u.splitlines():
            m = re.search(r"\b(Micro|Small|Medium)\b", ln)
            if m:
                cat, q = m.group(1).lower(), ln.strip()
                break
    out["category"] = dict(value=cat or "none", source="udyam", quote=q)

    m = re.search(r"MAJOR ACTIVITY\s*:\s*(\w+)", u)
    act = (m.group(1).lower() if m else "manufacturing")
    act = {"manufacturing": "manufacturing", "services": "services", "trading": "trading"}.get(act, act)
    out["activity"] = dict(value=act, source="udyam", quote=m.group(0) if m else "")

    m = re.search(r"DATE OF UDYAM REGISTRATION\s*:\s*([\d/\-]+)", u)
    out["registration_date"] = dict(value=_dmy(m.group(1)) if m else None, source="udyam",
                                    quote=m.group(0) if m else "")

    # payment term: first line mentioning payment/credit that has 'NN days'
    term, src, q = dict(days=None, basis=None, instrument="none"), "po", ""
    for name, instrument in (("po", "buyer_po"), ("invoice", "supplier_invoice_only")):
        for ln in docs.get(name, "").splitlines():
            if re.search(r"payment|credit", ln, re.I):
                m = re.search(r"(\d+)\s*days", ln, re.I)
                if m:
                    low = ln.lower()
                    basis = ("invoice" if "invoice" in low else
                             "delivery" if re.search(r"receipt|deliver|grn", low) else "acceptance")
                    if "eom" in low:
                        basis = "month_end"
                    term = dict(days=int(m.group(1)), basis=basis, instrument=instrument)
                    src, q = name, ln.strip()
                    break
        if term["days"] is not None:
            break
    if q:
        q = re.sub(r"^\d+\.\s*", "", q)
    out["payment_term"] = dict(value=term, source=src, quote=q)

    # objections: a line with reject/complaint + a dd-mm-yyyy date; a later line with accepted/closed
    objs = []
    lines = docs.get("notes", "").splitlines()
    for i, ln in enumerate(lines):
        if re.search(r"reject|complain|objection", ln, re.I) and not re.search(r"closed|cleared", ln, re.I):
            raised = _dmy(ln)
            inv = next((iv for iv in invoices if iv in ln), None)
            if not raised or not inv:
                continue
            removed, rq = None, None
            for ln2 in lines[i + 1:]:
                if re.search(r"closed|cleared|accepted|replaced", ln2, re.I) and _dmy(ln2):
                    removed, rq = _dmy(ln2), ln2.strip()
                    break
            objs.append(dict(invoice=inv, raised=raised, raised_quote=ln.strip(),
                             removed=removed, removed_quote=rq, in_writing=True))
    out["objections"] = dict(value=objs, source="notes", quote="")
    return out
