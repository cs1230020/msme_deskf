# Evaluation report

18 synthetic vendor cases, 19 invoices, FY 2025-26, audit cut-off 2026-09-30.

## A. Engine on hand-labelled facts

**19/19** invoices match the hand-computed answer (C09 checked under both policy settings).

## B. Regex baseline alone (no AI, no guards)

| Fact | Correct |
|---|---|
| category | 17/18 |
| activity | 17/18 |
| registration_date | 18/18 |
| payment_term | 12/18 |
| objections | 17/18 |

Outcomes: {'correct': 13, 'SILENT_ERROR': 6}

Where it went wrong:

- C03 JPM/045: SILENT_ERROR (No written payment term; the only number near 'payment' is a delivery period (distractor).)
- C04 BST/2290: SILENT_ERROR (Trader registered on Udyam (activity shown as 'Services'; NIC code is wholesale trade) - outside s.15.)
- C06 KR/2231: SILENT_ERROR (Written objection within 15 days moves the day of acceptance to the day it is removed.)
- C08 OSE/118: SILENT_ERROR (Term written in words, with an advance; only the balance is outstanding at year end.)
- C09 LPW/2602: SILENT_ERROR (Term appears ONLY on the supplier's own invoice. Is that a 'written agreement'? A judgment call for the CA.)
- C15 GWP/4417: SILENT_ERROR (Payment clause written in Hindi.)

## B2. Regex reader + all guards and cross-checks

Outcomes: {'correct': 15, 'SILENT_ERROR': 1, 'review': 3}

When the regex reader finds no evidence (term in words or Hindi, unparsed objection date) the guards treat the fact as unknown and the case goes to a human. Safe, but the human still has to read the document. When it confidently reads the wrong clause, nothing disagrees with it:

- C03 JPM/045: SILENT_ERROR
- C06 KR/2231: review
- C08 OSE/118: review
- C15 GWP/4417: review

## C. Correct reading + regex cross-check + guards

Outcomes: {'correct': 17, 'review': 2} (C09 is SUPPOSED to go to review: the CA has not set the invoice-terms policy).

Reviews triggered only because the regex reader disagreed (the price of the cross-check):

- C03 JPM/045: review; pivotal = ['payment_term']
- C06 KR/2231: review; pivotal = ['objections']

## D. Fault injection

154 runs: one injected error per run, on top of otherwise-correct facts. A run counts as a SILENT ERROR if any invoice gets a wrong rupee figure with no review flag. 'Cross-checks' = the regex reader as a second opinion + the NIC-code rule + the objection tripwire.

| Arm | Correct, automatic | Sent to review (safe) | Silent error |
|---|---|---|---|
| no guards (trust the reader) | 94 | 0 | 60 |
| guards + sensitivity | 83 | 67 | 4 |
| guards + sensitivity + cross-checks | 80 | 73 | 1 |

Silent errors by fault type:

| Fault | no guards (trust the reader) | guards + sensitivity | guards + sensitivity + cross-checks |
|---|---|---|---|
| F1 invented quote | 27/72 | 1/72 | 0/72 |
| F2 wrong value, real quote | 27/72 | 0/72 | 0/72 |
| F3 wrong clause, real quote | 5/8 | 2/8 | 1/8 |
| F4 missed objection | 1/2 | 1/2 | 0/2 |

Remaining silent errors with every guard on:

- C03 F3 wrong clause, real quote on payment_term
