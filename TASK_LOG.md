# Task Log

## 2026-07-03

- Established the backend project documentation baseline.
- Standardized the repository around the web-first PULS backend flow.
- Added high-level project structure and maintenance documentation.

## 2026-07-04

- Improved backend persistence reliability and deployment diagnostics.
- Strengthened response formatting and knowledge-handling quality.

## 2026-07-05

- Added backend support for user vehicle management.
- Improved vehicle-aware handling for saved cases and user history.

## 2026-07-06

- Refined quota handling, persistence boundaries, and backend chat flow integration.
- Continued cleanup of legacy runtime assumptions in the web backend.

## 2026-07-17

- Expanded the vehicle profile workflow and related backend support for richer car data.
- Added backend support for internet-assisted vehicle enrichment before explicit save.

## 2026-07-18

- Improved Japanese chassis and VIN-related enrichment strategy.
- Stabilized the vehicle identification flow after experimentation.

## 2026-07-19

- Improved history handling, service-flow continuity, and backend data consistency.
- Consolidated schema and persistence documentation around the active production direction.
- Continued refinement of shared knowledge handling and user-facing diagnostic flows.

## 2026-07-20

- Added support request intake for PULS, including file attachments and backend persistence.
- Completed SMTP-based support email forwarding for support submissions.
- Verified the live support submission flow after production configuration.
- Polished the public backend repository presentation by simplifying public-facing documentation and replacing the backend README with a production-oriented overview, without changing runtime code.

## 2026-09-13

- Added PHASE 1 local Search Provider configuration for the backend parser flow.
- Preserved remote parser first behavior and the legacy 1G-GZE local case while
  making local AI search provider selection explicit through `SEARCH_PROVIDER`.
- Set Claude as the default local search provider and kept OpenAI available only
  when explicitly selected for future A/B testing.
- Added focused tests for provider selection, no silent cross-vendor fallback,
  remote parser precedence, parser contract preservation, `/chat` route
  connectivity, deep mode, and user-language history preservation.
- Added PHASE 2 optional Diagnostic Provider integration point after parser
  aggregation and before localization/formatter output. The provider is disabled
  by default with `DIAGNOSTIC_PROVIDER=none`; OpenAI synthesis is available only
  when explicitly configured, uses no search tools, and falls back to the
  existing formatter flow on disabled, failed, or malformed provider output.
- Added the current clean backend architecture boundary for diagnostic context
  aggregation. Diagnostic Provider now receives the same vendor-neutral
  aggregated context shape from internal KB/history matches and parser/search
  results, while `DIAGNOSTIC_PROVIDER=none` preserves deterministic formatter
  behavior.
- Updated confirmed-case knowledge promotion so shared `knowledge_cases` are
  written as canonical English reusable knowledge using the existing
  `solved_cases`, `knowledge_cases`, and `knowledge_events` flow without a
  database schema change.
- Added regression coverage for aggregated internal-knowledge diagnostic context
  and canonical English knowledge promotion.
- Added a focused Response Source filtering layer after parser normalization and
  before user-facing formatter/persistence output. Parser discovery remains
  broad and raw parser evidence is preserved, while `/chat` response links can
  be conservatively narrowed to the current question topic. Added tests for the
  Toyota Crown 1G-GZE engine-oil source case, unknown-topic fallback, parser raw
  evidence preservation, filtered `ChatResponse.links`, and the unchanged
  `/chat` response contract.

## 2026-09-14

- Refined the existing backend `/chat` conversational flow so short follow-up
  answers are interpreted against the current conversation before parser/search
  is considered. The change keeps the current vehicle/topic from recent
  messages ahead of stale older history, asks one high-value clarification for
  sparse cases, proceeds when the user cannot provide more detail, checks PULS
  internal knowledge before external parser, preserves parser evidence for
  negative feedback/deeper search, and answers source/why questions from stored
  evidence without a new search. Changed `app/services/decision_engine.py`,
  `app/services/conversation_service.py`, and added
  `tests/test_conversational_context_flow.py`. No database schema change.
  Verified with `python -m py_compile app\services\decision_engine.py
  app\services\conversation_service.py tests\test_conversational_context_flow.py`
  and `python -m unittest discover -s tests` after `pytest` was unavailable in
  the local Python environment.

## Summary

- The backend has evolved from an initial web migration into a production-oriented FastAPI service.
- Major project milestones include vehicle management, history persistence, support intake, schema consolidation, and operational stabilization.
- Detailed internal implementation notes are preserved outside the public-facing documentation set.
