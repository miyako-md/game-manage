# Latest resource month default

Live source periods are ascending YYYYMM, so the previous first-item default selected the oldest month. Added latest_month_period: compare only valid six-digit YYYYMM with a nonzero year and months 01–12. Select the maximum valid period without reordering the returned list. Unknown formats are not inferred from display titles; if all periods are unknown, use the first source period as a compatibility fallback, without asserting it is chronologically latest. Empty lists yield no selection.

TDD: seven helper cases initially failed for the missing helper and the adapter regression returned 202607 instead of 202609. After the fix, ascending, unordered, cross-year, single-month, unknown-only, mixed-validity and empty-list cases pass; the adapter test confirms the request targets September while UI period ordering stays unchanged. Updated contract wording.

Focused adapter/route/auth suite: **52 passed**, 2 existing dependency deprecation warnings. Isolated PYTHONPATH and primary interpreter used. git diff --check passed after removing the editor-added blank EOF line. No full suite requested; root will perform final integrated validation. No main checkout, production data, live requests or UI changes.
