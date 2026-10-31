"""Real Chromium: a WuWa role image carries the built-in default score in its echo score card (synthetic echoes)."""
import pytest
from game_assistant.assessment_projection import with_assessment
from game_assistant.qq.render_snapshot import role_snapshot
from tests.test_assessment_routes import detail_snapshot
from tests.test_qq_browser_rendering import NOW, SCOPE, browser, envelope


@pytest.mark.parametrize('character,scored', [('1205', True), ('c1', False)])
async def test_wuwa_role_image_embeds_the_default_score_only_when_scored(character, scored):
    renderer = browser()
    row = detail_snapshot(character)
    value = role_snapshot('wuthering_waves', row, NOW, detail=with_assessment(row, None, SCOPE, 'wuthering_waves'), resolved_id=character)
    observed = {}
    original_close = renderer._bounded_close
    async def inspect_close(operation):
        if renderer._browser is not None and renderer._browser.contexts and renderer.last_state and renderer.last_state.get('state') == 'ready':
            page = renderer._browser.contexts[0].pages[0]
            observed['blocks'] = await page.locator('.render-page .personal-assessment').count()
            observed['card'] = ' '.join(await page.locator('.render-page .wuwa-detail-echoes .role-score-hero').all_inner_texts())
            observed['badges'] = await page.locator('.render-page .wuwa-echo-score').count()
        return await original_close(operation)
    renderer._bounded_close = inspect_close
    try:
        image = await renderer.render_summary_async(SCOPE, envelope(value), budget_seconds=10)
        assert renderer.last_state['state'] == 'ready' and image.page == 1
        # 168.16 is the golden total of tests.test_assessment_defaults. The score is the echo section's
        # score card (total with the unofficial source) and a badge per echo, never a block of its own.
        assert observed['blocks'] == 0
        assert ('168.16' in observed['card'], '非官方' in observed['card'], observed['badges'] > 0) == (scored, scored, scored)
    finally:
        await renderer.aclose()
