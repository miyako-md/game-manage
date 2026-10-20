"""Community fallback adds independent pools without guessing missing dates."""
import json
from datetime import datetime, timezone
from urllib.parse import parse_qs

import httpx
import pytest
import respx

from game_assistant.accounts.query import CloudPublicQuery
from game_assistant.adapters.wuthering_waves.adapter import WutheringWavesAdapter
from game_assistant.config import Settings
from game_assistant.models import Capability
from game_assistant.registry import GameRegistry
from game_assistant.snapshots import SnapshotStore
from tests.adapters.test_wuwa_public import LIST, DETAIL


BASE = {'postId': '9001', 'postTitle': '3.6版本内容说明', 'publishTime': 1787198400000}
BASE_BODY = '<p>[签到]七日签到活动</p><p>活动时间</p><p>3.6版本更新后 ~ 2026年9月29日03:59</p>'
CARD = {'postId': '9002', 'postTitle': '3.6版本「角色甲」角色活动唤取', 'publishTime': 1788926400000}
CARD_BODY = '<p>「角色甲」角色活动唤取、「武器甲」武器活动唤取限时开启</p><p>唤取时间</p><p>2026年9月10日10:00 ~ 2026年9月29日11:59</p>'


def mock_notices(rows, bodies, failed=None):
    respx.post(LIST).respond(200, json={'code': 200, 'data': {'list': rows}})
    def detail(request):
        ident = parse_qs(request.content.decode())['postId'][0]
        if ident == failed:
            return httpx.Response(403)
        row = next(r for r in rows if r['postId'] == ident)
        return httpx.Response(200, json={'code': 200, 'data': {'postDetail': {
            **row, 'postH5Content': bodies[ident]}}})
    return respx.post(DETAIL).mock(side_effect=detail)


@respx.mock
async def test_cross_line_and_independent_grouped_pools_preserve_source_and_precision():
    mock_notices([BASE, CARD], {'9001': BASE_BODY, '9002': CARD_BODY})
    result = await WutheringWavesAdapter(Settings()).fetch(Capability.EVENTS)
    assert result.ok
    events = {e.name: e.model_dump(mode='json') for e in result.payload}
    assert set(events) == {'签到', '角色甲', '武器甲'}
    assert events['签到']['start_at'] is None and events['签到']['start_precision'] == 'relative'
    assert events['签到']['start_text'] == '3.6版本更新后'
    assert events['角色甲']['source_post_id'] == '9002'
    assert events['角色甲']['source'] == 'community' and events['角色甲']['version'] == '3.6'
    assert events['角色甲']['source_url'] == 'https://www.kurobbs.com/forum/post/9002'


@respx.mock
async def test_other_version_pool_and_undated_short_date_do_not_enter_calendar():
    other = {**CARD, 'postId': '9003', 'postTitle': '3.7版本「别的角色」角色活动唤取'}
    mock_notices([BASE, other], {'9001': BASE_BODY, '9003': CARD_BODY})
    result = await WutheringWavesAdapter(Settings()).fetch(Capability.EVENTS)
    assert result.ok and [e.name for e in result.payload] == ['签到']
    # With no publication year or explicit date year, the source cannot anchor dates.
    undated = {**BASE, 'publishTime': None}
    mock_notices([undated], {'9001': BASE_BODY.replace('2026年9月29日', '9月29日')})
    result = await WutheringWavesAdapter(Settings()).fetch(Capability.EVENTS)
    assert result.ok and result.payload[0].end_at is None
    assert result.payload[0].end_precision == 'unknown'


@respx.mock
async def test_independent_pool_failure_preserves_old_full_calendar_snapshot():
    mock_notices([BASE, CARD], {'9001': BASE_BODY, '9002': CARD_BODY}, failed='9002')
    adapter = WutheringWavesAdapter(Settings())
    registry = GameRegistry()
    registry.register(adapter)
    store = SnapshotStore(':memory:')
    store.save('wuthering_waves', 'events', json.dumps([{'name': '旧卡池'}]))
    old = store.get('wuthering_waves', 'events')
    query = CloudPublicQuery(registry, store)
    await query.poll('wuthering_waves')
    assert store.get('wuthering_waves', 'events') == old
    assert query.read('wuthering_waves', 'events').state == 'error'


@respx.mock
async def test_independent_pool_revision_deduplicates_baseline_and_requests_are_bounded():
    cards = [{**CARD, 'postId': str(9100+i)} for i in range(20)]
    body = BASE_BODY + CARD_BODY
    route = mock_notices([BASE, *cards], {'9001': body, **{r['postId']: CARD_BODY for r in cards}})
    result = await WutheringWavesAdapter(Settings()).fetch(Capability.EVENTS)
    assert result.ok and {e.name for e in result.payload} == {'签到', '角色甲', '武器甲'}
    assert len(result.payload) == 3
    assert route.call_count <= 9


@respx.mock
async def test_preannouncement_pools_with_body_version_evidence_are_not_dropped():
    # Public titles/ordering from the audited missing 3.7 pool notices; synthetic bodies.
    base = {**BASE, 'postTitle': '3.7版本内容说明',
            'publishTime': int(datetime(2026, 9, 30, tzinfo=timezone.utc).timestamp()*1000)}
    cards = [{'postId': ident, 'postTitle': title,
              'publishTime': int(datetime(2026, 9, 29, tzinfo=timezone.utc).timestamp()*1000)}
             for ident, title in [('1554095213865066496', '「角色甲」角色活动唤取'),
                                  ('1554095802058051584', '「武器甲」武器活动唤取')]]
    bodies = {'9001': BASE_BODY.replace('3.6', '3.7').replace('9月29日', '10月29日')}
    for card in cards:
        bodies[card['postId']] = '<p>活动期间，5星共鸣者的唤取概率限时提升！</p><p>✦活动时间✦</p><p>3.7版本更新后 ~ 2026年10月22日09:59</p>'
    mock_notices([base, *cards], bodies)
    result = await WutheringWavesAdapter(Settings()).fetch(Capability.EVENTS)
    assert result.ok and {e.source_post_id for e in result.payload} == {'9001', '1554095213865066496', '1554095802058051584'}


@respx.mock
async def test_first_phase_compilation_adds_six_pools_and_deduplicates_individuals():
    stamp = int(datetime(2026, 9, 29, tzinfo=timezone.utc).timestamp()*1000)
    base = {**BASE, 'postTitle': '3.7版本内容说明', 'publishTime': stamp+86400000}
    individual = {**CARD, 'postId': '1554095213865066496', 'postTitle': '「但愿长圆如此夜」角色活动唤取', 'publishTime': stamp}
    compilation = {'postId': '1554096755014008832', 'postTitle': '3.7版本第一期唤取活动说明', 'publishTime': stamp}
    body = ('3.7版本第一期唤取活动说明\n'
            '「但愿长圆如此夜」、「曙暮一线之间」、「漫于盈缺时轴」角色活动唤取，'
            '「玉阙玄华」、「昙切」、「万物持存的注释」武器活动唤取限时开启！\n'
            '✦活动时间✦\n3.7版本更新后 ~ 2026年10月22日09:59')
    mock_notices([base, individual, compilation], {
        '9001': BASE_BODY.replace('3.6', '3.7').replace('9月29日', '10月29日'),
        individual['postId']: '活动期间，5星共鸣者的唤取概率限时提升！\n✦活动时间✦\n3.7版本更新后 ~ 2026年10月22日09:59',
        compilation['postId']: body})
    result = await WutheringWavesAdapter(Settings()).fetch(Capability.EVENTS)
    assert result.ok and len(result.payload) == 7
    pools = [e for e in result.payload if '活动唤取' in (e.category or '')]
    assert len(pools) == 6 and len({e.name for e in pools}) == 6


@respx.mock
async def test_known_future_release_cannot_replace_current_version():
    future = {**BASE, 'postId': '9003', 'postTitle': '3.8版本内容说明', 'publishTime': 1791741600000}
    mock_notices([BASE, future], {'9001': BASE_BODY, '9003':
        '更新维护时间：2030年10月30日06:00\n[未来活动]限时活动\n活动时间：3.8版本更新后 ~ 2030年11月29日05:59'})
    result = await WutheringWavesAdapter(Settings()).fetch(Capability.EVENTS)
    assert result.ok and [e.name for e in result.payload] == ['签到']
    assert result.payload[0].version == '3.6'


@respx.mock
async def test_future_maintenance_notice_without_activities_keeps_the_current_calendar():
    # The newest notice only announces next version's maintenance and compensation.
    maintenance = {**BASE, 'postId': '9004', 'postTitle': '3.7版本维护更新公告', 'publishTime': 1791741600000}
    mock_notices([BASE, maintenance], {'9001': BASE_BODY, '9004': '更新维护时间：2030年10月30日06:00-11:00\n维护补偿：星声×300'})
    result = await WutheringWavesAdapter(Settings()).fetch(Capability.EVENTS)
    assert result.ok and [e.name for e in result.payload] == ['签到']


@respx.mock
async def test_unversioned_late_pool_survives_short_baseline_but_next_window_does_not():
    base = {**BASE, 'postTitle':'3.7版本内容说明', 'publishTime':1790737200000}
    future = {**BASE, 'postId':'9003', 'postTitle':'3.8版本维护更新公告', 'publishTime':1791849600000}
    late = {**CARD, 'postTitle':'「后半程」角色活动唤取', 'publishTime':1791676800000}
    outside = {**late, 'postId':'9004', 'postTitle':'「未来」角色活动唤取'}
    mock_notices([base, future, late, outside], {
        '9001':'更新维护时间：2026年10月1日06:00\n[签到]活动\n活动时间：2026年10月1日10:00 ~ 2026年10月10日10:00',
        '9003':'更新维护时间：2030年11月1日06:00',
        '9002':'活动时间：2026年10月12日10:00 ~ 2026年10月25日10:00',
        '9004':'活动时间：2030年11月2日10:00 ~ 2030年11月10日10:00'})
    result = await WutheringWavesAdapter(Settings()).fetch(Capability.EVENTS)
    assert result.ok and {e.name for e in result.payload} == {'签到','后半程'}
    assert next(e for e in result.payload if e.name=='后半程').version is None


@pytest.mark.parametrize('with_dated_supplement', [False, True])
@respx.mock
async def test_announced_future_pool_is_retained_and_exact_supplement_replaces_unknown(with_dated_supplement):
    # Pool identities are factual 3.7 excerpts; these date values are synthetic.
    base = {**BASE, 'postTitle':'3.7版本内容说明'}
    body = BASE_BODY.replace('3.6','3.7') + '<p>※可通过[余心所向九死未悔]角色活动唤取获得。</p><p>※可通过「沉冥」武器活动唤取获得。</p>'
    future = {**CARD, 'postTitle':'3.7版本「沉冥」武器活动唤取'}
    rows = [base, future] if with_dated_supplement else [base]
    bodies = {'9001':body, '9002':'<p>活动时间：2026年10月22日10:00 ~ 2026年11月11日09:59</p>'}
    mock_notices(rows,bodies)
    result = await WutheringWavesAdapter(Settings()).fetch(Capability.EVENTS)
    assert result.ok and {e.name for e in result.payload} == {'签到','余心所向九死未悔','沉冥'}
    assert len(result.payload) == 3
    unknown = next(e for e in result.payload if e.name == '余心所向九死未悔')
    assert unknown.start_at is None and unknown.end_at is None
    weapon = next(e for e in result.payload if e.name == '沉冥')
    if with_dated_supplement:
        assert weapon.start_at.isoformat() == '2026-10-22T10:00:00+08:00'
        assert weapon.source_post_id == '9002'
    else:
        assert weapon.start_at is None and weapon.end_at is None
