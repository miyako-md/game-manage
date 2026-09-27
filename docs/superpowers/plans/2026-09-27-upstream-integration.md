# Integrate upstream UI and preserve local game modules

## Objective and boundaries

Integrate public main ac6ca87 with the complete local checkpoint backup/local-before-sync-20260927. Use upstream's paper-terminal dark/light UI; retain local game artwork overrides, Wuwa/NTE guides and modules, inline resource visuals, viewport calendar, and LOL local archive analysis. Keep Endfield support and upstream reliability fixes. Do not push. Preserve live config, credentials, databases, and original artwork.

## Workspaces and ownership

Implementation: C:/Zcode/game-manage-integration-20260927. The normal checkout is saved on the checkpoint branch and continues serving existing dist until validation completes. Merge conflicts refer to ours=upstream, theirs=local checkpoint.

1. Backend: resolve src/game_assistant/api.py and adapters/league_of_legends/adapter.py, review auto-merged models/matches, retain all game route registration. Unify ChampionCatalog path with db_path. Reuse upstream remake detection in local analysis; remakes excluded from wins, losses, averages and streaks. Degrade uncertain Endfield pity records. Add regressions in tests/test_lol_routes.py, tests/adapters/test_lol_analysis.py and Endfield ledger tests; run focused pytest.
2. Wuwa: resolve WuwaActivities, WuwaCombat, WuwaDashboard, WuwaRoleDetail, WuwaRoles and wuwa.css. Keep local guides/dialog/visual features with upstream styling and safeUrl helpers; preserve reset/error/data semantics. Run Wuwa component tests.
3. NTE/LOL frontend: resolve NteRolesPanel and preserve local NTE modules/guides/inline stamina in upstream theme. Restore LOL announcement access and show remake separately, with summary based on corrected backend output. Run relevant component tests.
4. Shared shell: integrate App, GameCard, Overview, source panels, calendar, icons, resources, dashboard and style.css. Use upstream as shell base; wire all local modules and new Endfield module. Preserve theme-aware local image fallback. Keep calendar filling window, uniform typography, allow oversized error messages to scroll instead of clipping. Avoid invalid CSS var + alpha suffixes.

## Validation and completion

- Install frontend dependencies in isolated checkout. Baseline upstream already passed this turn: 747 backend, 161 frontend, production build.
- Run complete backend/frontend suite and build on integrated tree; fix meaningful regressions. Add tests for reported bugs before implementation.
- Independently review integrated diff and resolve actionable findings.
- Run isolated local UI checks with synthetic/no private network activity where possible; after safe fast-forward of local main, rebuild and restart via managed scripts, verify health and key real pages. Preserve config/data/local-game-icons.
- Verify no conflict markers, whitespace problems, untracked omitted modules, private artwork or credentials in commit. Check the existing push gate without pushing.
- Create local integration commit, update local main by fast-forward, retain checkpoint branch. Record results and limitations. No GitHub push.
