"""The law, as code. Every rule has an id, a citation and an effective window.

Knowledge lives HERE (and in the CA's policy file), not in the model and not in a retrieval
index. The rules are short; a reviewer can read this whole file in ten minutes and a test
pins each one. When the law moves, a person edits this file and re-runs the tests.

The pack carries `verified_on` and `review_by`. After `review_by` the engine refuses to run
(unless --allow-stale is passed and that is printed on every output), because a silently
out-of-date rule is worse than no answer.
"""
from datetime import date

PACK = dict(
    id="IN-MSE-PAYMENT-TAX",
    version="2026.11.0",
    jurisdiction="India",
    verified_on=date(2026, 11, 2),
    review_by=date(2027, 1, 31),
    verified_by="<name of the CA who signs off this pack>",
)

# Interpretations that are not settled law are marked kind="interpretation" and can be
# switched by the firm's policy file; settled rules are kind="statute".
RULES = {
    "APP-01": dict(kind="statute",
                   text="Only a micro or small enterprise is a 'supplier'; medium enterprises are outside s.15.",
                   cite="MSMED Act 2006 s.2(n), s.15; ITA 1961 s.43B(h); ITA 2025 s.37(2)(g)"),
    "APP-02": dict(kind="statute",
                   text="Retail and wholesale traders registered on Udyam get priority-sector lending benefits only, not delayed-payment protection.",
                   cite="MoMSME OM 02-07-2021 and 01-09-2021; MoMSME clarification 28-06-2024"),
    "APP-03": dict(kind="interpretation",
                   text="Supplier must be registered on or before the date of the order (contract) to be a 'supplier' for it.",
                   cite="Silpi Industries v. KSRTC (Supreme Court, 2021) - applied by analogy"),
    "APP-04": dict(kind="interpretation", policy_key="exclude_capital",
                   text="Capital expenditure is not a deduction 'otherwise allowable' for the year, so it is outside s.43B(h).",
                   cite="Commentary and ITAT decisions; firm policy"),
    "ACC-01": dict(kind="statute",
                   text="Day of acceptance = day of actual delivery of goods / rendering of services (deemed acceptance if no written objection within 15 days).",
                   cite="MSMED Act 2006 s.2(b) Explanation (i)(a), (ii)"),
    "ACC-02": dict(kind="statute",
                   text="If the buyer objects in writing within 15 days of delivery, the day of acceptance is the day the supplier removes the objection.",
                   cite="MSMED Act 2006 s.2(b) Explanation (i)(b)"),
    "ACC-03": dict(kind="statute",
                   text="A written objection raised more than 15 days after delivery does not move the day of acceptance.",
                   cite="MSMED Act 2006 s.2(b) Explanation (ii)"),
    "DUE-01": dict(kind="statute",
                   text="No written agreement on payment: pay on or before the 15th day after acceptance (before the 'appointed day').",
                   cite="MSMED Act 2006 s.2(b), s.15"),
    "DUE-02": dict(kind="statute",
                   text="Written agreement: pay on or before the agreed date, but the agreed period can never exceed 45 days from acceptance.",
                   cite="MSMED Act 2006 s.15 and proviso"),
    "DUE-03": dict(kind="interpretation", policy_key="invoice_terms_are_agreement",
                   text="Whether a payment term printed only on the supplier's own invoice is an agreement 'in writing' between the parties.",
                   cite="Unsettled - decided by the signing CA, recorded in policy.json"),
    "TAX-1961": dict(kind="statute", fy_from="2023-24", fy_to="2025-26",
                     text="Sum payable to a micro/small enterprise beyond the s.15 time limit is deductible only in the year actually paid; "
                          "payment before the return due date does not help (clause (h) excluded from the proviso).",
                     cite="Income-tax Act 1961 s.43B(h); report in Form 3CD clause 22"),
    "TAX-2025": dict(kind="statute", fy_from="2026-27", fy_to=None,
                     text="Same rule under the new Act: deductible only on actual payment; s.37(3) relief does not apply to clause (g).",
                     cite="Income-tax Act 2025 s.37(2)(g), s.37(3); report in Form 26 (Income-tax Rules 2026, rule 47)"),
}

# Things that are moving. Listed so a reviewer sees them; none changes a number today.
WATCH = [
    dict(item="MSMED (Amendment) Act 2026 (Act 16 of 2026), assent 13-08-2026",
         status="S.O. 5575(E) of 12-10-2026: ss.2-7, 11, 13-17 in force from 15-10-2026; s.12 from 15-12-2026; ss.8-10 (dispute "
                "resolution) not yet. Secondary sources report the s.15 15/45-day rule unchanged; adds s.15A (TReDS for CPSEs) "
                "and civil penalties.",
         action="Confirm the amended s.2 definitions and s.15/s.16 against the gazette text before the next audit season."),
    dict(item="MSME classification limits revised from 01-04-2025 (S.O. 1364(E), 21-03-2025)",
         status="More suppliers are now micro/small. The Udyam certificate row for the year is the source of truth, not the limits.",
         action="None for the engine; vendor master refresh."),
    dict(item="Form 3CD replaced by Form 26 from tax year 2026-27",
         status="Clause numbers change; the underlying test does not.",
         action="Update report template mapping."),
]

FY_INFO = {
    "2024-25": dict(start=date(2024, 4, 1), end=date(2025, 3, 31), tax_rule="TAX-1961"),
    "2025-26": dict(start=date(2025, 4, 1), end=date(2026, 3, 31), tax_rule="TAX-1961"),
    "2026-27": dict(start=date(2026, 4, 1), end=date(2027, 3, 31), tax_rule="TAX-2025"),
}


class StaleRulePack(RuntimeError):
    pass


def check_fresh(today: date, allow_stale: bool = False):
    if today > PACK["review_by"] and not allow_stale:
        raise StaleRulePack(
            f"Rule pack {PACK['version']} was due for review by {PACK['review_by']}. "
            "Re-verify the law and bump the pack, or pass --allow-stale (every output will say so).")
    return today > PACK["review_by"]


def fy_info(fy: str):
    if fy not in FY_INFO:
        raise KeyError(f"No rules loaded for FY {fy}")
    return FY_INFO[fy]
