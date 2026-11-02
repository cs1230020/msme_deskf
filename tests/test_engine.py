"""Rule-level tests. Each pins one sentence of the law; if the law changes, a test should fail."""
import glob
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from msme_desk import verify                                  # noqa: E402
from msme_desk.engine import compute                          # noqa: E402
from msme_desk.pipeline import AS_OF, DEFAULT_POLICY, load_case, run_case  # noqa: E402
from msme_desk.textutil import dates_in, numbers_in          # noqa: E402

BASE = dict(category="micro", activity="manufacturing", registration_date="2020-01-01",
            payment_term=dict(days=30, basis="delivery", instrument="buyer_po"), objections=[])


def ledger(delivery="2026-03-01", pays=(), amount=100, capital=False):
    return dict(case="T", fy="2025-26", po_date="2026-02-01", capital=capital,
                invoices=[dict(no="I1", delivery=delivery, invoice_date=delivery, amount=amount)],
                payments=[dict(invoice="I1", date=d, amount=a) for d, a in pays])


def one(led, **over):
    facts = dict(BASE, **over)
    return compute(led, facts, DEFAULT_POLICY, AS_OF)[0]


def test_cap_45_days():           # s.15 proviso
    r = one(ledger(), payment_term=dict(days=90, basis="delivery", instrument="buyer_po"))
    assert r.due == date(2026, 4, 15)


def test_no_agreement_15_days():  # s.2(b) appointed day
    r = one(ledger(), payment_term=dict(days=None, basis=None, instrument="none"))
    assert r.due == date(2026, 3, 16)


def test_objection_within_15_days_moves_acceptance():
    r = one(ledger(), objections=[dict(invoice="I1", raised="2026-03-10", removed="2026-03-20", in_writing=True)])
    assert r.acceptance == date(2026, 3, 20)


def test_objection_after_15_days_ignored():
    r = one(ledger(), objections=[dict(invoice="I1", raised="2026-03-20", removed="2026-03-25", in_writing=True)])
    assert r.acceptance == date(2026, 3, 1)


def test_paid_late_but_within_year_not_disallowed():
    r = one(ledger(delivery="2026-01-01", pays=[("2026-03-20", 100)]))
    assert r.disallowed == 0 and r.late


def test_partial_on_time_after_year_end():
    r = one(ledger(pays=[("2026-03-25", 20), ("2026-04-10", 30), ("2026-05-30", 50)]),
            payment_term=dict(days=45, basis="delivery", instrument="buyer_po"))   # due 15-Apr
    assert r.outstanding_at_fye == 80 and r.disallowed == 50


def test_medium_and_trader_and_late_registration_out_of_scope():
    led = ledger(pays=[("2026-06-01", 100)])
    assert one(led, category="medium").disallowed == 0
    assert one(led, activity="trading").disallowed == 0
    assert one(led, registration_date="2026-02-15").disallowed == 0
    assert one(led).disallowed == 100


def test_capital_excluded_by_policy():
    assert one(ledger(pays=[("2026-06-01", 100)], capital=True)).disallowed == 0


def test_month_end_basis():
    r = one(ledger(delivery="2026-03-10"), payment_term=dict(days=10, basis="month_end", instrument="buyer_po"))
    assert r.due == date(2026, 4, 10)


def test_verifier_catches_invented_quote_and_wrong_year():
    docs = {"udyam": "1 | 2024-25 | Small | x\n2 | 2025-26 | Medium | y\n"}
    assert verify.check("category", dict(value="small", source="udyam", quote="2 | 2025-26 | Small | y"), docs, "2025-26")
    assert verify.check("category", dict(value="small", source="udyam", quote="1 | 2024-25 | Small | x"), docs, "2025-26")
    assert not verify.check("category", dict(value="medium", source="udyam", quote="2 | 2025-26 | Medium | y"), docs, "2025-26")


def test_verifier_rejects_wrong_source():
    docs = {"po": "this vendor is Medium"}
    assert verify.check("category", dict(value="medium", source="po", quote="this vendor is Medium"), docs, "2025-26")


def test_text_parsers():
    assert date(2026, 3, 28) in dates_in("QC cleared the lot on 28th March.")
    assert 21 in numbers_in("balance within twenty-one days")
    assert 30 in numbers_in("माल प्राप्ति के 30 दिनों के भीतर")


def test_every_case_engine_matches_hand_answer():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for p in sorted(glob.glob(os.path.join(root, "cases", "C*"))):
        docs, led, gold = load_case(p)
        facts = {k: v["value"] for k, v in gold["facts"].items()}
        out = run_case(p, {k: dict(v, alternates=[]) for k, v in gold["facts"].items()}, "ref", use_cross_check=False)
        for d in out["decisions"]:
            exp = gold["expected"][d["invoice"]]
            if exp["decision"] == "AUTO":
                assert d["decision"] == "AUTO" and d["disallowed"] == exp["disallowed"], (p, d)
            else:
                assert d["decision"] == "REVIEW", (p, d)
