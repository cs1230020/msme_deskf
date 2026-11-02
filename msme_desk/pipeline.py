"""End-to-end run for one vendor folder."""
import json
import os
import re
from datetime import date

from . import extract_regex, verify
from .sensitivity import FACTS, decide

DEFAULT_POLICY = dict(exclude_capital=True, invoice_terms_are_agreement=None)
AS_OF = date(2026, 9, 30)      # tax-audit cut-off: payments known up to this date


def load_case(path):
    docs = {}
    for name in ("udyam", "po", "invoice", "notes"):
        p = os.path.join(path, f"{name}.txt")
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                docs[name] = f.read()
    with open(os.path.join(path, "ledger.json"), encoding="utf-8") as f:
        ledger = json.load(f)
    gold = None
    gp = os.path.join(path, "gold.json")
    if os.path.exists(gp):
        with open(gp, encoding="utf-8") as f:
            gold = json.load(f)
    return docs, ledger, gold


def as_candidates(facts: dict, origin: str) -> dict:
    """Extractor output -> name: [primary, *alternates], each tagged with where it came from."""
    out = {}
    for n in FACTS:
        f = facts.get(n)
        if not f:
            out[n] = []
            continue
        prim = {k: f.get(k) for k in ("value", "source", "quote")}
        prim["_origin"] = origin
        alts = [dict(a, _origin=origin + ":alt") for a in (f.get("alternates") or [])]
        out[n] = [prim] + alts
    return out


def cross_check(cands: dict, baseline: dict) -> dict:
    """Add the regex baseline's reading wherever it disagrees with every existing candidate."""
    merged = {}
    for n in FACTS:
        have = {verify.key(c.get("value")) for c in cands.get(n, [])}
        b = baseline.get(n)
        merged[n] = list(cands.get(n, []))
        if b is not None and verify.key(b.get("value")) not in have:
            merged[n].append(dict(b, _origin="regex"))
    return merged


TRADE_NIC_DIVISIONS = {"45", "46", "47"}      # NIC-2008 section G: wholesale and retail trade
OBJECTION_WORDS = re.compile(r"reject|complain|defect|objection|short[- ]suppl|not accepted", re.I)


def nic_rule(docs, cands):
    """Rule APP-02 in code: if EVERY NIC code on the certificate is wholesale/retail trade, the
    supplier is a trader whatever 'Major Activity' says. If only some are, add 'trading' as a
    reading and let the sensitivity check decide whether it matters.
    (Added after fault injection showed both readers trusting 'Major Activity : Services'.)"""
    lines = [ln for ln in docs.get("udyam", "").splitlines() if re.match(r"\s*\d+\s*\|\s*\d{5}\s*-", ln)]
    codes = [(re.search(r"\|\s*(\d{5})", ln).group(1), ln.strip()) for ln in lines]
    trade = [(c, ln) for c, ln in codes if c[:2] in TRADE_NIC_DIVISIONS]
    if not trade:
        return cands
    cand = dict(value="trading", source="udyam", quote=trade[0][1], _origin="nic-rule")
    if len(trade) == len(codes):
        cands["activity"] = [cand]
    elif "trading" not in {c.get("value") for c in cands.get("activity", [])}:
        cands["activity"] = cands.get("activity", []) + [cand]
    return cands


def objection_tripwire(docs, ledger, cands):
    """Recall net for the one fact no quote-check can catch: an objection the reader MISSED.
    Any notes line with objection words that names an invoice not covered by an extracted
    objection -> that invoice is flagged. (Disallowance can only fall when acceptance moves
    later, so the flag matters only when the primary reading disallows something.)"""
    covered = {o.get("invoice") for c in cands.get("objections", []) for o in (c.get("value") or [])}
    hits = {}
    for ln in docs.get("notes", "").splitlines():
        if OBJECTION_WORDS.search(ln):
            for inv in ledger["invoices"]:
                if inv["no"] in ln and inv["no"] not in covered:
                    hits.setdefault(inv["no"], ln.strip())
    return hits


def run_case(path, facts: dict, origin: str, use_cross_check=True, policy=None, as_of=AS_OF):
    docs, ledger, _ = load_case(path)
    cands = as_candidates(facts, origin)
    if use_cross_check:
        base = extract_regex.extract(docs, ledger["fy"], [i["no"] for i in ledger["invoices"]])
        cands = cross_check(cands, base)
        cands = nic_rule(docs, cands)
    trip = objection_tripwire(docs, ledger, cands) if use_cross_check else {}
    out = decide(ledger, docs, cands, policy or DEFAULT_POLICY, as_of)
    for dct in out["decisions"]:
        if dct["invoice"] in trip and dct["primary"]["disallowed"] > 0 and dct["decision"] == "AUTO":
            dct["decision"], dct["disallowed"] = "REVIEW", None
            dct["pivotal"].append(dict(fact="objections", readings=[], tripwire=trip[dct["invoice"]]))
    out["tripwire"] = trip
    out["case"] = ledger["case"]
    out["supplier"] = ledger["supplier"]
    out["origin"] = origin
    return out
