"""NTE QQ images on the neon skin, checked in a real browser (skipped without the isolated Chromium/font)."""
import asyncio
from datetime import datetime
import os

import pytest

from game_assistant.accounts.models import QueryResult
from game_assistant.qq.browser_rendering import BrowserRenderer
from game_assistant.qq.guides import reply as guide_reply
from game_assistant.qq.render_snapshot import game_panel, game_snapshot, gacha_snapshot, role_snapshot

NOW = datetime.fromisoformat('2026-10-21T12:00:00+08:00')
MIN_TEXT = """()=>{const small=[];for(const e of document.querySelectorAll('.lab-sheet *')){if(e.closest('svg'))continue
 if(![...e.childNodes].some(n=>n.nodeType===3&&n.textContent.trim()))continue
 const cs=getComputedStyle(e),b=e.getBoundingClientRect();if(cs.display==='none'||cs.visibility==='hidden'||!b.width)continue
 if(parseFloat(cs.fontSize)<17)small.push(e.className+' '+cs.fontSize)}return small}"""


def piece(kind, i):
    return {'id': f'{kind}{i}', 'name': f'合成{kind}{i}', 'level': 20, 'main_properties': [{'name': '攻击力', 'value': '63'}],
            'properties': [{'name': '暴击率', 'value': '3.1%'}, {'name': '暴击伤害', 'value': '6.2%'}]}


def role(core, pie):
    return {'id': '1003', 'name': '早雾', 'quality': 'S', 'level': 90, 'element': '光', 'awaken_level': 0,
            'weapon': {'name': '合成弧盘', 'level': 80, 'breakthrough_level': 4, 'properties': [{'name': '攻击力', 'value': '570'}]},
            'suit': {'name': '合成套装', 'activation_count': 4, 'core': [piece('卡带', i) for i in range(core)], 'pie': [piece('驱动', i) for i in range(pie)]},
            'skills': [{'id': '1', 'name': '合成技能', 'level': 4}], 'city_skills': [{'id': '2', 'name': '城区技能', 'level': None}]}


GACHA = {'schema_version': 1, 'luck_title': '合成评价', 'luck_type': 2, 'pools': [
    {'name': '限定角色', 'total_draws': 120, 's_count': 2, 'average': 60.0, 'guarantee': 90, 'details': [
        {'item_id': '9001', 'name': '合成角色甲', 'pity': 72, 'lucky_type': 2, 'obtained_at': '2026-10-12T20:01:00+08:00'},
        {'item_id': '9002', 'name': None, 'pity': None, 'lucky_type': None, 'obtained_at': None}]}]}
PROGRESS = {'schema_version': 1, 'completed': 269, 'total': 480, 'bronze': 120, 'silver': 96, 'gold': 53, 'categories': [
    {'id': '1', 'name': '城市漫游', 'current': 88, 'total': 140}, {'id': '2', 'name': '引力Type IV', 'current': 61, 'total': 53},
    {'id': '3', 'name': '未知分类', 'current': None, 'total': 30}]}


def snapshots():
    panel = lambda cap, payload: game_panel('nte', 'tajiduo', cap, QueryResult(payload, NOW.isoformat(), 'ok', True))
    return {
        'guide': guide_reply('nte', '主角·零', NOW)[1],
        'gacha': gacha_snapshot('nte', QueryResult(GACHA, NOW.isoformat(), 'ok', True), NOW),
        'progress': game_snapshot([panel('progress', PROGRESS)], NOW, title='异环 · 进度', command='异环 进度'),
        'detail': role_snapshot('nte', QueryResult({'schema_version': 1, 'entries': [role(5, 1)]}, NOW.isoformat(), 'ok', True), NOW, resolved_id='1003'),
    }


async def test_real_nte_neon_pages_stay_legible_and_keep_their_layout():
    executable, font = os.environ.get('QQ_RENDER_TEST_EXECUTABLE'), os.environ.get('QQ_RENDER_TEST_FONT')
    if not executable or not font:
        pytest.skip('Set isolated Chromium/font paths for native acceptance')
    renderer = BrowserRenderer(template='a', executable_path=executable, font_path=font, dist_path=os.environ.get('QQ_RENDER_TEST_DIST', ''))
    renderer._a_images = {}; renderer._a_forbidden = []; renderer._a_asset_misses = []
    results = {}
    try:
        async with asyncio.timeout(60):
            await renderer._a_ready()
            page = renderer._a_page
            for name, snap in snapshots().items():
                await page.evaluate('(input)=>window.mountLongRender(input)', {'snapshot': snap, 'asset_urls': [], 'job_id': name, 'input_fingerprint': name})
                assert (await page.evaluate('window.__LONG_RENDER_STATE__'))['state'] == 'ready', name
                results[name] = await page.evaluate("""(name)=>{const box=s=>[...document.querySelectorAll(s)].map(e=>e.getBoundingClientRect())
                 const sheet=document.querySelector('.lab-sheet'),out={skin:sheet.dataset.skin,small:(%s)()}
                 if(name==='guide'){out.text=box('.guide-role-context > div').map(b=>b.width);out.sheet=sheet.getBoundingClientRect().width}
                 if(name==='gacha'){out.track=[...document.querySelectorAll('.cloud-gacha .bar-track')].map(e=>getComputedStyle(e).backgroundColor)
                   out.ink=getComputedStyle(document.querySelector('.cloud-gacha .bar-values')).color}
                 if(name==='progress'){out.card=box('.nte-card')[0].right;out.tag=box('.categories .target-met').map(b=>b.right)
                   out.bars=box('.categories progress').map(b=>[Math.round(b.left),Math.round(b.right)])}
                 if(name==='detail'){out.cells=box('.sheet-piece').length;out.kinds=[...document.querySelectorAll('.piece-title span')].map(e=>e.textContent.split(' ')[0])
                   const suit=box('.sheet-pieces')[0];out.inside=box('.sheet-piece').every(b=>b.left>=suit.left&&b.right<=suit.right)}
                 return out}""" % MIN_TEXT, name)
                await page.evaluate('window.disposeLongRender()')
    finally:
        await renderer.aclose()
    assert {r['skin'] for r in results.values()} == {'nte'}
    assert all(not r['small'] for r in results.values()), {k: r['small'] for k, r in results.items()}
    # 主角·零 has no portrait: the title column spans the header instead of collapsing to 96px.
    assert results['guide']['text'] and results['guide']['text'][0] > results['guide']['sheet'] / 2
    # Gacha bars sit in a dim well with light numbers (the light template used a near-white track).
    alpha = lambda c: float(c.split(',')[3].strip(' )')) if c.startswith('rgba') else 1.0
    assert all(alpha(c) <= .2 for c in results['gacha']['track']), results['gacha']['track']
    assert sum(int(v) for v in results['gacha']['ink'].strip('rgba()').split(',')[:3]) > 600
    # An over-total category keeps its tag inside the card and every bar shares one column.
    progress = results['progress']
    assert progress['tag'] and all(right <= progress['card'] for right in progress['tag'])
    assert len({tuple(b) for b in progress['bars']}) == 1, progress['bars']
    # Odd piece counts: one cell per piece inside the role sheet's piece grid, cartridges first.
    assert results['detail']['cells'] == 6 and results['detail']['inside']
    assert results['detail']['kinds'] == ['卡带'] * 5 + ['驱动']


def test_nte_skin_keeps_glow_out_of_gradients():
    # D9: dithered gradients do not compress; two header glows cost a short page ~100 KiB.
    from pathlib import Path
    css = (Path(__file__).parents[1] / 'frontend' / 'src' / 'qq-image' / 'skin-nte.css').read_text(encoding='utf-8')
    assert 'radial-gradient' not in css
    assert 'inset 0 0 28px' in css and 'text-shadow' in css
