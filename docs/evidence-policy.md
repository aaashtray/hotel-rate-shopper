# Evidence policy

Never invent HTML, screenshots, XHR or observed prices. User examples live under synthetic/.
observed/ is empty except its explanatory README. M1 raw evidence is the original synthetic
JSON bytes, saved before parsing, with SHA-256 and a path in each RawObservation.
All fabricated supplementary values are described in fixture assumptions.
A content-addressed file is never overwritten; unexpected differing content raises integrity failure.
Normalized offers and historical reports are independent of the evidence file.

Future captures must record requested/final URL, UTC-aware timestamp, scenario, source fragments,
auth state, connector version, HTTP status, and available permitted JSON/HTML/text/screenshots.
Missing artifacts remain null with explanations where applicable. Capture only permitted public data.
Do not bypass protection or send bookings/payments. Prefer official API/feed, public page JSON,
structured page data, then DOM and browser fallback.
Before observed fixtures enter Git, manually sanitize personal data, cookies, headers, credentials,
private URLs and profiles. `.gitignore` is a guard, not a sanitization system.
Runtime reports/evidence are ignored. Explicitly authorized sanitized observed fixtures can be versioned.
M1 has no credential configuration, network access or live capture implementation.

M2 update: one real Yandex CAPTCHA capture is stored locally; a sanitized metadata/title projection
is in observed/. Full HTML is ignored and remains separate from normalized reports. See m2-capture.md.
