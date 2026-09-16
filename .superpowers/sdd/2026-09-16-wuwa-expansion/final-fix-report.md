# Persisted fallback review fix

Root cause confirmed with real temporary SQLite: SnapshotStore.get returns JSON text in payload; Task 1's dict-only check skipped the persisted snapshot. The original dict stub incorrectly bypassed that boundary, so its earlier report claim of restart verification was insufficient.

Changed only the Wuwa adapter and its tests: decode JSON text defensively, reject invalid JSON/non-object payloads, and keep exact account/server identity validation. No SnapshotStore contract change. Replaced the misleading dict stub with a real SQLite save/get regression: collect and save successful combat and resource payloads, create a fresh adapter with empty memory caches, then fail one combat source and the monthly report. Assertions verify unchanged successful source/data/timestamp and unchanged original resource period/time despite the available month advancing. Separate real-store cases reject broken JSON, null, arrays, scalars, foreign accounts/servers, and missing identity.

TDD reproduction: restart test failed before the fix (hologram became error/data=null/time=null); it passes after decoding. Focused adapter/route/auth suite: **44 passed**. Full integrated backend suite: **600 passed, 4 skipped**, 2 existing dependency deprecation warnings, 12.76 seconds. All Python commands set PYTHONPATH to this isolated worktree and used C:/Zcode/game-manage/.venv/Scripts/python.exe. git diff --check passed (CRLF advisories only).

Only temporary pytest databases were used; no production data, secrets, upstream calls, main checkout, UI or parent documentation changed. This report supplements and corrects Task 1's persisted-restore evidence.
