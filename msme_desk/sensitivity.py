"""Decision-relevant uncertainty.

Instead of trusting a model's confidence score, we enumerate every reading that survived
verification (the LLM's, its alternates, the regex baseline's when it disagrees, and the
whole domain when the primary reading failed a guard), run the deterministic engine on every
combination, and look at the rupee outcome:

    all combinations give the same disallowance  -> AUTO   (uncertainty did not matter)
    they differ                                  -> REVIEW (one precise question + rupee impact)

A human is asked only when the answer to their question changes the number.
"""
import itertools

from . import verify
from .engine import compute

DOMAIN = {
    "category": ["micro", "small", "medium", "none"],
    "activity": ["manufacturing", "services", "trading"],
    "registration_date": ["2000-01-01", None],
    "payment_term": [dict(days=None, basis=None, instrument="none"),
                     dict(days=0, basis="acceptance", instrument="buyer_po"),
                     dict(days=45, basis="acceptance", instrument="buyer_po")],
    "objections": [[]],
}
FACTS = ["category", "activity", "registration_date", "payment_term", "objections"]
MAX_SCENARIOS = 2000


def _dedupe(vals):
    seen, out = set(), []
    for v in vals:
        k = verify.key(v)
        if k not in seen:
            seen.add(k)
            out.append(v)
    return out


def _expand_term(v):
    """A term anchored on an undated event ('other') is bounded by the earliest and latest
    possible due dates; disallowance is monotone in the due date, so the two bounds suffice."""
    if v and v.get("basis") == "other" and v.get("days") is not None:
        return [dict(v, basis="acceptance"), dict(days=45, basis="acceptance", instrument=v.get("instrument"))]
    return [v]


def resolve(name, cands, docs, fy):
    log, verified = [], []
    for c in cands:
        fails = verify.check(name, c, docs, fy)
        log.append(dict(value=c.get("value"), source=c.get("source"), quote=c.get("quote"),
                        origin=c.get("_origin", "?"), fails=fails))
        if not fails:
            verified.append(c["value"])
    primary_failed = bool(log[0]["fails"]) if log else True
    values = _dedupe(verified)
    if primary_failed or not values:
        values = _dedupe(values + DOMAIN[name])
    if name == "payment_term":
        values = _dedupe([x for v in values for x in _expand_term(v)])
    return values, log, primary_failed


def decide(ledger, docs, cand_facts, policy, as_of):
    """cand_facts: name -> list of candidate dicts (first = primary reading)."""
    fy = ledger["fy"]
    options, logs, tripped = {}, {}, []
    for n in FACTS:
        options[n], logs[n], failed = resolve(n, cand_facts.get(n, []), docs, fy)
        if failed:
            tripped.append(n)
    pol_opts = [policy.get("invoice_terms_are_agreement")]
    if pol_opts[0] is None:
        pol_opts = [False, True]

    names = FACTS + ["_policy"]
    choices = [options[n] for n in FACTS] + [pol_opts]
    n_scen = 1
    for c in choices:
        n_scen *= len(c)
    if n_scen > MAX_SCENARIOS:
        raise RuntimeError(f"{n_scen} scenarios - too uncertain to enumerate; route whole vendor to review")

    def run(combo):
        facts = dict(zip(FACTS, combo[:-1]))
        pol = dict(policy, invoice_terms_are_agreement=combo[-1])
        return {r.invoice: r for r in compute(ledger, facts, pol, as_of)}

    primary = tuple(c[0] for c in choices)
    base = run(primary)
    outcomes = {inv: {} for inv in base}
    for combo in itertools.product(*choices):
        res = run(combo)
        for inv, r in res.items():
            outcomes[inv].setdefault(r.disallowed, combo)

    decisions = []
    for inv, r0 in base.items():
        amounts = sorted(outcomes[inv])
        pivotal = []
        for i, n in enumerate(names):
            if len(choices[i]) < 2:
                continue
            seen = {}
            for v in choices[i]:
                combo = list(primary)
                combo[i] = v
                seen.setdefault(run(tuple(combo))[inv].disallowed, v)
            if len(seen) > 1:
                pivotal.append(dict(fact=n, readings=[dict(value=v, disallowed=a) for a, v in seen.items()]))
        if len(amounts) > 1 and not pivotal:
            pivotal.append(dict(fact="combination", readings=[]))
        review = len(amounts) > 1 or bool(r0.flags)
        decisions.append(dict(
            invoice=inv, decision="REVIEW" if review else "AUTO",
            disallowed=None if review else r0.disallowed,
            range=[amounts[0], amounts[-1]],
            primary=dict(disallowed=r0.disallowed, acceptance=str(r0.acceptance), due=str(r0.due),
                         applicable=r0.applicable, late=r0.late, trail=r0.trail, flags=r0.flags),
            pivotal=pivotal, scenarios=n_scen))
    return dict(decisions=decisions, evidence=logs, guards_tripped=tripped,
                options={n: options[n] for n in FACTS}, policy_options=pol_opts)
