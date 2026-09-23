from datetime import datetime, timezone

from game_assistant.sources.bilibili_store import BilibiliStore
from game_assistant.sources.bilibili import classify_dynamic
from tests.test_bilibili_source import post, UID, NOW

def published_now(text):
    # rows() keeps the last 60 days by the real clock, so a fixed publish time
    # would age out of the window.
    now = datetime.now(timezone.utc)
    return classify_dynamic(post(text, published=now.timestamp()), UID, now)

def test_idempotent_ingestion_retains_filter_audit_and_source_isolation(tmp_path):
    store = BilibiliStore(tmp_path/'news.db')
    good = published_now('9月15日版本更新公告')
    store.save_rows('nte', UID, [good, good])
    assert len(store.rows('nte', UID)) == 1
    assert len(store.rows('nte', UID, 'accepted')) == 1
    rejected = published_now('9月15日版本PV发布')
    store.save_rows('nte', UID, [rejected])
    assert store.rows('nte', UID, 'accepted') == []
    assert store.rows('nte', UID)[0]['reason'] == 'promotion'
    assert store.rows('lol', UID) == []

def test_failed_run_keeps_previous_success_and_history_coverage(tmp_path):
    store = BilibiliStore(tmp_path/'news.db')
    store.set_state('nte', UID, status='ok', last_success=NOW.isoformat(), history_complete=True)
    store.set_state('nte', UID, status='error', message='访问受限')
    state = store.state('nte', UID)
    assert state['last_success'] == NOW.isoformat() and state['history_complete']

def test_incomplete_article_does_not_replace_last_complete_accepted_record(tmp_path):
    store = BilibiliStore(tmp_path/'news.db')
    good = published_now('9月15日版本更新公告\n完整活动安排')
    store.save_rows('nte', UID, [good])
    partial = {**good, 'body':'截断摘要...', 'decision':'excluded', 'reason':'incomplete'}
    store.save_rows('nte', UID, [partial])
    row = store.rows('nte', UID, 'accepted')[0]
    assert row['body'] == good['body'] and row['last_observation_error']
