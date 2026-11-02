"""43B(h) Desk - evidence-first checker for tax disallowance of late payments to
micro and small enterprises (India: MSMED Act 2006 s.15 + Income-tax Act 1961 s.43B(h) /
Income-tax Act 2025 s.37(2)(g)).

Layers (each in its own module, so the exact parts never touch the probabilistic ones):
  extract_llm / extract_regex  -> candidate facts, each with a verbatim quote   (probabilistic)
  verify                       -> mechanical checks on every quote                (deterministic)
  rulepack + engine            -> dated law as code, computes the disallowance   (deterministic)
  sensitivity                  -> re-runs the engine over every plausible reading;
                                  escalates only when the rupee outcome changes    (deterministic)
"""
__version__ = "0.1.0"
