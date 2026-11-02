"""Builds desk/review_desk.html (the clickable review-desk mock) from a real pipeline run.

    python desk/build_desk.py            # reference reader + cross-checks (default)
"""
import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from msme_desk.pipeline import load_case, run_case          # noqa: E402
from msme_desk.report import questions                       # noqa: E402
from msme_desk.rulepack import PACK, RULES, WATCH            # noqa: E402

cases = []
for p in sorted(glob.glob(os.path.join(ROOT, "cases", "C*"))):
    docs, ledger, gold = load_case(p)
    facts = {k: dict(v, alternates=[]) for k, v in gold["facts"].items()}
    out = run_case(p, facts, "reader", use_cross_check=True)
    for d in out["decisions"]:
        d["questions"] = questions(d)
        d["primary"]["trail"] = [list(t) for t in d["primary"]["trail"]]
    cases.append(dict(case=out["case"], supplier=out["supplier"], tests=gold["tests"],
                      docs=docs, ledger=ledger, decisions=out["decisions"],
                      evidence=out["evidence"], tripwire=out.get("tripwire", {})))

data = dict(pack={k: str(v) for k, v in PACK.items()}, rules=RULES, watch=WATCH, cases=cases)
blob = json.dumps(data, ensure_ascii=False, default=str).replace("</", "<\\/")
with open(os.path.join(ROOT, "desk", "template.html"), encoding="utf-8") as f:
    html = f.read()
with open(os.path.join(ROOT, "desk", "review_desk.html"), "w", encoding="utf-8") as f:
    f.write(html.replace("/*__DATA__*/null", blob))
print("wrote desk/review_desk.html", len(blob), "bytes of data")
