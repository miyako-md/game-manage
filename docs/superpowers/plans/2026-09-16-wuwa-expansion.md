# Wuwa Expansion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Implement task-by-task with tests and review.

**Goal:** Deliver the approved Wuwa panels, read-only details, resource reports, gacha import/statistics and account-scoped historical archive.
**Architecture:** Extend existing adapter snapshots for periodically collected data; add on-demand routes for role/resource details. A dedicated SQLite archive captures successful observations and imported draws. Vue panels consume those contracts and retain the existing style.
**Tech Stack:** Python 3.11+, FastAPI, httpx, SQLite, Vue 3, node:test, pytest/respx.
**Spec:** docs/superpowers/specs/2026-09-16-wuwa-expansion-design.md

## Global Constraints
- Work only in C:/Zcode/game-manage-wuwa-expansion. Other tasks modify the primary checkout.
- Tests: set PYTHONPATH to this worktree's src, invoke C:/Zcode/game-manage/.venv/Scripts/python.exe; frontend node_modules is a junction to installed dependencies.
- Do not print credentials, submit SMS, send notifications, execute downloaded reference code, or upload private data to third-party services.
- Keep missing fields unknown, preserve partial failures and last successful data, validate account identity on every private read/write.
- No pity analysis, echo scoring, equipment comparison or damage computation implementation.
- Reference source is read-only at C:/Users/PublicUser/AppData/Local/Temp/game-manage-wavesuid-review-20260916; its head is 1d693a2 (2025-11-23). Existing endpoints plus getRoleDetail/challengeDetails/slashDetail/moreActivity/period-list/month were live-verified on 2026-09-16.

### Task 1: Data contracts, adapter expansion and private detail routes
**Files:** adapters/wuthering_waves/{adapter.py,endpoints.py,rolebox_client.py,role.py,rolebox.py}; create data_models.py, detail_parse.py, routes.py; modify models.py/base.py/scheduler.py/api.py/auth/service.py only as integration requires. Tests under tests/adapters/test_wuwa_expansion.py and tests/test_wuwa_routes.py.
**Consumes:** existing Settings, LoginService, BaseGameAdapter, SnapshotStore.
**Produces:** Capability.COMBAT='combat', ACTIVITIES='activities', RESOURCES='resources'; standard snapshots for those capabilities; enriched account.extra and roles compatible with prior summary fields. Install routes via install_wuwa_routes(app).
Routes: GET /api/wuwa/roles/{role_id}; GET /api/wuwa/resources/{kind}/{period}. Return {payload,fetched_at} or explicit error with proper non-success HTTP status; no arbitrary upstream URL. Resource kind one of week/month/version, period validated against period/list.
Payloads must be normalized snake_case, schema_version=1 for new capability objects, include role_id/server_id identity and provenance. Combat has independently represented tower/hologram/slash results; activities normalize all actual returned gameplay sections; resources include available periods and current month's report. Document exact finalized JSON examples in docs/wuwa-expansion-contract.md for subsequent tasks.
- [x] Write failing tests: base account collections kept; role list enhancement; tower area/floor stars and team IDs survive; expired season rejected; nullable/zero fields retained; role detail requires owned id; monthly resource quantities are source-derived; one combat source failure retains successful siblings; session switch cannot publish another account's detail.
- [x] Implement typed parsers and client requests with existing roleBox auth/refresh behavior. Keep subrequest error handling consistent with main service.
- [x] Run targeted and full backend tests; update old tests only when endpoint behavior intentionally changes; preserve their behavioral assertions.
- [x] Commit owned files, self-review, write task-1-report.md including precise payload contract and test results.

### Task 2: Historical archive and gacha ingestion
**Files:** create wuwa_history.py, wuwa_gacha.py, wuwa_archive_routes.py; modify snapshots.py/scheduler.py/api.py narrowly for success hooks and installation; tests/test_wuwa_history.py, test_wuwa_gacha.py, test_wuwa_archive_routes.py.
**Consumes:** Task 1 capability payloads and identity contract in docs/wuwa-expansion-contract.md.
**Produces:** SQLite tables scoped by account+server; GET /api/wuwa/history?kind=tower|roles|role_detail; GET /api/wuwa/gacha; POST /api/wuwa/gacha/import accepting {url:string} or {records:object|array}; POST /api/wuwa/history/backfill for bounded migration of available local snapshots/official accessible data. All write routes require same-origin X-Game-Assistant:1 and bounded body. Do not store URL/recordId credentials.
- [x] Failing tests cover success-only history, repeated observation dedup, two accounts with same role-character id isolation, tower seasons separate, null-vs-zero deltas, no imaginary backfill, gacha repeat import idempotency, unknown rarity preserved, malicious URL/redirect blocked, wrong account rejected, partial/incomplete coverage explicit.
- [x] Implement bounded SQLite reads/history deltas; use role/server identity from active adapter and account generation checks around awaited network requests. Record role-list training history automatically, and full role details when actually queried.
- [x] Implement official-record link parser/fixed-host client and JSON normalization, stable draw identity, per-pool stats and gold detail. No pity calculations. Empty input produces clear need-import state, never sample draws.
- [x] Document source coverage, archive start and backfill outcome; append concrete endpoint examples to shared contract doc; run tests and commit; write task-2-report.md.

### Task 3: Wuwa UI and integration
**Files:** frontend/src/components/Wuwa*.vue; frontend/src/wuwa-api.js; integrate components/GameCard.vue without changing NTE/LoL behavior. Tests components/Wuwa*.test.js and src/wuwa*.test.js.
**Consumes:** Task 1 and Task 2 exact JSON/route contracts in docs/wuwa-expansion-contract.md.
**Produces:** navigable Wuwa sections for profile/collections, enhanced roles and complete detail/equipment, challenge reports, gameplay progress, resource period selection, gacha import/statistics, history and progress changes. Reuse native styling, existing snapshot/state load and errors.
- [x] Tests verify field rendering, actual equipped weapon distinct from weapon type, null values, partial combat failures, resource selector requests, stale detail request cancellation/account switching, gacha zero/duplicate/empty/error handling, history start/no-backfill states.
- [x] Build responsive panels; role details on demand with accessible dialog/panel and safe URLs. Import accepts paste URL or local JSON file, never exposes authorization values afterward. Explain imported window and no historical coverage when absent.
- [x] Preserve overview stamina/announcement/calendar access; don't duplicate automatic fetches or drop existing sidebar behavior.
- [x] Run npm test and npm run build; commit and write task-3-report.md.

### Task 4: Evaluation, live verification and final integration
**Files:** docs/wuwa-expansion.md and docs/wuwa-analysis-feasibility.md; update plan completion statuses.
**Consumes:** working implementation, tests, actual logged-in main configuration for final read-only verification.
- [x] Controller researches public projects for pity import, echo scoring, build comparison and damage calculation. Record source URLs, license, inputs, freshness and reuse boundary; do not implement algorithms.
- [x] Review task commits and whole branch; fix substantive findings through implementer and scoped re-review.
- [x] Safely integrate selected worktree commits with current checkout's independent changes. Verify all tests and build; restart using project-owned scripts and verify health and browser pages. Use real data where available; if no gacha URL/JSON supplied, report import feature verified with fixtures and live backfill unavailable.
- [x] Record what is complete and remaining external-data limits. Do not ask whether to continue authorized tasks.

## Final acceptance

Completed 2026-09-16. Primary checkout: 657 backend tests passed, 4 conditional skips; 134 frontend tests passed; production build, managed restart, real refresh and browser acceptance passed. See docs/wuwa-expansion.md for coverage, backups and remaining source limits. Real gacha import is intentionally user-controlled and was not performed.
