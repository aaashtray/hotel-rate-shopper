# Product contract

Question: where is Otello cheaper, dearer, in parity, or unavailable compared with equivalent
public competitor tariffs, and how trustworthy is the conclusion?

Comparison unit: canonical hotel + check-in/out + guests (including child ages) + room count +
room category + bed + meal + cancellation conditions/deadline + payment timing + taxes + access.
Positive gap means competitor is dearer than Otello. Negative means competitor is cheaper.
Parity in M1 means exact monetary equality; no tolerance is silently applied.

M1 implements only offline synthetic domain ingestion, matching, quality, history and reports.
Reference scenario is 2026-11-20 through 2026-11-22, two adults, one room, no children, RUB;
2026-11-10 is a supplied scenario anchor, not proof of a capture performed that day.
Five case groups exercise Savoy, Cosmos, Sunflower, Safmar and Discovery.
Missing terms are synthetic assumptions for tests, never established source facts.
The test report is not suitable for real pricing decisions.

Future MVP: 10–30 Moscow hotels, 2–3 scenarios, 1–2 daily runs. Initial roster: Савой,
Cosmos Москва ВДНХ, Maidens Hotel Moscow, Stella di Mosca, Вега Измайлово,
Sunflower Avenue, Бета Измайлово, YES Botanica, Сафмар Грандъ, Discovery.
This is a practical sample, not an official ranking. No repricing or bookings.

A successful observation is a complete valid public offer or an evidenced sold-out result
with verified scenario and hotel. A successful observation does not guarantee a comparable tariff.
A sold-out comparison carries no gap. Any unresolved match enters manual review.
SUCCESS requires every expected observation valid; some valid means PARTIAL_SUCCESS; none means FAILED.
CLI exits 0 / 1 / 2 respectively. Expected observations are explicit, so missing results cannot disappear.
