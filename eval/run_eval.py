"""Evaluation harness. Run from the repo root:

    python eval/run_eval.py            # engine, regex baseline, cross-check, fault injection
    python eval/run_eval.py --llm      # also runs the live LLM extractor (needs OPENROUTER_* env vars)

Writes outputs/eval_report.md and outputs/eval_results.json.

What each block measures
  A  Engine on hand-labelled facts       -> is the law-as-code right?            (should be 19/19)
  B  Regex baseline end to end           -> how far does a non-AI reader get?
  C  Reference facts + regex cross-check -> how many needless reviews does the cross-check cost?
  D  Fault injection                     -> when the reader is WRONG in the ways LLMs are wrong,
                                            how often does a wrong number go out unflagged?
  E  Live LLM (optional)                 -> the real thing, on a free OpenRouter model
"""
import argparse
import copy
import glob
import json
import os
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from msme_desk import extract_regex                      # noqa: E402
from msme_desk.engine import compute                      # noqa: E402
from msme_desk.pipeline import AS_OF, DEFAULT_POLICY, load_case, run_case  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CASES = sorted(glob.glob(os.path.join(ROOT, "cases", "C*")))
OUT = os.path.join(ROOT, "outputs")


def score(decisions, expected):
    """-> list of (invoice, verdict) with verdict in correct | review | SILENT_ERROR."""
    out = []
    for dct in decisions:
        exp = expected[dct["invoice"]]
        if exp["decision"] == "REVIEW":
            v = "correct" if dct["decision"] == "REVIEW" else "SILENT_ERROR"
        elif dct["decision"] == "REVIEW":
            v = "review"
        else:
            v = "correct" if dct["disallowed"] == exp["disallowed"] else "SILENT_ERROR"
        out.append((dct["invoice"], v))
    return out


def same_fact(name, a, b):
    if name == "payment_term":
        a, b = a or {}, b or {}
        if a.get("days") is None and b.get("days") is None:
            return True
        return (a.get("days"), a.get("instrument"), a.get("basis")) == (b.get("days"), b.get("instrument"), b.get("basis"))
    if name == "objections":
        f = lambda xs: sorted((o["invoice"], o["raised"], o.get("removed")) for o in xs or [])
        return f(a) == f(b)
    return a == b


# ---------------------------------------------------------------- fault models
WRONG_CAT = {"micro": "medium", "small": "medium", "medium": "micro", "none": "small"}
WRONG_ACT = {"manufacturing": "trading", "services": "trading", "trading": "services"}


def wrong_term(t):
    if t.get("days") is None:
        return dict(days=45, basis="acceptance", instrument="buyer_po")
    return dict(days=15 if t["days"] >= 30 else 45, basis=t.get("basis") or "acceptance",
                instrument=t.get("instrument"))


def faults_for(gold, fy):
    """Yield (fault_name, fact_name, faulty_fact). Each mimics a real LLM failure mode."""
    g = gold["facts"]
    yield "F1 invented quote", "category", dict(value=WRONG_CAT[g["category"]["value"]], source="udyam",
                                                  quote=f"{fy} | {WRONG_CAT[g['category']['value']].title()} | 01/04/2025")
    yield "F1 invented quote", "activity", dict(value=WRONG_ACT[g["activity"]["value"]], source="udyam",
                                                  quote=f"MAJOR ACTIVITY : {WRONG_ACT[g['activity']['value']].title()}")
    yield "F1 invented quote", "registration_date", dict(value="2019-01-01", source="udyam",
                                                           quote="DATE OF UDYAM REGISTRATION : 01/01/2019")
    wt = wrong_term(g["payment_term"]["value"])
    yield "F1 invented quote", "payment_term", dict(value=wt, source="po",
                                                      quote=f"Payment within {wt['days']} days of receipt of material.")
    yield "F2 wrong value, real quote", "category", dict(g["category"], value=WRONG_CAT[g["category"]["value"]])
    yield "F2 wrong value, real quote", "activity", dict(g["activity"], value=WRONG_ACT[g["activity"]["value"]])
    yield "F2 wrong value, real quote", "registration_date", dict(g["registration_date"], value="2019-01-01")
    yield "F2 wrong value, real quote", "payment_term", dict(g["payment_term"], value=wt)
    for n, dist in gold.get("distractors", {}).items():
        yield "F3 wrong clause, real quote", n, dict(dist)
    if g["objections"]["value"]:
        yield "F4 missed objection", "objections", dict(g["objections"], value=[])


def gold_facts(gold):
    return {k: dict(v, alternates=[]) for k, v in gold["facts"].items()}


def run_raw(path, facts):
    """'No guards' arm: trust the reader's values blindly, one engine run, always AUTO."""
    docs, ledger, gold = load_case(path)
    vals = {k: v["value"] for k, v in facts.items()}
    return [dict(invoice=r.invoice, decision="AUTO", disallowed=r.disallowed)
            for r in compute(ledger, vals, DEFAULT_POLICY, AS_OF)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--llm", action="store_true")
    args = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    R = dict()
    lines = ["# Evaluation report", "",
             f"{len(CASES)} synthetic vendor cases, "
             f"{sum(len(load_case(p)[1]['invoices']) for p in CASES)} invoices, FY 2025-26, audit cut-off {AS_OF}.", ""]

    # A ---------------------------------------------------------------------------
    a_rows, a_ok, a_n = [], 0, 0
    for p in CASES:
        docs, ledger, gold = load_case(p)
        facts = {k: v["value"] for k, v in gold["facts"].items()}
        for inv in ledger["invoices"]:
            exp = gold["expected"][inv["no"]]
            if exp["decision"] == "REVIEW":
                got = {pol: {r.invoice: r.disallowed for r in compute(
                    ledger, facts, dict(DEFAULT_POLICY, invoice_terms_are_agreement=pol), AS_OF)}[inv["no"]]
                       for pol in (True, False)}
                ok = got[True] == exp["if_policy_true"] and got[False] == exp["if_policy_false"]
            else:
                got = {r.invoice: r.disallowed for r in compute(ledger, facts, DEFAULT_POLICY, AS_OF)}[inv["no"]]
                ok = got == exp["disallowed"]
            a_ok += ok
            a_n += 1
            a_rows.append((ledger["case"], inv["no"], exp, got, ok))
    R["A"] = dict(correct=a_ok, total=a_n)
    lines += ["## A. Engine on hand-labelled facts", "",
              f"**{a_ok}/{a_n}** invoices match the hand-computed answer (C09 checked under both policy settings).", ""]

    # B ---------------------------------------------------------------------------
    b_fact = defaultdict(lambda: [0, 0])
    b_verdicts, b_detail = Counter(), []
    for p in CASES:
        docs, ledger, gold = load_case(p)
        rx = extract_regex.extract(docs, ledger["fy"], [i["no"] for i in ledger["invoices"]])
        for n, gv in gold["facts"].items():
            b_fact[n][1] += 1
            b_fact[n][0] += same_fact(n, rx[n]["value"], gv["value"])
        raw = run_raw(p, {k: dict(v, alternates=[]) for k, v in rx.items()})
        for inv, v in score(raw, gold["expected"]):
            b_verdicts[v] += 1
            if v != "correct":
                b_detail.append(f"{ledger['case']} {inv}: {v} ({gold['tests']})")
    R["B"] = dict(fact_accuracy={k: v for k, v in b_fact.items()}, verdicts=dict(b_verdicts), misses=b_detail)
    lines += ["## B. Regex baseline alone (no AI, no guards)", "",
              "| Fact | Correct |", "|---|---|"]
    lines += [f"| {k} | {v[0]}/{v[1]} |" for k, v in b_fact.items()]
    lines += ["", f"Outcomes: {dict(b_verdicts)}", "", "Where it went wrong:", ""]
    lines += [f"- {x}" for x in b_detail] + [""]

    # B2 --------------------------------------------------------------------------
    b2_verdicts, b2_detail = Counter(), []
    for p in CASES:
        docs, ledger, gold = load_case(p)
        rx = extract_regex.extract(docs, ledger["fy"], [i["no"] for i in ledger["invoices"]])
        out = run_case(p, rx, "regex", use_cross_check=True)
        for inv, v in score(out["decisions"], gold["expected"]):
            b2_verdicts[v] += 1
            if v != "correct":
                b2_detail.append(f"{ledger['case']} {inv}: {v}")
    R["B2"] = dict(verdicts=dict(b2_verdicts), misses=b2_detail)
    lines += ["## B2. Regex reader + all guards and cross-checks", "",
              f"Outcomes: {dict(b2_verdicts)}", "",
              "When the regex reader finds no evidence (term in words or Hindi, unparsed objection date) the "
              "guards treat the fact as unknown and the case goes to a human. Safe, but the human still has "
              "to read the document. When it confidently reads the wrong clause, nothing disagrees with it:", ""]
    lines += [f"- {x}" for x in b2_detail] + [""]

    # C ---------------------------------------------------------------------------
    c_verdicts, c_detail, c_runs = Counter(), [], {}
    for p in CASES:
        docs, ledger, gold = load_case(p)
        out = run_case(p, gold_facts(gold), "reference", use_cross_check=True)
        c_runs[ledger["case"]] = out
        for inv, v in score(out["decisions"], gold["expected"]):
            c_verdicts[v] += 1
            if v != "correct":
                piv = [x["fact"] for d in out["decisions"] if d["invoice"] == inv for x in d["pivotal"]]
                c_detail.append(f"{ledger['case']} {inv}: {v}; pivotal = {piv}")
    R["C"] = dict(verdicts=dict(c_verdicts), extra_reviews=c_detail)
    lines += ["## C. Correct reading + regex cross-check + guards", "",
              f"Outcomes: {dict(c_verdicts)} (C09 is SUPPOSED to go to review: the CA has not set the invoice-terms policy).", "",
              "Reviews triggered only because the regex reader disagreed (the price of the cross-check):", ""]
    lines += [f"- {x}" for x in c_detail if not x.startswith("C09")] + [""]
    with open(os.path.join(OUT, "reference_run.json"), "w", encoding="utf-8") as f:
        json.dump(c_runs, f, indent=1, default=str, ensure_ascii=False)

    # D ---------------------------------------------------------------------------
    arms = {"no guards (trust the reader)": None, "guards + sensitivity": False,
            "guards + sensitivity + cross-checks": True}
    d_tab = {a: Counter() for a in arms}
    d_by_fault = {a: defaultdict(Counter) for a in arms}
    d_silent = defaultdict(list)
    n_runs = 0
    for p in CASES:
        docs, ledger, gold = load_case(p)
        for fname, fact, faulty in faults_for(gold, ledger["fy"]):
            facts = gold_facts(gold)
            facts[fact] = dict(faulty, alternates=[])
            n_runs += 1
            for arm, xc in arms.items():
                decs = run_raw(p, facts) if xc is None else run_case(p, facts, "faulty", use_cross_check=xc)["decisions"]
                verdicts = [v for _, v in score(decs, gold["expected"])]
                worst = "SILENT_ERROR" if "SILENT_ERROR" in verdicts else ("review" if "review" in verdicts else "correct")
                d_tab[arm][worst] += 1
                d_by_fault[arm][fname][worst] += 1
                if worst == "SILENT_ERROR":
                    d_silent[arm].append(f"{ledger['case']} {fname} on {fact}")
    R["D"] = dict(runs=n_runs, by_arm={a: dict(c) for a, c in d_tab.items()},
                  by_fault={a: {f: dict(c) for f, c in v.items()} for a, v in d_by_fault.items()},
                  silent={a: v for a, v in d_silent.items()})
    lines += ["## D. Fault injection", "",
              f"{n_runs} runs: one injected error per run, on top of otherwise-correct facts. A run counts as a "
              "SILENT ERROR if any invoice gets a wrong rupee figure with no review flag. 'Cross-checks' = the regex "
              "reader as a second opinion + the NIC-code rule + the objection tripwire.", "",
              "| Arm | Correct, automatic | Sent to review (safe) | Silent error |", "|---|---|---|---|"]
    for a, c in d_tab.items():
        lines.append(f"| {a} | {c['correct']} | {c['review']} | {c['SILENT_ERROR']} |")
    lines += ["", "Silent errors by fault type:", "", "| Fault | " + " | ".join(arms) + " |",
              "|---|" + "---|" * len(arms)]
    for fname in sorted({f for a in d_by_fault for f in d_by_fault[a]}):
        cells = []
        for a in arms:
            c = d_by_fault[a][fname]
            cells.append(f"{c['SILENT_ERROR']}/{sum(c.values())}")
        lines.append(f"| {fname} | " + " | ".join(cells) + " |")
    lines += ["", "Remaining silent errors with every guard on:", ""]
    lines += [f"- {x}" for x in d_silent["guards + sensitivity + cross-checks"]] + [""]

    # E ---------------------------------------------------------------------------
    if args.llm:
        from msme_desk import extract_llm
        e_verdicts, e_fact, e_detail = Counter(), defaultdict(lambda: [0, 0]), []
        model = os.environ.get("OPENROUTER_MODEL")
        cache_dir = os.path.join(OUT, "llm_cache", (model or "none").replace("/", "_").replace(":", "_"))
        os.makedirs(cache_dir, exist_ok=True)
        for p in CASES:
            docs, ledger, gold = load_case(p)
            cp = os.path.join(cache_dir, ledger["case"] + ".json")
            if os.path.exists(cp):
                with open(cp, encoding="utf-8") as f:
                    lx = json.load(f)
            else:
                try:
                    lx = extract_llm.extract(docs, ledger)
                except Exception as e:      # an extraction failure is itself a result
                    lx = {"_error": str(e)}
                with open(cp, "w", encoding="utf-8") as f:
                    json.dump(lx, f, indent=1, ensure_ascii=False)
            for n, gv in gold["facts"].items():
                e_fact[n][1] += 1
                e_fact[n][0] += bool(lx.get(n)) and same_fact(n, (lx.get(n) or {}).get("value"), gv["value"])
            out = run_case(p, lx, "llm", use_cross_check=True)
            for inv, v in score(out["decisions"], gold["expected"]):
                e_verdicts[v] += 1
                if v != "correct":
                    e_detail.append(f"{ledger['case']} {inv}: {v}")
        R["E"] = dict(model=model, verdicts=dict(e_verdicts), fact_accuracy=dict(e_fact), misses=e_detail)
        lines += [f"## E. Live LLM ({model}) + guards + cross-check", "",
                  "| Fact | LLM correct |", "|---|---|"] + [f"| {k} | {v[0]}/{v[1]} |" for k, v in e_fact.items()]
        lines += ["", f"Outcomes: {dict(e_verdicts)}", ""] + [f"- {x}" for x in e_detail] + [""]

    with open(os.path.join(OUT, "eval_results.json"), "w", encoding="utf-8") as f:
        json.dump(R, f, indent=1, default=str)
    with open(os.path.join(OUT, "eval_report.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("\n".join(lines))


if __name__ == "__main__":
    main()
