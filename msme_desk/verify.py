"""Mechanical guards on every extracted fact. A fact that fails any guard is treated as
UNKNOWN downstream (never silently used). The guards cannot tell a right reading from a
wrong one; they catch the cheap, common failures: invented quotes, quotes that do not say
what the value says, facts taken from the wrong document, and the wrong year's row.
"""
import json
import re

from .textutil import dates_in, norm, numbers_in

ALLOWED_SOURCES = {
    "category": {"udyam"},
    "activity": {"udyam"},
    "registration_date": {"udyam"},
    "payment_term": {"po", "contract", "invoice"},
    "objections": {"notes"},
}
PAYMENT_WORDS = ("pay", "credit", "net ", "भुगतान", "due")
CATEGORY_WORDS = {"micro": ("micro",), "small": ("small",), "medium": ("medium",)}
ACTIVITY_WORDS = {"manufacturing": ("manufactur",), "services": ("service",),
                  "trading": ("trading", "trader", "wholesale", "retail")}


def _quote_ok(quote, doc):
    return bool(quote) and norm(quote) in norm(doc)


def check(name: str, cand: dict, docs: dict, fy: str) -> list[str]:
    """Return the list of failed guards for one candidate fact ([] means it passed)."""
    fails = []
    src, quote, val = cand.get("source"), cand.get("quote", ""), cand.get("value")
    if src not in ALLOWED_SOURCES[name]:
        return [f"source '{src}' not allowed for {name}"]
    doc = docs.get(src, "")

    if name == "objections":
        for o in val or []:
            if not _quote_ok(o.get("raised_quote"), doc):
                fails.append("objection quote not found in notes")
            elif o.get("raised") and __import__("datetime").date.fromisoformat(o["raised"]) not in dates_in(o["raised_quote"]):
                fails.append("objection date not in its quote")
            if o.get("removed"):
                if not _quote_ok(o.get("removed_quote"), doc):
                    fails.append("removal quote not found in notes")
                elif __import__("datetime").date.fromisoformat(o["removed"]) not in dates_in(o["removed_quote"]):
                    fails.append("removal date not in its quote")
        return fails

    if name == "category" and val == "none":
        # verify an ABSENCE: no classification row for this FY in the certificate
        rows = [ln for ln in doc.splitlines() if re.match(r"\s*\d+\s*\|\s*\d{4}-\d{2}\s*\|", ln)]
        if any(fy in ln for ln in rows):
            fails.append(f"certificate does have a row for {fy}")
        return fails

    if not _quote_ok(quote, doc):
        return ["quote not found verbatim in source"]
    q = norm(quote)
    if name == "category":
        if fy not in q:
            fails.append(f"quote is not the {fy} row")
        if not any(w in q for w in CATEGORY_WORDS.get(val, ("<none>",))):
            fails.append("category word not in quote")
    elif name == "activity":
        if not any(w in q for w in ACTIVITY_WORDS.get(val, ("<none>",))):
            fails.append("activity word not in quote")
    elif name == "registration_date":
        from datetime import date
        if val and date.fromisoformat(val) not in dates_in(quote):
            fails.append("date not in quote")
    elif name == "payment_term":
        days = (val or {}).get("days")
        if days is not None:
            if not any(w in q for w in PAYMENT_WORDS):
                fails.append("quote is not about payment")
            if int(days) not in numbers_in(quote):
                fails.append("number of days not in quote")
            inst = (val or {}).get("instrument")
            if src == "invoice" and inst != "supplier_invoice_only":
                fails.append("term from supplier invoice labelled as an agreement")
    return fails


def key(v) -> str:
    return json.dumps(v, sort_keys=True, ensure_ascii=False)
