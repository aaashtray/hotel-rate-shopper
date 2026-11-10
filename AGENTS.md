# Hotel Rate Shopper — permanent engineering invariants

- Prices, dates, availability and access conditions come from evidence; never infer them with AI.
- Keep raw evidence separate and immutable. Never fabricate observed pages or website results.
- Synthetic fixtures must explicitly identify provenance and all invented conditions.
- Public, member, mobile, bank and crossed-out totals stay separate. Ozon bank price is not public.
- All money uses Decimal, whole-stay RUB totals. Reject floats at ingestion.
- No confident hotel/scenario/tariff match means no absolute or percentage gap.
- User explicitly authorized a separate preliminary public-minimum mode on 2026-11-10.
  It may show exploratory gaps for different tariffs, always labeled as requiring review.
  Never promote those gaps to strict matches; exclude personal/bank prices, known extra
  fees, conflicting registry IDs and explicit mapping disputes.
- Unknown is not equal to unknown. Cancellation deadlines and payment timing matter.
- Distinguish SOLD_OUT, CAPTCHA, rate limit, missing hotel, missing price and parsing errors.
- Business run status is independent of process completion. Zero valid observations is FAILED.
- Do not bypass CAPTCHA, authentication or rate limits; never book or pay.
- Do not collect private cookies/tokens/profiles or commit runtime evidence without sanitizing.
- Keep connector, extraction, normalization, matching, quality and persistence separate.
- M1 stays offline. User now authorizes multi-source capture, local HTML and Excel reports. User authorized public GitHub Pages publication on 2026-11-10; publish a sanitized public-only snapshot and source. Scheduled collection remains a later task. No repricing or heavy infrastructure.
- Run pytest, Ruff and strict mypy before declaring completion; record actual results.
- No push/publication or local commits unless explicitly requested.
