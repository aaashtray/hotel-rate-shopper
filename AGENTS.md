# Hotel Rate Shopper — permanent engineering invariants

- Prices, dates, availability and access conditions come from evidence; never infer them with AI.
- Keep raw evidence separate and immutable. Never fabricate observed pages or website results.
- Synthetic fixtures must explicitly identify provenance and all invented conditions.
- Public, member, mobile, bank and crossed-out totals stay separate. Ozon bank price is not public.
- All money uses Decimal, whole-stay RUB totals. Reject floats at ingestion.
- No confident hotel/scenario/tariff match means no absolute or percentage gap.
- User explicitly authorized a separate preliminary minimum-price mode on 2026-11-10.
  It may show exploratory gaps for different tariffs, always labeled as requiring review.
  Never promote those gaps to strict matches; exclude known extra fees, conflicting registry
  IDs and explicit mapping disputes. User subsequently requested statistics including Yandex:
  keep all-collected, no-bank/corporate, and public-only price scopes separate and labeled.
- Unknown is not equal to unknown. Cancellation deadlines and payment timing matter.
- Distinguish SOLD_OUT, CAPTCHA, rate limit, missing hotel, missing price and parsing errors.
- Business run status is independent of process completion. Zero valid observations is FAILED.
- Do not bypass CAPTCHA, authentication or rate limits; never book or pay.
- Do not collect private cookies/tokens/profiles or commit runtime evidence without sanitizing.
- Keep connector, extraction, normalization, matching, quality and persistence separate.
- M1 stays offline. User now authorizes multi-source capture, local HTML and Excel reports. User authorized public GitHub Pages publication on 2026-11-10; publish a sanitized snapshot and source. User explicitly authorized publishing ALL collected public, personal, corporate and bank prices on 2026-11-10; preserve access labels and keep conditional statistics separate from the public baseline and strict matches. Scheduled collection remains a later task. No repricing or heavy infrastructure.
- Run pytest, Ruff and strict mypy before declaring completion; record actual results.
- No push/publication or local commits unless explicitly requested.
