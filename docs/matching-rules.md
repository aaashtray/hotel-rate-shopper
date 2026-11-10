# Matching rules v1

Hard gates: Otello reference versus a different platform; resolved same hotel; exact scenario
signature and IDs; RUB; available positive public whole-stay total; verified unauthenticated access;
all-in taxes; field evidence; complete tariff terms. Special conditions/access require review.
Free cancellation additionally requires an evidenced matching deadline. Unknown terms cannot match.

Weights: room category .25, meal .20, cancellation .20, payment .15, bed .15, area .05.
Begin at 1, subtract missing/different dimensions, then cap by both extraction confidences.
Any blocking issue caps confidence at .49 and rejects. Confidence below .90 requires review.
Area missing on both sides is only a supporting uncertainty: otherwise complete terms score .95
(strong). Known unequal areas reject conservatively. This score is a rule score, not a calibrated
probability. Exact means complete equal dimensions with score 1; strong is accepted score ≥ .90.
No fuzzy name aliasing is implemented. Fixtures already provide canonical categories.

absolute_gap = competitor.public_total - otello.public_total
percent_gap = (competitor.public_total / otello.public_total - 1) * 100
Percentage rounds to two decimals with ROUND_HALF_UP. Rejected matches have both gaps null.
A lower member/bank/mobile price is never selected in place of public_total.
Sold out remains an explicit availability difference with a null gap.
Unresolved candidates enter review; same raw name can route a candidate to review but cannot
establish identity or permit calculation. Human review does not yet have a writeback workflow.

Regression expectations: Savoy -3000/-10% and -6357/-21.19%; Cosmos exact parity;
Sunflower non-refundable Ozon rejected; Safmar Ozon SOLD_OUT; Discovery room/refund/identity
mismatches rejected. These tests use synthetic terms, not reconstructed website evidence.
