from datetime import datetime, timedelta, timezone

import pytest

from game_assistant.sources.bilibili import classify_dynamic
from game_assistant.sources.bilibili_store import BilibiliStore
from game_assistant.sources.bilibili_service import BilibiliService
from game_assistant.config import Settings
from game_assistant.sources.public_content import calendar_from_posts, merge_events
from game_assistant.event_calendar import parse_events_from_lines
from tests.test_bilibili_source import post, UID

NOW = datetime(2026, 10, 1, tzinfo=timezone.utc)
BODY = '''「镜锁妄世，心照红尘」3.7版本内容说明
更新维护时间：2026年9月30日04:00 ~ 2026年9月30日11:00
[梦构匣中]区域探索活动
活动时间：3.7版本更新后 ~ 2026年11月11日03:59
[没有日期的活动]战斗活动
[朝月鱼涌]网页活动
活动时间：2026年10月15日10:00 ~ 2026年11月1日09:59
[天工寻物]限时活动
活动时间：2026年10月8日04:00 ~ 2026年10月26日03:59'''


@pytest.mark.parametrize('title', ['3.7版本内容说明', '3.6版本内容说明', '1.5版本更新公告'])
def test_numbered_version_notice_can_contain_web_event_sections(title):
    row = classify_dynamic(post(title + '\n' + '\n'.join(BODY.splitlines()[1:])), UID, NOW)
    assert row['decision'] == 'accepted'


def test_version_notice_does_not_add_web_events_or_borrow_their_dates():
    row = classify_dynamic(post(BODY), UID, NOW)
    result = calendar_from_posts([row], 'wuthering_waves', NOW)
    assert result['version'] == '3.7'
    assert {e['name'] for e in result['events']} == {'梦构匣中', '天工寻物'}
    event = next(e for e in result['events'] if e['name'] == '梦构匣中')
    assert event['start_date'] == '2026-09-30'
    assert event['end_at'] == '2026-11-11T03:59:00+08:00'


@pytest.mark.parametrize('body,kind,reason', [
    ('3.7版本网页活动内容说明\n活动时间：10月15日10:00', 'DYNAMIC_TYPE_WORD', 'promotion'),
    (BODY, 'DYNAMIC_TYPE_AV', 'video'),
    (BODY + '\n转评赞参与抽奖', 'DYNAMIC_TYPE_WORD', 'lottery'),
    ('3.7版本内容说明\n网页活动敬请期待', 'DYNAMIC_TYPE_WORD', 'no_date'),
])
def test_version_title_does_not_bypass_other_exclusions(body, kind, reason):
    assert classify_dynamic(post(body, kind=kind), UID, NOW)['reason'] == reason


def test_version_notice_still_requires_complete_body():
    raw = post(BODY)
    raw['modules']['module_dynamic']['major']['opus']['summary']['has_more'] = True
    assert classify_dynamic(raw, UID, NOW)['reason'] == 'incomplete'


def test_community_parser_stops_at_next_heading_and_omits_web_events():
    lines = ['[故梦寻契]留影收集活动', '开放时间：3.7版本更新后永久开放',
             '[天工寻物]限时活动', '活动时间：2026年10月8日04:00 ~ 2026年10月26日03:59',
             '[朝月鱼涌]网页活动', '活动时间：2026年10月15日10:00 ~ 2026年11月1日09:59']
    result = parse_events_from_lines(lines)
    assert [e.name for e in result] == ['天工寻物']
    assert result[0].start_at.day == 8


def test_old_community_web_event_cache_cannot_reenter_ingame_calendar():
    row = {'name':'朝月鱼涌','category':'网页活动','source_title':'3.7版本内容说明'}
    assert merge_events([], [row], None) == []


async def test_rule_upgrade_refetches_old_notices_beyond_incremental_window(tmp_path):
    path = tmp_path / 'bili.db'
    now = datetime.now(timezone.utc)
    raw = post(BODY, published=(now-timedelta(days=10)).timestamp())
    original = classify_dynamic(raw, UID, now)
    original.update(decision='excluded', reason='promotion', reason_text='宣传展示或社区内容', rule_version=5,
                    last_observation_error='本次正文获取不完整，保留上次完整记录')
    store = BilibiliStore(path)
    store.save_rows('wuthering_waves', UID, [original])
    store.set_state('wuthering_waves', UID, history_complete=True, last_success=now.isoformat(), rule_version=5)
    store.close()

    class Client:
        def __init__(self, *args): pass
        async def page(self, offset):
            return {'items': [raw], 'has_more': False}

    service = BilibiliService(Settings(db_path=str(path)), {'wuthering_waves': UID}, Client)
    try:
        await service.run('wuthering_waves')
        rows = service.store.rows('wuthering_waves', UID, 'accepted')
        assert len(rows) == 1
        assert rows[0]['rule_version'] == 6
        assert rows[0]['body'] == original['body']
        state = service.store.state('wuthering_waves', UID)
        assert state['history_complete'] is True and state['rule_version'] == 6
        assert not service.store.rows('nte', UID)
    finally:
        await service.close()
