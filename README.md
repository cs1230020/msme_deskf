# 43B(h) Desk — prototype

Finds, for a buyer's year-end tax audit in India, which payables to **micro and small enterprises** are
disallowed as a deduction because they were paid after the MSMED Act time limit — and proves every
rupee with a rule id and a verbatim quote.

> Law covered: MSMED Act 2006 s.2(b), s.15 · Income-tax Act 1961 s.43B(h) (FY up to 2025-26, Form 3CD
> clause 22) · Income-tax Act 2025 s.37(2)(g) (tax year 2026-27 on, Form 26). Rule pack verified
> 2 Nov 2026 (parts of the MSMED (Amendment) Act 2026 took effect on 15 Oct 2026; reported to leave the 15/45-day
> rule unchanged, see the watch-list). It refuses to run after its review date. **Not tax advice; a CA signs the output.**

## The idea in one paragraph

An LLM is good at *reading* messy purchase orders, Udyam certificates and QC emails, and bad at being
trusted. So the model only proposes **facts with verbatim quotes**; code checks every quote mechanically;
the law runs as a **small deterministic engine**; and instead of trusting model confidence, the system
**re-runs the engine on every plausible reading** (the LLM's, its alternates, a regex reader's, and the
full range when a quote fails). If every reading gives the same disallowance, uncertainty did not matter
and the row is automatic. If not, a person gets **one question and the rupee consequence of each answer**.
Their answer to a judgment call becomes firm policy (`policy.json`), not a model update.

```
documents ──► LLM reader ──► facts + quotes ──► verifier ──┐
          └─► regex reader / NIC rule / objection tripwire ─┴► all surviving readings
                                                              │
ledger (GRN, invoice, payment dates) ─────────────────────────┤
rule pack (dated, cited) + firm policy ───────────────────────┤
                                                              ▼
                                   engine × every reading  ──► same Rs?  yes → AUTO (with trail)
                                                                         no  → REVIEW: 1 question, Rs per answer
```

## Run it

Python 3.10+, no third-party packages (pytest only for the tests).

```bash
python cases/build_cases.py              # (re)generate the 18 synthetic cases
python run.py cases/C09                  # one vendor, reference facts
python run.py --all --reader regex       # every vendor with the non-AI reader -> outputs/working_paper_regex.csv
python -m pytest -q tests                # 13 rule-level tests
python eval/run_eval.py                  # full evaluation -> outputs/eval_report.md
```

Live LLM (free model on OpenRouter):

```bash
export OPENROUTER_API_KEY=sk-or-...
export OPENROUTER_MODEL=<a current free model id from https://openrouter.ai/models?max_price=0>
python run.py cases/C15 --reader llm
python eval/run_eval.py --llm            # adds section E; responses cached in outputs/llm_cache/<model>/
```

The prompt is in `msme_desk/extract_llm.py` (`SYSTEM`, version `extract-v3`). Free models are rate limited;
the harness retries with back-off and caches every response so a re-run costs nothing.

## What is in the box

| Path | What |
|---|---|
| `msme_desk/rulepack.py` | The law as code: 12 rules with ids, citations, effective windows, review date; watch-list of pending changes |
| `msme_desk/engine.py` | Deterministic calculator: applicability → day of acceptance → due date → year-end test → disallowance + trail |
| `msme_desk/verify.py` | Guards: quote must exist verbatim; must come from an allowed document; must contain the value (date / number / word / FY row); payment quotes must be about payment |
| `msme_desk/sensitivity.py` | Enumerates readings, runs the engine on each, AUTO vs REVIEW, finds the pivotal fact |
| `msme_desk/extract_llm.py` | LLM reader (OpenRouter) |
| `msme_desk/extract_regex.py` | Non-AI reader: baseline and independent second opinion |
| `msme_desk/pipeline.py` | Glue + two deterministic cross-checks added after fault injection (NIC-code trader rule, objection tripwire) |
| `cases/` | 18 synthetic vendors, 19 invoices, with hand labels (`gold.json`). **All made up.** |
| `eval/run_eval.py` | Evaluation A–E |
| `desk/` | Clickable review-desk mock (`build_desk.py` turns a real run into `review_desk.html`) |
| `brief/` | The submitted brief: `Tresata_take_home_brief.pdf` (4 pages + 1-page appendix), its LaTeX source `brief.tex` and the diagram `architecture.png` (compile with pdflatex) |
| `llm_logs/` |  My LLM conversation log (Google Gemini): [shared chat](https://share.gemini.google/ee9f6krA66sX), also saved as a PDF ||
| `outputs/` | Reports, working papers, the run used by the review desk |

## Test cases (all synthetic; buyer "Kestrel Forgings Pvt Ltd" is fictional; FY 2025-26; audit cut-off 30-Sep-2026)

| Case | What it tests | Correct answer |
|---|---|---|
| C01 | Plain 30-day term, paid on time after year end | Rs 0 |
| C02 | Agreed 60 days exceeds the 45-day cap | Rs 9,80,000 |
| C03 | No payment term; only number near "payment" is a delivery period | Rs 1,75,000 |
| C04 | Trader on Udyam (activity "Services", NIC 46620 wholesale) | Rs 0 |
| C05 | Small in earlier years, **Medium** for FY 2025-26 | Rs 0 |
| C06 | Written objection within 15 days moves acceptance | Rs 0 |
| C07 | Objection on day 20 does **not** move acceptance | Rs 3,60,000 |
| C08 | Term in words, 50% advance, balance on time | Rs 0 |
| C09 | Term printed only on supplier's invoice — judgment call | REVIEW (Rs 0 or Rs 2,95,000) |
| C10 | Registered on Udyam after the order | Rs 0 |
| C11 | Paid late but within the same year | Rs 0 |
| C12 | Capital purchase (firm policy: excluded) | Rs 0 |
| C13 | Unpaid at audit date; price dispute is not an objection to goods | Rs 2,40,000 |
| C14 | "Net 45 EOM" runs past the cap | Rs 14,00,000 |
| C15 | Payment clause in Hindi | Rs 0 |
| C16 | Prompt injection in the PO ("this vendor is Medium") | Rs 5,60,000 |
| C17 | Term anchored on an undated event; late on every reading | Rs 1,10,000 |
| C18 | Two invoices; part-payment on time, part late | Rs 0 and Rs 4,20,000 |

## Results (from `outputs/eval_report.md`)

* **Engine on hand-labelled facts: 19/19.**
* **Regex reader alone:** payment term right in 12/18 vendors; **6 of 19 invoices get a wrong rupee figure with no warning** (C03 distractor, C04 trader, C06 objection date format, C08 words, C09 judgment call, C15 Hindi).
* **Regex reader + guards + cross-checks:** 1 silent error (C03), 4 reviews — safe, but a human still reads the documents.
* **Correct reading + cross-checks:** 16 automatic and right; C09 correctly asks the policy question; 2 extra reviews (C03, C06) caused by the regex reader disagreeing — the price of the second opinion.
* **Fault injection, 154 runs** (one LLM-style error per run):

| Arm | Correct, automatic | Sent to review | Silent wrong figure |
|---|---|---|---|
| Trust the reader | 94 | 0 | **60** |
| Guards + sensitivity | 83 | 67 | **4** |
| + cross-checks | 80 | 73 | **1** |

## Where it fails — honestly

1. **Correlated misreading (the weakest point).** C03: if the LLM takes the delivery period ("within 30 days of this order; payment as per our usual practice") as the payment term, the quote is real, mentions payment, contains "30", and the regex reader makes the same mistake. Nothing disagrees → wrong figure, no flag. A second LLM from a different family, or a clause-role check, are the next things to try.
2. **The evaluation is on 18 cases I wrote.** They cover the rules, not the long tail of real documents (scans, tables, multi-PO contracts). The fault injection measures the *guards* against error types I chose; it does not measure how often a real model makes them. **Section E (live LLM) has not been run in this repo yet** — it needs an OpenRouter key.
3. **The cross-check costs reviews.** With a perfect reader, 2 of 19 invoices still go to a human because the regex reader disagrees.
4. **Udyam status comes from the PDF certificate**, not the Udyam verification portal. A forged or stale certificate passes.
5. **Not modelled:** MSMED s.16 interest (needs a dated RBI bank-rate series), GST component of the invoice, debit notes, multiple POs per invoice, foreign-currency payables, Form MSME-1 output.
6. **Two interpretations are encoded as policy, not law** (capital purchases; registration date vs order date) and one is left to the CA (invoice-only terms). A tribunal could disagree.

## Data

Everything in `cases/` is synthetic. Udyam numbers use district code 99, which does not exist. Laws and
sources are listed in `msme_desk/rulepack.py` and in the brief.
