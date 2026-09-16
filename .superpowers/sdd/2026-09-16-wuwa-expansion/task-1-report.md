# Task 1 implementation report

Status: complete; implementation commit `eab92ef`.

## Delivered

- Added combat/activities/resources capabilities, base dispatch, polling intervals, renewable roleBox coverage.
- Expanded account.extra with typed collection/profile validation; original summary fields retained. Enhanced roles keep the original array/fields and add normalized extra, account_role_id/server_id/provenance.
- Added fixed getRoleDetail/challengeDetails/slashDetail/moreActivity/period-list/week/month/version requests. Resource period list is GET and resource calls add existing token alongside b-at; successful live requests verified these headers.
- Added versioned typed envelopes and lossless snake_case normalization. Unknown/null/zero retained; absolute HTTP(S) URLs only. Full tower difficulties/areas/floors/team IDs survive and expired tower durations are rejected.
- Combat subsource failures retain successful siblings and older failed subsource payload/time, including reload from matching persisted snapshots on process restart. Resource report failure leaves period selection available and can retain a correctly labelled older report.
- Installed owned-character and allowlisted-period private GET routes, explicit 401/404/409/422/502 errors, shared LoginService renewal. Added `account_generation(game)` separate from credential version so same-account renewal succeeds while actual login/logout/switch invalidates in-flight private reads. Account identity is checked around the await.
- `docs/wuwa-expansion-contract.md` gives exact example JSON, live field map, identity/provenance rules, stale handling, downstream archive/UI integration points.

## Tests and evidence

Used TDD: missing parser imports first failed, adapter behavior tests failed for missing methods/profile fields, URL/resource fallback and malformed-payload tests failed before implementation, session switch and same-account renewal tests failed before account-generation changes.

Final command (isolated source, primary interpreter):

`$env:PYTHONPATH='C:/Zcode/game-manage-wuwa-expansion/src'; & C:/Zcode/game-manage/.venv/Scripts/python.exe -m pytest -q`

Result: **576 passed, 4 skipped, 2 existing dependency deprecation warnings**, 9.36 seconds. Baseline was 558/4. Targeted adapter/routes/auth integration run also passed. `git diff --check` passed (only repository CRLF advisory warnings).

Read-only live structural calibration on 2026-09-16 used Settings/LoginService to load existing authorized account. Printed only key names/types/counts and success states, no credential or account values. Live request success: baseData, roleData, getRoleDetail, towerDataDetail, challengeDetails, slashDetail, moreActivity, period/list, month. Final adapter-level probe exited 0 and passed account, roles, role detail, all three combat sources, activities and resources. It stubbed `_refresh_rolebox` to avoid modifying upstream cached state; no database writes, renewal, credential persistence, SMS, notifications or uploads were performed. Initial structural probe had a cleanup-only AttributeError after all requests succeeded; corrected final probe passed.

Live additions beyond the older reference: baseData phantomBoxList; six moreActivity sections (floroRanch, honamiStory, permanentRouge, phantomBattle, phantomBattleRecord, trapDefense); resource itemList with totals/deltas/details; full skill branch/equipment property fields. All are retained generically.

## Self-review and downstream notes

- Preserved base account token-expiry behavior: token-side 401/403 does not renew b-at; new FetchResult.error_source distinguishes roleBox errors for account profile calls. Existing behavior assertions preserved while account fixtures now include newly requested refresh/baseData.
- Parent-owned `docs/wuwa-analysis-feasibility.md` remains unstaged/unmodified by this task.
- No UI, archive, gacha or history hook implemented here. Task 2 should use `roles[].extra.account_role_id` (outer role_id is character ID); other new payloads use account role_id/server_id. Archive only combat subresults whose state is ok, keeping source timestamp and tower season_end_at. Typed envelope provenance fetched_at changes each observation; omit observation times when computing content dedup hashes.
- MoreActivity and equipment internals intentionally preserve actual source fields, rather than hardcoding the older reference schema. UI should render unknown sections/nullable fields and treat descriptions as plain text.
- Combat auth failures escape to the common renewal handler; persistent auth failure preserves the prior whole snapshot through existing scheduler semantics. Non-auth subsource failures use independent stale/error envelopes.
- Live role-detail test checked one owned character, not every account character. Resource week/version transport paths are fixed and share the verified resource client; only the default month was queried live.
