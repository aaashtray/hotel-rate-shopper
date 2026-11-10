# Roadmap

- M0: product/data/matching/evidence contracts and permanent AGENTS.md invariants.
- M1: offline synthetic vertical slice with CLI, JSON/CSV, history, replay and tested gates.
- M2: select one authorized stable real source; capture evidence and implement its deterministic
  parser with observed fixture contracts. Verify URL/form scenario, hotel mapping, capture freshness,
  completeness of tariff terms and taxes before producing any real gap. Do not invent selectors.
- M3: remaining platforms, full top-10, scenario scheduler, bounded retries, run metrics and review triage.
- M4: PostgreSQL with migrations, API and compact review dashboard after domain stability.
- M5: scale only after measuring extraction accuracy, stability, review effort and signal utility.

Deferred tests: website parser contracts, layout regressions and opt-in live smoke tests require
real observed captures and an implemented connector. M1 tests cover the domain import contract
for all three platform labels, not their website schemas.

M2 status on 2026-11-10: partial. Real reconnaissance captured CAPTCHA; capture/replay and blocker
contracts implemented. Successful tariff extraction blocked by public source access restrictions.
