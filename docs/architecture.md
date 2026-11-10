# Architecture and reversible decisions

Python 3.12+, Pydantic v2, Decimal. One process, no network dependencies in M1.
`CLI → evidence.save → fixture parser → normalization → quality/matcher → SQLite → JSON/CSV/table`.
The fixture parser validates canonical domain input; normalization intentionally does not guess.
The Connector protocol is only a boundary, not an implemented website integration.

Evidence uses content-addressed local files; the `save(bytes)` interface can later back onto S3.
SQLite stores immutable report snapshots keyed by pipeline version plus input SHA-256.
Changed input creates another historical row. Identical replay does not duplicate history or evidence.
Repeated execution attempts have separate timings in attempts.jsonl; report contents stay deterministic.
The latest JSON/CSV are convenience views, and prior reports remain in SQLite.
Pipeline/schema changes must bump the pipeline version to avoid replaying a previous interpretation.
M1 source timestamps are fixture timestamps. Real capture time and execution time must stay distinct.

SQLite stdlib is sufficient for this vertical slice. SQLAlchemy/Alembic/Postgres are deferred to M4.
Pydantic provides schema validation; pytest, Ruff and mypy are development-only dependencies.
httpx/Playwright/FastAPI are deliberately deferred until they have an implemented responsibility.
No API/dashboard/scheduler is claimed. Invalid fixture schema exits 2 and preserves input evidence;
it does not fabricate a normal business report from malformed data.

M1 supports one offer per observation, one scenario per fixture. Historical snapshots are
whole input batches; cross-batch temporal matching and per-field SQL querying are future work.
Before live comparisons add capture freshness windows and mapping verification against real evidence.

M2 update: see m2-capture.md. httpx now provides a single-request public capture boundary;
observed_pipeline is deliberately separate from synthetic Fixture ingestion. The new source parser
only classifies failures until successful observed tariff schemas become available.
