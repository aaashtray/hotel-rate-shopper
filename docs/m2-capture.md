# M2 — partial implementation, blocked on accessible tariff data

## Observed facts

2026-11-10 16:11 Moscow: public Otello Savoy URL redirected to Sber ID.
Yandex Savoy URL https://travel.yandex.ru/hotels/moscow/savoi/ redirected to /showcaptcha.
Final HTTP status was 200; exact title was «Вы не робот?». Capture timestamp:
2026-11-10T13:11:51.378819+00:00. No successful tariff extraction is claimed.
Search was used only to discover hotel page URLs, never to source prices.

The reconnaissance urllib request followed ordinary redirects before detecting the challenge.
The implemented httpx connector is stricter: one request, redirects never followed, no retries,
no cookie jar persisted, no login, explicit UA, 20-second timeout, 5 MiB decoded-body limit.
No additional live request was made after detecting CAPTCHA. MockTransport responses are synthetic.

## Implemented flow

Public GET → content-hashed local HTML + observed manifest → deterministic classification
→ status-only normalization → existing quality gates → immutable SQLite report and JSON.
Capture manifest records original source time, requested scenario, safe URLs, status, hash,
connector version and relative raw path. URL queries are stripped from persisted URL fields;
allowed request scenario parameters are retained separately as unverified requested_query.
Redirect challenge/auth parameters, response headers, Set-Cookie and credentials are not persisted.
Original HTML remains local and ignored; do not commit it without further sanitization.
The sanitized observed fixture contains exact extracted title and metadata, not reconstructed HTML.

Replay verifies SHA-256 and confines raw paths to the capture directory. The parser version
is part of the historical run ID. Status-only results are not counted as extracted offers.
A challenge produces FAILED with zero offers and zero matches. A generic 404 is not evidence
that a hotel was not found; a generic 403 is not automatically CAPTCHA. Unsupported successful
HTML is PARSE_ERROR. Rate-limited and auth responses are separate states.

## Known limits / completion gate

M2 is not complete. Hotel identity, scenario echo, tariff schema, public access, whole-stay total,
taxes and room conditions remain unverified. The connector accepts a hotel target to satisfy
its interface, but never asserts that the returned page identifies that hotel.
It does not fabricate query parameter semantics or infer availability from a search result.
No HTML/XHR offer parser can be validated until an accessible real sample is available.
No cross-source or cross-time price matching is performed by the observed pipeline.
M1 remains unchanged as a separate synthetic arithmetic regression suite.

To complete M2, obtain an authorized API/feed or an accessible real public tariff response,
then add its observed parser contract and only enable offer emission after scenario/identity/
public access/tax and cancellation evidence checks. If the site still blocks automated access,
use an authorized partner feed or a manually supplied sanitized export rather than bypassing it.
