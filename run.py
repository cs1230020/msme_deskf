"""Command line entry point.

  python run.py cases/C09                    # one vendor, reference facts (stand-in for a perfect reader)
  python run.py cases/C09 --reader regex     # the non-AI reader
  python run.py cases/C09 --reader llm       # live LLM (OPENROUTER_API_KEY, OPENROUTER_MODEL)
  python run.py --all --reader regex         # every case; writes outputs/working_paper_<reader>.csv
  python run.py cases/C09 --policy policy.json
"""
import argparse
import csv
import glob
import json
import os
from datetime import date

from msme_desk import extract_regex, rulepack
from msme_desk.pipeline import DEFAULT_POLICY, load_case, run_case
from msme_desk.report import questions, rupees, text_summary


def facts_for(path, reader):
    docs, ledger, gold = load_case(path)
    if reader == "reference":
        return {k: dict(v, alternates=[]) for k, v in gold["facts"].items()}
    if reader == "regex":
        return extract_regex.extract(docs, ledger["fy"], [i["no"] for i in ledger["invoices"]])
    if reader == "llm":
        from msme_desk import extract_llm
        return extract_llm.extract(docs, ledger)
    raise ValueError(reader)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("case", nargs="?")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--reader", default="reference", choices=["reference", "regex", "llm"])
    ap.add_argument("--policy")
    ap.add_argument("--no-cross-check", action="store_true")
    ap.add_argument("--allow-stale", action="store_true")
    a = ap.parse_args()

    stale = rulepack.check_fresh(date.today(), a.allow_stale)
    policy = dict(DEFAULT_POLICY)
    if a.policy:
        with open(a.policy) as f:
            policy.update(json.load(f))
    paths = sorted(glob.glob("cases/C*")) if a.all else [a.case]
    rows, outs = [], []
    for p in paths:
        out = run_case(p, facts_for(p, a.reader), a.reader, use_cross_check=not a.no_cross_check, policy=policy)
        out["rulepack"] = dict(rulepack.PACK, stale=stale)
        outs.append(out)
        print(text_summary(out) + ("\n  !! RULE PACK PAST REVIEW DATE" if stale else "") + "\n")
        for d in out["decisions"]:
            rows.append(dict(case=out["case"], supplier=out["supplier"], invoice=d["invoice"],
                             decision=d["decision"], disallowed=d["disallowed"],
                             low=d["range"][0], high=d["range"][1],
                             acceptance=d["primary"]["acceptance"], due=d["primary"]["due"],
                             rules=" ".join(r for r, _ in d["primary"]["trail"]),
                             question=" | ".join(q["question"] for q in questions(d))))
    if a.all:
        os.makedirs("outputs", exist_ok=True)
        with open(f"outputs/working_paper_{a.reader}.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
        with open(f"outputs/desk_{a.reader}.json", "w", encoding="utf-8") as f:
            json.dump(outs, f, indent=1, default=str, ensure_ascii=False)
        auto = [r for r in rows if r["decision"] == "AUTO"]
        print(f"{len(rows)} invoices: {len(auto)} automatic "
              f"(total disallowed {rupees(sum(r['disallowed'] for r in auto))}), "
              f"{len(rows) - len(auto)} to review.")


if __name__ == "__main__":
    main()
