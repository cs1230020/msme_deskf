"""Turns a decision into what the reviewer sees: the number, the rule trail, the evidence,
and - only when needed - ONE question with the rupee consequence of each answer."""
from .textutil import rupees  # noqa: F401  (re-exported)


def _fmt_val(fact, v):
    if fact == "payment_term":
        if not v or v.get("days") is None:
            return "no written payment term (15-day default)"
        where = {"buyer_po": "in the PO", "contract": "in the contract",
                 "supplier_invoice_only": "only on the supplier's invoice"}.get(v.get("instrument"), "")
        return f"{v['days']} days from {v.get('basis')} {where}".strip()
    if fact == "_policy":
        return "counts as a written agreement" if v else "does NOT count as a written agreement"
    if fact == "objections":
        if not v:
            return "no written objection"
        return "; ".join(f"objection {o['raised']} removed {o.get('removed')}" for o in v)
    if fact == "registration_date":
        return f"registered {v}" if v else "not registered"
    return str(v)


QUESTION = {
    "category": "Confirm the supplier's enterprise type for the year on the Udyam portal.",
    "activity": "Is this supplier a manufacturer/service provider, or a trader (traders are outside s.15)?",
    "registration_date": "When did the supplier register on Udyam, relative to the order date?",
    "payment_term": "Which payment term was agreed in writing?",
    "objections": "Was a written objection raised within 15 days of delivery, and when was it removed?",
    "_policy": "Does a payment term printed only on the supplier's own invoice count as a written agreement? "
               "(Decide once - it is saved as firm policy and applied to every vendor.)",
}


def questions(dec):
    out = []
    for p in dec["pivotal"]:
        q = dict(fact=p["fact"], question=QUESTION.get(p["fact"], "Reconcile the readings below."),
                 answers=[dict(reading=_fmt_val(p["fact"], r["value"]), disallowed=r["disallowed"])
                          for r in p.get("readings", [])])
        if p.get("tripwire"):
            q["question"] = ("The notes mention a possible objection that was not extracted: "
                             f"“{p['tripwire']}”. " + QUESTION["objections"])
        out.append(q)
    return out


def text_summary(case_out):
    lines = [f"{case_out['case']}  {case_out['supplier']}   (reader: {case_out['origin']})"]
    if case_out.get("guards_tripped"):
        lines.append(f"  guards tripped on: {', '.join(case_out['guards_tripped'])}")
    for d in case_out["decisions"]:
        if d["decision"] == "AUTO":
            lines.append(f"  {d['invoice']:<10} AUTO    disallowed {rupees(d['disallowed'])}")
        else:
            lo, hi = d["range"]
            span = (f"between {rupees(lo)} and {rupees(hi)}" if lo != hi
                    else f"provisionally {rupees(hi)} (may be lower)")
            lines.append(f"  {d['invoice']:<10} REVIEW  {span}")
            for q in questions(d):
                lines.append(f"      Q: {q['question']}")
                for a in q["answers"]:
                    lines.append(f"         - if {a['reading']}: {rupees(a['disallowed'])}")
        for rule, why in d["primary"]["trail"]:
            lines.append(f"        [{rule}] {why}")
    return "\n".join(lines)
